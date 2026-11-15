"""Discover an intercompany chain through native links and write its progress to every member.

A chain is every submitted intercompany PO/SO/DN/PR/SI/PI (returns included) reachable
from a trigger document. There is no hub: all members get the same values. Runs without
permission checks; only the progress fields are written.
"""

import frappe

from erpnext_addons.intercompany.progress import FIELDS, compute

MAX_MEMBERS = 500

INTERNAL_FLAG = {
	"Purchase Order": "is_internal_supplier",
	"Sales Order": "is_internal_customer",
	"Delivery Note": "is_internal_customer",
	"Purchase Receipt": "is_internal_supplier",
	"Sales Invoice": "is_internal_customer",
	"Purchase Invoice": "is_internal_supplier",
}
DOCTYPES = tuple(INTERNAL_FLAG)
WITH_RETURNS = ("Delivery Note", "Purchase Receipt", "Sales Invoice", "Purchase Invoice")

# (doctype, child table or None for header, link field, linked doctype)
LINKS = (
	("Sales Order", "Sales Order Item", "purchase_order", "Purchase Order"),
	("Sales Order", None, "inter_company_order_reference", "Purchase Order"),
	("Purchase Order", None, "inter_company_order_reference", "Sales Order"),
	("Purchase Order", "Purchase Order Item", "sales_order", "Sales Order"),
	("Delivery Note", "Delivery Note Item", "against_sales_order", "Sales Order"),
	("Delivery Note", "Delivery Note Item", "against_sales_invoice", "Sales Invoice"),
	("Delivery Note", "Delivery Note Item", "purchase_order", "Purchase Order"),
	("Purchase Receipt", None, "inter_company_reference", "Delivery Note"),
	("Purchase Receipt", "Purchase Receipt Item", "purchase_order", "Purchase Order"),
	("Purchase Receipt", "Purchase Receipt Item", "sales_order", "Sales Order"),
	("Purchase Receipt", "Purchase Receipt Item", "purchase_invoice", "Purchase Invoice"),
	("Sales Invoice", "Sales Invoice Item", "sales_order", "Sales Order"),
	("Sales Invoice", "Sales Invoice Item", "delivery_note", "Delivery Note"),
	("Sales Invoice", "Sales Invoice Item", "purchase_order", "Purchase Order"),
	("Sales Invoice", None, "inter_company_invoice_reference", "Purchase Invoice"),
	("Purchase Invoice", None, "inter_company_invoice_reference", "Sales Invoice"),
	("Purchase Invoice", "Purchase Invoice Item", "purchase_order", "Purchase Order"),
	("Purchase Invoice", "Purchase Invoice Item", "purchase_receipt", "Purchase Receipt"),
) + tuple((dt, None, "return_against", dt) for dt in WITH_RETURNS)

# item table, qty field and the key it feeds in progress.compute
QTY_SOURCE = {
	"Purchase Order": ("Purchase Order Item", "stock_qty", "po"),
	"Sales Order": ("Sales Order Item", "stock_qty", "so"),
	"Delivery Note": ("Delivery Note Item", "stock_qty", "dn"),
	"Purchase Receipt": ("Purchase Receipt Item", "received_stock_qty", "pr"),
	"Sales Invoice": ("Sales Invoice Item", "stock_qty", "si"),
	"Purchase Invoice": ("Purchase Invoice Item", "stock_qty", "pi"),
}

EMPTY = {f: 0 for f in FIELDS[:-1]} | {"custom_ic_next_step": ""}


def is_intercompany(doc):
	flag = INTERNAL_FLAG.get(doc.doctype)
	return bool(flag and doc.get(flag))


def neighbours(doctype, name):
	"""Linked documents in both directions, submitted ones only (the start may be cancelled)."""
	found = set()
	for src, child, field, target in LINKS:
		if src == doctype:
			table, key = (child, "parent") if child else (src, "name")
			for value in frappe.get_all(table, filters={key: name}, pluck=field, distinct=True):
				if value:
					found.add((target, value))
		if target == doctype:
			table, key = (child, "parent") if child else (src, "name")
			for value in frappe.get_all(
				table, filters={field: name, "docstatus": 1}, pluck=key, distinct=True
			):
				found.add((src, value))
	found.discard((doctype, name))
	return found


