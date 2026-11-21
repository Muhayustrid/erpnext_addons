"""% Paid on Purchase Order / Purchase Receipt (no site needed)."""

import unittest
from types import SimpleNamespace
from unittest import mock

from erpnext_addons.tests.fakes import ensure_frappe_importable

ensure_frappe_importable()

from erpnext_addons.buying import paid


class TestRatio(unittest.TestCase):
	def test_ratio_full_partial_none(self):
		self.assertEqual(paid.invoice_ratio(100, 0), 1)
		self.assertEqual(paid.invoice_ratio(100, 40), 0.6)
		self.assertEqual(paid.invoice_ratio(100, 100), 0)

	def test_ratio_zero_total_and_overpaid(self):
		self.assertEqual(paid.invoice_ratio(0, 0), 0)
		self.assertEqual(paid.invoice_ratio(100, -20), 1)


class TestPercent(unittest.TestCase):
	def test_percent_proportional(self):
		self.assertEqual(paid.percent([(60, 1), (40, 0.5)], 100), 80)

	def test_percent_zero_total(self):
		self.assertEqual(paid.percent([(60, 1)], 0), 0)

	def test_percent_capped(self):
		self.assertEqual(paid.percent([(150, 1)], 100), 100)


class TestReceiptPercent(unittest.TestCase):
	def test_billed_amount_weighted_by_billing_invoices(self):
		# item 1: 60 billed by a fully paid PI; item 2: 40 billed by PIs 1/4 paid and unpaid
		items = [(60, [(60, 1)]), (40, [(30, 0.5), (30, 0)])]
		self.assertEqual(paid.receipt_percent(items, 100), 70)

	def test_unbilled_items_and_zero_totals(self):
		self.assertEqual(paid.receipt_percent([(0, []), (50, [])], 100), 0)
		self.assertEqual(paid.receipt_percent([(50, [(0, 1)])], 100), 0)
		self.assertEqual(paid.receipt_percent([(50, [(50, 1)])], 0), 0)


class TestRefresh(unittest.TestCase):
	def test_refresh_writes_only_changes(self):
		rows = [
			{"name": "PO-1", "total": 100, "amount": 50, "inv_total": 50, "outstanding": 0},
			{"name": "PO-2", "total": 80, "amount": 80, "inv_total": 80, "outstanding": 0},
		]
		current = {"PO-1": 0, "PO-2": 100}
		writes = []
		db = SimpleNamespace(
			sql=mock.Mock(return_value=rows),
			get_value=lambda doctype, name, field: current.get(name),
			set_value=lambda *args, **kwargs: writes.append((args, kwargs)),
		)
		with mock.patch.object(paid, "frappe", SimpleNamespace(db=db)):
			paid.refresh("Purchase Order", ["PO-1", "PO-2"])

		self.assertEqual(
			writes,
			[(("Purchase Order", "PO-1", paid.FIELD, 50.0), {"update_modified": False})],
		)
		sql = db.sql.call_args.args[0]
		self.assertIn("docstatus = 1", sql)
		self.assertIn("is_return = 0", sql)
		self.assertIn("pii.purchase_order", sql)

	def test_refresh_target_without_invoices_resets_to_zero(self):
		writes = []
		db = SimpleNamespace(
			sql=mock.Mock(return_value=[{"name": "PO-1", "total": 100, "amount": None, "inv_total": None, "outstanding": None}]),
			get_value=lambda *a: 40,
			set_value=lambda *args, **kwargs: writes.append(args),
		)
		with mock.patch.object(paid, "frappe", SimpleNamespace(db=db)):
			paid.refresh("Purchase Order", ["PO-1"])

		self.assertEqual(writes, [("Purchase Order", "PO-1", paid.FIELD, 0)])

	def test_refresh_receipt_uses_billed_amount_via_pr_or_po_item(self):
		rows = [
			# PR item billed directly (pr_detail) by a paid PI
			{"name": "PR-1", "total": 100, "item": "i1", "billed_amt": 60, "amount": 60, "inv_total": 60, "outstanding": 0},
			# PR item billed through its PO item by an unpaid PI
			{"name": "PR-1", "total": 100, "item": "i2", "billed_amt": 40, "amount": 40, "inv_total": 40, "outstanding": 40},
			# PR without any billing invoice
			{"name": "PR-2", "total": 50, "item": "i3", "billed_amt": 0, "amount": None, "inv_total": None, "outstanding": None},
		]
		writes = []
		db = SimpleNamespace(
			sql=mock.Mock(return_value=rows),
			get_value=lambda *a: 99,
			set_value=lambda *args, **kwargs: writes.append(args),
		)
		with mock.patch.object(paid, "frappe", SimpleNamespace(db=db)):
			paid.refresh("Purchase Receipt", ["PR-1", "PR-2"])

		self.assertEqual(
			writes,
			[("Purchase Receipt", "PR-1", paid.FIELD, 60.0), ("Purchase Receipt", "PR-2", paid.FIELD, 0)],
		)
		sql = db.sql.call_args.args[0]
		self.assertIn("pii.pr_detail = pri.name", sql)
		self.assertIn("pii.po_detail = pri.purchase_order_item", sql)

	def test_receipt_po_line_branch_skips_blank_links_and_update_stock(self):
		db = SimpleNamespace(sql=mock.Mock(return_value=[]), get_value=None, set_value=None)
		with mock.patch.object(paid, "frappe", SimpleNamespace(db=db)):
			paid.refresh("Purchase Receipt", ["PR-1"])
		sql = db.sql.call_args.args[0]
		# '' = '' would join unrelated PR and PI lines
		self.assertIn("ifnull(pri.purchase_order_item, '') != ''", sql)
		# ERPNext excludes update-stock invoices when splitting PO-line billing over receipts
		self.assertIn("pi.update_stock = 0", sql)

	def test_foreign_currency_payable_uses_base_totals(self):
		for doctype in paid.TARGETS:
			db = SimpleNamespace(sql=mock.Mock(return_value=[]), get_value=None, set_value=None)
			with mock.patch.object(paid, "frappe", SimpleNamespace(db=db)):
				paid.refresh(doctype, ["X-1"])
			sql = db.sql.call_args.args[0]
			self.assertIn("pi.party_account_currency != pi.currency", sql)
			self.assertIn("pi.base_rounded_total", sql)
			self.assertIn("pi.base_grand_total", sql)


