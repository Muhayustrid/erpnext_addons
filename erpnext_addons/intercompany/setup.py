"""Custom fields for intercompany progress, created from one definition for all six doctypes."""

from erpnext_addons.intercompany.chain import INTERNAL_FLAG
from erpnext_addons.intercompany.progress import FIELDS

# last field of the section holding `status` (all on the More Info tab)
INSERT_AFTER = {
	"Purchase Order": "per_received",
	"Sales Order": "advance_payment_status",
	"Delivery Note": "per_returned",
	"Purchase Receipt": "per_returned",
	"Sales Invoice": "is_discounted",
	"Purchase Invoice": "per_received",
}
LABELS = ("Ordered", "Delivered", "Received", "Sales Invoiced", "Purchase Invoiced", "Next Step")
SECTION = "custom_ic_progress_section"


def field_defs(doctype):
	common = {"read_only": 1, "no_copy": 1, "allow_on_submit": 1}
	defs = [
		{
			"fieldname": SECTION,
			"fieldtype": "Section Break",
			"label": "Intercompany Progress",
			"collapsible": 1,
			"depends_on": f"eval:doc.{INTERNAL_FLAG[doctype]}",
			"insert_after": INSERT_AFTER[doctype],
		},
		{
			**common,
			"fieldname": "custom_ic_next_step",
			"fieldtype": "Data",
			"label": "Next Step",
			"in_list_view": 1,
			"in_standard_filter": 1,
			"insert_after": SECTION,
		},
	]
	previous = "custom_ic_next_step"
	for fieldname, label in zip(FIELDS[:-1], LABELS[:-1], strict=True):
		defs.append({**common, "fieldname": fieldname, "fieldtype": "Check", "label": label, "insert_after": previous})
		previous = fieldname
	return defs


def ensure_fields():
	from frappe.custom.doctype.custom_field.custom_field import create_custom_fields

	create_custom_fields({dt: field_defs(dt) for dt in INSERT_AFTER}, update=True)
