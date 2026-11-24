"""Percentage column on the Profit and Loss Statement (no site needed)."""

import unittest

from erpnext_addons.tests.fakes import ensure_frappe_importable

ensure_frappe_importable()

from erpnext_addons.overrides import percentage


def column(fieldname, fieldtype="Currency"):
	return {"fieldname": fieldname, "fieldtype": fieldtype, "label": fieldname}


class TestFilters(unittest.TestCase):
	def test_enabled_by_default(self):
		self.assertTrue(percentage.is_enabled({}))
		self.assertTrue(percentage.is_enabled(None))
		self.assertTrue(percentage.is_enabled('{"show_percentage": 1}'))

	def test_disabled(self):
		self.assertFalse(percentage.is_enabled({"show_percentage": 0}))
		self.assertFalse(percentage.is_enabled('{"show_percentage": "0"}'))

	def test_invalid_filter_value_keeps_default(self):
		self.assertTrue(percentage.is_enabled("not json"))


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

	def test_appends_percentage_column_and_values(self):
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

	def test_idempotent(self):
		response = percentage.add_percentage_column(self.response())
		percentage.add_percentage_column(response)

		self.assertEqual(len(response["columns"]), 3)
		self.assertEqual(response["result"][0]["percentage"], 100.0)

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
