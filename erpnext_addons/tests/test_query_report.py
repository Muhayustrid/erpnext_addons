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


class TestRun(unittest.TestCase):
	def test_other_reports_are_untouched(self):
		response = pl_response()
		with mock.patch.object(query_report, "_original_run", return_value=response):
			self.assertIs(query_report.run(report_name="General Ledger"), response)

	def test_pnl_gets_percentage_column(self):
		with mock.patch.object(query_report, "_original_run", return_value=pl_response()):
			response = query_report.run(report_name="Profit and Loss Statement", filters={"show_percentage": 1})

		self.assertEqual(response["columns"][-1]["fieldname"], "percentage")
		self.assertEqual(response["result"][0]["percentage"], 100.0)

	def test_disabled_filter_skips_percentage(self):
		response = pl_response()
		with mock.patch.object(query_report, "_original_run", return_value=response):
			out = query_report.run(
				report_name="Profit and Loss Statement", filters={"show_percentage": 0}
			)

		self.assertIs(out, response)
		self.assertNotIn("percentage", response["columns"])

	def test_reads_report_and_filters_from_positional_args(self):
		with mock.patch.object(query_report, "_original_run", return_value=pl_response()):
			response = query_report.run("Profit and Loss Statement", '{"show_percentage": 1}')

		self.assertEqual(response["columns"][-1]["fieldname"], "percentage")


class TestGetScript(unittest.TestCase):
	def test_injects_show_percentage_only_for_pnl(self):
		with mock.patch.object(query_report, "_original_get_script", return_value={"script": "base"}):
			response = query_report.get_script("Profit and Loss Statement")

		self.assertEqual(response["script"], "base" + query_report.SHOW_PERCENTAGE_FILTER_JS)
		self.assertIn("show_percentage", response["script"])

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
