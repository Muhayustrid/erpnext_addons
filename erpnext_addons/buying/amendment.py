"""Amend a submitted Purchase Order so it also covers new Material Requests.

The guard keeps the automatic flow away from Purchase Orders that already have
receipts, invoices or an amendment; those are amended by hand.
"""

import frappe


def amend_blocker(po) -> str | None:
	if po.docstatus != 1:
		return "Purchase Order ini belum submitted, jadi belum bisa di-amend."
	if po.inter_company_order_reference:
		return "Purchase Order intercompany tidak bisa di-amend."
	return None


def assert_can_amend(po) -> None:
	blocker = amend_blocker(po)
	if blocker:
		frappe.throw(blocker, frappe.ValidationError)

	for item_doctype, label in (
		("Purchase Receipt Item", "Purchase Receipt"),
		("Purchase Invoice Item", "Purchase Invoice"),
	):
		for docstatus, state in ((1, "submitted"), (0, "draft")):
			if frappe.db.exists(item_doctype, {"purchase_order": po.name, "docstatus": docstatus}):
				frappe.throw(
					f"Purchase Order ini sudah punya {label} {state}, jadi tidak bisa di-amend.",
					frappe.ValidationError,
				)

	if frappe.db.exists("Purchase Order", {"amended_from": po.name}):
		frappe.throw("Purchase Order ini sudah pernah di-amend.", frappe.ValidationError)


def unique_material_requests(values) -> list[str]:
	unique = []
	for value in values:
		if value and value not in unique:
			unique.append(value)
	return unique


def assert_new_material_requests(po, material_requests) -> None:
	on_po = {row.material_request for row in po.get("items") or [] if row.material_request}
	repeated = [mr for mr in material_requests if mr in on_po]
	if repeated:
		frappe.throw(
			f"Material Request berikut sudah ada di Purchase Order ini: {', '.join(repeated)}.",
			frappe.ValidationError,
		)


@frappe.whitelist(methods=["POST"])
def create_amendment_for_material_request(name: str, material_requests: str) -> str:
	po = frappe.get_doc("Purchase Order", name)
	assert_can_amend(po)

	requests = unique_material_requests(frappe.parse_json(material_requests))
	if not requests:
		frappe.throw("Pilih minimal satu Material Request.", frappe.ValidationError)
	assert_new_material_requests(po, requests)

	# imported here: erpnext is absent in the host unit tests
	from erpnext.stock.doctype.material_request.material_request import make_purchase_order

	po.cancel()
	new = frappe.copy_doc(po)
	new.amended_from = po.name
	for mr in requests:
		new = make_purchase_order(mr, target_doc=new)
	new.insert()
	return new.name
