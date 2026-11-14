"""In-place ownership transfer of the `Naming Series Map` DocType.

Frappe uninstall deletes every DocType whose `module` belongs to the removed
app, so the DocType must point at `ERPNext Add-ons` before `stock_entry_series`
is uninstalled, and back at `Stock Entry Series` before `erpnext_addons` is.
These helpers never commit; install/migrate owns the transaction.
"""

import importlib.util

import frappe

DOCTYPE = "Naming Series Map"
NEW_MODULE, NEW_APP = "ERPNext Add-ons", "erpnext_addons"
OLD_MODULE, OLD_APP = "Stock Entry Series", "stock_entry_series"


def after_sync():
	_seed_then_take_over()


def after_migrate():
	_seed_then_take_over()


def _seed_then_take_over():
	from erpnext_addons.patches.v1_0 import (
		ensure_naming_series_map,
		seed_item_group_series,
		seed_stock_entry_series,
	)

	seed_item_group_series.execute()
	seed_stock_entry_series.execute()
	# runs last: during overlap the old app's JSON may have re-imported the old module
	ensure_naming_series_map.execute()


def take_over_naming_series_map():
	_set_owner(NEW_MODULE, NEW_APP)


def hand_back_naming_series_map():
	"""Rollback primitive (operator-invoked, before uninstalling erpnext_addons).

	Afterwards re-sync the old definition with
	`bench --site <site> reload-doc stock_entry_series "Stock Entry Series" naming_series_map`;
	do not run `migrate` while erpnext_addons is installed, its after_migrate takes over again.
	"""
	if OLD_APP not in frappe.get_installed_apps() or not _old_app_code_available():
		frappe.throw(
			f"Cannot hand {DOCTYPE} back: app {OLD_APP} must be installed and its code available",
			frappe.ValidationError,
		)
	_set_owner(OLD_MODULE, OLD_APP)


def assert_naming_series_map_owner(module_name, app_name):
	module = frappe.db.get_value("DocType", DOCTYPE, "module")
	owner_app = frappe.db.get_value("Module Def", module_name, "app_name")
	if module != module_name or owner_app != app_name:
		frappe.throw(
			f"{DOCTYPE} ownership check failed: DocType.module={module!r}, "
			f"Module Def {module_name!r}.app_name={owner_app!r}; expected {module_name!r}/{app_name!r}",
			frappe.ValidationError,
		)


def _set_owner(module_name, app_name):
	if not frappe.db.exists("DocType", DOCTYPE):
		frappe.throw(f"DocType {DOCTYPE} does not exist", frappe.ValidationError)

	if not frappe.db.exists("Module Def", module_name):
		frappe.get_doc({"doctype": "Module Def", "module_name": module_name, "app_name": app_name}).insert(
			ignore_permissions=True
		)
	elif frappe.db.get_value("Module Def", module_name, "app_name") != app_name:
		frappe.db.set_value("Module Def", module_name, "app_name", app_name)

	# db.set_value, not DocType.save: save would export JSON files in developer mode
	if frappe.db.get_value("DocType", DOCTYPE, "module") != module_name:
		frappe.db.set_value("DocType", DOCTYPE, "module", module_name)

	frappe.clear_cache(doctype=DOCTYPE)
	assert_naming_series_map_owner(module_name, app_name)


def _old_app_code_available():
	try:
		return importlib.util.find_spec(f"{OLD_APP}.stock_entry_series.doctype.naming_series_map") is not None
	except ModuleNotFoundError:  # find_spec raises, not returns None, when the parent package is gone
		return False
