# Copyright (c) 2015, Frappe Technologies Pvt. Ltd. and Contributors
# License: GNU General Public License v3. See license.txt

import frappe
from frappe.utils import today

from erpnext.accounts.doctype.sales_invoice.test_sales_invoice import create_sales_invoice
from erpnext.accounts.report.consolidated_accounts_receivable.consolidated_accounts_receivable import (
	execute,
)
from erpnext.accounts.test.accounts_mixin import AccountsTestMixin
from erpnext.tests.utils import ERPNextTestSuite


class TestConsolidatedAccountsReceivable(ERPNextTestSuite, AccountsTestMixin):
	def setUp(self):
		self.maxDiff = None
		# deliberately unrelated companies, there is no parent/child link between them
		self.company_a = self.create_test_company("_Test Unrelated A", "_TUNA")
		self.company_b = self.create_test_company("_Test Unrelated B", "_TUNB")
		self.create_customer("_Test Consolidation Customer")
		self.create_item("_Test Consolidation Item")

	def test_rows_carry_the_company_they_came_from(self):
		self.create_invoice(self.company_a, "_TUNA", 200)
		self.create_invoice(self.company_b, "_TUNB", 300)

		rows = execute(self.filters())[1]

		self.assertEqual([r.company for r in rows], [self.company_a, self.company_b])
		self.assertFalse(any(r.parent_company for r in rows))

	def test_group_by_party_adds_one_subtotal_for_all_companies(self):
		self.create_invoice(self.company_a, "_TUNA", 200)
		self.create_invoice(self.company_b, "_TUNB", 300)

		result = execute(self.filters(group_by_party=1))
		subtotals = [row for row in result[1] if row.get("bold")]

		self.assertEqual(len(subtotals), 1)
		self.assertEqual(subtotals[0].outstanding, 500.0)
		self.assertEqual(result[5], 1)  # skip_total_row, else the grand total double counts

	def test_group_company_expands_to_its_subsidiaries(self):
		group = self.create_test_company("_Test Consolidation Group", "_TCGRP", is_group=1)
		child = self.create_test_company("_Test Consolidation Child", "_TCCLD", parent=group)
		self.create_invoice(child, "_TCCLD", 400)

		rows = execute(self.filters(companies=[group]))[1]

		self.assertEqual([r.company for r in rows], [child])
		self.assertEqual([r.parent_company for r in rows], [group])

	# ---------- helpers ----------
	def filters(self, companies=None, **kwargs):
		return {
			"companies": companies or [self.company_a, self.company_b],
			"party_type": "Customer",
			"party": [self.customer],
			"report_date": today(),
			"range": "30, 60, 90, 120",
			**kwargs,
		}

	def create_invoice(self, company, abbr, rate):
		return create_sales_invoice(
			item=self.item,
			company=company,
			customer=self.customer,
			debit_to=f"Debtors - {abbr}",
			income_account=f"Sales - {abbr}",
			cost_center=f"Main - {abbr}",
			parent_cost_center=f"Main - {abbr}",
			warehouse=f"Stores - {abbr}",
			posting_date=today(),
			rate=rate,
			price_list_rate=rate,
		)

	def create_test_company(self, company_name, abbr, currency="INR", is_group=0, parent=None):
		if frappe.db.exists("Company", company_name):
			return company_name

		company = frappe.new_doc("Company")
		company.company_name = company_name
		company.abbr = abbr
		company.country = "India"
		company.default_currency = currency
		company.create_chart_of_accounts_based_on = "Standard Template"
		company.chart_of_accounts = "Standard"
		company.is_group = is_group
		company.parent_company = parent
		company.insert()

		return company.name
