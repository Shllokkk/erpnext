# Copyright (c) 2015, Frappe Technologies Pvt. Ltd. and Contributors
# License: GNU General Public License v3. See license.txt

from collections import OrderedDict

import frappe
from frappe import _
from frappe.model import numeric_fieldtypes
from frappe.utils import flt

from erpnext.accounts.report.accounts_receivable.accounts_receivable import ReceivablePayableReport
from erpnext.accounts.report.consolidated_financial_statement.consolidated_financial_statement import (
	get_subsidiary_companies,
)

# Outstanding invoices of a party across companies that need not be related to each other.
# Every row carries the company it belongs to, and a party's companies sit together.


def execute(filters=None):
	args = {
		"account_type": "Receivable",
		"naming_by": ["Selling Settings", "cust_master_name"],
	}
	return ConsolidatedReceivablePayable(filters).run(args)


class ConsolidatedReceivablePayable(ReceivablePayableReport):
	def run(self, args):
		self.companies = get_consolidated_companies(self.filters)
		self.filters.update(args)
		self.set_defaults()
		self.party_naming_by = frappe.db.get_single_value(args["naming_by"][0], args["naming_by"][1])

		self.get_columns()
		add_company_columns(self.columns)
		self.data = self.get_consolidated_data(args)
		self.get_chart_data()

		return self.columns, self.data, None, self.chart, None, self.skip_total_row

	def get_consolidated_data(self, args):
		data = []
		for rows in self.get_rows_by_party(args).values():
			data.extend(rows)
			if self.filters.get("group_by_party"):
				data.append(self.party_subtotal(rows))

		return data

	def get_rows_by_party(self, args):
		"""One engine run per company, regrouped so a party's companies sit together."""
		by_party = OrderedDict()
		for company in self.companies:
			filters = frappe._dict(self.filters)
			filters.company = company
			filters.pop("companies", None)
			# subtotals are appended once per party here, not once per company
			filters.group_by_party = 0

			parent = frappe.get_cached_value("Company", company, "parent_company")
			for row in ReceivablePayableReport(filters).run(args)[1]:
				row.company, row.parent_company = company, parent
				by_party.setdefault(row.party, []).append(row)

		return by_party

	def party_subtotal(self, rows):
		# same shape as the engine's own group-by-party subtotal
		subtotal = frappe._dict(party=rows[0].party, currency=rows[0].get("currency"), bold=1)
		for field in self.get_currency_fields():
			subtotal[field] = sum(flt(row.get(field)) for row in rows)

		return subtotal


def get_consolidated_companies(filters):
	"""Selected companies, a group company standing for the companies under it."""
	companies = []
	for selected in filters.get("companies") or []:
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

	return companies


def add_company_columns(columns):
	"""Company and its parent, right after the party columns, plus header alignment."""
	at = company_column_index(columns)
	columns.insert(
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
	columns.insert(
		at + 1,
		dict(
			label=_("Parent Company"),
			fieldname="parent_company",
			fieldtype="Link",
			options="Company",
			width=160,
		),
	)

	# datatable guesses alignment from the first row, which misreads an empty column
	for column in columns:
		column["align"] = "right" if column["fieldtype"] in numeric_fieldtypes else "left"


def company_column_index(columns):
	fieldnames = [column["fieldname"] for column in columns]
	for fieldname in ("party_name", "party"):
		if fieldname in fieldnames:
			return fieldnames.index(fieldname) + 1

	return 0
