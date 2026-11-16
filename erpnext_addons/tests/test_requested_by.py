"""Requested By: filled from the creator's full name on insert, backfilled once."""

import unittest
from unittest import mock

from erpnext_addons.tests.fakes import FakeFrappe, ensure_frappe_importable, new_doc

ensure_frappe_importable()

from erpnext_addons.overrides import material_request
from erpnext_addons.patches.v1_0 import backfill_requested_by


class SetRequestedByCase(unittest.TestCase):
	def setUp(self):
		self.f = FakeFrappe()
		p = mock.patch.object(material_request, "frappe", self.f)
		p.start()
		self.addCleanup(p.stop)
		self.f.add("User", "u1", full_name="Sofyan Budi Luhur")

	def test_fills_from_owner_full_name(self):
		doc = new_doc(owner="u1", custom_requested_by=None)
		material_request.set_requested_by(doc)
		self.assertEqual(doc.custom_requested_by, "Sofyan Budi Luhur")

	def test_keeps_existing_value(self):
		doc = new_doc(owner="u1", custom_requested_by="Diisi Manual")
		with mock.patch.object(self.f.db, "get_value", side_effect=AssertionError("no db read")):
			material_request.set_requested_by(doc)
		self.assertEqual(doc.custom_requested_by, "Diisi Manual")

	def test_falls_back_to_user_id_when_user_missing(self):
		doc = new_doc(owner="ghost@example.com")
		material_request.set_requested_by(doc)
		self.assertEqual(doc.custom_requested_by, "ghost@example.com")

	def test_falls_back_to_session_user_when_owner_missing(self):
		self.f.session = new_doc(user="u1")
		doc = new_doc(owner=None)
		material_request.set_requested_by(doc)
		self.assertEqual(doc.custom_requested_by, "Sofyan Budi Luhur")


class BackfillCase(unittest.TestCase):
	def test_execute_creates_field_and_updates_empty_rows(self):
		frappe_mock = mock.MagicMock()
		frappe_mock.db.commit.side_effect = AssertionError("patches must not commit")
		with (
			mock.patch.object(backfill_requested_by, "ensure_fields") as ensure,
			mock.patch.object(backfill_requested_by, "frappe", frappe_mock),
		):
			backfill_requested_by.execute()
		ensure.assert_called_once()
		frappe_mock.db.sql.assert_called_once()
		sql = frappe_mock.db.sql.call_args.args[0]
		self.assertIn("LEFT JOIN `tabUser` u ON u.name = mr.owner", sql)
		# owner id is the fallback when the user row is gone, matching set_requested_by
		self.assertIn("COALESCE(u.full_name, mr.owner)", sql)
		self.assertIn("custom_requested_by", sql)
		self.assertIn("WHERE ifnull(mr.custom_requested_by, '') = ''", sql)


if __name__ == "__main__":
	unittest.main()
