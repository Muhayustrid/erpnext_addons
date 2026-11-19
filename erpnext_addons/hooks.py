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
	"Purchase Order": [
		"public/js/order_update_pricing.js",
		"public/js/purchase_order_get_material_request.js",
	],
}

# Forward links (the current document holds the reference) cannot be counted by
# the native dashboard, so these overrides add the cards and a custom counter.
override_doctype_dashboards = {
	"Purchase Receipt": "erpnext_addons.dashboards.purchase_receipt",
	"Purchase Order": "erpnext_addons.dashboards.purchase_order",
	"Purchase Invoice": "erpnext_addons.dashboards.purchase_invoice",
	"Stock Entry": "erpnext_addons.dashboards.stock_entry",
	"Payment Entry": "erpnext_addons.dashboards.payment_entry",
}

app_include_js = ["/assets/erpnext_addons/js/list_settings_columns.js"]

_IC_PROGRESS_EVENTS = {
	"on_change": "erpnext_addons.intercompany.events.on_change",
	"before_cancel": "erpnext_addons.intercompany.events.before_cancel",
	"before_validate": "erpnext_addons.intercompany.events.guard",
	"before_update_after_submit": "erpnext_addons.intercompany.events.guard",
}

doc_events = {
	"Item": {"before_insert": "erpnext_addons.overrides.item.set_naming_series"},
	"Stock Entry": {"before_insert": "erpnext_addons.overrides.stock_entry.set_naming_series"},
	"Material Request": {
		"before_insert": [
			"erpnext_addons.overrides.material_request.set_naming_series",
			"erpnext_addons.overrides.material_request.set_requested_by",
		]
	},
	**{
		dt: dict(_IC_PROGRESS_EVENTS)
		for dt in (
			"Purchase Order",
			"Sales Order",
			"Delivery Note",
			"Purchase Receipt",
			"Sales Invoice",
			"Purchase Invoice",
		)
	},
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
