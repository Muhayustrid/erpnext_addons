"""Chain discovery and write against an in-memory table store (no site needed)."""

import unittest
from types import SimpleNamespace
from unittest import mock

from erpnext_addons.tests.fakes import ensure_frappe_importable

ensure_frappe_importable()

from erpnext_addons.intercompany import chain


class _Row(dict):
	__getattr__ = dict.get


class StoreFrappe:
	"""Rows per table; filters are equality only, as used by chain.py."""

	def __init__(self):
		self.tables = {}
		self.writes = []
		self.errors = []
		self.db = SimpleNamespace(get_value=self._get_value, set_value=self._set_value)

	def add(self, table, **row):
		self.tables.setdefault(table, []).append(_Row(row))

	def doc(self, doctype, name, internal=1, docstatus=1, status="To Bill", is_return=0, items=(), **header):
		self.add(
			doctype,
			name=name,
			docstatus=docstatus,
			status=status,
			is_return=is_return,
			**chain.EMPTY,  # column defaults, as in the database
			**{chain.INTERNAL_FLAG[doctype]: internal},
			**header,
		)
		table, qty_field, _ = chain.QTY_SOURCE[doctype]
		for item in items:
			item = dict(item)
			self.add(
				table, parent=name, docstatus=docstatus, item_code=item.pop("item"), **{qty_field: item.pop("qty")}, **item
			)

	def _match(self, table, filters):
		return [r for r in self.tables.get(table, []) if all(r.get(k) == v for k, v in filters.items())]

	def get_all(self, table, filters=None, pluck=None, fields=None, distinct=False):
		rows = self._match(table, filters or {})
		if pluck:
			values = [r.get(pluck) for r in rows]
			return list(dict.fromkeys(values)) if distinct else values
		return [_Row({f: r.get(f) for f in fields}) for r in rows]

	def _get_value(self, doctype, name, fields, as_dict=False):
		rows = self._match(doctype, {"name": name})
		if not rows:
			return None
		if isinstance(fields, str):
			return rows[0].get(fields)
		return _Row({f: rows[0].get(f) for f in fields})

	def _set_value(self, doctype, name, values, update_modified=True):
		assert update_modified is False
		self.writes.append((doctype, name, dict(values)))
		self._match(doctype, {"name": name})[0].update(values)

	def log_error(self, title=None, message=None):
		self.errors.append(title)


class ChainCase(unittest.TestCase):
	def setUp(self):
		self.f = StoreFrappe()
		patcher = mock.patch.object(chain, "frappe", self.f)
		patcher.start()
		self.addCleanup(patcher.stop)

	def value(self, doctype, name, field="custom_ic_next_step"):
		return self.f._get_value(doctype, name, field)


