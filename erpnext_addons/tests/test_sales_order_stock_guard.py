"""Sales Order stock guard: toggle field and validate hook (no site needed)."""

import unittest
from types import SimpleNamespace
from unittest import mock

from erpnext_addons.tests.fakes import FakeValidationError, ensure_frappe_importable, new_doc

ensure_frappe_importable()

from erpnext_addons import migration
from erpnext_addons.overrides import sales_order


def row(**values):
	defaults = {
		"idx": 1,
		"item_code": "BREAD",
		"qty": 1,
		"stock_qty": 1,
		"warehouse": "Kitchen",
		"is_stock_item": 1,
	}
	defaults.update(values)
	return new_doc(**defaults)


class StockGuardCase(unittest.TestCase):
	def setUp(self):
		self.enabled = True
		self.field_exists = True
		self.groups = set()
		self.frappe = SimpleNamespace(
			db=SimpleNamespace(get_single_value=lambda *args: self.enabled),
			get_meta=lambda *args: SimpleNamespace(has_field=lambda fieldname: self.field_exists),
			get_cached_value=self._cached_value,
			throw=self._throw,
		)
		for target in (
			mock.patch.object(sales_order, "frappe", self.frappe),
			mock.patch.object(
				sales_order,
				"_bin_details",
				return_value={"actual_qty": 0},
			),
		):
			target.start()
			self.addCleanup(target.stop)
		self.bin_details = sales_order._bin_details

	def _cached_value(self, doctype, name, field):
		if field == "is_group":
			return 1 if name in self.groups else 0
		return 1

	def _throw(self, msg, exc=None):
		raise FakeValidationError(msg)

	def validate(self, *rows, company="Kitchen Co"):
		doc = new_doc(company=company, items=list(rows))
		sales_order.validate(doc)

	def test_toggle_off_skips_stock_check(self):
		self.enabled = False
		self.validate(row(stock_qty=5))
		self.bin_details.assert_not_called()

	def test_missing_toggle_field_skips_stock_check(self):
		self.field_exists = False
		self.validate(row(stock_qty=5))
		self.bin_details.assert_not_called()

	def test_zero_stock_rejects(self):
		with self.assertRaisesRegex(FakeValidationError, "BREAD"):
			self.validate(row(stock_qty=5))

	def test_short_stock_rejects(self):
		self.bin_details.return_value = {"actual_qty": 3}
		with self.assertRaisesRegex(FakeValidationError, "3"):
			self.validate(row(stock_qty=5))

	def test_exact_stock_passes(self):
		self.bin_details.return_value = {"actual_qty": 5}
		self.validate(row(stock_qty=5))

	def test_fractional_rows_match_exact_stock(self):
		self.bin_details.return_value = {"actual_qty": 0.3}
		self.validate(row(stock_qty=0.1), row(stock_qty=0.2, idx=2))

	def test_non_stock_item_is_skipped(self):
		self.validate(row(stock_qty=5, is_stock_item=0))
		self.bin_details.assert_not_called()

	def test_supplier_delivered_row_is_skipped(self):
		self.validate(row(stock_qty=5, delivered_by_supplier=1))
		self.bin_details.assert_not_called()

	def test_string_zero_delivered_by_supplier_is_not_skipped(self):
		self.bin_details.return_value = {"actual_qty": 5}
		self.validate(row(stock_qty=5, delivered_by_supplier="0"))
		self.bin_details.assert_called_once()

	def test_string_zero_is_stock_item_is_skipped(self):
		self.validate(row(stock_qty=5, is_stock_item="0"))
		self.bin_details.assert_not_called()

	def test_group_warehouse_is_rejected(self):
		self.groups.add("Kitchen")
		with self.assertRaisesRegex(FakeValidationError, "group warehouse"):
			self.validate(row(stock_qty=5))
		self.bin_details.assert_not_called()

	def test_missing_is_stock_item_falls_back_to_item(self):
		self.frappe.get_cached_value = lambda *args: 0
		self.validate(row(stock_qty=5, is_stock_item=None))
		self.bin_details.assert_not_called()

	def test_zero_qty_row_is_skipped(self):
		self.validate(row(qty=0, stock_qty=0))
		self.bin_details.assert_not_called()

	def test_row_warehouse_is_used(self):
		self.bin_details.return_value = {"actual_qty": 5}
		self.validate(row(stock_qty=5))
		self.bin_details.assert_called_once_with("BREAD", "Kitchen")

	def test_rows_for_the_same_item_are_summed(self):
		self.bin_details.return_value = {"actual_qty": 5}
		with self.assertRaisesRegex(FakeValidationError, "6"):
			self.validate(row(stock_qty=3), row(stock_qty=3, idx=2))
		self.bin_details.assert_called_once()


class FieldDefsCase(unittest.TestCase):
	def test_field_defs(self):
		self.assertEqual(
			sales_order.field_defs(),
			[
				{
					"fieldname": "custom_block_so_insufficient_stock",
					"fieldtype": "Check",
					"label": "Block Sales Order if Stock is Insufficient",
					"default": "0",
					"insert_after": "allow_negative_stock",
					"description": (
						"Reject saving a Sales Order when an item's available stock is less "
						"than the ordered stock quantity."
					),
				}
			],
		)

	def test_after_migrate_creates_the_field(self):
		with mock.patch("erpnext_addons.migration._seed_then_take_over"), \
		     mock.patch("erpnext_addons.intercompany.setup.ensure_fields"), \
		     mock.patch("erpnext_addons.buying.paid.ensure_fields"), \
		     mock.patch("erpnext_addons.buying.setup.ensure_fields"), \
		     mock.patch.object(sales_order, "ensure_fields") as ensure:
			migration.after_migrate()
		ensure.assert_called_once()


if __name__ == "__main__":
	unittest.main()