class _Callbacks(list):
	def add(self, fn):
		self.append(fn)


class _Doc(dict):
	__getattr__ = dict.get

	def set(self, key, value):
		self[key] = value

	def is_new(self):
		return not self.get("name")


class TestFieldDefs(unittest.TestCase):
	def test_field_defs(self):
		defs = paid.field_defs()
		for doctype in ("Purchase Order", "Purchase Receipt"):
			(field,) = defs[doctype]
			self.assertEqual(
				field,
				{
					"fieldname": "custom_per_paid",
					"fieldtype": "Percent",
					"label": "% Paid",
					"read_only": 1,
					"no_copy": 1,
					"allow_on_submit": 1,
					"in_list_view": 1,
					"insert_after": "per_billed",
				},
			)
		(tab,) = defs["Payment Entry"]
		self.assertEqual(tab["fieldname"], "custom_connections_tab")
		self.assertEqual(tab["fieldtype"], "Tab Break")
		self.assertEqual(tab["label"], "Connections")
		self.assertEqual(tab["show_dashboard"], 1)
		self.assertEqual(tab["insert_after"], "auto_repeat")


class EventsCase(unittest.TestCase):
	def setUp(self):
		self.enqueued = []
		self.items = {}
		self.receipts = {}

		def get_all(table, filters=None, fields=None, pluck=None, distinct=False):
			if table == "Purchase Receipt Item":
				# filters={"purchase_order_item": ["in", [...]], "docstatus": 1}
				return [pr for poi in filters["purchase_order_item"][1] for pr in self.receipts.get(poi, [])]
			# Purchase Invoice Item rows for filters={"parent": ["in", [...]]}
			return [_Doc(row) for parent in filters["parent"][1] for row in self.items.get(parent, [])]

		self.f = SimpleNamespace(
			flags={},
			db=SimpleNamespace(after_commit=_Callbacks(), after_rollback=_Callbacks()),
			enqueue=lambda method, **kw: self.enqueued.append((method, kw)),
			get_all=get_all,
		)
		p = mock.patch.object(paid, "frappe", self.f)
		p.start()
		self.addCleanup(p.stop)

	def flush(self):
		for callback in self.f.db.after_commit:
			callback()


class TestEvents(EventsCase):
	def test_invoice_change_collects_targets(self):
		doc = _Doc(
			doctype="Purchase Invoice",
			items=[
				{"purchase_order": "PO-1", "purchase_receipt": "PR-1"},
				{"purchase_order": "PO-1", "purchase_receipt": None},
			],
		)
		paid.on_invoice_change(doc)
		paid.on_invoice_change(doc)
		self.flush()

		self.assertEqual(len(self.enqueued), 1)
		method, kwargs = self.enqueued[0]
		self.assertEqual(method, "erpnext_addons.buying.paid.process")
		self.assertEqual(kwargs["queue"], "short")
		self.assertEqual(kwargs["docs"], [["Purchase Order", "PO-1"], ["Purchase Receipt", "PR-1"]])

	def test_invoice_billed_through_po_also_queues_its_receipts(self):
		self.receipts = {"poi-1": ["PR-9"]}
		doc = _Doc(
			doctype="Purchase Invoice",
			items=[{"purchase_order": "PO-1", "po_detail": "poi-1", "purchase_receipt": None}],
		)
		paid.on_invoice_change(doc)
		self.flush()

		self.assertEqual(self.enqueued[0][1]["docs"], [["Purchase Order", "PO-1"], ["Purchase Receipt", "PR-9"]])

	def test_payment_change_follows_purchase_invoice_refs(self):
		self.items = {"PI-1": [{"purchase_order": "PO-1", "purchase_receipt": None}]}
		doc = _Doc(
			doctype="Payment Entry",
			references=[
				{"reference_doctype": "Purchase Invoice", "reference_name": "PI-1"},
				{"reference_doctype": "Sales Invoice", "reference_name": "SI-1"},
			],
		)
		paid.on_payment_change(doc)
		self.flush()

		self.assertEqual(self.enqueued[0][1]["docs"], [["Purchase Order", "PO-1"]])

	def test_journal_entry_follows_purchase_invoice_refs(self):
		self.items = {"PI-1": [{"purchase_order": None, "purchase_receipt": "PR-1"}]}
		doc = _Doc(
			doctype="Journal Entry",
			accounts=[
				{"reference_type": "Purchase Invoice", "reference_name": "PI-1"},
				{"reference_type": "", "reference_name": ""},
			],
		)
		paid.on_payment_change(doc)
		self.flush()

		self.assertEqual(self.enqueued[0][1]["docs"], [["Purchase Receipt", "PR-1"]])

	def test_payment_without_purchase_invoice_enqueues_nothing(self):
		paid.on_payment_change(_Doc(doctype="Payment Entry", references=[]))
		self.flush()
		self.assertEqual(self.enqueued, [])


