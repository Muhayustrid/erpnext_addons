"""Naming Series Map takeover/handback against an in-memory Frappe boundary."""

import unittest
from unittest import mock

from erpnext_addons.tests.fakes import FakeFrappe, FakeValidationError, ensure_frappe_importable

ensure_frappe_importable()

from erpnext_addons import migration
from erpnext_addons.buying import setup as buying_setup
from erpnext_addons.intercompany import setup as ic_setup
from erpnext_addons.patches.v1_0 import (
	backfill_intercompany_progress,
	ensure_naming_series_map,
	seed_item_group_series,
	seed_stock_entry_series,
)

DT = "Naming Series Map"


class MigrationCase(unittest.TestCase):
	def setUp(self):
		for target, name in (
			(buying_setup, "ensure_fields"),
			(ic_setup, "ensure_fields"),
			(backfill_intercompany_progress, "execute"),
		):
			p = mock.patch.object(target, name)
			p.start()
			self.addCleanup(p.stop)
		self.f = FakeFrappe()
		self.f.installed_apps = ["frappe", "erpnext", "stock_entry_series", "erpnext_addons"]
		self.f.get_installed_apps = lambda: list(self.f.installed_apps)
		for module in (migration, ensure_naming_series_map, seed_item_group_series, seed_stock_entry_series):
			p = mock.patch.object(module, "frappe", self.f)
			p.start()
			self.addCleanup(p.stop)
		# state while both apps are installed and the old JSON was synced last
		self.f.add("Module Def", "Stock Entry Series", module_name="Stock Entry Series", app_name="stock_entry_series")
		self.f.add("DocType", DT, module="Stock Entry Series")
		self.f.add(DT, "row1", document_type="Material Request", type_value="Purchase", naming_series="ADMIN-PUR")
		self.rows_before = dict(self.f.db.tables[DT])

	def owner(self):
		return self.f.db.get_value("DocType", DT, "module")


class TestTakeOver(MigrationCase):
	def test_creates_module_def_and_moves_doctype_without_touching_rows(self):
		migration.take_over_naming_series_map()
		self.assertEqual(self.owner(), "ERPNext Add-ons")
		self.assertEqual(self.f.db.get_value("Module Def", "ERPNext Add-ons", "app_name"), "erpnext_addons")
		self.assertEqual(self.f.db.tables[DT], self.rows_before)
		self.assertIn(DT, self.f.cleared)

	def test_fixes_module_def_with_wrong_app(self):
		self.f.add("Module Def", "ERPNext Add-ons", module_name="ERPNext Add-ons", app_name="other")
		migration.take_over_naming_series_map()
		self.assertEqual(self.f.db.get_value("Module Def", "ERPNext Add-ons", "app_name"), "erpnext_addons")

	def test_idempotent(self):
		migration.take_over_naming_series_map()
		writes = len(self.f.db.writes)
		inserts = len(self.f.inserted)
		migration.take_over_naming_series_map()
		self.assertEqual(self.owner(), "ERPNext Add-ons")
		self.assertEqual((len(self.f.db.writes), len(self.f.inserted)), (writes, inserts))

	def test_raises_when_read_back_differs(self):
		with mock.patch.object(self.f.db, "set_value"):  # write silently lost
			with self.assertRaises(FakeValidationError):
				migration.take_over_naming_series_map()

	def test_raises_when_doctype_missing(self):
		del self.f.db.tables["DocType"][DT]
		with self.assertRaises(FakeValidationError):
			migration.take_over_naming_series_map()


