import unittest
from unittest import mock

from erpnext_addons.tests.fakes import ensure_frappe_importable

ensure_frappe_importable()

from erpnext_addons import migration
from erpnext_addons.buying import setup


class FieldDefsCase(unittest.TestCase):
	def test_field_defs(self):
		self.assertEqual(
			setup.field_defs(),
			[
				{
					"fieldname": "custom_requested_by",
					"fieldtype": "Data",
					"label": "Requested By",
					"read_only": 1,
					"no_copy": 1,
					"insert_after": "title",
				}
			],
		)

	def test_after_migrate_creates_the_field(self):
		with mock.patch("erpnext_addons.migration._seed_then_take_over"), \
		     mock.patch("erpnext_addons.intercompany.setup.ensure_fields"), \
		     mock.patch.object(setup, "ensure_fields") as ensure:
			migration.after_migrate()
		ensure.assert_called_once()


if __name__ == "__main__":
	unittest.main()
