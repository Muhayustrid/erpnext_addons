"""Native Connections cards for links stored on the current document.

The dashboard counts links by looking for the current document's name in the
target doctype. These links point the other way (the current document or its
items hold the reference), so their names are collected here and returned in
the shape the dashboard expects.
"""

import frappe

# linked doctype config per source doctype.
# `fields` is a header field, a (child table, field) tuple, or "references"
# for Payment Entry's reference table filtered by reference_doctype.
LINKS = {
	"Purchase Receipt": {
		"Delivery Note": {"group": "Related", "fields": ("inter_company_reference",)},
	},
	"Purchase Order": {
		"Sales Order": {
			"group": "Related",
			"fields": ("inter_company_order_reference", ("items", "sales_order")),
		},
	},
	"Purchase Invoice": {
		"Sales Invoice": {"group": "Reference", "fields": ("inter_company_invoice_reference",)},
	},
	"Stock Entry": {
		"Work Order": {"group": "Related", "fields": ("work_order",)},
		"Job Card": {"group": "Related", "fields": ("job_card",)},
		"Pick List": {"group": "Related", "fields": ("pick_list",)},
		"Material Request": {"group": "Related", "fields": (("items", "material_request"),)},
		"Quality Inspection": {"group": "Related", "fields": (("items", "quality_inspection"),)},
		"BOM": {"group": "Reference", "fields": ("bom_no", ("items", "bom_no"))},
		"Project": {"group": "Reference", "fields": ("project", ("items", "project"))},
		"Asset Repair": {"group": "Reference", "fields": ("asset_repair",)},
		"Stock Entry": {
			"group": "Transactions",
			"fields": (
				"source_stock_entry",
				"outgoing_stock_entry",
				"amended_from",
				("items", "against_stock_entry"),
			),
		},
		"Purchase Order": {"group": "Transactions", "fields": ("purchase_order",)},
		"Subcontracting Order": {"group": "Transactions", "fields": ("subcontracting_order",)},
		"Subcontracting Inward Order": {
			"group": "Transactions",
			"fields": ("subcontracting_inward_order",),
		},
		"Purchase Receipt": {
			"group": "Transactions",
			"fields": ("purchase_receipt_no", ("items", "reference_purchase_receipt")),
		},
		"Delivery Note": {"group": "Transactions", "fields": ("delivery_note_no",)},
		"Sales Invoice": {"group": "Transactions", "fields": ("sales_invoice_no",)},
		"Journal Entry": {"group": "Accounting", "fields": ("credit_note",)},
	},
	"Payment Entry": {
		"Sales Invoice": {"group": "Related", "fields": "references"},
		"Purchase Invoice": {"group": "Related", "fields": "references"},
		"Sales Order": {"group": "Related", "fields": "references"},
		"Purchase Order": {"group": "Related", "fields": "references"},
		"Journal Entry": {"group": "Related", "fields": "references"},
	},
}


def purchase_receipt(data):
	return _add_links(data, "Purchase Receipt")


def purchase_order(data):
	return _add_links(data, "Purchase Order")


def purchase_invoice(data):
	return _add_links(data, "Purchase Invoice")


def stock_entry(data):
	return _add_links(data, "Stock Entry")


def payment_entry(data):
	return _add_links(data, "Payment Entry")


def _add_links(data, doctype):
	transactions = data.setdefault("transactions", [])
	internal_links = data.setdefault("internal_links", {})
	groups = {group.get("label"): group for group in transactions}

	for linked_doctype, config in LINKS[doctype].items():
		group = groups.get(config["group"])
		if group is None:
			group = {"label": config["group"], "items": []}
			transactions.append(group)
			groups[config["group"]] = group
		if linked_doctype not in group.setdefault("items", []):
			group["items"].append(linked_doctype)
		# a truthy internal link hides the "+" button, as for native connections
		internal_links.setdefault(linked_doctype, _sentinel(config["fields"]))

	data["method"] = "erpnext_addons.dashboards.get_open_count"
	# Payment Entry has no native dashboard fieldname; the client still needs one
	# to fetch counts. Custom cards resolve their names through internal_links_found.
	data.setdefault("fieldname", "name")
	return data


def _sentinel(fields):
	return ("references", "reference_name") if fields == "references" else fields[0]


@frappe.whitelist()
@frappe.read_only()
def get_open_count(doctype, name, items=None):
	"""Dashboard counts: custom forward links plus the native ones."""
	doc = frappe.get_lazy_doc(doctype, name, check_permission=True)
	if isinstance(items, str):
		items = frappe.parse_json(items)
	links = LINKS.get(doctype, {})
	custom = [item for item in items or [] if item in links]
	native = [item for item in items or [] if item not in links]

	out = _native_open_count(doctype, name, native)
	count = out.get("count")
	if not isinstance(count, dict):
		count = {"internal_links_found": [], "external_links_found": []}
		out["count"] = count
	count.setdefault("internal_links_found", [])
	count.setdefault("external_links_found", [])

	for linked_doctype in custom:
		names = _names(doc, linked_doctype, links[linked_doctype]["fields"])
		count["internal_links_found"].append(
			{
				"doctype": linked_doctype,
				"open_count": 0,
				"count": len(names),
				"names": names,
			}
		)

	return out


def _names(doc, linked_doctype, fields):
	if fields == "references":
		values = [
			row.get("reference_name")
			for row in doc.get("references") or []
			if row.get("reference_doctype") == linked_doctype
		]
	else:
		values = []
		for field in fields:
			if isinstance(field, tuple):
				table, fieldname = field
				values.extend(row.get(fieldname) for row in doc.get(table) or [])
			else:
				values.append(doc.get(field))
	return list(dict.fromkeys(value for value in values if value))


def _native_open_count(doctype, name, items):
	if not items:
		return {"count": {"internal_links_found": [], "external_links_found": []}}
	from frappe.desk import notifications

	return notifications.get_open_count(doctype, name, items)
