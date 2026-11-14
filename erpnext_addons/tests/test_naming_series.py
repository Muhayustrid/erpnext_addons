"""Naming series behaviour moved from item_group_series and stock_entry_series.

Unit classes run anywhere against FakeFrappe. Integration classes are the
ported originals; they need a real site (`bench run-tests`) and skip otherwise.
"""

import json
import unittest
from pathlib import Path
from unittest import mock

from erpnext_addons.tests.fakes import FakeFrappe, ensure_frappe_importable, new_doc

ensure_frappe_importable()

import frappe  # noqa: E402

from erpnext_addons.overrides import item, material_request, stock_entry  # noqa: E402
from erpnext_addons.patches.v1_0 import seed_item_group_series, seed_stock_entry_series  # noqa: E402

try:
	from frappe.tests import IntegrationTestCase

	HAS_SITE = bool(getattr(frappe.local, "site", None))
except ImportError:
	IntegrationTestCase, HAS_SITE = unittest.TestCase, False

PKG = Path(__file__).resolve().parents[1]


class FakeCase(unittest.TestCase):
	modules = (item, stock_entry, material_request, seed_item_group_series, seed_stock_entry_series)

	def setUp(self):
		self.f = FakeFrappe()
		for module in self.modules:
			patcher = mock.patch.object(module, "frappe", self.f)
			patcher.start()
			self.addCleanup(patcher.stop)
			if hasattr(module, "get_default_naming_series"):
				p = mock.patch.object(module, "get_default_naming_series", lambda dt: None)
				p.start()
				self.addCleanup(p.stop)


class TestItemNamingUnit(FakeCase):
	def setUp(self):
		super().setUp()
		self.f.add("Item Group", "Bahan Baku", custom_naming_series="BB.YY..####.")
		self.f.add("Item Group", "Kosong", custom_naming_series=None)
		self.f.meta_defaults["Item"] = {"naming_series": "STO-ITEM-.YYYY.-"}

	def test_group_series_applied_and_stable_when_called_twice(self):
		doc = new_doc(item_group="Bahan Baku", naming_series="")
		item.set_naming_series(doc)
		item.set_naming_series(doc)
		self.assertEqual(doc.naming_series, "BB.YY..####.")

	def test_field_default_is_replaced(self):
		doc = new_doc(item_group="Bahan Baku", naming_series="STO-ITEM-.YYYY.-")
		item.set_naming_series(doc)
		self.assertEqual(doc.naming_series, "BB.YY..####.")

	def test_explicit_series_respected(self):
		doc = new_doc(item_group="Bahan Baku", naming_series="MY-OWN-.YY.-")
		item.set_naming_series(doc)
		self.assertEqual(doc.naming_series, "MY-OWN-.YY.-")

	def test_unset_group_falls_back_and_missing_group_is_noop(self):
		doc = new_doc(item_group="Kosong", naming_series="")
		item.set_naming_series(doc)
		self.assertEqual(doc.naming_series, item.DEFAULT_SERIES)
		doc = new_doc(item_group=None, naming_series="")
		item.set_naming_series(doc)
		self.assertEqual(doc.naming_series, "")


class TestStockEntryNamingUnit(FakeCase):
	def setUp(self):
		super().setUp()
		self.f.add("Stock Entry Type", "Material Transfer", custom_naming_series="MTR-.YY.-.####")
		self.f.add("Stock Entry Type", "No Series", custom_naming_series="")

	def test_type_series_applied_and_stable_when_called_twice(self):
		doc = new_doc(stock_entry_type="Material Transfer", naming_series=stock_entry.DEFAULT_SERIES)
		stock_entry.set_naming_series(doc)
		stock_entry.set_naming_series(doc)
		self.assertEqual(doc.naming_series, "MTR-.YY.-.####")

	def test_explicit_series_respected(self):
		doc = new_doc(stock_entry_type="Material Transfer", naming_series="MY-OWN-.YY.-")
		stock_entry.set_naming_series(doc)
		self.assertEqual(doc.naming_series, "MY-OWN-.YY.-")

	def test_unknown_type_falls_back(self):
		for type_name in ("No Series", "Not A Type"):
			doc = new_doc(stock_entry_type=type_name, naming_series="")
			stock_entry.set_naming_series(doc)
			self.assertEqual(doc.naming_series, stock_entry.DEFAULT_SERIES)


