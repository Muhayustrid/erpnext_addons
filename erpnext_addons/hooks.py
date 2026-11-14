app_name = "erpnext_addons"
app_title = "ERPNext Add-ons"
app_publisher = "Muhammad Yusuf Tri Daryanto"
app_description = "General ERPNext enhancements for Roti Ropi: order Update Items pricing and naming series"
app_email = "114971841+Muhayustrid@users.noreply.github.com"
app_license = "mit"

required_apps = ["erpnext"]

doctype_js = {
	"Item": "public/js/item_form.js",
	"Stock Entry": "public/js/stock_entry_form.js",
	"Material Request": "public/js/material_request_form.js",
	"Sales Order": "public/js/order_update_pricing.js",
	"Purchase Order": "public/js/order_update_pricing.js",
}

doc_events = {
	"Item": {"before_insert": "erpnext_addons.overrides.item.set_naming_series"},
	"Stock Entry": {"before_insert": "erpnext_addons.overrides.stock_entry.set_naming_series"},
	"Material Request": {"before_insert": "erpnext_addons.overrides.material_request.set_naming_series"},
}

fixtures = [
	{
		"dt": "Custom Field",
		"filters": [
			["name", "in", ["Item Group-custom_naming_series", "Stock Entry Type-custom_naming_series"]]
		],
	}
]

# One orchestrator per lifecycle: seeds first, Naming Series Map takeover last.
# after_sync covers install-app (which does not run migrate).
after_sync = "erpnext_addons.migration.after_sync"
after_migrate = "erpnext_addons.migration.after_migrate"
