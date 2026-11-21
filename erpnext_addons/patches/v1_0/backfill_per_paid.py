import json

import frappe

from erpnext_addons.buying.paid import FIELD, TARGETS, ensure_fields, refresh

COLUMN = {"fieldname": FIELD, "label": "% Paid"}


def execute():
	"""Create the fields, compute % Paid once for every billed PO/PR, add the list column."""
	ensure_fields()
	for doctype in TARGETS:
		names = frappe.get_all(doctype, filters={"docstatus": 1, "per_billed": [">", 0]}, pluck="name")
		refresh(doctype, names)
	add_list_column()


def add_list_column():
	"""One-time: show % Paid after % Billed in existing List View Settings; later removal is respected."""
	for doctype in TARGETS:
		raw = frappe.db.get_value("List View Settings", doctype, "fields")
		if not raw:
			continue
		fields = json.loads(raw)
		if any(f.get("fieldname") == FIELD for f in fields):
			continue
		at = next((i + 1 for i, f in enumerate(fields) if f.get("fieldname") == "per_billed"), len(fields))
		fields.insert(at, COLUMN)
		frappe.db.set_value("List View Settings", doctype, "fields", json.dumps(fields))
		frappe.clear_document_cache("List View Settings", doctype)
