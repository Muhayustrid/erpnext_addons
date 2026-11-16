"""Custom fields for buying, created from code like the intercompany ones."""

REQUESTED_BY = "custom_requested_by"


def field_defs():
	return [
		{
			"fieldname": REQUESTED_BY,
			"fieldtype": "Data",
			"label": "Requested By",
			"read_only": 1,
			"no_copy": 1,
			"insert_after": "title",
		}
	]


def ensure_fields():
	from frappe.custom.doctype.custom_field.custom_field import create_custom_fields

	create_custom_fields({"Material Request": field_defs()}, update=True)
