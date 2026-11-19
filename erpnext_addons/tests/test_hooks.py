"""Structural contract for erpnext_addons hooks (pure Python, no Frappe needed)."""

import json
import tomllib
import unittest
from pathlib import Path

from erpnext_addons import hooks

PKG = Path(__file__).resolve().parents[1]
APP_ROOT = PKG.parent
NAMING_FIELDS = ["Item Group-custom_naming_series", "Stock Entry Type-custom_naming_series"]
IC_DOCTYPES = {
	"Purchase Order",
	"Sales Order",
	"Delivery Note",
	"Purchase Receipt",
	"Sales Invoice",
	"Purchase Invoice",
}
IC_EVENTS = {
	"on_change": "erpnext_addons.intercompany.events.on_change",
	"before_cancel": "erpnext_addons.intercompany.events.before_cancel",
	"before_validate": "erpnext_addons.intercompany.events.guard",
	"before_update_after_submit": "erpnext_addons.intercompany.events.guard",
}


def _as_list(value):
	return value if isinstance(value, list) else [value]


class TestHooks(unittest.TestCase):
	def test_app_metadata_targets_erpnext_v16(self):
		self.assertEqual(hooks.app_name, "erpnext_addons")
		self.assertEqual(hooks.app_title, "ERPNext Add-ons")
		self.assertEqual(hooks.required_apps, ["erpnext"])
		pyproject = tomllib.loads((APP_ROOT / "pyproject.toml").read_text())
		self.assertEqual(pyproject["project"]["name"], "erpnext_addons")
		self.assertEqual(pyproject["project"]["dependencies"], [])
		deps = pyproject["tool"]["bench"]["frappe-dependencies"]
		self.assertEqual(deps, {"frappe": ">=16.0.0,<17.0.0", "erpnext": ">=16.0.0,<17.0.0"})
		self.assertEqual((PKG / "modules.txt").read_text().strip(), "ERPNext Add-ons")

	def test_hooks_contain_only_approved_doctypes(self):
		self.assertEqual(
			set(hooks.doctype_js),
			{"Item", "Stock Entry", "Material Request", "Sales Order", "Purchase Order"},
		)
		self.assertEqual(hooks.doctype_js["Stock Entry"], "public/js/stock_entry_form.js")
		self.assertEqual(hooks.doctype_js["Sales Order"], "public/js/order_update_pricing.js")
		self.assertEqual(
			hooks.doctype_js["Purchase Order"],
			[
				"public/js/order_update_pricing.js",
				"public/js/purchase_order_get_material_request.js",
			],
		)
		self.assertEqual(
			set(hooks.override_doctype_dashboards),
			{"Purchase Receipt", "Purchase Order", "Purchase Invoice", "Stock Entry", "Payment Entry"},
		)
		naming = {"Item", "Stock Entry", "Material Request"}
		self.assertEqual(set(hooks.doc_events), naming | IC_DOCTYPES)
		for dt in naming:
			self.assertEqual(set(hooks.doc_events[dt]), {"before_insert"})
		# intercompany: progress tracking only (display fields), no sync or blocking hooks
		for dt in IC_DOCTYPES:
			self.assertEqual(hooks.doc_events[dt], IC_EVENTS)
		self.assertEqual(hooks.app_include_js, ["/assets/erpnext_addons/js/list_settings_columns.js"])
		self.assertEqual(len(hooks.fixtures), 1)
		fixture = hooks.fixtures[0]
		self.assertEqual(fixture["dt"], "Custom Field")
		self.assertEqual(fixture["filters"], [["name", "in", NAMING_FIELDS]])

	def test_no_intercompany_sync_hooks_are_registered(self):
		for name in (
			"scheduler_events",
			"override_doctype_class",
			"override_whitelisted_methods",
			"doctype_list_js",
			"before_migrate",
		):
			self.assertFalse(hasattr(hooks, name), name)
		self.assertNotIn("Payment Entry", hooks.doc_events)
		for dt in ("Sales Invoice", "Purchase Invoice", "Delivery Note", "Purchase Receipt"):
			self.assertNotIn(dt, hooks.doctype_js)
		source = (PKG / "hooks.py").read_text()
		for old in ("intercompany_sync", "item_group_series", "stock_entry_series", "ic_payment_reference"):
			self.assertNotIn(old, source)

	def test_hook_target_paths_exist(self):
		for js in hooks.doctype_js.values():
			for rel in _as_list(js):
				self.assertTrue((PKG / rel).is_file(), rel)
		for asset in hooks.app_include_js:
			self.assertTrue((PKG / "public" / asset.removeprefix("/assets/erpnext_addons/")).is_file(), asset)
		dotted = [p for ev in hooks.doc_events.values() for handler in ev.values() for p in _as_list(handler)]
		dotted += list(hooks.override_doctype_dashboards.values())
		dotted += _as_list(hooks.after_sync) + _as_list(hooks.after_migrate)
		# a patch entry is a module path; Frappe calls its execute()
		dotted += [f"{p}.execute" for p in (PKG / "patches.txt").read_text().split() if not p.startswith("[")]
		for path in dotted:
			parts = path.split(".")
			self.assertEqual(parts[0], "erpnext_addons", path)
			module_file = APP_ROOT.joinpath(*parts[:-1]).with_suffix(".py")
			self.assertTrue(module_file.is_file(), path)
			self.assertIn(f"def {parts[-1]}(", module_file.read_text(), path)

	def test_patches_file_has_both_sections_frappe_requires(self):
		import configparser

		parser = configparser.ConfigParser(allow_no_value=True, delimiters="\n")
		parser.read(PKG / "patches.txt")
		if parser.sections():  # Frappe throws when a sectioned file lacks either section
			self.assertEqual(set(parser.sections()), {"pre_model_sync", "post_model_sync"})

	def test_fixture_file_matches_hook_filter(self):
		records = json.loads((PKG / "fixtures" / "custom_field.json").read_text())
		self.assertEqual(sorted(r["name"] for r in records), NAMING_FIELDS)


if __name__ == "__main__":
	unittest.main()