class TestGuardAndJobs(unittest.TestCase):
	def test_guard_restores_saved_value(self):
		meta = SimpleNamespace(has_field=lambda fieldname: True)
		db = SimpleNamespace(get_value=lambda doctype, name, field: 40)
		with mock.patch.object(paid, "frappe", SimpleNamespace(db=db)):
			new = _Doc(doctype="Purchase Order", meta=meta, custom_per_paid=99)
			paid.guard(new)
			existing = _Doc(doctype="Purchase Order", name="PO-1", meta=meta, custom_per_paid=99)
			paid.guard(existing)

		self.assertEqual(new["custom_per_paid"], 0)
		self.assertEqual(existing["custom_per_paid"], 40)

	def test_guard_skips_before_field_exists(self):
		doc = _Doc(doctype="Purchase Order", name="PO-1", meta=SimpleNamespace(has_field=lambda f: False))
		paid.guard(doc)
		self.assertNotIn("custom_per_paid", doc)

	def test_process_refreshes_grouped_and_commits(self):
		commits = []
		with (
			mock.patch.object(paid, "frappe", SimpleNamespace(db=SimpleNamespace(commit=lambda: commits.append(1)))),
			mock.patch.object(paid, "refresh") as refresh,
		):
			paid.process([["Purchase Order", "PO-1"], ["Purchase Receipt", "PR-1"], ["Purchase Order", "PO-2"]])

		refresh.assert_any_call("Purchase Order", ["PO-1", "PO-2"])
		refresh.assert_any_call("Purchase Receipt", ["PR-1"])
		self.assertEqual(commits, [1])

	def test_daily_refreshes_every_billed_target(self):
		calls = []
		f = SimpleNamespace(
			get_all=lambda doctype, filters, pluck: calls.append((doctype, filters)) or [f"{doctype}-1"],
			db=SimpleNamespace(commit=lambda: None),
		)
		with mock.patch.object(paid, "frappe", f), mock.patch.object(paid, "refresh") as refresh:
			paid.daily()

		for doctype in paid.TARGETS:
			# no "< 100" filter: unreconciled payments can push a 100% target back down
			self.assertIn((doctype, {"docstatus": 1, "per_billed": [">", 0]}), calls)
			refresh.assert_any_call(doctype, [f"{doctype}-1"])


class TestListColumn(unittest.TestCase):
	def test_column_added_once_after_per_billed(self):
		import json

		from erpnext_addons.patches.v1_0 import backfill_per_paid as patch

		po = [{"fieldname": "status_field"}, {"fieldname": "per_billed"}, {"fieldname": "per_received"}]
		pr_done = [{"fieldname": "per_billed"}, {"fieldname": "custom_per_paid"}]
		rows = {"Purchase Order": json.dumps(po), "Purchase Receipt": json.dumps(pr_done)}
		writes, cleared = [], []

		def set_value(doctype, name, field, value):
			rows[name] = value
			writes.append(name)

		f = SimpleNamespace(
			db=SimpleNamespace(get_value=lambda dt, name, field: rows.get(name), set_value=set_value),
			clear_document_cache=lambda dt, name: cleared.append(name),
		)
		with mock.patch.object(patch, "frappe", f):
			patch.add_list_column()

		self.assertEqual(writes, ["Purchase Order"])
		self.assertEqual(cleared, ["Purchase Order"])
		self.assertEqual(
			[c["fieldname"] for c in json.loads(rows["Purchase Order"])],
			["status_field", "per_billed", "custom_per_paid", "per_received"],
		)

	def test_execute_adds_list_column(self):
		from erpnext_addons.patches.v1_0 import backfill_per_paid as patch

		with (
			mock.patch.object(patch, "frappe", SimpleNamespace(get_all=lambda *a, **k: [])),
			mock.patch.object(patch, "ensure_fields"),
			mock.patch.object(patch, "refresh"),
			mock.patch.object(patch, "add_list_column") as add,
		):
			patch.execute()
		add.assert_called_once()


if __name__ == "__main__":
	unittest.main()
