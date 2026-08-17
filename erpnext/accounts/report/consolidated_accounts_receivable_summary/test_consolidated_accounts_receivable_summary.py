# Copyright (c) 2015, Frappe Technologies Pvt. Ltd. and Contributors
# License: GNU General Public License v3. See license.txt

import frappe
from frappe.utils import today

from erpnext.accounts.doctype.sales_invoice.test_sales_invoice import create_sales_invoice
from erpnext.accounts.report.accounts_receivable_summary.accounts_receivable_summary import (
	execute as execute_summary,
)
from erpnext.accounts.report.consolidated_accounts_receivable_summary.consolidated_accounts_receivable_summary import (
	execute,
)
from erpnext.accounts.test.accounts_mixin import AccountsTestMixin
from erpnext.tests.utils import ERPNextTestSuite


class TestConsolidatedAccountsReceivableSummary(ERPNextTestSuite, AccountsTestMixin):
	def setUp(self):
		self.maxDiff = None
		# deliberately unrelated companies, there is no parent/child link between them
		self.company_a = self.create_test_company("_Test Unrelated A", "_TUNA")
		self.company_b = self.create_test_company("_Test Unrelated B", "_TUNB")
		self.create_customer("_Test Consolidation Customer")
		self.create_item("_Test Consolidation Item")

	def test_party_gets_a_row_per_company_plus_a_total(self):
		self.create_invoice(self.company_a, "_TUNA", 200)
		self.create_invoice(self.company_b, "_TUNB", 300)

		rows = self.run_report()

		self.assertEqual([r.company for r in rows], [self.company_a, self.company_b, "Total"])
		self.assertEqual([r.outstanding for r in rows], [200.0, 300.0, 500.0])
		self.assertTrue(rows[-1].bold)

	def test_total_matches_individual_company_summaries(self):
		self.create_invoice(self.company_a, "_TUNA", 200)
		self.create_invoice(self.company_b, "_TUNB", 300)

		total = self.run_report()[-1].outstanding
		individual = sum(self.company_outstanding(company) for company in (self.company_a, self.company_b))

		self.assertEqual(total, individual)

	def test_company_without_transactions_is_omitted(self):
		self.create_invoice(self.company_a, "_TUNA", 200)

		rows = self.run_report()

		self.assertEqual([r.company for r in rows], [self.company_a, "Total"])
		self.assertEqual(rows[-1].outstanding, 200.0)

	def test_a_single_company_is_rejected(self):
		self.assertRaises(frappe.ValidationError, execute, self.filters(companies=[self.company_a]))

	def test_party_filter_is_mandatory(self):
		filters = self.filters()
		filters.pop("party")
		self.assertRaises(frappe.ValidationError, execute, filters)

	def test_companies_with_different_currencies_are_rejected(self):
		usd = self.create_test_company("_Test Unrelated USD", "_TUNU", currency="USD")
		self.assertRaises(frappe.ValidationError, execute, self.filters(companies=[self.company_a, usd]))

	# ---------- helpers ----------
	def filters(self, companies=None):
		return {
			"companies": companies or [self.company_a, self.company_b],
			"party_type": "Customer",
			"party": [self.customer],
			"report_date": today(),
			"range": "30, 60, 90, 120",
		}

	def run_report(self):
		return [row for row in execute(self.filters())[1] if row.party == self.customer]

	def company_outstanding(self, company):
		filters = {"company": company, "report_date": today(), "range": "30, 60, 90, 120"}
		return sum(r.outstanding for r in execute_summary(filters)[1] if r.party == self.customer)

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

	def create_test_company(self, company_name, abbr, currency="INR"):
		if frappe.db.exists("Company", company_name):
			return company_name

		company = frappe.new_doc("Company")
		company.company_name = company_name
		company.abbr = abbr
		company.country = "India"
		company.default_currency = currency
		company.create_chart_of_accounts_based_on = "Standard Template"
		company.chart_of_accounts = "Standard"
		company.insert()

		return company.name