class TestChain(ChainCase):
	def test_po_split_into_two_sales_orders_shares_one_state(self):
		f = self.f
		f.doc("Purchase Order", "PO1", items=[{"item": "A", "qty": 10}])
		f.doc("Sales Order", "SO1", items=[{"item": "A", "qty": 6, "purchase_order": "PO1"}])
		f.doc("Sales Order", "SO2", items=[{"item": "A", "qty": 4, "purchase_order": "PO1"}])
		f.doc("Delivery Note", "DN1", items=[{"item": "A", "qty": 6, "against_sales_order": "SO1"}])

		chain.refresh_chain("Delivery Note", "DN1")

		for dt, dn in [("Purchase Order", "PO1"), ("Sales Order", "SO1"), ("Sales Order", "SO2"), ("Delivery Note", "DN1")]:
			self.assertEqual(self.value(dt, dn), "To Deliver (60%)", dn)
			self.assertEqual(self.value(dt, dn, "custom_ic_ordered"), 1, dn)
			self.assertEqual(self.value(dt, dn, "custom_ic_delivered"), 0, dn)

	def test_receipt_linked_only_by_header_reference(self):
		f = self.f
		f.doc("Delivery Note", "DN1", items=[{"item": "A", "qty": 5}])
		f.doc("Purchase Receipt", "PR1", inter_company_reference="DN1", items=[{"item": "A", "qty": 5}])

		members = chain.find_chain("Delivery Note", "DN1")

		self.assertEqual(set(members), {("Delivery Note", "DN1"), ("Purchase Receipt", "PR1")})

	def test_sales_return_joins_by_return_against_and_asks_for_purchase_return(self):
		f = self.f
		f.doc("Purchase Order", "PO1", items=[{"item": "A", "qty": 10}])
		f.doc("Sales Order", "SO1", items=[{"item": "A", "qty": 10, "purchase_order": "PO1"}])
		f.doc("Delivery Note", "DN1", items=[{"item": "A", "qty": 10, "against_sales_order": "SO1"}])
		f.doc("Purchase Receipt", "PR1", inter_company_reference="DN1", items=[{"item": "A", "qty": 10}])
		f.doc("Delivery Note", "DN2", is_return=1, return_against="DN1", items=[{"item": "A", "qty": -2}])

		chain.refresh_chain("Delivery Note", "DN2")

		self.assertEqual(self.value("Purchase Order", "PO1"), "To Create Purchase Return")
		self.assertEqual(self.value("Delivery Note", "DN2", "custom_ic_received"), 0)

	def test_non_intercompany_and_draft_neighbours_are_excluded(self):
		f = self.f
		f.doc("Purchase Order", "PO1", items=[{"item": "A", "qty": 10}])
		f.doc("Sales Order", "SO1", items=[{"item": "A", "qty": 10, "purchase_order": "PO1"}])
		f.doc("Purchase Receipt", "PRX", internal=0, items=[{"item": "A", "qty": 10, "purchase_order": "PO1"}])
		f.doc("Delivery Note", "DND", docstatus=0, items=[{"item": "A", "qty": 10, "against_sales_order": "SO1"}])

		members = chain.find_chain("Purchase Order", "PO1")

		self.assertEqual(set(members), {("Purchase Order", "PO1"), ("Sales Order", "SO1")})

	def test_unchanged_values_are_not_rewritten(self):
		f = self.f
		f.doc("Purchase Order", "PO1", items=[{"item": "A", "qty": 10}])
		chain.refresh_chain("Purchase Order", "PO1")
		chain.refresh_chain("Purchase Order", "PO1")
		self.assertEqual(f.writes, [("Purchase Order", "PO1", {"custom_ic_next_step": "To Create Sales Order"})])

	def test_cancelled_so_marks_itself_and_recomputes_po(self):
		f = self.f
		f.doc("Purchase Order", "PO1", items=[{"item": "A", "qty": 10}])
		f.doc("Sales Order", "SO1", docstatus=2, items=[{"item": "A", "qty": 10, "purchase_order": "PO1"}])

		chain.refresh_chain("Sales Order", "SO1")

		self.assertEqual(self.value("Sales Order", "SO1"), "Cancelled")
		self.assertEqual(self.value("Sales Order", "SO1", "custom_ic_ordered"), 0)
		self.assertEqual(self.value("Purchase Order", "PO1"), "To Create Sales Order")

	def test_closed_sales_order_closes_the_chain(self):
		f = self.f
		f.doc("Purchase Order", "PO1", items=[{"item": "A", "qty": 10}])
		f.doc("Sales Order", "SO1", status="Closed", items=[{"item": "A", "qty": 10, "purchase_order": "PO1"}])
		chain.refresh_chain("Purchase Order", "PO1")
		self.assertEqual(self.value("Purchase Order", "PO1"), "Closed")

	def test_closed_branch_does_not_hide_open_branch(self):
		f = self.f
		f.doc("Purchase Order", "PO1", items=[{"item": "A", "qty": 10}])
		f.doc(
			"Sales Order",
			"SO1",
			status="Closed",
			items=[{"item": "A", "qty": 6, "purchase_order": "PO1", "delivered_qty": 1, "conversion_factor": 6}],
		)
		f.doc("Sales Order", "SO2", items=[{"item": "A", "qty": 4, "purchase_order": "PO1"}])
		f.doc("Delivery Note", "DN1", items=[{"item": "A", "qty": 6, "against_sales_order": "SO1"}])

		chain.refresh_chain("Delivery Note", "DN1")

		self.assertEqual(self.value("Sales Order", "SO2"), "To Deliver (60%)")
		self.assertEqual(self.value("Sales Order", "SO2", "custom_ic_delivered"), 0)

	def test_invoice_amount_mismatch_blocks_purchase_invoiced(self):
		f = self.f
		f.doc("Sales Invoice", "SI1", items=[{"item": "A", "qty": 10, "net_amount": 100000}])
		f.doc(
			"Purchase Invoice",
			"PI1",
			inter_company_invoice_reference="SI1",
			items=[{"item": "A", "qty": 10, "net_amount": 90000}],
		)
		chain.refresh_chain("Purchase Invoice", "PI1")
		self.assertEqual(self.value("Sales Invoice", "SI1", "custom_ic_purchase_invoiced"), 0)

	def test_chain_cap_logs_and_writes_nothing(self):
		f = self.f
		f.doc("Purchase Order", "PO1", items=[{"item": "A", "qty": 1}])
		for i in range(chain.MAX_MEMBERS + 1):
			f.doc("Sales Order", f"SO{i}", items=[{"item": "A", "qty": 1, "purchase_order": "PO1"}])

		chain.refresh_chain("Purchase Order", "PO1")

		self.assertEqual(f.writes, [])
		self.assertEqual(f.errors, ["Intercompany progress: chain too large"])

	def test_oversized_chain_is_walked_once_per_batch(self):
		f = self.f
		f.doc("Purchase Order", "PO1", items=[{"item": "A", "qty": 1}])
		for i in range(chain.MAX_MEMBERS + 1):
			f.doc("Sales Order", f"SO{i}", items=[{"item": "A", "qty": 1, "purchase_order": "PO1"}])
		done = set()
		chain.refresh_chain("Purchase Order", "PO1", done=done)
		chain.refresh_chain("Sales Order", "SO7", done=done)
		self.assertEqual(f.errors, ["Intercompany progress: chain too large"])

	def test_done_set_skips_already_written_chains(self):
		f = self.f
		f.doc("Purchase Order", "PO1", items=[{"item": "A", "qty": 10}])
		f.doc("Sales Order", "SO1", items=[{"item": "A", "qty": 10, "purchase_order": "PO1"}])
		done = set()
		chain.refresh_chain("Purchase Order", "PO1", done=done)
		writes = len(f.writes)
		chain.refresh_chain("Sales Order", "SO1", done=done)
		self.assertEqual(len(f.writes), writes)


if __name__ == "__main__":
	unittest.main()
