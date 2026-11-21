"""% Paid on Purchase Order and Purchase Receipt.

Paid share of the linked submitted Purchase Invoices, weighted by item amount like
the native `per_billed`. Stored in a Percent field so the list view draws its bar.
"""

import frappe

FIELD = "custom_per_paid"
TARGETS = {"Purchase Order": "purchase_order", "Purchase Receipt": "purchase_receipt"}
QUEUE = "per_paid_queue"
JOB = "erpnext_addons.buying.paid.process"


def field_defs():
	percent_field = {
		"fieldname": FIELD,
		"fieldtype": "Percent",
		"label": "% Paid",
		"read_only": 1,
		"no_copy": 1,
		"allow_on_submit": 1,
		"in_list_view": 1,
		"insert_after": "per_billed",
	}
	# Payment Entry has no tabs, so its Connections cards sit above the first field;
	# a trailing tab with show_dashboard moves them out of the way.
	tab = {
		"fieldname": "custom_connections_tab",
		"fieldtype": "Tab Break",
		"label": "Connections",
		"show_dashboard": 1,
		"insert_after": "auto_repeat",
	}
	return {
		"Purchase Order": [dict(percent_field)],
		"Purchase Receipt": [dict(percent_field)],
		"Payment Entry": [tab],
	}


def ensure_fields():
	from frappe.custom.doctype.custom_field.custom_field import create_custom_fields

	create_custom_fields(field_defs(), update=True)


def _add(doctype, name):
	queue = frappe.flags.get(QUEUE)
	if queue is None:
		queue = frappe.flags[QUEUE] = []
		frappe.db.after_commit.add(_enqueue)
		# a rolled back request must not leave a stale queue for the next transaction
		frappe.db.after_rollback.add(lambda: frappe.flags.pop(QUEUE, None))
	if [doctype, name] not in queue:
		queue.append([doctype, name])


def _enqueue():
	docs = frappe.flags.pop(QUEUE, None)
	if docs:
		frappe.enqueue(JOB, queue="short", docs=docs)


def _add_items(items):
	po_lines = []
	for item in items:
		for doctype, link in TARGETS.items():
			if item.get(link):
				_add(doctype, item.get(link))
		if item.get("po_detail") and not item.get("purchase_receipt"):
			po_lines.append(item.get("po_detail"))
	# an invoice billed against the PO line also bills the receipts of that line
	if po_lines:
		for receipt in frappe.get_all(
			"Purchase Receipt Item",
			filters={"purchase_order_item": ["in", po_lines], "docstatus": 1},
			pluck="parent",
			distinct=True,
		):
			_add("Purchase Receipt", receipt)


def on_invoice_change(doc, method=None):
	_add_items(doc.get("items") or [])


def on_payment_change(doc, method=None):
	"""Payment Entry / Journal Entry: follow their Purchase Invoice references."""
	if doc.doctype == "Journal Entry":
		refs = [(r.get("reference_type"), r.get("reference_name")) for r in doc.get("accounts") or []]
	else:
		refs = [(r.get("reference_doctype"), r.get("reference_name")) for r in doc.get("references") or []]
	invoices = list(dict.fromkeys(name for doctype, name in refs if doctype == "Purchase Invoice" and name))
	if invoices:
		_add_items(
			frappe.get_all(
				"Purchase Invoice Item",
				filters={"parent": ["in", invoices]},
				fields=[*TARGETS.values(), "po_detail"],
			)
		)


def process(docs):
	"""Background job queued after the business commit."""
	grouped = {}
	for doctype, name in docs:
		grouped.setdefault(doctype, []).append(name)
	for doctype, names in grouped.items():
		refresh(doctype, names)
	frappe.db.commit()


def daily():
	"""Safety net for paths that change outstanding without these events (e.g. reconciliation)."""
	for doctype in TARGETS:
		# no "< 100" filter: an unreconciled payment can push a 100% target back down
		names = frappe.get_all(doctype, filters={"docstatus": 1, "per_billed": [">", 0]}, pluck="name")
		refresh(doctype, names)
	frappe.db.commit()


def guard(doc, method=None):
	"""Keep % Paid system-owned: revert values coming from form, API or import."""
	if not doc.meta.has_field(FIELD):
		return
	saved = 0 if doc.is_new() else frappe.db.get_value(doc.doctype, doc.name, FIELD)
	doc.set(FIELD, saved or 0)