class TestHandBack(MigrationCase):
	def setUp(self):
		super().setUp()
		migration.take_over_naming_series_map()
		self.f.cleared.clear()

	def test_restores_old_owner_and_is_idempotent(self):
		self.f.db.set_value("Module Def", "Stock Entry Series", "app_name", None)
		with mock.patch.object(migration, "_old_app_code_available", return_value=True):
			migration.hand_back_naming_series_map()
			migration.hand_back_naming_series_map()
		self.assertEqual(self.owner(), "Stock Entry Series")
		self.assertEqual(
			self.f.db.get_value("Module Def", "Stock Entry Series", "app_name"), "stock_entry_series"
		)
		self.assertEqual(self.f.db.tables[DT], self.rows_before)
		self.assertIn(DT, self.f.cleared)

	def test_creates_missing_old_module_def(self):
		del self.f.db.tables["Module Def"]["Stock Entry Series"]
		with mock.patch.object(migration, "_old_app_code_available", return_value=True):
			migration.hand_back_naming_series_map()
		self.assertEqual(
			self.f.db.get_value("Module Def", "Stock Entry Series", "app_name"), "stock_entry_series"
		)

	def test_refuses_without_old_app_installed(self):
		self.f.installed_apps.remove("stock_entry_series")
		with mock.patch.object(migration, "_old_app_code_available", return_value=True):
			with self.assertRaises(FakeValidationError):
				migration.hand_back_naming_series_map()
		self.assertEqual(self.owner(), "ERPNext Add-ons")

	def test_refuses_without_old_app_code(self):
		with mock.patch.object(migration, "_old_app_code_available", return_value=False):
			with self.assertRaises(FakeValidationError):
				migration.hand_back_naming_series_map()
		self.assertEqual(self.owner(), "ERPNext Add-ons")

	def test_missing_old_package_refuses_cleanly(self):
		# real check, not mocked: the old package is not importable on this host
		with mock.patch.object(migration, "OLD_APP", "no_such_app"):
			self.f.installed_apps.append("no_such_app")
			self.assertFalse(migration._old_app_code_available())
			with self.assertRaises(FakeValidationError):
				migration.hand_back_naming_series_map()
		self.assertEqual(self.owner(), "ERPNext Add-ons")

	def test_raises_when_read_back_differs(self):
		with mock.patch.object(migration, "_old_app_code_available", return_value=True):
			with mock.patch.object(self.f.db, "set_value"):
				with self.assertRaises(FakeValidationError):
					migration.hand_back_naming_series_map()


class TestLifecycle(MigrationCase):
	def test_seeds_run_before_takeover_and_old_sync_is_overridden(self):
		order = []
		with (
			mock.patch.object(seed_item_group_series, "execute", lambda: order.append("item_group")),
			mock.patch.object(seed_stock_entry_series, "execute", lambda: order.append("stock_entry")),
			mock.patch.object(ensure_naming_series_map, "seed_rows", lambda: order.append("mr_rows")),
			mock.patch.object(
				migration, "take_over_naming_series_map", lambda: order.append("takeover")
			),
			mock.patch.object(backfill_intercompany_progress, "execute", lambda: order.append("backfill")),
			mock.patch.object(ic_setup, "ensure_fields", lambda: order.append("ic_fields")),
			mock.patch.object(buying_setup, "ensure_fields", lambda: order.append("buying_fields")),
		):
			migration.after_sync()
			migration.after_migrate()
		seeds = ["item_group", "stock_entry", "mr_rows", "takeover"]
		self.assertEqual(order, [*seeds, "backfill", *seeds, "buying_fields", "ic_fields"])

	def test_second_migrate_after_old_resync_ends_on_new_owner(self):
		migration.after_migrate()
		self.f.db.set_value("DocType", DT, "module", "Stock Entry Series")  # old JSON re-imported
		migration.after_migrate()
		self.assertEqual(self.owner(), "ERPNext Add-ons")

	def test_mr_seed_only_adds_missing_rows(self):
		ensure_naming_series_map.execute()
		ensure_naming_series_map.execute()
		rows = self.f.db.tables[DT]
		purchase = [r for r in rows.values() if r["type_value"] == "Purchase"]
		self.assertEqual([r["naming_series"] for r in purchase], ["ADMIN-PUR"])
		self.assertEqual(len(rows), len(ensure_naming_series_map.SEED_MAP))
		self.assertEqual(self.owner(), "ERPNext Add-ons")


if __name__ == "__main__":
	unittest.main()
