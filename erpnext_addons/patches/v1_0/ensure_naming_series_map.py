import frappe

SEED_MAP = {
	"Purchase": "MREQ-PUR-.YY.-.####",
	"Material Transfer": "MREQ-MTR-.YY.-.####",
	"Material Issue": "MREQ-MIS-.YY.-.####",
	"Manufacture": "MREQ-MFG-.YY.-.####",
	"Subcontracting": "MREQ-SBC-.YY.-.####",
	"Customer Provided": "MREQ-CUS-.YY.-.####",
}


def execute():
	"""Seed missing Material Request rows, then make erpnext_addons own the DocType."""
	from erpnext_addons.migration import take_over_naming_series_map

	seed_rows()
	take_over_naming_series_map()


def seed_rows():
	"""Seed Naming Series Map rows for Material Request types (UI-editable)."""
	for type_value, series in SEED_MAP.items():
		if not frappe.db.exists(
			"Naming Series Map", {"document_type": "Material Request", "type_value": type_value}
		):
			frappe.get_doc({
				"doctype": "Naming Series Map",
				"document_type": "Material Request",
				"type_value": type_value,
				"naming_series": series,
			}).insert(ignore_permissions=True)
