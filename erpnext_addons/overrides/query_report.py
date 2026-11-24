"""Add the P&L percentage column through the query report API.

`run` post-processes the normal report response and `get_script` injects the
`Show Percentage` filter. `patch` rebinds the module-level `run` so internal
callers (Excel export, prepared reports) also get the column.
"""

import frappe
from frappe.desk import query_report as _query_report

from erpnext_addons.overrides import percentage

# captured at import time, before `patch` replaces the module attribute
_original_run = _query_report.run
_original_get_script = _query_report.get_script

_patched = False

SHOW_PERCENTAGE_FILTER_JS = """
// injected by erpnext_addons
(function () {
	const report_name = "Profit and Loss Statement";
	const settings = frappe.query_reports && frappe.query_reports[report_name];
	if (!settings) return;

	settings.filters = settings.filters || [];
	if (!settings.filters.some((filter) => filter.fieldname === "show_percentage")) {
		settings.filters.push({
			fieldname: "show_percentage",
			label: __("Show Percentage"),
			fieldtype: "Check",
			default: 1,
		});
	}
})();
"""


@frappe.whitelist()
@frappe.read_only()
def run(*args, **kwargs):
	response = _original_run(*args, **kwargs)

	report_name = kwargs.get("report_name") or (args[0] if args else None)
	if report_name not in percentage.SUPPORTED_REPORTS:
		return response

	filters = kwargs.get("filters")
	if filters is None and len(args) > 1:
		filters = args[1]

	if not percentage.is_enabled(filters):
		return response

	return percentage.add_percentage_column(response)


@frappe.whitelist()
@frappe.read_only()
def get_script(report_name):
	response = _original_get_script(report_name)
	if report_name in percentage.SUPPORTED_REPORTS and isinstance(response, dict):
		response["script"] = (response.get("script") or "") + SHOW_PERCENTAGE_FILTER_JS
	return response


def patch(**kwargs):
	"""Idempotent; called from the `before_request` / `before_job` hooks."""
	global _patched
	if _patched:
		return

	_query_report.run = run
	_patched = True
