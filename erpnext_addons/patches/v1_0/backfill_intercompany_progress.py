import json

import frappe

from erpnext_addons.intercompany.chain import DOCTYPES, INTERNAL_FLAG, refresh_chain
from erpnext_addons.intercompany.setup import ensure_fields

COLUMN = {"fieldname": "custom_ic_next_step", "label": "Next Step"}


def execute():
	"""Create the fields, compute every existing intercompany chain once, add the list column."""
	ensure_fields()
	done = set()
	for doctype in DOCTYPES:
		names = frappe.get_all(doctype, filters={"docstatus": 1, INTERNAL_FLAG[doctype]: 1}, pluck="name")
		for name in names:
			refresh_chain(doctype, name, done=done)
	add_list_column()


def add_list_column():
	"""One-time: show Next Step after Status in existing List View Settings; later removal is respected."""
	for doctype in DOCTYPES:
		raw = frappe.db.get_value("List View Settings", doctype, "fields")
		if not raw:
			continue
		fields = json.loads(raw)
		if any(f.get("fieldname") == COLUMN["fieldname"] for f in fields):
			continue
		at = next((i + 1 for i, f in enumerate(fields) if f.get("fieldname") == "status_field"), len(fields))
		fields.insert(at, COLUMN)
		frappe.db.set_value("List View Settings", doctype, "fields", json.dumps(fields))
		frappe.clear_document_cache("List View Settings", doctype)
