"""Query report overrides for the P&L percentage column (no site needed)."""

import json
import unittest
from types import SimpleNamespace
from unittest import mock

from erpnext_addons.tests.fakes import ensure_frappe_importable

ensure_frappe_importable()

from erpnext_addons.overrides import query_report


def pl_response():
	return {
		"columns": [
			{"fieldname": "account", "fieldtype": "Link"},
			{"fieldname": "total", "fieldtype": "Currency"},
		],
		"result": [
			{"account": "Sales", "total": 1000, "is_group": 0, "account_type": "Income Account"},
			{"account": "Total Income (Credit)", "total": 1000, "opening_balance": 0},
		],
	}


def monthly_pl_response():
	return {
		"columns": [
			{"fieldname": "account", "fieldtype": "Link"},
			{"fieldname": "oct_2026", "fieldtype": "Currency"},
			{"fieldname": "nov_2026", "fieldtype": "Currency"},
			{"fieldname": "total", "fieldtype": "Currency"},
		],
		"result": [
			{
				"account": "Sales A",
				"oct_2026": 800,
				"nov_2026": 2000,
				"total": 2800,
				"is_group": 0,
				"account_type": "Income Account",
			},
			{"account": "Total Income (Credit)", "oct_2026": 800, "nov_2026": 2000, "total": 2800, "opening_balance": 0},
		],
	}


