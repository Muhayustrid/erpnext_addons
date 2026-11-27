"""Query report overrides for the P&L percentage column (no site needed)."""

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
					"show_monthly_percentage": 1,
					"show_total_percentage": 1,
				},
			)

		self.assertEqual(
			[col["fieldname"] for col in response["columns"]],
			["account", "oct_2026", "oct_2026_percentage", "nov_2026", "nov_2026_percentage", "total", "percentage"],
		)

	def test_quarterly_report_has_only_total_percentage(self):
		with mock.patch.object(query_report, "_original_run", return_value=monthly_pl_response()):
			response = query_report.run(
				report_name="Profit and Loss Statement",
				filters={"periodicity": "Quarterly"},
			)

		self.assertEqual(
			[col["fieldname"] for col in response["columns"]],
			["account", "oct_2026", "nov_2026", "total", "percentage"],
		)

	def test_monthly_filter_can_be_disabled(self):
		with mock.patch.object(query_report, "_original_run", return_value=monthly_pl_response()):
			response = query_report.run(
				report_name="Profit and Loss Statement",
				filters={
					"periodicity": "Monthly",
					"show_monthly_percentage": 0,
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
					"show_monthly_percentage": 1,
					"show_total_percentage": 0,
				},
			)

		self.assertIn("oct_2026_percentage", [col["fieldname"] for col in response["columns"]])
		self.assertNotIn("percentage", [col["fieldname"] for col in response["columns"]])

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
		self.assertIn("show_monthly_percentage", response["script"])
		self.assertIn("show_total_percentage", response["script"])

	def test_other_reports_are_untouched(self):
		response = {"script": "base"}
		with mock.patch.object(query_report, "_original_get_script", return_value=response):
			self.assertIs(query_report.get_script("General Ledger"), response)

	def test_non_dict_response_is_untouched(self):
		with mock.patch.object(query_report, "_original_get_script", return_value=None):
			self.assertIsNone(query_report.get_script("Profit and Loss Statement"))


class TestPatch(unittest.TestCase):
	def test_patch_replaces_run_once(self):
		original = object()
		fake = SimpleNamespace(run=original)
		with (
			mock.patch.object(query_report, "_query_report", fake),
			mock.patch.object(query_report, "_patched", False),
		):
			query_report.patch()
			self.assertIs(fake.run, query_report.run)
			query_report.patch()
			self.assertIs(fake.run, query_report.run)


if __name__ == "__main__":
	unittest.main()