class TestMaterialRequestNamingUnit(FakeCase):
	def test_map_row_wins_then_code_map_then_default(self):
		self.f.add(
			"Naming Series Map", "h1", document_type="Material Request", type_value="Manufacture",
			naming_series="MAPTEST-.YY.-.###",
		)
		self.assertEqual(material_request.get_series_for_type("Manufacture"), "MAPTEST-.YY.-.###")
		self.assertEqual(
			material_request.get_series_for_type("Purchase"), material_request.SERIES_MAP["Purchase"]
		)
		self.assertEqual(material_request.get_series_for_type("Unknown"), material_request.DEFAULT_SERIES)

	def test_without_table_uses_code_map(self):
		self.assertFalse(self.f.db.table_exists("Naming Series Map"))
		self.assertEqual(
			material_request.get_series_for_type("Purchase"), material_request.SERIES_MAP["Purchase"]
		)

	def test_called_twice_is_stable_and_explicit_respected(self):
		doc = new_doc(material_request_type="Purchase", naming_series="")
		material_request.set_naming_series(doc)
		material_request.set_naming_series(doc)
		self.assertEqual(doc.naming_series, material_request.SERIES_MAP["Purchase"])
		doc = new_doc(material_request_type="Purchase", naming_series="MY-OWN-.YY.-")
		material_request.set_naming_series(doc)
		self.assertEqual(doc.naming_series, "MY-OWN-.YY.-")


class TestSeedsUnit(FakeCase):
	def test_item_group_seed_fills_only_empty_values(self):
		self.f.db.columns.add(("Item Group", "custom_naming_series"))
		self.f.add("Item Group", "Bahan Baku", custom_naming_series="ADMIN-.###")
		self.f.add("Item Group", "ATK", custom_naming_series="")
		seed_item_group_series.execute()
		seed_item_group_series.execute()
		self.assertEqual(self.f.db.get_value("Item Group", "Bahan Baku", "custom_naming_series"), "ADMIN-.###")
		self.assertEqual(self.f.db.get_value("Item Group", "ATK", "custom_naming_series"), "ATK.YY..####.")
		self.assertEqual(len(self.f.db.writes), 1)

	def test_stock_entry_type_seed_fills_only_empty_values(self):
		self.f.db.columns.add(("Stock Entry Type", "custom_naming_series"))
		self.f.add("Stock Entry Type", "Repack", custom_naming_series="ADMIN-RPK")
		self.f.add("Stock Entry Type", "Manufacture", custom_naming_series=None)
		seed_stock_entry_series.execute()
		seed_stock_entry_series.execute()
		self.assertEqual(self.f.db.get_value("Stock Entry Type", "Repack", "custom_naming_series"), "ADMIN-RPK")
		self.assertEqual(
			self.f.db.get_value("Stock Entry Type", "Manufacture", "custom_naming_series"), "MFG-.YY.-.####"
		)
		self.assertEqual(len(self.f.db.writes), 1)

	def test_seeds_skip_when_column_missing(self):
		self.f.add("Item Group", "ATK", custom_naming_series="")
		seed_item_group_series.execute()
		seed_stock_entry_series.execute()
		self.assertEqual(self.f.db.writes, [])


class TestFixtures(unittest.TestCase):
	def test_fixture_records_have_no_old_module_owner(self):
		records = json.loads((PKG / "fixtures" / "custom_field.json").read_text())
		by_name = {r["name"]: r for r in records}
		self.assertEqual(
			set(by_name), {"Item Group-custom_naming_series", "Stock Entry Type-custom_naming_series"}
		)
		for r in records:
			self.assertNotIn("module", r)
			self.assertEqual((r["fieldname"], r["fieldtype"]), ("custom_naming_series", "Data"))
		self.assertEqual(by_name["Item Group-custom_naming_series"]["dt"], "Item Group")
		self.assertEqual(by_name["Stock Entry Type-custom_naming_series"]["dt"], "Stock Entry Type")


# ---- Integration tests ported verbatim (namespace only); need a real site ----

TEST_TYPE = "_Test SE Type With Series"
TEST_SERIES = "TSE-.YY.-.####"


def _ensure_test_type():
	if not frappe.db.exists("Stock Entry Type", TEST_TYPE):
		frappe.get_doc({
			"doctype": "Stock Entry Type",
			"__newname": TEST_TYPE,
			"purpose": "Material Transfer",
			"custom_naming_series": TEST_SERIES,
		}).insert(ignore_permissions=True)


