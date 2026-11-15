"""Event hooks and field definitions for intercompany progress (no site needed)."""

import unittest
from itertools import pairwise
from types import SimpleNamespace
from unittest import mock

from erpnext_addons.tests.fakes import ensure_frappe_importable

ensure_frappe_importable()

from erpnext_addons.intercompany import events, setup
from erpnext_addons.intercompany.progress import FIELDS


class _Callbacks(list):
	def add(self, fn):
		self.append(fn)


class _Doc(dict):
	__getattr__ = dict.get

	def set(self, key, value):
		self[key] = value

	def is_new(self):
		return not self.get("name")


class _Meta:
	def __init__(self, installed):
		self.installed = installed

	def has_field(self, fieldname):
		return self.installed and fieldname in FIELDS


def po(installed=True, **values):
	return _Doc(
		{
			"doctype": "Purchase Order",
			"name": "PO1",
			"docstatus": 1,
			"is_internal_supplier": 1,
			"meta": _Meta(installed),
			**values,
		}
	)


class _Deadlock(Exception):
	pass


class EventsCase(unittest.TestCase):
	def setUp(self):
		self.db_values = {}
		self.enqueued, self.commits, self.rollbacks = [], [], []
		self.f = SimpleNamespace(
			flags={},
			QueryDeadlockError=_Deadlock,
			db=SimpleNamespace(
				after_commit=_Callbacks(),
				after_rollback=_Callbacks(),
				get_value=lambda dt, name, fields, as_dict=False: dict(self.db_values),
				commit=lambda: self.commits.append(1),
				rollback=lambda: self.rollbacks.append(1),
			),
			enqueue=lambda method, **kw: self.enqueued.append((method, kw)),
		)
		for target in (
			mock.patch.object(events, "frappe", self.f),
			mock.patch.object(events, "filelock", mock.MagicMock()),
		):
			target.start()
			self.addCleanup(target.stop)


class TestOnChange(EventsCase):
	def test_draft_and_non_intercompany_are_ignored(self):
		events.on_change(po(docstatus=0))
		events.on_change(po(is_internal_supplier=0))
		events.on_change(po(installed=False))
		self.assertNotIn(events.QUEUE, self.f.flags)
		self.assertEqual(self.f.db.after_commit, [])

	def test_enqueues_one_job_after_commit_not_inside_the_transaction(self):
		events.on_change(po())
		events.on_change(po())
		events.on_change(po(name="PO2", docstatus=2))
		self.assertEqual(self.enqueued, [], "nothing runs before commit")
		self.assertEqual(len(self.f.db.after_commit), 1)
		self.f.db.after_commit[0]()
		self.assertEqual(
			self.enqueued,
			[(events.JOB, {"queue": "short", "docs": [["Purchase Order", "PO1"], ["Purchase Order", "PO2"]]})],
		)
		self.assertNotIn(events.QUEUE, self.f.flags)

	def test_rollback_drops_the_queue(self):
		events.on_change(po())
		self.f.db.after_rollback[0]()
		self.assertNotIn(events.QUEUE, self.f.flags)

	def test_before_cancel_queues_neighbours_while_links_exist(self):
		with mock.patch.object(events, "neighbours", return_value={("Sales Invoice", "SI1")}):
			events.before_cancel(po(doctype="Purchase Invoice", name="PI1"))
		self.assertEqual(self.f.flags[events.QUEUE], [["Sales Invoice", "SI1"]])


class TestProcess(EventsCase):
	def test_refreshes_with_one_done_set_and_commits(self):
		calls = []
		with mock.patch.object(events, "refresh_chain", lambda dt, n, done: calls.append((dt, n, id(done)))):
			events.process([["Purchase Order", "PO1"], ["Sales Order", "SO1"]])
		self.assertEqual([c[:2] for c in calls], [("Purchase Order", "PO1"), ("Sales Order", "SO1")])
		self.assertEqual(calls[0][2], calls[1][2])
		self.assertEqual(self.commits, [1])

	def test_deadlock_retries_then_raises(self):
		with mock.patch.object(events, "refresh_chain", side_effect=_Deadlock()), self.assertRaises(_Deadlock):
			events.process([["Purchase Order", "PO1"]])
		self.assertEqual(len(self.rollbacks), events.ATTEMPTS)
		self.assertEqual(self.commits, [])

	def test_deadlock_once_then_succeeds(self):
		effects = iter([_Deadlock(), None])

		def refresh(*a, **k):
			e = next(effects)
			if e:
				raise e

		with mock.patch.object(events, "refresh_chain", refresh):
			events.process([["Purchase Order", "PO1"]])
		self.assertEqual((len(self.rollbacks), len(self.commits)), (1, 1))


class TestGuard(EventsCase):
	def test_existing_doc_reverts_to_saved_values(self):
		self.db_values = {f: 0 for f in FIELDS} | {"custom_ic_ordered": 1, "custom_ic_next_step": "To Receive (0%)"}
		doc = po(custom_ic_delivered=1, custom_ic_next_step="Completed")
		events.guard(doc)
		self.assertEqual({f: doc[f] for f in FIELDS}, self.db_values)

	def test_new_doc_gets_defaults(self):
		doc = po(name=None, custom_ic_ordered=1, custom_ic_next_step="Completed")
		events.guard(doc)
		self.assertEqual({f: doc[f] for f in FIELDS}, {f: 0 for f in FIELDS[:-1]} | {"custom_ic_next_step": ""})


class TestGuardBeforeMigrate(EventsCase):
	def test_fields_not_created_yet_leaves_doc_untouched(self):
		self.f.db.get_value = lambda *a, **k: self.fail("must not query missing columns")
		doc = po(installed=False, custom_ic_ordered=1)
		events.guard(doc)
		self.assertEqual(doc["custom_ic_ordered"], 1)


class TestFieldDefs(unittest.TestCase):
	def test_seven_system_owned_fields_per_doctype(self):
		for doctype, after in setup.INSERT_AFTER.items():
			defs = setup.field_defs(doctype)
			self.assertEqual([d["fieldname"] for d in defs], [setup.SECTION, "custom_ic_next_step", *FIELDS[:-1]])
			section, next_step, *checks = defs
			self.assertEqual(section["insert_after"], after)
			self.assertEqual(section["collapsible"], 1)
			self.assertTrue(section["depends_on"].startswith("eval:doc.is_internal_"))
			self.assertEqual((next_step["in_list_view"], next_step["in_standard_filter"]), (1, 1))
			self.assertEqual([c["label"] for c in checks], ["Ordered", "Delivered", "Received", "Sales Invoiced", "Purchase Invoiced"])
			for d in defs[1:]:
				self.assertEqual((d["read_only"], d["no_copy"], d["allow_on_submit"]), (1, 1, 1), d["fieldname"])
			for prev, d in pairwise(defs):
				self.assertEqual(d["insert_after"], prev["fieldname"])


if __name__ == "__main__":
	unittest.main()