class TestRun(unittest.TestCase):
	def test_other_reports_are_untouched(self):
		response = pl_response()
		with mock.patch.object(query_report, "_original_run", return_value=response):
			self.assertIs(query_report.run(report_name="General Ledger"), response)

	def test_pnl_gets_both_percentage_columns(self):
		with mock.patch.object(query_report, "_original_run", return_value=monthly_pl_response()):
			response = query_report.run(
				report_name="Profit and Loss Statement",
				filters={
					"periodicity": "Monthly",
					"show_period_percentage": 1,
					"show_total_percentage": 1,
				},
			)

		self.assertEqual(
			[col["fieldname"] for col in response["columns"]],
			["account", "oct_2026", "oct_2026_percentage", "nov_2026", "nov_2026_percentage", "total", "percentage"],
		)

	def test_quarterly_report_gets_period_percentage(self):
		with mock.patch.object(query_report, "_original_run", return_value=monthly_pl_response()):
			response = query_report.run(
				report_name="Profit and Loss Statement",
				filters={
					"periodicity": "Quarterly",
					"show_period_percentage": 1,
					"show_total_percentage": 1,
				},
			)

		self.assertEqual(
			[col["fieldname"] for col in response["columns"]],
			["account", "oct_2026", "oct_2026_percentage", "nov_2026", "nov_2026_percentage", "total", "percentage"],
		)

	def test_half_yearly_report_gets_period_percentage(self):
		with mock.patch.object(query_report, "_original_run", return_value=monthly_pl_response()):
			response = query_report.run(
				report_name="Profit and Loss Statement",
				filters={"periodicity": "Half-Yearly", "show_period_percentage": 1},
			)

		self.assertIn("oct_2026_percentage", [col["fieldname"] for col in response["columns"]])
		self.assertIn("nov_2026_percentage", [col["fieldname"] for col in response["columns"]])
		self.assertNotIn("percentage", [col["fieldname"] for col in response["columns"]])

	def test_legacy_monthly_filter_still_enables_period_percentage(self):
		with mock.patch.object(query_report, "_original_run", return_value=monthly_pl_response()):
			response = query_report.run(
				report_name="Profit and Loss Statement",
				filters={"periodicity": "Quarterly", "show_monthly_percentage": 1},
			)

		self.assertIn("oct_2026_percentage", [col["fieldname"] for col in response["columns"]])

	def test_unchecked_filters_are_absent_and_disable_both(self):
		with mock.patch.object(query_report, "_original_run", return_value=monthly_pl_response()):
			response = query_report.run(
				report_name="Profit and Loss Statement",
				filters={"periodicity": "Monthly"},
			)

		self.assertEqual(
			[col["fieldname"] for col in response["columns"]],
			["account", "oct_2026", "nov_2026", "total"],
		)

	def test_period_checked_total_unchecked(self):
		with mock.patch.object(query_report, "_original_run", return_value=monthly_pl_response()):
			response = query_report.run(
				report_name="Profit and Loss Statement",
				filters={"periodicity": "Monthly", "show_period_percentage": 1},
			)

		self.assertIn("oct_2026_percentage", [col["fieldname"] for col in response["columns"]])
		self.assertNotIn("percentage", [col["fieldname"] for col in response["columns"]])

	def test_total_checked_period_unchecked(self):
		with mock.patch.object(query_report, "_original_run", return_value=monthly_pl_response()):
			response = query_report.run(
				report_name="Profit and Loss Statement",
				filters={"periodicity": "Monthly", "show_total_percentage": 1},
			)

		self.assertNotIn("oct_2026_percentage", [col["fieldname"] for col in response["columns"]])
		self.assertIn("percentage", [col["fieldname"] for col in response["columns"]])

	def test_period_filter_can_be_disabled(self):
		with mock.patch.object(query_report, "_original_run", return_value=monthly_pl_response()):
			response = query_report.run(
				report_name="Profit and Loss Statement",
				filters={
					"periodicity": "Monthly",
					"show_period_percentage": 0,
					"show_total_percentage": 1,
				},
			)

		self.assertNotIn("oct_2026_percentage", [col["fieldname"] for col in response["columns"]])
		self.assertIn("percentage", [col["fieldname"] for col in response["columns"]])

	def test_total_filter_can_be_disabled(self):
		with mock.patch.object(query_report, "_original_run", return_value=monthly_pl_response()):
			response = query_report.run(
				report_name="Profit and Loss Statement",
				filters={
					"periodicity": "Monthly",
					"show_period_percentage": 1,
					"show_total_percentage": 0,
				},
			)

		self.assertIn("oct_2026_percentage", [col["fieldname"] for col in response["columns"]])
		self.assertNotIn("percentage", [col["fieldname"] for col in response["columns"]])

	def test_hide_total_drops_the_total_columns(self):
		with mock.patch.object(query_report, "_original_run", return_value=monthly_pl_response()):
			response = query_report.run(
				report_name="Profit and Loss Statement",
				filters={
					"periodicity": "Monthly",
					"show_period_percentage": 1,
					"show_total_percentage": 1,
					"hide_total": 1,
				},
			)

		self.assertEqual(
			[col["fieldname"] for col in response["columns"]],
			["account", "oct_2026", "oct_2026_percentage", "nov_2026", "nov_2026_percentage"],
		)

	def test_hide_total_works_without_percentage_filters(self):
		with mock.patch.object(query_report, "_original_run", return_value=monthly_pl_response()):
			response = query_report.run(
				report_name="Profit and Loss Statement",
				filters={"hide_total": 1},
			)

		self.assertEqual(
			[col["fieldname"] for col in response["columns"]],
			["account", "oct_2026", "nov_2026"],
		)

	def test_hide_total_applies_to_growth_and_margin_views(self):
		for view in ("Growth", "Margin"):
			response = monthly_pl_response()
			with mock.patch.object(query_report, "_original_run", return_value=response):
				query_report.run(
					report_name="Profit and Loss Statement",
					filters={"selected_view": view, "hide_total": 1},
				)

			self.assertNotIn("total", [col["fieldname"] for col in response["columns"]])
			self.assertEqual(
				[col["fieldname"] for col in response["columns"]],
				["account", "oct_2026", "nov_2026"],
			)

	def test_legacy_disabled_filter_skips_percentage(self):
		response = pl_response()
		with mock.patch.object(query_report, "_original_run", return_value=response):
			out = query_report.run(
				report_name="Profit and Loss Statement", filters={"show_percentage": 0}
			)

		self.assertIs(out, response)
		self.assertNotIn("percentage", response["columns"])

	def test_growth_and_margin_views_are_untouched(self):
		for view in ("Growth", "Margin"):
			response = monthly_pl_response()
			with mock.patch.object(query_report, "_original_run", return_value=response):
				out = query_report.run(
					report_name="Profit and Loss Statement",
					filters={"selected_view": view},
				)
			self.assertIs(out, response)
			self.assertNotIn("percentage", [col["fieldname"] for col in response["columns"]])

	def test_reads_report_and_filters_from_positional_args(self):
		with mock.patch.object(query_report, "_original_run", return_value=pl_response()):
			response = query_report.run("Profit and Loss Statement", '{"show_percentage": 1}')

		self.assertEqual(response["columns"][-1]["fieldname"], "percentage")


class TestGetScript(unittest.TestCase):
	def test_injects_percentage_filters_only_for_pnl(self):
		with mock.patch.object(query_report, "_original_get_script", return_value={"script": "base"}):
			response = query_report.get_script("Profit and Loss Statement")

		self.assertEqual(response["script"], "base" + query_report.PERCENTAGE_FILTERS_JS)
		self.assertIn("show_period_percentage", response["script"])
		self.assertIn("show_total_percentage", response["script"])
		self.assertIn("hide_total", response["script"])

	def test_other_reports_are_untouched(self):
		response = {"script": "base"}
		with mock.patch.object(query_report, "_original_get_script", return_value=response):
			self.assertIs(query_report.get_script("General Ledger"), response)

	def test_non_dict_response_is_untouched(self):
		with mock.patch.object(query_report, "_original_get_script", return_value=None):
			self.assertIsNone(query_report.get_script("Profit and Loss Statement"))