@unittest.skipUnless(HAS_SITE, "needs a Frappe site (bench run-tests)")
class TestItemGroupSeries(IntegrationTestCase):
	def test_naming_series_assigned_from_item_group(self):
		doc = frappe.new_doc("Item")
		doc.item_code = "_Test Item Bahan Baku"
		doc.item_name = "_Test Item Bahan Baku"
		doc.item_group = "Bahan Baku"
		doc.stock_uom = "Nos"
		item.set_naming_series(doc)
		expected = frappe.db.get_value("Item Group", "Bahan Baku", "custom_naming_series")
		self.assertEqual(doc.naming_series, expected)

	def test_field_default_series_is_replaced_by_group_series(self):
		field_default = frappe.get_meta("Item").get_field("naming_series").default or ""
		doc = frappe.new_doc("Item")
		doc.item_group = "Bahan Baku"
		doc.naming_series = field_default
		item.set_naming_series(doc)
		expected = frappe.db.get_value("Item Group", "Bahan Baku", "custom_naming_series")
		self.assertEqual(doc.naming_series, expected)

	def test_fallback_naming_series_for_unset_group(self):
		group_name = "_Test Group No Series"
		if not frappe.db.exists("Item Group", group_name):
			frappe.get_doc({
				"doctype": "Item Group",
				"item_group_name": group_name,
				"parent_item_group": "All Item Groups",
				"is_group": 0,
			}).insert(ignore_permissions=True)

		doc = frappe.new_doc("Item")
		doc.item_code = "_Test Item Fallback"
		doc.item_name = "_Test Item Fallback"
		doc.item_group = group_name
		doc.stock_uom = "Nos"
		item.set_naming_series(doc)
		self.assertEqual(doc.naming_series, item.DEFAULT_SERIES)

	def test_e2e_insert_with_item_group_series(self):
		doc = frappe.get_doc({
			"doctype": "Item",
			"item_name": "_Test E2E Bahan Baku Item",
			"item_group": "Bahan Baku",
			"stock_uom": "Nos",
		}).insert(ignore_permissions=True)

		self.assertEqual(doc.naming_series, "BB.YY..####.")
		self.assertTrue(doc.name.startswith("BB26") or "BB" in doc.name)

		dynamic_group = "_Test Group Dynamic Series"
		if not frappe.db.exists("Item Group", dynamic_group):
			frappe.get_doc({
				"doctype": "Item Group",
				"item_group_name": dynamic_group,
				"parent_item_group": "All Item Groups",
				"is_group": 0,
				"custom_naming_series": "DYN.YY..####.",
			}).insert(ignore_permissions=True)

		item_dyn = frappe.get_doc({
			"doctype": "Item",
			"item_name": "_Test E2E Dynamic Item",
			"item_group": dynamic_group,
			"stock_uom": "Nos",
		}).insert(ignore_permissions=True)

		self.assertEqual(item_dyn.naming_series, "DYN.YY..####.")
		self.assertTrue(item_dyn.name.startswith("DYN26") or "DYN" in item_dyn.name)


@unittest.skipUnless(HAS_SITE, "needs a Frappe site (bench run-tests)")
class TestStockEntrySeries(IntegrationTestCase):
	def test_series_assigned_from_stock_entry_type(self):
		_ensure_test_type()
		doc = frappe.new_doc("Stock Entry")
		doc.stock_entry_type = TEST_TYPE
		stock_entry.set_naming_series(doc)
		self.assertEqual(doc.naming_series, TEST_SERIES)

	def test_series_not_overridden_when_explicit(self):
		doc = frappe.new_doc("Stock Entry")
		doc.stock_entry_type = "Material Transfer"
		doc.naming_series = "MY-OWN-.YY.-"
		stock_entry.set_naming_series(doc)
		self.assertEqual(doc.naming_series, "MY-OWN-.YY.-")

	def test_fallback_naming_series_for_type_without_series(self):
		type_name = "_Test SE Type No Series"
		if not frappe.db.exists("Stock Entry Type", type_name):
			frappe.get_doc({
				"doctype": "Stock Entry Type",
				"__newname": type_name,
				"purpose": "Material Transfer",
			}).insert(ignore_permissions=True)

		doc = frappe.new_doc("Stock Entry")
		doc.stock_entry_type = type_name
		stock_entry.set_naming_series(doc)
		self.assertEqual(doc.naming_series, stock_entry.DEFAULT_SERIES)

	def test_e2e_insert_uses_type_series(self):
		company = frappe.get_all("Company", pluck="name", limit=1)
		items = frappe.get_all("Item", pluck="name", limit=2)
		warehouses = frappe.get_all(
			"Warehouse",
			filters={"is_group": 0, "company": company[0]} if company else {"is_group": 0},
			pluck="name",
			limit=2,
		)
		if not (company and len(items) >= 1 and len(warehouses) >= 2):
			self.skipTest("Site lacks company/item/warehouses needed for e2e test")

		_ensure_test_type()
		series_prefix = "TSE-26-"
		series_before = frappe.db.sql("SELECT `current` FROM `tabSeries` WHERE `name` = %s", series_prefix)
		series_before = series_before[0][0] if series_before else None

		doc = frappe.get_doc({
			"doctype": "Stock Entry",
			"stock_entry_type": TEST_TYPE,
			"company": company[0],
			"items": [{
				"item_code": items[0],
				"s_warehouse": warehouses[0],
				"t_warehouse": warehouses[1],
				"qty": 1,
				"basic_rate": 1000,
			}],
		}).insert(ignore_permissions=True)

		self.assertEqual(doc.naming_series, TEST_SERIES)
		self.assertTrue(doc.name.startswith(series_prefix))

		frappe.delete_doc("Stock Entry", doc.name, force=True, ignore_permissions=True)
		if series_before is not None:
			frappe.db.sql(
				"UPDATE `tabSeries` SET `current` = %s WHERE `name` = %s", (series_before, series_prefix)
			)