def invoice_ratio(total, outstanding):
	total = float(total or 0)
	if total <= 0:
		return 0
	return min(max((total - float(outstanding or 0)) / total, 0), 1)


def percent(amounts, target_total):
	target_total = float(target_total or 0)
	if target_total <= 0:
		return 0
	paid = sum(float(amount or 0) * ratio for amount, ratio in amounts)
	return round(min(max(paid / target_total * 100, 0), 100), 2)


def receipt_percent(items, target_total):
	"""items: (billed_amt, [(PI item amount, PI ratio), ...]) per PR item.

	ERPNext often bills a PR through its PO line, so the PR's billed amount comes from
	`billed_amt` and is weighted by the paid ratio of the invoice lines billing it.
	"""
	paid = 0
	for billed_amt, invoices in items:
		invoiced = sum(float(amount or 0) for amount, _ in invoices)
		if invoiced > 0:
			paid += float(billed_amt or 0) * sum(float(a or 0) * r for a, r in invoices) / invoiced
	return percent([(paid, 1)], target_total)


# outstanding_amount is in the payable account currency; compare it with totals in that currency
_INV_TOTAL = """if(pi.party_account_currency != pi.currency,
				if(pi.disable_rounded_total = 1 or ifnull(pi.base_rounded_total, 0) = 0,
					pi.base_grand_total, pi.base_rounded_total),
				if(pi.disable_rounded_total = 1 or ifnull(pi.rounded_total, 0) = 0,
					pi.grand_total, pi.rounded_total)) as inv_total,
			pi.outstanding_amount as outstanding"""

# LEFT JOINs keep targets without invoices so they reset to 0
_ORDER_SQL = f"""
		select t.name, t.total, pii.amount, {_INV_TOTAL}
		from `tabPurchase Order` t
		left join `tabPurchase Invoice Item` pii on pii.purchase_order = t.name
		left join `tabPurchase Invoice` pi on pi.name = pii.parent
			and pi.docstatus = 1 and pi.is_return = 0
		where t.name in %(names)s
		"""

# shortcut: several receipts on one PO line share that line's blended paid ratio when the
# invoice is billed against the PO line; exact per-receipt allocation would need ERPNext's
# billed_amt split logic.
_RECEIPT_SQL = f"""
		select t.name, t.total, pri.name as item, pri.billed_amt, pii.amount, {_INV_TOTAL}
		from `tabPurchase Receipt` t
		join `tabPurchase Receipt Item` pri on pri.parent = t.name
		left join `tabPurchase Invoice Item` pii on (
			pii.pr_detail = pri.name
			or (
				ifnull(pri.purchase_order_item, '') != ''
				and pii.po_detail = pri.purchase_order_item
				and ifnull(pii.purchase_receipt, '') = ''
			)
		)
		left join `tabPurchase Invoice` pi on pi.name = pii.parent
			and pi.docstatus = 1 and pi.is_return = 0
			and (pii.pr_detail = pri.name or pi.update_stock = 0)
		where t.name in %(names)s
		"""


def _ratio(row):
	return invoice_ratio(row["inv_total"], row["outstanding"])


def refresh(doctype, names):
	names = list(dict.fromkeys(n for n in names if n))
	if not names:
		return
	receipt = doctype == "Purchase Receipt"
	rows = frappe.db.sql(_RECEIPT_SQL if receipt else _ORDER_SQL, {"names": names}, as_dict=True)

	values = {}
	if receipt:
		per_target = {}
		for row in rows:
			total, items = per_target.setdefault(row["name"], (row["total"], {}))
			_, invoices = items.setdefault(row["item"], (row["billed_amt"], []))
			if row.get("inv_total") is not None:
				invoices.append((row["amount"], _ratio(row)))
		for name, (total, items) in per_target.items():
			values[name] = receipt_percent(items.values(), total)
	else:
		per_target = {}
		for row in rows:
			total, amounts = per_target.setdefault(row["name"], (row["total"], []))
			if row.get("inv_total") is not None:
				amounts.append((row["amount"], _ratio(row)))
		for name, (total, amounts) in per_target.items():
			values[name] = percent(amounts, total)

	for name, value in values.items():
		if float(frappe.db.get_value(doctype, name, FIELD) or 0) != value:
			frappe.db.set_value(doctype, name, FIELD, value, update_modified=False)
