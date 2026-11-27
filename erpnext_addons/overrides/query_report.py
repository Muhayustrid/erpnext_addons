"""Add the P&L percentage columns through the query report API.

`run` post-processes the normal report response and `get_script` injects the
`Show Monthly Percentage` and `Show Total Percentage` filters. `patch` rebinds
the module-level `run` so internal callers (Excel export, prepared reports) also
get the columns.
"""

import frappe
from frappe.desk import query_report as _query_report

from erpnext_addons.overrides import percentage

# captured at import time, before `patch` replaces the module attribute
_original_run = _query_report.run
_original_get_script = _query_report.get_script

_patched = False

PERCENTAGE_FILTERS_JS = """
// injected by erpnext_addons
(function () {
	const report_name = "Profit and Loss Statement";
	const settings = frappe.query_reports && frappe.query_reports[report_name];
	if (!settings) return;

	settings.filters = settings.filters || [];
	const percentage_filters = [
		{
			fieldname: "show_monthly_percentage",
			label: __("Show Monthly Percentage"),
			fieldtype: "Check",
			default: 1,
			depends_on: "eval:doc.periodicity == 'Monthly'",
		},
		{
			fieldname: "show_total_percentage",
			label: __("Show Total Percentage"),
			fieldtype: "Check",
			default: 1,
		},
	];
	percentage_filters.forEach((filter) => {
		if (!settings.filters.some((existing) => existing.fieldname === filter.fieldname)) {
			settings.filters.push(filter);
		}
	});
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

	# Growth and Margin views already replace the amounts with percentages.
	filters_dict = percentage.as_dict(filters)
	if filters_dict.get("selected_view") in ("Growth", "Margin"):
		return response

	monthly = percentage.is_monthly_enabled(filters) and filters_dict.get("periodicity") == "Monthly"
	total = percentage.is_total_enabled(filters)
	if not monthly and not total:
		return response

	return percentage.add_percentage_column(response, monthly=monthly, total=total)


@frappe.whitelist()
@frappe.read_only()
def get_script(report_name):
	response = _original_get_script(report_name)
	if report_name in percentage.SUPPORTED_REPORTS and isinstance(response, dict):
		response["script"] = (response.get("script") or "") + PERCENTAGE_FILTERS_JS
	return response


def patch(**kwargs):
	"""Idempotent; called from the `before_request` / `before_job` hooks."""
	global _patched
	if _patched:
		return

	_query_report.run = run
	_patched = True
