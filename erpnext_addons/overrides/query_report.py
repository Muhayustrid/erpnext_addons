"""Add the P&L percentage columns through the query report API.

`run` post-processes the normal report response and `get_script` injects the
`Show Period Percentage`, `Show Total Percentage` and `Hide Total` filters.
`patch` rebinds the module-level `run` so internal callers (Excel export,
prepared reports) also get the columns, and keeps the display-only filters out
of the prepared report key so toggling them reuses the same prepared report.
"""

from types import SimpleNamespace

import frappe
from frappe.desk import query_report as _query_report

from erpnext_addons.overrides import percentage

# captured at import time, before `patch` replaces the module attribute
_original_run = _query_report.run
_original_get_script = _query_report.get_script

_patched = False
# the original prepared report functions, captured before they are rebound
_original_prepared_report = None

PERCENTAGE_FILTERS_JS = """
// injected by erpnext_addons
(function () {
	const report_name = "Profit and Loss Statement";
	const settings = frappe.query_reports && frappe.query_reports[report_name];
	if (!settings) return;

	settings.filters = settings.filters || [];
	const percentage_filters = [
		{
			fieldname: "show_period_percentage",
			label: __("Show Period Percentage"),
			fieldtype: "Check",
			default: 1,
		},
		{
			fieldname: "show_total_percentage",
			label: __("Show Total Percentage"),
			fieldtype: "Check",
			default: 1,
			// Yearly/accumulated views have no separate Total column, and Hide Total removes it
			depends_on: "eval:doc.periodicity != 'Yearly' && !doc.accumulated_values && !doc.hide_total",
		},
		{
			fieldname: "hide_total",
			label: __("Hide Total"),
			fieldtype: "Check",
			default: 0,
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

	# Hide Total only changes the rendered columns, so it applies to every view.
	if percentage.is_total_hidden(filters):
		response = percentage.drop_total_columns(response)

	# Growth and Margin views already replace the amounts with percentages.
	filters_dict = percentage.as_dict(filters)
	if filters_dict.get("selected_view") in ("Growth", "Margin"):
		return response

	period = percentage.is_period_enabled(filters)
	total = percentage.is_total_enabled(filters)
	if period or total:
		response = percentage.add_percentage_column(response, period=period, total=total)

	return response


@frappe.whitelist()
@frappe.read_only()
def get_script(report_name):
	response = _original_get_script(report_name)
	if report_name in percentage.SUPPORTED_REPORTS and isinstance(response, dict):
		response["script"] = (response.get("script") or "") + PERCENTAGE_FILTERS_JS
	return response


def _strip_display_filters(report_name, filters):
	if report_name in percentage.SUPPORTED_REPORTS:
		return percentage.strip_display_filters(filters)
	return filters


# The desk dispatches these two by their `frappe.core...` path; the whitelist
# registry is keyed by function object, so the replacements must be whitelisted
# too. The lookup below is internal and stays private.
@frappe.whitelist()
def make_prepared_report(report_name, filters=None):
	return _original_prepared_report.make(report_name, _strip_display_filters(report_name, filters))


def get_prepared_report(filters, user, report_name):
	return _original_prepared_report.lookup(
		_strip_display_filters(report_name, filters), user, report_name
	)


@frappe.whitelist()
def get_reports_in_queued_state(report_name, filters):
	return _original_prepared_report.queued(
		report_name, _strip_display_filters(report_name, filters)
	)


# Frappe 16.52 renamed the lookup; support both names.
PREPARED_REPORT_LOOKUP_NAMES = (
	"get_last_processed_prepared_report",
	"get_completed_prepared_report",
)


def patch(**kwargs):
	"""Idempotent; called from the `before_request` / `before_job` hooks."""
	global _patched, _original_prepared_report
	if _patched:
		return

	_query_report.run = run

	# A prepared report is keyed by its filters. The display-only checkboxes must
	# not split one P&L report into one prepared report per checkbox state.
	from frappe.core.doctype.prepared_report import prepared_report

	lookup_name = next(
		(name for name in PREPARED_REPORT_LOOKUP_NAMES if hasattr(prepared_report, name)),
		None,
	)
	make = getattr(prepared_report, "make_prepared_report", None)
	queued = getattr(prepared_report, "get_reports_in_queued_state", None)
	if make and lookup_name and make is not make_prepared_report:
		# snapshot the functions: holding the module itself would make the
		# wrappers resolve to themselves after the rebind and recurse
		_original_prepared_report = SimpleNamespace(
			make=make,
			lookup=getattr(prepared_report, lookup_name),
			queued=queued,
		)
		prepared_report.make_prepared_report = make_prepared_report
		setattr(prepared_report, lookup_name, get_prepared_report)
		if queued:
			prepared_report.get_reports_in_queued_state = get_reports_in_queued_state

	_patched = True
