"""Financial statement query scoping (no site needed)."""

import unittest

from erpnext_addons.reports import performance

ROOT_QUERY = """select lft, rgt from tabAccount
			where root_type=%s and ifnull(parent_account, '') = ''"""

COMPANY_QUERY = """ select name, default_currency from `tabCompany`
		where lft >= %(company_lft)s and rgt <= %(company_rgt)s"""


class TestRootQuery(unittest.TestCase):
	def test_single_company_scope(self):
		result = performance.rewrite_sql(
			ROOT_QUERY,
			"Income",
			{"report": "Profit and Loss Statement", "company": "ACME", "group": None},
		)
		self.assertIsNotNone(result)
		query, values = result
		self.assertIn("root_type=%s and company=%s", query)
		self.assertEqual(values, ("Income", "ACME"))

	def test_consolidated_group_scope(self):
		result = performance.rewrite_sql(
			ROOT_QUERY,
			"Income",
			{
				"report": "Consolidated Financial Statement",
				"company": "GROUP",
				"group": ("GROUP", "A", "B"),
			},
		)
		self.assertIsNotNone(result)
		query, values = result
		self.assertIn("root_type=%s and company in %s", query)
		self.assertEqual(values, ("Income", ("GROUP", "A", "B")))

	def test_already_scoped_query_is_untouched(self):
		query = "select lft, rgt from tabAccount where root_type=%s and company=%s and ifnull(parent_account, '') = ''"
		self.assertIsNone(
			performance.rewrite_sql(
				query,
				("Income", "ACME"),
				{"report": "Profit and Loss Statement", "company": "ACME"},
			)
		)

	def test_missing_scope_is_untouched(self):
		self.assertIsNone(performance.rewrite_sql(ROOT_QUERY, "Income", None))
		self.assertIsNone(
			performance.rewrite_sql(
				ROOT_QUERY,
				"Income",
				{"report": "Profit and Loss Statement", "company": None},
			)
		)

	def test_unrelated_query_is_untouched(self):
		self.assertIsNone(
			performance.rewrite_sql(
				"select name from tabAccount where name=%s",
				"ACME",
				{"report": "Profit and Loss Statement", "company": "ACME"},
			)
		)


class TestCompanyQuery(unittest.TestCase):
	def test_root_company_scope(self):
		result = performance.rewrite_sql(
			COMPANY_QUERY,
			{"company_lft": 1, "company_rgt": 10},
			{
				"report": "Consolidated Financial Statement",
				"company": "GROUP",
				"root_company": "A",
			},
		)
		self.assertIsNotNone(result)
		query, values = result
		self.assertEqual(query, "select name, default_currency from `tabCompany` where name = %(root_company)s")
		self.assertEqual(values, {"root_company": "A"})

	def test_missing_root_company_is_untouched(self):
		self.assertIsNone(
			performance.rewrite_sql(
				COMPANY_QUERY,
				{"company_lft": 1, "company_rgt": 10},
				{"report": "Consolidated Financial Statement", "company": "GROUP"},
			)
		)


if __name__ == "__main__":
	unittest.main()
