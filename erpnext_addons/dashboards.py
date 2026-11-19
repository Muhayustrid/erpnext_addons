"""Native Connections cards for intercompany chains.

The native dashboard counts links by looking for the current document's name in
the target doctype. These links mostly point the other way, and Delivery Note /
Sales Invoice are only reachable through the chain, so their names are
collected here and returned in the shape the dashboard expects.
"""

import frappe

GROUP = "Dokumen Terkait"
CHAIN_DOCTYPES = (
	"Purchase Order",
	"Sales Order",
	"Delivery Note",
	"Purchase Receipt",
	"Sales Invoice",
	"Purchase Invoice",
)
PAYMENT_ENTRY = "Payment Entry"

# Non-chain doctypes keep their own card groups.
LINKS = {
	"Stock Entry": {
		"Work Order": {"group": GROUP, "fields": ("work_order",)},
		"Job Card": {"group": GROUP, "fields": ("job_card",)},
		"Pick List": {"group": GROUP, "fields": ("pick_list",)},
		"Material Request": {"group": GROUP, "fields": (("items", "material_request"),)},
		"Quality Inspection": {"group": GROUP, "fields": (("items", "quality_inspection"),)},
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
		"Sales Invoice": {"group": GROUP, "fields": "references"},
		"Purchase Invoice": {"group": GROUP, "fields": "references"},
		"Sales Order": {"group": GROUP, "fields": "references"},
		"Purchase Order": {"group": GROUP, "fields": "references"},
		"Journal Entry": {"group": GROUP, "fields": "references"},
	},
}


def purchase_order(data):
	return _add_chain_group(data, "Purchase Order")


def sales_order(data):
	return _add_chain_group(data, "Sales Order")


def delivery_note(data):
	return _add_chain_group(data, "Delivery Note")


def purchase_receipt(data):
	return _add_chain_group(data, "Purchase Receipt")


def sales_invoice(data):
	return _add_chain_group(data, "Sales Invoice")


def purchase_invoice(data):
	return _add_chain_group(data, "Purchase Invoice")


def stock_entry(data):
	return _add_link_groups(data, "Stock Entry")


def payment_entry(data):
	return _add_link_groups(data, "Payment Entry")


def _add_chain_group(data, doctype):
	"""One native group with the other chain doctypes, without duplicates elsewhere."""
	transactions = data.setdefault("transactions", [])
	internal_links = data.setdefault("internal_links", {})
	if any(group.get("label") == GROUP for group in transactions):
		return data

	items = [chain_doctype for chain_doctype in CHAIN_DOCTYPES if chain_doctype != doctype]
	items.append(PAYMENT_ENTRY)
	transactions.insert(0, {"label": GROUP, "items": items})
	for item in items:
		# a truthy internal link hides the "+" button, as for native connections
		internal_links[item] = True

	remaining = []
	for group in transactions[1:]:
		group["items"] = [item for item in group.get("items", []) if item not in items]
		if group["items"]:
			remaining.append(group)
	transactions[1:] = remaining

	data["method"] = "erpnext_addons.dashboards.get_open_count"
	data.setdefault("fieldname", "name")
	return data


def _add_link_groups(data, doctype):
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
	"""Dashboard counts: chain/custom links plus the native ones."""
	if isinstance(items, str):
		items = frappe.parse_json(items)
	items = list(items or [])

	doc = frappe.get_lazy_doc(doctype, name, check_permission=True)
	custom = _custom_names(doc, doctype, name, items)
	native_items = [item for item in items if item not in custom]

	out = _native_open_count(doctype, name, native_items)
	count = out.get("count")
	if not isinstance(count, dict):
		count = {"internal_links_found": [], "external_links_found": []}
		out["count"] = count
	count.setdefault("internal_links_found", [])
	count.setdefault("external_links_found", [])

	for linked_doctype in items:
		if linked_doctype not in custom:
			continue
		names = custom[linked_doctype]
		count["internal_links_found"].append(
			{
				"doctype": linked_doctype,
				"open_count": 0,
				"count": len(names),
				"names": names,
			}
		)

	return out


def _custom_names(doc, doctype, name, items):
	if doctype in CHAIN_DOCTYPES:
		members = _chain_members(doctype, name)
		grouped = _direct_names(doctype, name)
		for member_doctype, member_name in members:
			if (member_doctype, member_name) == (doctype, name):
				continue
			grouped.setdefault(member_doctype, set()).add(member_name)
		# a cancelled original is still related, and native counts include it
		for member_doctype, member_names in list(grouped.items()):
			revisions = frappe.get_all(
				member_doctype,
				filters={"name": ["in", list(member_names)]},
				fields=["amended_from"],
			)
			grouped[member_doctype].update(
				revision.amended_from for revision in revisions if revision.amended_from
			)

		names = {
			item: sorted(grouped.get(item, set()))
			for item in items
			if item in CHAIN_DOCTYPES and item != doctype
		}
		if PAYMENT_ENTRY in items:
			pairs = {(dt, dn) for dt, names in grouped.items() for dn in names}
			pairs.add((doctype, name))
			names[PAYMENT_ENTRY] = _payment_names(pairs)
		return names

	links = LINKS.get(doctype, {})
	return {
		item: _names(doc, item, links[item]["fields"])
		for item in items
		if item in links
	}


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


def _direct_names(doctype, name):
	"""Direct links in both directions, including drafts and cancelled docs."""
	from erpnext_addons.intercompany.chain import LINKS

	found = {}
	for src, child, field, target in LINKS:
		if src == doctype:
			table, key = (child, "parent") if child else (src, "name")
			for value in frappe.get_all(table, filters={key: name}, pluck=field, distinct=True):
				if value and not (target == doctype and value == name):
					found.setdefault(target, set()).add(value)
		if target == doctype:
			table, key = (child, "parent") if child else (src, "name")
			for value in frappe.get_all(table, filters={field: name}, pluck=key, distinct=True):
				if value and not (src == doctype and value == name):
					found.setdefault(src, set()).add(value)
	return found


def _chain_members(doctype, name):
	from erpnext_addons.intercompany.chain import find_chain

	return find_chain(doctype, name) or {}


def _payment_names(members):
	pairs = set(members)
	if not pairs:
		return []

	rows = frappe.get_all(
		"Payment Entry Reference",
		filters={
			"reference_doctype": ["in", sorted({doctype for doctype, _ in pairs})],
			"reference_name": ["in", sorted({name for _, name in pairs})],
		},
		fields=["parent", "reference_doctype", "reference_name"],
		distinct=True,
	)
	return sorted(
		{row.parent for row in rows if (row.reference_doctype, row.reference_name) in pairs}
	)


def _native_open_count(doctype, name, items):
	if not items:
		return {"count": {"internal_links_found": [], "external_links_found": []}}
	from frappe.desk import notifications

	return notifications.get_open_count(doctype, name, items)
