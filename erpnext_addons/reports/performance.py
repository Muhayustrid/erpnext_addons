"""Fast paths for the ERPNext financial statement reports.

ERPNext v16 loads the root accounts of every company, then runs the GL query
for each root. For one company that is hundreds of unused queries, and the
consolidated report runs a query for every root/company pair. Scope the root
query to the selected company or group, and query only the company that owns
each consolidated root.

The report logic is not copied; only the two SQL statements are rewritten
while the target report runs. The scope lives in a ContextVar, so it is
thread-local and cleared by the Report wrapper.
"""

import contextvars
import re

TARGET_REPORTS = frozenset(
	{
		"Profit and Loss Statement",
		"Balance Sheet",
		"Consolidated Financial Statement",
	}
)
CONSOLIDATED_REPORT = "Consolidated Financial Statement"

_scope = contextvars.ContextVar("erpnext_addons_report_scope", default=None)
_patched = False

# shortcut: these match the v16 SQL text; revisit when ERPNext changes these reports
ROOT_ACCOUNT_RE = re.compile(
	r"where\s+root_type=%s\s+and\s+(ifnull\s*\(\s*parent_account\s*,\s*''\s*\)\s*=\s*'')",
	re.IGNORECASE,
)
COMPANY_QUERY_MARKERS = (
	"from `tabCompany`",
	"lft >= %(company_lft)s",
	"rgt <= %(company_rgt)s",
)


def rewrite_sql(query, values, scope):
	"""Return the scoped (query, values) or None when this query is not ours."""
	if not scope:
		return None

	scoped = _scope_root_accounts(query, values, scope)
	if scoped:
		return scoped

	return _scope_company_list(query, scope)


def _root_type(values):
	if isinstance(values, (tuple, list)):
		return values[0] if values else None
	return values


def _scope_root_accounts(query, values, scope):
	if "company=%s" in query or "company in %s" in query:
		return None
	if not ROOT_ACCOUNT_RE.search(query):
		return None

	root_type = _root_type(values)
	if not root_type:
		return None

	if scope.get("report") == CONSOLIDATED_REPORT:
		group = scope.get("group")
		if not group:
			return None
		query = ROOT_ACCOUNT_RE.sub(r"where root_type=%s and company in %s and \1", query, count=1)
		return query, (root_type, tuple(group))

	company = scope.get("company")
	if not company:
		return None
	query = ROOT_ACCOUNT_RE.sub(r"where root_type=%s and company=%s and \1", query, count=1)
	return query, (root_type, company)


def _scope_company_list(query, scope):
	if scope.get("root_company") is None:
		return None
	if not all(marker in query for marker in COMPANY_QUERY_MARKERS):
		return None
	return (
		"select name, default_currency from `tabCompany` where name = %(root_company)s",
		{"root_company": scope["root_company"]},
	)


def patch(**kwargs):
	"""Install the report scope once; called from before_request/before_job."""
	global _patched

	if not _patched:
		_install_report_wrapper()
		_install_consolidated_wrapper()
		_patched = True

	_install_sql_wrapper()


def _install_sql_wrapper():
	import frappe

	db = frappe.db
	if getattr(db, "_erpnext_addons_perf_sql", False):
		return

	original = db.sql

	def scoped_sql(query, *args, **kwargs):
		scope = _scope.get()
		if scope:
			values = args[0] if args else kwargs.get("values", ())
			rewritten = rewrite_sql(query, values, scope)
			if rewritten:
				new_query, new_values = rewritten
				rest = args[1:]
				kwargs = {key: value for key, value in kwargs.items() if key != "values"}
				return original(new_query, new_values, *rest, **kwargs)
		return original(query, *args, **kwargs)

	scoped_sql.__erpnext_addons_perf = True
	db.sql = scoped_sql
	db._erpnext_addons_perf_sql = True


def _install_report_wrapper():
	from frappe.core.doctype.report.report import Report

	if getattr(Report.execute_module, "_erpnext_addons_perf", False):
		return

	original = Report.execute_module

	def execute_module(self, filters):
		report_name = getattr(self, "report_name", None) or self.name
		if report_name not in TARGET_REPORTS:
			return original(self, filters)

		company = _company(filters)
		if not company:
			return original(self, filters)

		group = None
		if report_name == CONSOLIDATED_REPORT:
			from erpnext.accounts.report.consolidated_financial_statement.consolidated_financial_statement import (
				get_subsidiary_companies,
			)

			group = tuple(get_subsidiary_companies(company))
			if not group:
				return original(self, filters)

		token = _scope.set(
			{
				"report": report_name,
				"company": company,
				"group": group,
				"root_company": None,
			}
		)
		try:
			return original(self, filters)
		finally:
			_scope.reset(token)

	execute_module.__erpnext_addons_perf = True
	Report.execute_module = execute_module


def _install_consolidated_wrapper():
	import frappe
	from erpnext.accounts.report.consolidated_financial_statement import (
		consolidated_financial_statement as report,
	)

	if getattr(report.set_gl_entries_by_account, "_erpnext_addons_perf", False):
		return

	original = report.set_gl_entries_by_account

	def set_gl_entries_by_account(
		from_date,
		to_date,
		root_lft,
		root_rgt,
		filters,
		gl_entries_by_account,
		accounts_by_name,
		accounts,
		ignore_closing_entries=False,
		root_type=None,
	):
		scope = _scope.get()
		if not scope or scope.get("report") != CONSOLIDATED_REPORT:
			return original(
				from_date,
				to_date,
				root_lft,
				root_rgt,
				filters,
				gl_entries_by_account,
				accounts_by_name,
				accounts,
				ignore_closing_entries=ignore_closing_entries,
				root_type=root_type,
			)

		root_filters = {"lft": root_lft, "rgt": root_rgt}
		if root_type:
			root_filters["root_type"] = root_type
		root_company = frappe.db.get_value("Account", root_filters, "company")
		if not root_company:
			return original(
				from_date,
				to_date,
				root_lft,
				root_rgt,
				filters,
				gl_entries_by_account,
				accounts_by_name,
				accounts,
				ignore_closing_entries=ignore_closing_entries,
				root_type=root_type,
			)

		token = _scope.set({**scope, "root_company": root_company})
		try:
			return original(
				from_date,
				to_date,
				root_lft,
				root_rgt,
				filters,
				gl_entries_by_account,
				accounts_by_name,
				accounts,
				ignore_closing_entries=ignore_closing_entries,
				root_type=root_type,
			)
		finally:
			_scope.reset(token)

	set_gl_entries_by_account.__erpnext_addons_perf = True
	report.set_gl_entries_by_account = set_gl_entries_by_account


def _company(filters):
	import frappe

	if isinstance(filters, str):
		filters = frappe.parse_json(filters) or {}
	return (filters or {}).get("company") if hasattr(filters, "get") else None
