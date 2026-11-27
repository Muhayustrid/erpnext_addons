"""Percentage column on the Profit and Loss Statement (no site needed)."""

import unittest

from erpnext_addons.tests.fakes import ensure_frappe_importable

ensure_frappe_importable()

from erpnext_addons.overrides import percentage


def column(fieldname, fieldtype="Currency"):
	return {"fieldname": fieldname, "fieldtype": fieldtype, "label": fieldname}


class TestFilters(unittest.TestCase):
	def test_disabled_when_filter_is_absent(self):
		# Frappe's report filter collector drops falsy Check values, so an
		# unchecked box reaches the backend as a missing key.
		self.assertFalse(percentage.is_monthly_enabled({}))
		self.assertFalse(percentage.is_total_enabled({}))
		self.assertFalse(percentage.is_monthly_enabled(None))
		self.assertFalse(percentage.is_total_enabled(None))

	def test_disabled_independently(self):
		self.assertFalse(percentage.is_monthly_enabled({"show_monthly_percentage": 0}))
		self.assertTrue(percentage.is_total_enabled({"show_total_percentage": 1}))
		self.assertFalse(percentage.is_total_enabled({"show_total_percentage": "0"}))
		self.assertTrue(percentage.is_monthly_enabled({"show_monthly_percentage": "1"}))

	def test_legacy_filter_disables_both(self):
		self.assertFalse(percentage.is_monthly_enabled({"show_percentage": 0}))
		self.assertFalse(percentage.is_total_enabled({"show_percentage": "0"}))

	def test_legacy_filter_enables_both(self):
		self.assertTrue(percentage.is_monthly_enabled('{"show_percentage": 1}'))
		self.assertTrue(percentage.is_total_enabled('{"show_percentage": 1}'))

	def test_new_filter_wins_over_legacy(self):
		filters = {"show_percentage": 0, "show_monthly_percentage": 1, "show_total_percentage": 1}
		self.assertTrue(percentage.is_monthly_enabled(filters))
		self.assertTrue(percentage.is_total_enabled(filters))

	def test_invalid_filter_value_disables(self):
		self.assertFalse(percentage.is_monthly_enabled("not json"))
		self.assertFalse(percentage.is_total_enabled("not json"))


class TestValueField(unittest.TestCase):
	def test_total_column_wins(self):
		self.assertEqual(
			percentage.get_value_fieldname([column("account", "Link"), column("dec_2026"), column("total")]),
			"total",
		)

	def test_last_amount_column_fallback(self):
		self.assertEqual(
			percentage.get_value_fieldname([column("account", "Link"), column("dec_2026")]),
			"dec_2026",
		)

	def test_no_amount_column(self):
		self.assertIsNone(percentage.get_value_fieldname([column("account", "Link"), column("percentage", "Percent")]))


class TestIncomeTotal(unittest.TestCase):
	def test_classic_excludes_cost_accounts(self):
		rows = [
			{"account": "Sales", "total": 1000, "is_group": 1},
			{"account": "Sales A", "total": 1000, "is_group": 0, "account_type": "Income Account"},
			{"account": "COGS", "total": -300, "is_group": 0, "account_type": "Cost of Goods Sold"},
			{"account": "Stock Adj", "total": -100, "is_group": 0, "account_type": "Stock Adjustment"},
			{"account": "Expense", "total": 50, "is_group": 0, "account_type": "Expense Account"},
			{"account": "Total Income (Credit)", "total": 550, "opening_balance": 0},
		]
		self.assertEqual(percentage.get_income_total(rows, "total"), 1000)

	def test_classic_without_leaf_has_no_total(self):
		rows = [
			{"account": "Sales", "total": 0, "is_group": 1},
			{"account": "Total Income (Credit)", "total": 0, "opening_balance": 0},
		]
		self.assertIsNone(percentage.get_income_total(rows, "total"))

	def test_template_uses_first_revenue_section(self):
		rows = [
			{"account": "Sales Revenue", "indent": 0, "account_filters": '{"and": []}', "total": 900},
			{"account": "Product A", "indent": 1, "total": 400, "account_type": "Income Account"},
			{"account": "Cost of Goods Sold", "indent": 0, "account_filters": '["x", "=", "y"]', "total": -200},
		]
		self.assertEqual(percentage.get_income_total(rows, "total"), 900)

	def test_total_row_detection_respects_parent_account(self):
		self.assertTrue(percentage.is_classic_total_row({"account": "Total", "opening_balance": 0}))
		self.assertFalse(
			percentage.is_classic_total_row(
				{"account": "Sales", "opening_balance": 0, "parent_account": ""}
			)
		)