@unittest.skipUnless(HAS_SITE, "needs a Frappe site (bench run-tests)")
class TestMaterialRequestSeries(IntegrationTestCase):
	def test_series_assigned_from_type(self):
		doc = frappe.new_doc("Material Request")
		doc.material_request_type = "Purchase"
		material_request.set_naming_series(doc)
		self.assertEqual(doc.naming_series, material_request.SERIES_MAP["Purchase"])

	def test_naming_series_map_row_wins_over_code_map(self):
		row = frappe.db.get_value(
			"Naming Series Map", {"document_type": "Material Request", "type_value": "Manufacture"}
		)
		if row:
			frappe.db.set_value("Naming Series Map", row, "naming_series", "MAPTEST-.YY.-.###")
		else:
			frappe.get_doc({
				"doctype": "Naming Series Map",
				"document_type": "Material Request",
				"type_value": "Manufacture",
				"naming_series": "MAPTEST-.YY.-.###",
			}).insert(ignore_permissions=True)

		self.assertEqual(material_request.get_series_for_type("Manufacture"), "MAPTEST-.YY.-.###")

		doc = frappe.new_doc("Material Request")
		doc.material_request_type = "Manufacture"
		material_request.set_naming_series(doc)
		self.assertEqual(doc.naming_series, "MAPTEST-.YY.-.###")

	def test_series_not_overridden_when_explicit(self):
		doc = frappe.new_doc("Material Request")
		doc.material_request_type = "Purchase"
		doc.naming_series = "MY-OWN-.YY.-"
		material_request.set_naming_series(doc)
		self.assertEqual(doc.naming_series, "MY-OWN-.YY.-")

	def test_e2e_insert_uses_type_series(self):
		company = frappe.get_all("Company", pluck="name", limit=1)
		items = frappe.get_all("Item", pluck="name", limit=1)
		warehouses = frappe.get_all(
			"Warehouse",
			filters={"is_group": 0, "company": company[0]} if company else {"is_group": 0},
			pluck="name",
			limit=1,
		)
		if not (company and items and warehouses):
			self.skipTest("Site lacks company/item/warehouses needed for e2e test")

		series_prefix = "MREQ-PUR-26-"
		series_before = frappe.db.sql("SELECT `current` FROM `tabSeries` WHERE `name` = %s", series_prefix)
		series_before = series_before[0][0] if series_before else None

		doc = frappe.get_doc({
			"doctype": "Material Request",
			"material_request_type": "Purchase",
			"company": company[0],
			"items": [{
				"item_code": items[0],
				"qty": 1,
				"schedule_date": frappe.utils.add_days(None, 7),
				"warehouse": warehouses[0],
			}],
		}).insert(ignore_permissions=True)

		self.assertEqual(doc.naming_series, material_request.SERIES_MAP["Purchase"])
		self.assertTrue(doc.name.startswith(series_prefix))

		frappe.delete_doc("Material Request", doc.name, force=True, ignore_permissions=True)
		if series_before is not None:
			frappe.db.sql(
				"UPDATE `tabSeries` SET `current` = %s WHERE `name` = %s", (series_before, series_prefix)
			)


if __name__ == "__main__":
	unittest.main()
