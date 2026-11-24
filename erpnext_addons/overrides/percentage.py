"""Percentage column for the Profit and Loss Statement.

Ported from the MIT-licensed `financial_report_percentage` app. The denominator
is the gross income (income leaves without cost accounts); report templates use
their first revenue section instead.
"""

import json
import math

SUPPORTED_REPORTS = ("Profit and Loss Statement",)
PERCENTAGE_FIELDNAME = "percentage"
PERCENTAGE_LABEL = "%"

# Account types that must not count towards the gross income (100%), even when
# the accounts sit below the income root (e.g. cost of goods sold accounts).
COST_ACCOUNT_TYPES = frozenset(
	{
		"Cost of Goods Sold",
		"Expenses Included In Valuation",
		"Expenses Included In Asset Valuation",
		"Stock Adjustment",
		"Stock Received But Not Billed",
		"Depreciation",
		"Expense Account",
	}
)


def _cint(value) -> int:
	try:
		return int(value)
	except (TypeError, ValueError):
		try:
			return int(float(value))
		except (TypeError, ValueError):
			return 0


def _rounded(num, precision=0):
	"""Match `frappe.utils.rounded` with its default legacy banker's rounding."""
	multiplier = 10**precision
	num = round(num * multiplier if precision else num, 8)
	floor_num = math.floor(num)
	decimal_part = num - floor_num

	if not precision and decimal_part == 0.5:
		num = floor_num if (floor_num % 2 == 0) else floor_num + 1
	else:
		if decimal_part == 0.5:
			num = floor_num + 1
		else:
			num = round(num)

	return (num / multiplier) if precision else num


def _flt(value, precision=None) -> float:
	if value is None:
		return 0.0
	if isinstance(value, str):
		value = value.replace(",", "")
	try:
		number = float(value)
		if precision is not None:
			number = _rounded(number, precision)
	except (TypeError, ValueError):
		number = 0.0
	return number


def is_enabled(filters) -> bool:
	"""`show_percentage` defaults to 1 so the column is shown unless explicitly unchecked."""
	return bool(_cint(as_dict(filters).get("show_percentage", 1)))


def as_dict(filters) -> dict:
	if not filters:
		return {}
	if isinstance(filters, str):
		try:
			filters = json.loads(filters)
		except (TypeError, ValueError):
			return {}
	return filters if isinstance(filters, dict) else {}


def get_value_fieldname(columns) -> str | None:
	"""Column the percentage is based on: `total` when present, else the last amount column."""
	fieldnames = [column.get("fieldname") for column in columns if isinstance(column, dict)]
	if "total" in fieldnames:
		return "total"

	for column in reversed(columns):
		if (
			isinstance(column, dict)
			and column.get("fieldname")
			and column.get("fieldtype") in ("Currency", "Float")
		):
			return column["fieldname"]

	return None


def is_classic_total_row(row) -> bool:
	"""Total rows appended by `erpnext.accounts.report.financial_statements.add_total_row`."""
	return isinstance(row, dict) and bool(row) and "opening_balance" in row and "parent_account" not in row


def is_template_section_row(row) -> bool:
	"""First account data row (indent 0) of a report built with a Report Template."""
	return (
		isinstance(row, dict)
		and bool(row)
		and bool(row.get("account_filters"))
		and _cint(row.get("indent")) == 0
		and not row.get("is_blank_line")
	)


def get_income_total(data, value_field) -> float | None:
	"""Total income for the column used as 100%."""
	rows = [row for row in data or [] if isinstance(row, dict) and row]
	if not rows:
		return None

	# report template engine: use the first revenue section
	if any(is_template_section_row(row) for row in rows):
		for row in rows:
			if is_template_section_row(row):
				return _flt(row.get(value_field))
		return None

	# classic report: the income section ends where the first total row
	# (appended by `add_total_row`) starts
	income_rows = []
	for row in rows:
		if is_classic_total_row(row):
			break
		income_rows.append(row)

	return get_gross_income_total(income_rows, value_field)


def is_cost_account(row) -> bool:
	return (row.get("account_type") or "") in COST_ACCOUNT_TYPES


def get_gross_income_total(income_rows, value_field) -> float | None:
	"""Sum of the income accounts (leaves), leaving cost accounts out.

	Charts of accounts that nest the cost of goods sold below the income root
	make ERPNext's own total income a net figure (revenue minus costs), so the
	percentage has to be based on the gross income instead.
	"""
	found_leaf = False
	income_total = 0.0

	for row in income_rows:
		if row.get("is_group") or row.get("is_blank_line"):
			continue
		found_leaf = True
		if is_cost_account(row):
			continue
		income_total += _flt(row.get(value_field))

	return income_total if found_leaf else None


def add_percentage_column(response: dict) -> dict:
	if not isinstance(response, dict):
		return response

	columns = response.get("columns") or []
	data = response.get("result") or []

	value_field = get_value_fieldname(columns)
	if not value_field:
		return response

	income_total = get_income_total(data, value_field)
	if not income_total:
		return response

	for row in data:
		if not isinstance(row, dict) or not row or row.get("is_blank_line"):
			continue
		row[PERCENTAGE_FIELDNAME] = _flt(_flt(row.get(value_field)) / income_total * 100, 2)

	if not any(
		isinstance(column, dict) and column.get("fieldname") == PERCENTAGE_FIELDNAME
		for column in columns
	):
		columns.append(
			{
				"fieldname": PERCENTAGE_FIELDNAME,
				"label": PERCENTAGE_LABEL,
				"fieldtype": "Percent",
				"width": 120,
			}
		)

	return response
