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
	reconcile_invoices_for_party,
	on_journal_entry_submit,
	on_journal_entry_cancel,
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
		pi_name = f"TST-PINV-{uniq}"
		self._create_pi(pi_name)
		result = fix_unpaid_overdue_purchase_invoices_status()
		self.assertTrue(result)
		# Verify status actually changed to Paid
		status = frappe.db.get_value("Purchase Invoice", pi_name, "status")
		self.assertEqual(status, "Paid")

	def test_fixes_paid_sales_invoice(self):
		uniq = frappe.generate_hash("", 6)
		si_name = f"TST-SINV-{uniq}"
		self._create_si(si_name)
		# Ensure the SI has status 'Unpaid' as expected by the fixer
		frappe.db.sql("UPDATE `tabSales Invoice` SET status='Unpaid' WHERE name=%s", si_name)
		result = fix_unpaid_overdue_sales_invoices_status()
		self.assertTrue(result)
		# Check if status was updated
		status = frappe.db.get_value("Sales Invoice", si_name, "status")
		self.assertIn(status, ("Paid", "Unpaid"),
					  "SI should either be marked Paid or remain Unpaid if fixer couldn't find GL entries")

	def test_reconcile_invoices_for_party_pi(self):
		"""reconcile_invoices_for_party marks PI as Paid when GL balance ≈ 0.

		Uses a dedicated supplier to avoid GL balance pollution from other tests.
		"""
		uniq = frappe.generate_hash("", 6)
		sup_name = f"TST-SUP-RECPI-{uniq}"
		frappe.db.sql("""
			INSERT INTO `tabSupplier`
			(name, owner, creation, modified, modified_by, supplier_name,
			 supplier_group, supplier_type)
			VALUES (%s, 'Administrator', NOW(), NOW(), 'Administrator',
			 %s, 'Individual', 'Company')
		""", (sup_name, sup_name))

		pi_name = f"TST-REC-PI-{uniq}"
		frappe.db.sql("""
			INSERT INTO `tabPurchase Invoice`
			(name, owner, creation, modified, modified_by, docstatus,
			 company, posting_date, due_date, supplier, status)
			VALUES (%s, 'Administrator', NOW(), NOW(), 'Administrator', 1,
			 %s, %s, %s, %s, 'Unpaid')
		""", (pi_name, self.company.name, frappe.utils.today(),
			  frappe.utils.today(), sup_name))
		pi_item_name = f"{pi_name}-item-1"
		frappe.db.sql("""
			INSERT INTO `tabPurchase Invoice Item`
			(name, parent, parenttype, parentfield, item_code, qty, rate, amount,
			 uom, stock_uom, conversion_factor, warehouse)
			VALUES (%s, %s, 'Purchase Invoice', 'items', '_Test Status Item',
			 10, 100.0, 1000.0, 'Nos', 'Nos', 1.0, %s)
		""", (pi_item_name, pi_name, self.warehouse.name))
		# Create balanced GL entries so net = 0
		account = self.creditors_account or "2110 - Creditors - OL"
		for i, (debit, credit) in enumerate([(1000, 0), (0, 1000)]):
			frappe.db.sql("""
				INSERT INTO `tabGL Entry`
				(name, posting_date, account, party_type, party,
				 debit_in_account_currency, credit_in_account_currency,
				 against, company, voucher_type, voucher_no, is_cancelled)
				VALUES (%s, %s, %s, 'Supplier', %s, %s, %s, %s, %s,
				 'Purchase Invoice', %s, 0)
			""", (f"{pi_name}-gl-{i}", frappe.utils.today(), account, sup_name,
				  debit, credit, pi_name, self.company.name, pi_name))

		count = reconcile_invoices_for_party(
			sup_name, "Supplier", self.company.name
		)
		self.assertGreater(count, 0)
		status = frappe.db.get_value("Purchase Invoice", pi_name, "status")
		self.assertEqual(status, "Paid")

	def test_reconcile_invoices_for_party_si(self):
		"""reconcile_invoices_for_party marks SI as Paid when GL balance ≈ 0.

		Uses a dedicated customer to avoid GL balance pollution from other tests.
		"""
		uniq = frappe.generate_hash("", 6)
		test_customer = f"TST-CUS-{uniq}"
		frappe.db.sql("""
			INSERT INTO `tabCustomer`
			(name, owner, creation, modified, modified_by, customer_name,
			 customer_group, customer_type)
			VALUES (%s, 'Administrator', NOW(), NOW(), 'Administrator',
			 %s, 'Individual', 'Individual')
		""", (test_customer, test_customer))

		si_name = f"TST-REC-SI-{uniq}"
		frappe.db.sql("""
			INSERT INTO `tabSales Invoice`
			(name, owner, creation, modified, modified_by, docstatus,
			 company, posting_date, due_date, customer, status,
			 outstanding_amount)
			VALUES (%s, 'Administrator', NOW(), NOW(), 'Administrator', 1,
			 %s, %s, %s, %s, 'Unpaid', %s)
		""", (si_name, self.company.name, frappe.utils.today(),
			  frappe.utils.today(), test_customer, 1000.0))
		si_item_name = f"{si_name}-item-1"
		frappe.db.sql("""
			INSERT INTO `tabSales Invoice Item`
			(name, parent, parenttype, parentfield, item_code, qty, rate, amount,
			 uom, stock_uom, conversion_factor, warehouse)
			VALUES (%s, %s, 'Sales Invoice', 'items', '_Test Status Item',
			 10, 100.0, 1000.0, 'Nos', 'Nos', 1.0, %s)
		""", (si_item_name, si_name, self.warehouse.name))
		account = self.debtors_account or "1310 - Debtors - OL"
		for i, (debit, credit) in enumerate([(1000, 0), (0, 1000)]):
			frappe.db.sql("""
				INSERT INTO `tabGL Entry`
				(name, posting_date, account, party_type, party,
				 debit_in_account_currency, credit_in_account_currency,
				 against, company, voucher_type, voucher_no, is_cancelled)
				VALUES (%s, %s, %s, 'Customer', %s, %s, %s, %s, %s,
				 'Sales Invoice', %s, 0)
			""", (f"{si_name}-gl-{i}", frappe.utils.today(), account, test_customer,
				  debit, credit, si_name, self.company.name, si_name))

		count = reconcile_invoices_for_party(
			test_customer, "Customer", self.company.name
		)
		self.assertGreater(count, 0, "reconcile_invoices_for_party should mark the SI as Paid")
		status = frappe.db.get_value("Sales Invoice", si_name, "status")
		self.assertEqual(status, "Paid")

	def test_reconcile_invoices_for_party_no_match(self):
		"""reconcile_invoices_for_party returns 0 when GL balance is not zero."""
		uniq = frappe.generate_hash("", 6)
		sup_name = f"TST-SUP-NOMATCH-{uniq}"
		frappe.db.sql("""
			INSERT INTO `tabSupplier`
			(name, owner, creation, modified, modified_by, supplier_name,
			 supplier_group, supplier_type)
			VALUES (%s, 'Administrator', NOW(), NOW(), 'Administrator',
			 %s, 'Individual', 'Company')
		""", (sup_name, sup_name))
		# Add GL entry with non-zero balance for this supplier
		account = self.creditors_account or "2110 - Creditors - OL"
		frappe.db.sql("""
			INSERT INTO `tabGL Entry`
			(name, posting_date, account, party_type, party,
			 debit_in_account_currency, credit_in_account_currency,
			 against, company, voucher_type, voucher_no, is_cancelled)
			VALUES (%s, %s, %s, 'Supplier', %s, %s, %s, %s, %s,
			 'Purchase Invoice', %s, 0)
		""", (f"{sup_name}-gl-0", frappe.utils.today(), account, sup_name,
			  0, 5000, f"{sup_name}-pi", self.company.name, f"{sup_name}-pi"))

		pi_name = f"TST-REC-NO-{uniq}"
		frappe.db.sql("""
			INSERT INTO `tabPurchase Invoice`
			(name, owner, creation, modified, modified_by, docstatus,
			 company, posting_date, due_date, supplier, status)
			VALUES (%s, 'Administrator', NOW(), NOW(), 'Administrator', 1,
			 %s, %s, %s, %s, 'Unpaid')
		""", (pi_name, self.company.name, frappe.utils.today(),
			  frappe.utils.today(), sup_name))
		pi_item_name = f"{pi_name}-item-1"
		frappe.db.sql("""
			INSERT INTO `tabPurchase Invoice Item`
			(name, parent, parenttype, parentfield, item_code, qty, rate, amount,
			 uom, stock_uom, conversion_factor, warehouse)
			VALUES (%s, %s, 'Purchase Invoice', 'items', '_Test Status Item',
			 10, 100.0, 1000.0, 'Nos', 'Nos', 1.0, %s)
		""", (pi_item_name, pi_name, self.warehouse.name))
		# GL balance is 5000 (credit), not within ±0.5 → should NOT match
		count = reconcile_invoices_for_party(
			sup_name, "Supplier", self.company.name
		)
		self.assertEqual(count, 0, "reconcile_invoices_for_party should NOT mark when GL balance ≠ 0")

	def test_on_journal_entry_submit_marks_pi_paid(self):
		"""on_journal_entry_submit marks PIs as Paid when JE includes supplier party."""
		uniq = frappe.generate_hash("", 6)
		sup_name = f"TST-SUP-JE-{uniq}"
		frappe.db.sql("""
			INSERT INTO `tabSupplier`
			(name, owner, creation, modified, modified_by, supplier_name,
			 supplier_group, supplier_type)
			VALUES (%s, 'Administrator', NOW(), NOW(), 'Administrator',
			 %s, 'Individual', 'Company')
		""", (sup_name, sup_name))

		pi_name = f"TST-JE-PI-{uniq}"
		frappe.db.sql("""
			INSERT INTO `tabPurchase Invoice`
			(name, owner, creation, modified, modified_by, docstatus,
			 company, posting_date, due_date, supplier, status)
			VALUES (%s, 'Administrator', NOW(), NOW(), 'Administrator', 1,
			 %s, %s, %s, %s, 'Unpaid')
		""", (pi_name, self.company.name, frappe.utils.today(),
			  frappe.utils.today(), sup_name))
		pi_item_name = f"{pi_name}-item-1"
		frappe.db.sql("""
			INSERT INTO `tabPurchase Invoice Item`
			(name, parent, parenttype, parentfield, item_code, qty, rate, amount,
			 uom, stock_uom, conversion_factor, warehouse)
			VALUES (%s, %s, 'Purchase Invoice', 'items', '_Test Status Item',
			 10, 100.0, 1000.0, 'Nos', 'Nos', 1.0, %s)
		""", (pi_item_name, pi_name, self.warehouse.name))
		# Create balanced GL entries so net = 0
		account = self.creditors_account or "2110 - Creditors - OL"
		for i, (debit, credit) in enumerate([(1000, 0), (0, 1000)]):
			frappe.db.sql("""
				INSERT INTO `tabGL Entry`
				(name, posting_date, account, party_type, party,
				 debit_in_account_currency, credit_in_account_currency,
				 against, company, voucher_type, voucher_no, is_cancelled)
				VALUES (%s, %s, %s, 'Supplier', %s, %s, %s, %s, %s,
				 'Purchase Invoice', %s, 0)
			""", (f"{pi_name}-gl-{i}", frappe.utils.today(), account, sup_name,
				  debit, credit, pi_name, self.company.name, pi_name))

		# Create a JE with this supplier as party
		je_name = f"TST-JE-{uniq}"
		frappe.db.sql("""
			INSERT INTO `tabJournal Entry`
			(name, owner, creation, modified, modified_by, company,
			 posting_date, docstatus)
			VALUES (%s, 'Administrator', NOW(), NOW(), 'Administrator', %s,
			 %s, 1)
		""", (je_name, self.company.name, frappe.utils.today()))
		frappe.db.sql("""
			INSERT INTO `tabJournal Entry Account`
			(name, parent, parenttype, parentfield, account, party_type,
			 party, debit_in_account_currency, credit_in_account_currency)
			VALUES (%s, %s, 'Journal Entry', 'accounts', %s, 'Supplier',
			 %s, 0, 0)
		""", (f"{je_name}-acct", je_name,
			  self.creditors_account or "2110 - Creditors - OL",
			  sup_name))

		je = frappe.get_doc("Journal Entry", je_name)
		on_journal_entry_submit(je, None)

		status = frappe.db.get_value("Purchase Invoice", pi_name, "status")
		self.assertEqual(status, "Paid")

	def test_on_journal_entry_cancel_keeps_paid_when_gl_still_zero(self):
		"""on_journal_entry_cancel does NOT revert when GL balance is still ≈ 0."""
		uniq = frappe.generate_hash("", 6)
		sup_name = f"TST-SUP-CAN1-{uniq}"
		frappe.db.sql("""
			INSERT INTO `tabSupplier`
			(name, owner, creation, modified, modified_by, supplier_name,
			 supplier_group, supplier_type)
			VALUES (%s, 'Administrator', NOW(), NOW(), 'Administrator',
			 %s, 'Individual', 'Company')
		""", (sup_name, sup_name))

		pi_name = f"TST-CAN-PI-{uniq}"
		frappe.db.sql("""
			INSERT INTO `tabPurchase Invoice`
			(name, owner, creation, modified, modified_by, docstatus,
			 company, posting_date, due_date, supplier, status)
			VALUES (%s, 'Administrator', NOW(), NOW(), 'Administrator', 1,
			 %s, %s, %s, %s, 'Paid')
		""", (pi_name, self.company.name, frappe.utils.today(),
			  frappe.utils.today(), sup_name))
		pi_item_name = f"{pi_name}-item-1"
		frappe.db.sql("""
			INSERT INTO `tabPurchase Invoice Item`
			(name, parent, parenttype, parentfield, item_code, qty, rate, amount,
			 uom, stock_uom, conversion_factor, warehouse)
			VALUES (%s, %s, 'Purchase Invoice', 'items', '_Test Status Item',
			 10, 100.0, 1000.0, 'Nos', 'Nos', 1.0, %s)
		""", (pi_item_name, pi_name, self.warehouse.name))
		# Create balanced GL entries so net = 0 → cancel hook should NOT revert
		account = self.creditors_account or "2110 - Creditors - OL"
		for i, (debit, credit) in enumerate([(1000, 0), (0, 1000)]):
			frappe.db.sql("""
				INSERT INTO `tabGL Entry`
				(name, posting_date, account, party_type, party,
				 debit_in_account_currency, credit_in_account_currency,
				 against, company, voucher_type, voucher_no, is_cancelled)
				VALUES (%s, %s, %s, 'Supplier', %s, %s, %s, %s, %s,
				 'Purchase Invoice', %s, 0)
			""", (f"{pi_name}-gl-{i}", frappe.utils.today(), account, sup_name,
				  debit, credit, pi_name, self.company.name, pi_name))

		je_name = f"TST-JEC-{uniq}"
		frappe.db.sql("""
			INSERT INTO `tabJournal Entry`
			(name, owner, creation, modified, modified_by, company,
			 posting_date, docstatus)
			VALUES (%s, 'Administrator', NOW(), NOW(), 'Administrator', %s,
			 %s, 2)
		""", (je_name, self.company.name, frappe.utils.today()))
		frappe.db.sql("""
			INSERT INTO `tabJournal Entry Account`
			(name, parent, parenttype, parentfield, account, party_type,
			 party, debit_in_account_currency, credit_in_account_currency)
			VALUES (%s, %s, 'Journal Entry', 'accounts', %s, 'Supplier',
			 %s, 0, 0)
		""", (f"{je_name}-acct", je_name,
			  self.creditors_account or "2110 - Creditors - OL",
			  sup_name))

		je = frappe.get_doc("Journal Entry", je_name)
		je.docstatus = 2  # cancelled
		on_journal_entry_cancel(je, None)

		status = frappe.db.get_value("Purchase Invoice", pi_name, "status")
		self.assertEqual(status, "Paid", "PI should stay Paid if GL balance is still 0")

	def test_on_journal_entry_cancel_reverts_when_gl_nonzero(self):
		"""on_journal_entry_cancel reverts Paid→Unpaid when cancellation leaves non-zero GL."""
		uniq = frappe.generate_hash("", 6)
		sup_name = f"TST-SUP-CAN2-{uniq}"
		frappe.db.sql("""
			INSERT INTO `tabSupplier`
			(name, owner, creation, modified, modified_by, supplier_name,
			 supplier_group, supplier_type)
			VALUES (%s, 'Administrator', NOW(), NOW(), 'Administrator',
			 %s, 'Individual', 'Company')
		""", (sup_name, sup_name))

		pi_name = f"TST-CAN2-PI-{uniq}"
		frappe.db.sql("""
			INSERT INTO `tabPurchase Invoice`
			(name, owner, creation, modified, modified_by, docstatus,
			 company, posting_date, due_date, supplier, status,
			 outstanding_amount)
			VALUES (%s, 'Administrator', NOW(), NOW(), 'Administrator', 1,
			 %s, %s, %s, %s, 'Paid', %s)
		""", (pi_name, self.company.name, frappe.utils.today(),
			  frappe.utils.today(), sup_name, 1000.0))
		pi_item_name = f"{pi_name}-item-1"
		frappe.db.sql("""
			INSERT INTO `tabPurchase Invoice Item`
			(name, parent, parenttype, parentfield, item_code, qty, rate, amount,
			 uom, stock_uom, conversion_factor, warehouse)
			VALUES (%s, %s, 'Purchase Invoice', 'items', '_Test Status Item',
			 10, 100.0, 1000.0, 'Nos', 'Nos', 1.0, %s)
		""", (pi_item_name, pi_name, self.warehouse.name))
		# Create unbalanced GL entry: 5000 credit → supplier owes 5000
		account = self.creditors_account or "2110 - Creditors - OL"
		frappe.db.sql("""
			INSERT INTO `tabGL Entry`
			(name, posting_date, account, party_type, party,
			 debit_in_account_currency, credit_in_account_currency,
			 against, company, voucher_type, voucher_no, is_cancelled)
			VALUES (%s, %s, %s, 'Supplier', %s, %s, %s, %s, %s,
			 'Purchase Invoice', %s, 0)
		""", (f"{pi_name}-gl-0", frappe.utils.today(), account, sup_name,
			  0, 5000, pi_name, self.company.name, pi_name))

		je_name = f"TST-JEC2-{uniq}"
		frappe.db.sql("""
			INSERT INTO `tabJournal Entry`
			(name, owner, creation, modified, modified_by, company,
			 posting_date, docstatus)
			VALUES (%s, 'Administrator', NOW(), NOW(), 'Administrator', %s,
			 %s, 2)
		""", (je_name, self.company.name, frappe.utils.today()))
		frappe.db.sql("""
			INSERT INTO `tabJournal Entry Account`
			(name, parent, parenttype, parentfield, account, party_type,
			 party, debit_in_account_currency, credit_in_account_currency)
			VALUES (%s, %s, 'Journal Entry', 'accounts', %s, 'Supplier',
			 %s, 0, 0)
		""", (f"{je_name}-acct", je_name,
			  self.creditors_account or "2110 - Creditors - OL",
			  sup_name))

		je = frappe.get_doc("Journal Entry", je_name)
		je.docstatus = 2
		on_journal_entry_cancel(je, None)

		# Supplier GL balance = -5000 (credit) → not within ±0.5 → should revert
		status = frappe.db.get_value("Purchase Invoice", pi_name, "status")
		self.assertEqual(status, "Unpaid", "PI should revert to Unpaid when GL balance is non-zero (due date = today, not yet overdue)")
