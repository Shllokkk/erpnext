# Copyright (c) 2015, Frappe Technologies Pvt. Ltd. and Contributors
# License: GNU General Public License v3. See license.txt

from collections import OrderedDict

import frappe
from frappe import _
from frappe.utils import flt

from erpnext.accounts.report.accounts_receivable_summary.accounts_receivable_summary import (
	AccountsReceivableSummary,
)
from erpnext.accounts.report.consolidated_financial_statement.consolidated_financial_statement import (
	get_subsidiary_companies,
)
from erpnext.accounts.utils import get_currency_precision, get_party_types_from_account_type

# What a party owes (or is owed) across companies that need not be related to each other.
# Each party gets one row per company, followed by a total row for that party.


def execute(filters=None):
	args = {
		"account_type": "Receivable",
		"naming_by": ["Selling Settings", "cust_master_name"],
	}
	return ConsolidatedReceivablePayableSummary(filters).run(args)


class ConsolidatedReceivablePayableSummary(AccountsReceivableSummary):
	def run(self, args):
		self.account_type = args.get("account_type")
		self.party_type = get_party_types_from_account_type(self.account_type)
		self.party_naming_by = frappe.db.get_single_value(args.get("naming_by")[0], args.get("naming_by")[1])
		self.currency_precision = get_currency_precision() or 2
		self.companies = self.get_companies()
		self.get_columns()
		self.get_data(args)
		return self.columns, self.data

	def get_companies(self):
		"""No companies selected simply yields an empty report, like the plain summaries."""
		companies = []
		for selected in self.filters.get("companies") or []:
			# a group company stands for the companies under it, each still its own row
			for company in get_subsidiary_companies(selected):
				if company not in companies:
					companies.append(company)

		currencies = {frappe.get_cached_value("Company", c, "default_currency") for c in companies}
		if len(currencies) > 1:
			frappe.throw(
				_("Companies being compared must share the same default currency. Found: {0}").format(
					", ".join(sorted(currencies))
				)
			)

		self.company_currency = currencies.pop() if currencies else None
		return companies

	def get_data(self, args):
		self.data = []
		for rows in self.get_rows_by_party(args).values():
			self.data.extend(rows)
			self.data.append(self.total_row(rows))

	def get_rows_by_party(self, args):
		"""One inner summary run per company, regrouped so a party's companies sit together."""
		by_party = OrderedDict()
		for company in self.companies:
			filters = frappe._dict(self.filters)
			filters.company = company
			filters.pop("companies", None)

			parent = frappe.get_cached_value("Company", company, "parent_company")
			for row in AccountsReceivableSummary(filters).run(args)[1]:
				row.company, row.parent_company = company, parent
				by_party.setdefault(row.party, []).append(row)

		return by_party

	def total_row(self, rows):
		# label sits in the first column, like the total row of the plain summary reports;
		# `bold` is picked up by the formatter in the report's js
		total = frappe._dict(
			party_type=_("Total"),
			party="",
			company="",
			currency=self.company_currency,
			bold=1,
		)
		for row in rows:
			for field, value in row.items():
				# `advance` arrives as an int when there is none, so don't filter on float alone
				if isinstance(value, int | float) and not isinstance(value, bool):
					total[field] = flt(total.get(field)) + value

		return total

	def get_columns(self):
		super().get_columns()
		at = self.company_column_index()
		self.columns.insert(
			at,
			dict(
				label=_("Company"),
				fieldname="company",
				fieldtype="Data",
				options=None,
				width=180,
				sticky=True,
			),
		)
		self.columns.insert(
			at + 1,
			dict(
				label=_("Parent Company"),
				fieldname="parent_company",
				fieldtype="Link",
				options="Company",
				width=160,
			),
		)

	def company_column_index(self):
		# straight after Party, and after the party name column when naming series is in use
		return 3 if self.party_naming_by == "Naming Series" else 2