class TestPatch(unittest.TestCase):
	def setUp(self):
		from frappe.core.doctype.prepared_report import prepared_report

		self.prepared_report = prepared_report
		self.originals = {
			name: getattr(prepared_report, name)
			for name in (
				"make_prepared_report",
				"get_completed_prepared_report",
				"get_reports_in_queued_state",
			)
		}

	def tearDown(self):
		for name, original in self.originals.items():
			setattr(self.prepared_report, name, original)
		query_report._patched = False
		query_report._original_prepared_report = None

	def test_patch_replaces_run_once(self):
		original = object()
		fake = SimpleNamespace(run=original)
		with mock.patch.object(query_report, "_query_report", fake):
			query_report.patch()
			self.assertIs(fake.run, query_report.run)
			query_report.patch()
			self.assertIs(fake.run, query_report.run)

	def test_patch_rebinds_the_prepared_report_functions(self):
		fake = SimpleNamespace(run=object())
		with mock.patch.object(query_report, "_query_report", fake):
			query_report.patch()

		self.assertIs(self.prepared_report.make_prepared_report, query_report.make_prepared_report)
		self.assertIs(
			self.prepared_report.get_completed_prepared_report,
			query_report.get_prepared_report,
		)
		self.assertIs(
			self.prepared_report.get_reports_in_queued_state,
			query_report.get_reports_in_queued_state,
		)

	def test_patch_uses_the_version_specific_lookup_name(self):
		from frappe.core.doctype import prepared_report as prepared_report_pkg

		fake = SimpleNamespace(
			make_prepared_report=lambda report_name, filters=None: "make",
			get_last_processed_prepared_report=lambda filters, user, report_name: "lookup",
			get_reports_in_queued_state=lambda report_name, filters: "queued",
		)
		with (
			mock.patch.object(query_report, "_query_report", SimpleNamespace(run=object())),
			mock.patch.object(prepared_report_pkg, "prepared_report", fake),
		):
			query_report.patch()

		self.assertIs(fake.get_last_processed_prepared_report, query_report.get_prepared_report)

	def test_patched_functions_call_the_originals_not_themselves(self):
		fake = SimpleNamespace(run=object())
		with mock.patch.object(query_report, "_query_report", fake):
			query_report.patch()
			result = self.prepared_report.get_completed_prepared_report(
				{"company": "C", "hide_total": 1}, "Administrator", "Profit and Loss Statement"
			)

		self.assertEqual(result, {"company": "C"})


class TestPreparedReportFilters(unittest.TestCase):
	def fake_module(self, calls):
		def record(name):
			def fn(*args):
				calls.append((name, args))
				return "ok"

			return fn

		return SimpleNamespace(
			make=record("make"),
			lookup=record("lookup"),
			queued=record("queued"),
		)

	def test_pnl_filters_are_stripped_for_store_lookup_and_queue(self):
		calls = []
		with mock.patch.object(query_report, "_original_prepared_report", self.fake_module(calls)):
			filters = {"company": "C", "show_period_percentage": 1, "hide_total": 1}
			query_report.make_prepared_report("Profit and Loss Statement", filters)
			query_report.get_prepared_report(filters, "Administrator", "Profit and Loss Statement")
			query_report.get_reports_in_queued_state("Profit and Loss Statement", filters)

		self.assertEqual(
			[args for _, args in calls],
			[
				("Profit and Loss Statement", {"company": "C"}),
				({"company": "C"}, "Administrator", "Profit and Loss Statement"),
				("Profit and Loss Statement", {"company": "C"}),
			],
		)

	def test_other_reports_keep_their_filters(self):
		calls = []
		with mock.patch.object(query_report, "_original_prepared_report", self.fake_module(calls)):
			filters = {"company": "C", "show_percentage": 1, "hide_total": 1}
			query_report.make_prepared_report("Custom Report", filters)
			query_report.get_prepared_report(filters, "Administrator", "Custom Report")

		self.assertEqual(
			[args for _, args in calls],
			[
				("Custom Report", filters),
				(filters, "Administrator", "Custom Report"),
			],
		)

	def test_store_and_lookup_share_one_key_across_checkbox_states(self):
		def normalize(filters):
			return json.dumps(filters, sort_keys=True, separators=(",", ":"))

		fake = SimpleNamespace(
			make=lambda report_name, filters: normalize(filters),
			lookup=lambda filters, user, report_name: normalize(filters),
			queued=lambda report_name, filters: normalize(filters),
		)
		checked = {"company": "C", "show_period_percentage": 1, "hide_total": 1}
		unchecked = {"company": "C", "show_period_percentage": 1}

		with mock.patch.object(query_report, "_original_prepared_report", fake):
			stored = query_report.make_prepared_report("Profit and Loss Statement", checked)
			lookup_hit = query_report.get_prepared_report(unchecked, "u", "Profit and Loss Statement")
			lookup_other = query_report.get_prepared_report(
				{"company": "D"}, "u", "Profit and Loss Statement"
			)

		self.assertEqual(stored, lookup_hit)
		self.assertNotEqual(stored, lookup_other)


if __name__ == "__main__":
	unittest.main()
