"""Backfill visits every submitted intercompany entry point and preserves admin list settings."""

import json
import unittest
from types import SimpleNamespace
from unittest import mock

from erpnext_addons.tests.fakes import ensure_frappe_importable

ensure_frappe_importable()

from erpnext_addons.patches.v1_0 import backfill_intercompany_progress as patch


class TestBackfill(unittest.TestCase):
	def test_visits_all_six_types_not_just_orders(self):
		calls = []
		get_all = mock.Mock(side_effect=lambda dt, **kw: [f"{dt}-1"])
		with (
			mock.patch.object(patch, "frappe", SimpleNamespace(get_all=get_all)),
			mock.patch.object(patch, "ensure_fields") as ensure,
			mock.patch.object(patch, "refresh_chain", side_effect=lambda dt, name, done: calls.append((dt, name, id(done)))),
			mock.patch.object(patch, "add_list_column") as add,
		):
			patch.execute()
		ensure.assert_called_once()
		add.assert_called_once()
		self.assertEqual([c[0] for c in calls], list(patch.DOCTYPES))
		self.assertEqual(len({c[2] for c in calls}), 1)
		for call in get_all.call_args_list:
			dt = call.args[0]
			self.assertEqual(call.kwargs["filters"], {"docstatus": 1, patch.INTERNAL_FLAG[dt]: 1})

	def test_list_column_added_once_after_status_without_reordering_other_fields(self):
		fields = [{"fieldname": "supplier_name"}, {"fieldname": "status_field"}, {"fieldname": "company"}]
		rows = {"Purchase Order": json.dumps(fields), "Sales Order": ""}
		writes, cleared = [], []

		def set_value(dt, name, field, value):
			self.assertEqual((dt, field), ("List View Settings", "fields"))
			rows[name] = value
			writes.append(name)

		f = SimpleNamespace(
			db=SimpleNamespace(get_value=lambda dt, name, field: rows.get(name), set_value=set_value),
			clear_document_cache=lambda dt, name: cleared.append(name),
		)
		with mock.patch.object(patch, "frappe", f):
			patch.add_list_column()
			patch.add_list_column()
		self.assertEqual(writes, ["Purchase Order"])
		self.assertEqual(cleared, ["Purchase Order"])
		self.assertEqual(json.loads(rows["Purchase Order"]), [*fields[:2], patch.COLUMN, fields[2]])


if __name__ == "__main__":
	unittest.main()