class TestAddPercentageColumn(unittest.TestCase):
	def response(self):
		return {
			"columns": [column("account", "Link"), column("total")],
			"result": [
				{"account": "Sales", "total": 1000, "is_group": 0, "account_type": "Income Account"},
				{"account": "COGS", "total": -300, "is_group": 0, "account_type": "Cost of Goods Sold"},
				{"account": "Total Income (Credit)", "total": 700, "opening_balance": 0},
				{"account": "Expense", "total": 200, "is_group": 0, "account_type": "Expense Account"},
				{},
			],
		}

	def monthly_response(self):
		return {
			"columns": [
				column("account", "Link"),
				column("oct_2026"),
				column("nov_2026"),
				column("total"),
			],
			"result": [
				{
					"account": "Sales",
					"oct_2026": 1000,
					"nov_2026": 2000,
					"total": 3000,
					"is_group": 1,
				},
				{
					"account": "Sales A",
					"oct_2026": 800,
					"nov_2026": 2000,
					"total": 2800,
					"is_group": 0,
					"account_type": "Income Account",
				},
				{
					"account": "COGS",
					"oct_2026": -200,
					"nov_2026": -500,
					"total": -700,
					"is_group": 0,
					"account_type": "Cost of Goods Sold",
				},
				{
					"account": "Total Income (Credit)",
					"oct_2026": 600,
					"nov_2026": 1500,
					"total": 2100,
					"opening_balance": 0,
				},
				{
					"account": "Expense",
					"oct_2026": 100,
					"nov_2026": 300,
					"total": 400,
					"is_group": 0,
					"account_type": "Expense Account",
				},
				{},
			],
		}

	def test_appends_total_percentage_column_and_values(self):
		response = percentage.add_percentage_column(self.response())

		self.assertEqual(
			response["columns"][-1],
			{"fieldname": "percentage", "label": "%", "fieldtype": "Percent", "width": 120},
		)
		self.assertEqual(
			[row.get("percentage") for row in response["result"][:4]],
			[100.0, -30.0, 70.0, 20.0],
		)
		self.assertNotIn("percentage", response["result"][4])

	def test_each_month_gets_its_own_percentage_column_beside_it(self):
		response = percentage.add_percentage_column(self.monthly_response())

		self.assertEqual(
			[col["fieldname"] for col in response["columns"]],
			[
				"account",
				"oct_2026",
				"oct_2026_percentage",
				"nov_2026",
				"nov_2026_percentage",
				"total",
				"percentage",
			],
		)
		self.assertEqual(response["columns"][2]["label"], "oct_2026 %")

		rows = response["result"]
		self.assertEqual(
			[rows[0][key] for key in ("oct_2026_percentage", "nov_2026_percentage", "percentage")],
			[125.0, 100.0, 107.14],
		)
		self.assertEqual(
			[rows[1][key] for key in ("oct_2026_percentage", "nov_2026_percentage", "percentage")],
			[100.0, 100.0, 100.0],
		)
		self.assertEqual(
			[rows[2][key] for key in ("oct_2026_percentage", "nov_2026_percentage", "percentage")],
			[-25.0, -25.0, -25.0],
		)
		self.assertEqual(
			[rows[3][key] for key in ("oct_2026_percentage", "nov_2026_percentage", "percentage")],
			[75.0, 75.0, 75.0],
		)
		self.assertNotIn("oct_2026_percentage", rows[5])

	def test_monthly_only(self):
		response = percentage.add_percentage_column(self.monthly_response(), monthly=True, total=False)

		self.assertNotIn("percentage", [col["fieldname"] for col in response["columns"]])
		self.assertEqual(response["columns"][2]["fieldname"], "oct_2026_percentage")
		self.assertNotIn("percentage", response["result"][0])

	def test_total_only(self):
		response = percentage.add_percentage_column(self.monthly_response(), monthly=False, total=True)

		self.assertEqual(
			[col["fieldname"] for col in response["columns"]],
			["account", "oct_2026", "nov_2026", "total", "percentage"],
		)

	def test_single_period_does_not_duplicate_the_total_column(self):
		response = {
			"columns": [column("account", "Link"), column("2026")],
			"result": [
				{"account": "Sales", "2026": 1000, "is_group": 0, "account_type": "Income Account"},
				{"account": "Total Income (Credit)", "2026": 1000, "opening_balance": 0},
			],
		}
		percentage.add_percentage_column(response)

		self.assertEqual(
			[col["fieldname"] for col in response["columns"]],
			["account", "2026", "percentage"],
		)
		self.assertEqual(response["result"][0]["percentage"], 100.0)

	def test_single_month_with_total_column_gets_its_own_percentage(self):
		response = {
			"columns": [column("account", "Link"), column("oct_2026"), column("total")],
			"result": [
				{"account": "Sales", "oct_2026": 800, "total": 800, "is_group": 0, "account_type": "Income Account"},
				{"account": "Total Income (Credit)", "oct_2026": 800, "total": 800, "opening_balance": 0},
			],
		}
		percentage.add_percentage_column(response)

		self.assertEqual(
			[col["fieldname"] for col in response["columns"]],
			["account", "oct_2026", "oct_2026_percentage", "total", "percentage"],
		)
		self.assertEqual(response["result"][0]["oct_2026_percentage"], 100.0)

	def test_month_without_income_is_skipped(self):
		response = self.monthly_response()
		for row in response["result"]:
			row["oct_2026"] = 0

		percentage.add_percentage_column(response)

		fieldnames = [col["fieldname"] for col in response["columns"]]
		self.assertNotIn("oct_2026_percentage", fieldnames)
		self.assertIn("nov_2026_percentage", fieldnames)

	def test_segment_report_is_untouched(self):
		response = {
			"columns": [column("seg_1_account", "Link"), column("seg_1_total")],
			"result": [
				{"seg_1_account": "Sales", "seg_1_total": 1000, "segment_values": {"seg_1": {}}},
			],
		}
		self.assertIs(percentage.add_percentage_column(response), response)
		self.assertEqual(len(response["columns"]), 2)

	def test_idempotent(self):
		response = percentage.add_percentage_column(self.monthly_response())
		percentage.add_percentage_column(response)

		self.assertEqual(len(response["columns"]), 7)
		self.assertEqual(response["result"][0]["percentage"], 107.14)

	def test_percentage_rounds_to_two_decimals(self):
		response = {
			"columns": [column("account", "Link"), column("total")],
			"result": [
				{"account": "A", "total": 1, "is_group": 0},
				{"account": "B", "total": 2, "is_group": 0},
				{"account": "Total Income (Credit)", "total": 3, "opening_balance": 0},
			],
		}
		percentage.add_percentage_column(response)
		self.assertEqual(
			[row["percentage"] for row in response["result"]],
			[33.33, 66.67, 100.0],
		)

	def test_zero_income_returns_response_untouched(self):
		response = {
			"columns": [column("account", "Link"), column("total")],
			"result": [
				{"account": "Sales", "total": 0, "is_group": 0},
				{"account": "Total Income (Credit)", "total": 0, "opening_balance": 0},
			],
		}
		self.assertEqual(percentage.add_percentage_column(response), response)
		self.assertNotIn("percentage", response["columns"])

	def test_skips_non_dict_rows(self):
		response = {
			"columns": [column("account", "Link"), column("total")],
			"result": [["Sales", 1000]],
		}
		percentage.add_percentage_column(response)
		self.assertNotIn("percentage", response["columns"])


if __name__ == "__main__":
	unittest.main()
