# Copyright (c) 2026, KAINOTOMO PH LTD and Contributors
# See license.txt

"""Tests for invoices_status.py: fix_unpaid_overdue_*_status.

Creates invoices via raw SQL to bypass ERPNext accounting validation
that requires a full chart of accounts.
"""

import frappe
from frappe.tests import IntegrationTestCase

from optimusland.optimusland.tests import (
	get_or_create_test_company,
	get_or_create_test_warehouse,
	get_or_create_test_supplier,
	get_or_create_test_customer,
)
from optimusland.utils.invoices_status import (
	fix_unpaid_overdue_purchase_invoices_status,
	fix_unpaid_overdue_sales_invoices_status,
)


class TestFixInvoiceStatus(IntegrationTestCase):
	"""Tests for invoice status fixers."""

	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		cls.company = get_or_create_test_company()
		cls.warehouse = get_or_create_test_warehouse(cls.company.name)
		cls.supplier = get_or_create_test_supplier(cls.company.name)
		cls.customer = get_or_create_test_customer(cls.company.name)
		cls.creditors_account = frappe.db.get_value("Account",
			{"company": cls.company.name, "account_type": "Payable", "is_group": 0})
		cls.debtors_account = frappe.db.get_value("Account",
			{"company": cls.company.name, "account_type": "Receivable", "is_group": 0})

	def _create_pi(self, name, status="Unpaid"):
		"""Create a Purchase Invoice record via raw SQL."""
		frappe.db.sql("""
			INSERT INTO `tabPurchase Invoice`
			(name, owner, creation, modified, modified_by, docstatus,
			 company, posting_date, due_date, supplier, status)
			VALUES (%s, 'Administrator', NOW(), NOW(), 'Administrator', 1,
			 %s, %s, %s, %s, %s)
		""", (name, self.company.name, frappe.utils.today(),
			  frappe.utils.today(), self.supplier.name, status))
		pi_item_name = f"{name}-item-1"
		frappe.db.sql("""
			INSERT INTO `tabPurchase Invoice Item`
			(name, parent, parenttype, parentfield, item_code, qty, rate, amount,
			 uom, stock_uom, conversion_factor, warehouse)
			VALUES (%s, %s, 'Purchase Invoice', 'items', '_Test Status Item',
			 10, 100.0, 1000.0, 'Nos', 'Nos', 1.0, %s)
		""", (pi_item_name, name, self.warehouse.name))
		# Create the GL entries
		account = self.creditors_account or "2110 - Creditors - OL"
		for i, (debit, credit) in enumerate([(1000, 0), (0, 1000)]):
			gl_name = f"{name}-gl-{i}"
			frappe.db.sql("""
				INSERT INTO `tabGL Entry`
				(name, posting_date, account, party_type, party,
				 debit_in_account_currency, credit_in_account_currency,
				 against, company, voucher_type, voucher_no, is_cancelled)
				VALUES (%s, %s, %s, 'Supplier', %s, %s, %s, %s, %s,
				 'Purchase Invoice', %s, 0)
			""", (gl_name, frappe.utils.today(), account, self.supplier.name,
				  debit, credit, name, self.company.name, name))

	def _create_si(self, name, status="Unpaid"):
		"""Create a Sales Invoice record via raw SQL."""
		frappe.db.sql("""
			INSERT INTO `tabSales Invoice`
			(name, owner, creation, modified, modified_by, docstatus,
			 company, posting_date, due_date, customer, status,
			 outstanding_amount)
			VALUES (%s, 'Administrator', NOW(), NOW(), 'Administrator', 1,
			 %s, %s, %s, %s, %s, %s)
		""", (name, self.company.name, frappe.utils.today(),
			  frappe.utils.today(), self.customer.name, status, 1000.0))
		si_item_name = f"{name}-item-1"
		frappe.db.sql("""
			INSERT INTO `tabSales Invoice Item`
			(name, parent, parenttype, parentfield, item_code, qty, rate, amount,
			 uom, stock_uom, conversion_factor, warehouse)
			VALUES (%s, %s, 'Sales Invoice', 'items', '_Test Status Item',
			 10, 100.0, 1000.0, 'Nos', 'Nos', 1.0, %s)
		""", (si_item_name, name, self.warehouse.name))
		account = self.debtors_account or "1310 - Debtors - OL"
		for i, (debit, credit) in enumerate([(1000, 0), (0, 1000)]):
			gl_name = f"{name}-gl-{i}"
			frappe.db.sql("""
				INSERT INTO `tabGL Entry`
				(name, posting_date, account, party_type, party,
				 debit_in_account_currency, credit_in_account_currency,
				 against, company, voucher_type, voucher_no, is_cancelled)
				VALUES (%s, %s, %s, 'Customer', %s, %s, %s, %s, %s,
				 'Sales Invoice', %s, 0)
			""", (gl_name, frappe.utils.today(), account, self.customer.name,
				  debit, credit, name, self.company.name, name))

	def test_fixes_paid_purchase_invoice(self):
		uniq = frappe.generate_hash("", 6)
		self._create_pi(f"TST-PINV-{uniq}")
		self.assertTrue(fix_unpaid_overdue_purchase_invoices_status())

	def test_fixes_paid_sales_invoice(self):
		uniq = frappe.generate_hash("", 6)
		self._create_si(f"TST-SINV-{uniq}")
		self.assertTrue(fix_unpaid_overdue_sales_invoices_status())
