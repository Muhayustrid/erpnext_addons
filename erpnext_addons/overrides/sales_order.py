"""Reject a Sales Order while its stock items are not fully available.

The guard is opt-in through a Stock Settings checkbox created by `ensure_fields`.
Stock is checked per item and source warehouse against `Bin.actual_qty`; rows
delivered by the supplier are skipped.
"""

import frappe

TOGGLE = "custom_block_so_insufficient_stock"
# Bin and Sales Order Item quantities are DECIMAL(21,9).
PRECISION = 9


def field_defs():
	return [
		{
			"fieldname": TOGGLE,
			"fieldtype": "Check",
			"label": "Block Sales Order if Stock is Insufficient",
			"default": "0",
			"insert_after": "allow_negative_stock",
			"description": (
				"Reject saving a Sales Order when an item's available stock is less "
				"than the ordered stock quantity."
			),
		}
	]


def ensure_fields():
	from frappe.custom.doctype.custom_field.custom_field import create_custom_fields

	create_custom_fields({"Stock Settings": field_defs()}, update=True)


def validate(doc, method=None):
	if not _enabled():
		return

	for (item_code, warehouse), demand in _needed_by_item(doc).items():
		if warehouse and _checked(frappe.get_cached_value("Warehouse", warehouse, "is_group")):
			frappe.throw(
				f"Row #{demand['idx']}: warehouse {warehouse} is a group warehouse; "
				"choose a child warehouse."
			)
		available = _available_qty(item_code, warehouse)
		if demand["qty"] > available:
			frappe.throw(
				f"Row #{demand['idx']}: {item_code} has {available} in stock at "
				f"warehouse {warehouse}, but the order needs {demand['qty']}."
			)


def _enabled():
	# The field is created on install/migrate; until then treat the guard as
	# disabled instead of failing every Sales Order.
	if not frappe.get_meta("Stock Settings").has_field(TOGGLE):
		return False
	return bool(frappe.db.get_single_value("Stock Settings", TOGGLE))


def _needed_by_item(doc):
	needed = {}
	for item in doc.get("items") or []:
		if _checked(item.get("delivered_by_supplier")):
			continue
		if not _is_stock_item(item):
			continue
		qty = _qty(item.get("stock_qty")) or _qty(item.get("qty"))
		if qty <= 0:
			continue
		key = (item.get("item_code"), item.get("warehouse"))
		demand = needed.setdefault(key, {"qty": 0.0, "idx": item.get("idx")})
		demand["qty"] = _qty(demand["qty"] + qty)
	return needed


def _is_stock_item(item):
	is_stock_item = item.get("is_stock_item")
	if is_stock_item is None:
		is_stock_item = frappe.get_cached_value("Item", item.get("item_code"), "is_stock_item")
	return _checked(is_stock_item)


def _available_qty(item_code, warehouse):
	# shortcut: physical Bin.actual_qty only; open Sales Orders, Stock Reservation
	# reservations and product-bundle components are not subtracted. Revisit when needed.
	return _qty(_bin_details(item_code, warehouse).get("actual_qty"))


def _bin_details(item_code, warehouse):
	from erpnext.stock.get_item_details import get_bin_details

	return get_bin_details(item_code, warehouse)


def _checked(value):
	# Check fields may arrive as "0"/"1" strings from the API.
	return bool(int(float(value or 0)))


def _qty(value):
	return round(float(value or 0), PRECISION)
