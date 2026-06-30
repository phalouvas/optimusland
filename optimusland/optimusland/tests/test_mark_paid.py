# Copyright (c) 2026, KAINOTOMO PH LTD and Contributors
# See license.txt

"""Tests for mark_paid in both sales_invoice.py and purchase_invoice.py.

These functions use raw SQL to bypass all Frappe validation — testing
them is critical since they are irreversible, one-click operations.
"""

import frappe
from frappe.tests import IntegrationTestCase

from optimusland.optimusland.tests import (
	get_or_create_test_company,
	get_or_create_test_warehouse,
	get_or_create_test_customer,
	get_or_create_test_supplier,
	get_or_create_test_potato_item,
	get_or_create_test_packaging_item,
	setup_item_valuation,
	create_test_batch,
	create_test_sales_invoice,
	create_test_purchase_receipt,
)
from optimusland.utils.sales_invoice import mark_paid as mark_si_paid
from optimusland.utils.purchase_invoice import mark_paid as mark_pi_paid


class TestMarkSalesInvoicePaid(IntegrationTestCase):
	"""Tests for sales_invoice.mark_paid."""

	# TEMPORARY: This will fail to verify pre-push hook works
	def test_push_hook_verification(self):
		"""DELETE THIS TEST after verifying — intentionally fails."""
		self.assertTrue(False, "Pre-push hook is working — this failure is intentional")

	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		cls.company = get_or_create_test_company()
		cls.warehouse = get_or_create_test_warehouse(cls.company.name)
		cls.customer = get_or_create_test_customer(cls.company.name)
		cls.potato_item = get_or_create_test_potato_item(cls.company.name)

	def test_mark_sales_invoice_paid(self):
		"""Submitted unpaid SI → status becomes Paid."""
		si = create_test_sales_invoice(
			items_data=[{
				"item_code": self.potato_item.item_code,
				"qty": 10,
				"rate": 10.0,
			}],
			customer=self.customer.name,
			company=self.company.name,
			warehouse=self.warehouse.name,
		)

		# Manually set status to Unpaid (submit sets it to something else)
		frappe.db.set_value("Sales Invoice", si.name, "status", "Unpaid")

		mark_si_paid(si.name)

		status = frappe.db.get_value("Sales Invoice", si.name, "status")
		self.assertEqual(status, "Paid")

	def test_mark_sales_invoice_paid_idempotent(self):
		"""Calling mark_paid twice doesn't error."""
		si = create_test_sales_invoice(
			items_data=[{
				"item_code": self.potato_item.item_code,
				"qty": 10,
				"rate": 10.0,
			}],
			customer=self.customer.name,
			company=self.company.name,
			warehouse=self.warehouse.name,
		)
		frappe.db.set_value("Sales Invoice", si.name, "status", "Unpaid")

		mark_si_paid(si.name)
		mark_si_paid(si.name)  # Second call — should not raise

		status = frappe.db.get_value("Sales Invoice", si.name, "status")
		self.assertEqual(status, "Paid")


class TestMarkPurchaseInvoicePaid(IntegrationTestCase):
	"""Tests for purchase_invoice.mark_paid."""

	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		cls.company = get_or_create_test_company()
		cls.warehouse = get_or_create_test_warehouse(cls.company.name)
		cls.supplier = get_or_create_test_supplier(cls.company.name)
		cls.potato_item = get_or_create_test_potato_item(cls.company.name)
		cls.packaging_item = get_or_create_test_packaging_item(cls.company.name)
		setup_item_valuation(cls.packaging_item.item_code, 0.50, cls.company.name)
		cls.test_batch = create_test_batch(cls.potato_item.item_code,
										   cls.supplier.name, prefix="MKRPAID")

	def test_mark_purchase_invoice_paid(self):
		"""Submitted unpaid PI → status becomes Paid."""
		pr = create_test_purchase_receipt(
			items_data=[{
				"item_code": self.potato_item.item_code,
				"qty": 10,
				"rate": 0.50,
				"batch_no": self.test_batch.name,
			}],
			supplier=self.supplier.name,
			company=self.company.name,
			warehouse=self.warehouse.name,
		)

		pi = frappe.get_doc({
			"doctype": "Purchase Invoice",
			"supplier": self.supplier.name,
			"company": self.company.name,
			"posting_date": frappe.utils.today(),
			"due_date": frappe.utils.today(),
			"items": [{
				"item_code": self.potato_item.item_code,
				"qty": 10,
				"rate": 0.50,
				"warehouse": self.warehouse.name,
				"uom": self.potato_item.stock_uom,
				"stock_uom": self.potato_item.stock_uom,
				"conversion_factor": 1.0,
				"purchase_receipt": pr.name,
			}],
		})
		pi.insert(ignore_permissions=True)
		pi.submit()
		frappe.db.set_value("Purchase Invoice", pi.name, "status", "Unpaid")

		mark_pi_paid(pi.name)

		status = frappe.db.get_value("Purchase Invoice", pi.name, "status")
		self.assertEqual(status, "Paid")

	def test_mark_purchase_invoice_paid_idempotent(self):
		"""Calling mark_paid twice doesn't error."""
		pr = create_test_purchase_receipt(
			items_data=[{
				"item_code": self.potato_item.item_code,
				"qty": 10,
				"rate": 0.50,
				"batch_no": self.test_batch.name,
			}],
			supplier=self.supplier.name,
			company=self.company.name,
			warehouse=self.warehouse.name,
		)

		pi = frappe.get_doc({
			"doctype": "Purchase Invoice",
			"supplier": self.supplier.name,
			"company": self.company.name,
			"posting_date": frappe.utils.today(),
			"due_date": frappe.utils.today(),
			"items": [{
				"item_code": self.potato_item.item_code,
				"qty": 10,
				"rate": 0.50,
				"warehouse": self.warehouse.name,
				"uom": self.potato_item.stock_uom,
				"stock_uom": self.potato_item.stock_uom,
				"conversion_factor": 1.0,
				"purchase_receipt": pr.name,
			}],
		})
		pi.insert(ignore_permissions=True)
		pi.submit()
		frappe.db.set_value("Purchase Invoice", pi.name, "status", "Unpaid")

		mark_pi_paid(pi.name)
		mark_pi_paid(pi.name)

		status = frappe.db.get_value("Purchase Invoice", pi.name, "status")
		self.assertEqual(status, "Paid")
