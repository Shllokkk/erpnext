# Copyright (c) 2015, Frappe Technologies Pvt. Ltd. and Contributors
# License: GNU General Public License v3. See license.txt

from collections import OrderedDict

import frappe
from frappe import _
from frappe.utils import flt

from erpnext.accounts.report.accounts_receivable_summary.accounts_receivable_summary import (
	AccountsReceivableSummary,
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
		self.companies = self.validate_filters()
		self.get_columns()
		self.get_data(args)
		return self.columns, self.data

	def validate_filters(self):
		companies = self.filters.get("companies") or []
		if len(companies) < 2:
			frappe.throw(_("Select at least two Companies to compare"))

		# this is a party-centric view, scanning every party of every company is not the intent
		if not self.filters.get("party"):
			frappe.throw(_("Select a Party"))

		currencies = {frappe.get_cached_value("Company", c, "default_currency") for c in companies}
		if len(currencies) > 1:
			frappe.throw(
				_("Companies being compared must share the same default currency. Found: {0}").format(
					", ".join(sorted(currencies))
				)
			)

		self.company_currency = currencies.pop()
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

			for row in AccountsReceivableSummary(filters).run(args)[1]:
				row.company = company
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
		self.columns.insert(
			self.company_column_index(),
			dict(label=_("Company"), fieldname="company", fieldtype="Data", options=None, width=180),
		)

	def company_column_index(self):
		# straight after Party, and after the party name column when naming series is in use
		return 3 if self.party_naming_by == "Naming Series" else 2
