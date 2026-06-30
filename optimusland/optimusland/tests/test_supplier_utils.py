# Copyright (c) 2026, KAINOTOMO PH LTD and Contributors
# See license.txt

"""Tests for supplier.py: get_supplier_unlinked_journal_entries.
"""

import frappe
from frappe.tests import IntegrationTestCase

from optimusland.optimusland.tests import (
	get_or_create_test_company,
	get_or_create_test_supplier,
	get_or_create_test_customer,
)
from optimusland.utils.supplier import get_supplier_unlinked_journal_entries


class TestSupplierUnlinkedJEs(IntegrationTestCase):
	"""Tests for get_supplier_unlinked_journal_entries."""

	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		cls.company = get_or_create_test_company()
		cls.company_abbr = frappe.db.get_value("Company", cls.company.name, "abbr")
		cls.supplier = get_or_create_test_supplier(cls.company.name)
		# Ensure a Customer exists with the Supplier's name (needed for JE party validation)
		if not frappe.db.exists("Customer", cls.supplier.name):
			customer = get_or_create_test_customer(cls.company.name)
			# Create a copy with the supplier's name
			dup = frappe.copy_doc(customer)
			dup.customer_name = cls.supplier.name
			dup.insert(ignore_permissions=True)

	def test_no_unlinked_jvs_returns_true(self):
		"""Supplier with no JEs → returns True."""
		result = get_supplier_unlinked_journal_entries(self.supplier.name)
		self.assertTrue(result)

	def test_detects_unlinked_jvs(self):
		"""Supplier JEs that also appear as Customer → returns warning message."""
		# Find proper accounts for Supplier and Customer party types
		creditors_account = frappe.db.get_value("Account",
			{"company": self.company.name, "account_type": "Payable", "is_group": 0})
		debtors_account = frappe.db.get_value("Account",
			{"company": self.company.name, "account_type": "Receivable", "is_group": 0})

		# Create a JE with the supplier as both Supplier and Customer party
		je = frappe.get_doc({
			"doctype": "Journal Entry",
			"company": self.company.name,
			"posting_date": frappe.utils.today(),
			"accounts": [
				{
					"account": creditors_account,
					"party_type": "Supplier",
					"party": self.supplier.name,
					"debit_in_account_currency": 100,
					"credit_in_account_currency": 0,
				},
				{
					"account": debtors_account or creditors_account,
					"party_type": "Customer",
					"party": self.supplier.name,
					"debit_in_account_currency": 0,
					"credit_in_account_currency": 100,
					"reference_type": None,
					"reference_name": None,
				},
			],
		})
		je.insert(ignore_permissions=True)
		je.submit()

		result = get_supplier_unlinked_journal_entries(self.supplier.name)
		self.assertIsInstance(result, str)  # Returns HTML message string
		self.assertIn(self.supplier.name, result)
