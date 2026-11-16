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
	if po.is_subcontracted:
		return "Purchase Order subkontrak tidak bisa ditambah MR lewat alur ini."
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

	for reference_doctype, label, filter_key in (
		("Payment Entry Reference", "Payment Entry", "reference_doctype"),
		("Journal Entry Account", "Journal Entry", "reference_type"),
	):
		reference_filter = {
			filter_key: "Purchase Order",
			"reference_name": po.name,
			"docstatus": 1,
		}
		if frappe.db.exists(reference_doctype, reference_filter):
			parent = frappe.db.get_value(reference_doctype, reference_filter, "parent")
			frappe.throw(
				f"Purchase Order ini sudah dipakai di {label} {parent} yang submitted, "
				"jadi tidak bisa di-amend.",
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


def parse_material_requests(value) -> list[str]:
	parsed = frappe.parse_json(value)
	if not isinstance(parsed, list):
		frappe.throw("Daftar Material Request tidak valid.", frappe.ValidationError)
	return unique_material_requests(parsed)


def material_request_blocker(mr, po) -> str | None:
	"""Return why this Material Request cannot be added to `po`, or None."""
	if not mr:
		return "Material Request tidak ditemukan."
	name = mr.get("name")
	if mr.get("material_request_type") != "Purchase":
		return f"Material Request {name} bukan bertipe Purchase."
	if mr.get("company") != po.company:
		return f"Material Request {name} berasal dari company lain, jadi tidak bisa ditambahkan."
	if mr.get("docstatus") != 1:
		return f"Material Request {name} belum submitted."
	if mr.get("status") == "Stopped":
		return f"Material Request {name} berstatus Stopped, jadi tidak bisa dipesan."
	if (mr.get("per_ordered") or 0) >= 100:
		return f"Material Request {name} sudah dipesan semuanya."
	return None


def assert_purchasable_material_requests(po, material_requests) -> None:
	for mr in material_requests:
		row = frappe.db.get_value(
			"Material Request",
			mr,
			["name", "material_request_type", "company", "docstatus", "status", "per_ordered"],
			as_dict=True,
		)
		blocker = material_request_blocker(dict(row) if row else None, po)
		if blocker:
			frappe.throw(blocker, frappe.ValidationError)


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

	requests = parse_material_requests(material_requests)
	if not requests:
		frappe.throw("Pilih minimal satu Material Request.", frappe.ValidationError)
	assert_new_material_requests(po, requests)
	assert_purchasable_material_requests(po, requests)

	# imported here: erpnext is absent in the host unit tests
	from erpnext.stock.doctype.material_request.material_request import make_purchase_order

	po.cancel()
	new = frappe.copy_doc(po)
	# copy_doc keeps docstatus when frappe.in_test is set, and the copy must be a draft
	new.docstatus = 0
	new.amended_from = po.name
	for mr in requests:
		new = make_purchase_order(mr, target_doc=new)
	new.insert()
	return new.name