def _member(doctype, name):
	"""Header row when the document is a submitted intercompany member, else None."""
	fields = ["docstatus", "status", INTERNAL_FLAG[doctype]] + (["is_return"] if doctype in WITH_RETURNS else [])
	row = frappe.db.get_value(doctype, name, fields, as_dict=True)
	if row and row.docstatus == 1 and row.get(INTERNAL_FLAG[doctype]):
		return row
	return None


def find_chain(doctype, name, seen=None):
	"""Map of (doctype, name) -> header row for every member reachable from the start.

	Returns None when the chain exceeds MAX_MEMBERS (logged, nothing should be written).
	`seen` receives every visited node, so a batch can skip an oversized chain afterwards.
	"""
	members, queue = {}, [(doctype, name)]
	seen = set() if seen is None else seen
	seen.add((doctype, name))
	while queue:
		current = queue.pop()
		row = _member(*current)
		if row is None and current != (doctype, name):
			continue
		if row is not None:
			members[current] = row
			if len(members) > MAX_MEMBERS:
				frappe.log_error(
					title="Intercompany progress: chain too large",
					message=f"{doctype} {name}: more than {MAX_MEMBERS} members, progress not updated",
				)
				return None
		for nxt in neighbours(*current):
			if nxt not in seen and nxt[0] in INTERNAL_FLAG:
				seen.add(nxt)
				queue.append(nxt)
	return members


# a Closed order only still requires what it already fulfilled (native qty is in transaction UOM)
CLOSED_REQUIREMENT = {
	"Sales Order": ("delivered_qty", "sod"),
	"Purchase Order": ("received_qty", "por"),
}
AMOUNT_KEY = {"Sales Invoice": "si_amt", "Purchase Invoice": "pi_amt"}


def aggregate(members):
	"""Per item code: net stock qty, required qty after Close, and invoice net amount.

	Returns (qty, closed) for progress.compute; `closed` is True when any PO/SO is Closed.
	"""
	qty, closed = {}, False
	for (doctype, name), row in members.items():
		table, field, key = QTY_SOURCE[doctype]
		fields = ["item_code", field]
		required = CLOSED_REQUIREMENT.get(doctype)
		if required:
			fields += [required[0], "conversion_factor"]
		if doctype in AMOUNT_KEY:
			fields.append("net_amount")
		is_closed = row.status == "Closed" and required is not None
		closed = closed or is_closed
		for item in frappe.get_all(table, filters={"parent": name}, fields=fields):
			value = float(item.get(field) or 0)
			bucket = qty.setdefault(item.item_code, {})
			bucket[key] = bucket.get(key, 0) + value
			if row.get("is_return"):
				bucket[f"{key}_ret"] = bucket.get(f"{key}_ret", 0) + abs(value)
			if required:
				done = float(item.get(required[0]) or 0) * float(item.get("conversion_factor") or 1)
				need = min(done, value) if is_closed else value
				bucket[required[1]] = bucket.get(required[1], 0) + need
			if doctype in AMOUNT_KEY:
				amt = AMOUNT_KEY[doctype]
				bucket[amt] = bucket.get(amt, 0) + float(item.get("net_amount") or 0)
	return qty, closed


def _norm(field, value):
	return (value or "") if field == "custom_ic_next_step" else int(value or 0)


def _write(doctype, name, values):
	current = frappe.db.get_value(doctype, name, list(values), as_dict=True) or {}
	changed = {k: v for k, v in values.items() if _norm(k, current.get(k)) != v}
	if changed:
		frappe.db.set_value(doctype, name, changed, update_modified=False)


def refresh_chain(doctype, name, done=None):
	"""Recompute and write the chain containing doctype/name.

	`done` collects members already written in this run so a batch (flush, backfill) does not
	recompute the same chain twice. A cancelled start gets "Cancelled" and its former
	neighbours are refreshed instead.
	"""
	done = set() if done is None else done
	if (doctype, name) in done:
		return
	if frappe.db.get_value(doctype, name, "docstatus") == 2:
		done.add((doctype, name))
		_write(doctype, name, EMPTY | {"custom_ic_next_step": "Cancelled"})
		for nxt in neighbours(doctype, name):
			if nxt[0] in INTERNAL_FLAG:
				refresh_chain(*nxt, done=done)
		return

	seen = set()
	members = find_chain(doctype, name, seen=seen)
	if not members:
		done.update(seen)  # oversized or empty: do not walk it again from another member
		return
	done.update(members)
	values = compute(*aggregate(members))
	for dt, dn in members:
		_write(dt, dn, values)
