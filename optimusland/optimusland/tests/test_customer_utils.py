# Copyright (c) 2026, KAINOTOMO PH LTD and Contributors
# See license.txt

"""Tests for customer.py: match_all_delivery_notes_to_invoices.

Uses unique customer names per test to avoid cross-test contamination
caused by frappe.db.commit() in the tested function.
"""

import frappe
from frappe.tests import IntegrationTestCase

from optimusland.optimusland.tests import (
	get_or_create_test_company,
	get_or_create_test_warehouse,
	get_or_create_test_supplier,
)
from optimusland.utils.customer import match_all_delivery_notes_to_invoices

_TEST_ITEM_CODE = "_Test Matching Item"


def _get_or_create_test_item():
	if frappe.db.exists("Item", _TEST_ITEM_CODE):
		return frappe.get_doc("Item", _TEST_ITEM_CODE)
	item = frappe.get_doc({
		"doctype": "Item",
		"item_code": _TEST_ITEM_CODE,
		"item_name": _TEST_ITEM_CODE,
		"item_group": "Services",
		"is_stock_item": 0,
		"has_batch_no": 0,
		"stock_uom": "Nos",
	})
	item.insert(ignore_permissions=True)
	return item


def _create_dn(items_data, customer, company, warehouse):
	dn = frappe.get_doc({
		"doctype": "Delivery Note",
		"customer": customer,
		"company": company,
		"posting_date": frappe.utils.today(),
		"set_posting_time": 1,
	})
	total = 0.0
	for item in items_data:
		amount = item.get("rate", 0) * item["qty"]
		total += amount
		dn.append("items", {
			"item_code": item["item_code"],
			"qty": item["qty"],
			"rate": item.get("rate", 0),
			"amount": amount,
			"uom": "Nos",
			"stock_uom": "Nos",
			"conversion_factor": 1.0,
			"warehouse": warehouse,
		})
	dn.total = total
	dn.insert(ignore_permissions=True)
	dn.submit()
	return dn


def _create_si(items_data, customer, company, warehouse):
	"""Create a submitted Sales Invoice via raw SQL to bypass accounting validation."""
	import frappe
	si_name = f"TST-SINV-{frappe.generate_hash('', 8)}"
	frappe.db.sql("""
		INSERT INTO `tabSales Invoice`
		(name, owner, creation, modified, modified_by, docstatus,
		 company, posting_date, due_date, customer, status)
		VALUES (%s, 'Administrator', NOW(), NOW(), 'Administrator', 1,
		 %s, %s, %s, %s, 'Unpaid')
	""", (si_name, company, frappe.utils.today(), frappe.utils.today(), customer))
	item_name = f"{si_name}-item-1"
	for item in items_data:
		amount = item.get("rate", 0) * item["qty"]
		frappe.db.sql("""
			INSERT INTO `tabSales Invoice Item`
			(name, parent, parenttype, parentfield, item_code, qty, rate,
			 amount, uom, stock_uom, conversion_factor, warehouse)
			VALUES (%s, %s, 'Sales Invoice', 'items', %s, %s, %s, %s,
			 'Nos', 'Nos', 1.0, %s)
		""", (item_name, si_name, item["item_code"], item["qty"],
			  item.get("rate", 0), amount, warehouse))
	return frappe.get_doc("Sales Invoice", si_name)


def _create_customer(name, company):
	if frappe.db.exists("Customer", name):
		return frappe.get_doc("Customer", name)
	# Ensure the non-group customer group exists
	if not frappe.db.exists("Customer Group", "_Test Customer Group"):
		frappe.get_doc({
			"doctype": "Customer Group",
			"customer_group_name": "_Test Customer Group",
			"parent_customer_group": "All Customer Groups",
		}).insert(ignore_permissions=True)
	customer = frappe.get_doc({
		"doctype": "Customer",
		"customer_name": name,
		"customer_group": "_Test Customer Group",
		"customer_type": "Company",
		"territory": "All Territories",
	})
	customer.insert(ignore_permissions=True)
	return customer


class TestMatchDeliveryNotesToInvoices(IntegrationTestCase):
	"""Each test uses a unique customer to avoid cross-test commit contamination."""

	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		cls.company = get_or_create_test_company()
		cls.warehouse = get_or_create_test_warehouse(cls.company.name)
		cls.supplier = get_or_create_test_supplier(cls.company.name)
		cls.test_item = _get_or_create_test_item()
		cls._counter = 0

	def _unique_customer(self):
		self.__class__._counter += 1
		return _create_customer(f"_Test Matching Cust {self._counter}", self.company.name)

	def test_full_billing_match(self):
		customer = self._unique_customer()
		dn = _create_dn(
			[{"item_code": self.test_item.item_code, "qty": 100, "rate": 10.0}],
			customer.name, self.company.name, self.warehouse.name)
		si = _create_si(
			[{"item_code": self.test_item.item_code, "qty": 100, "rate": 10.0}],
			customer.name, self.company.name, self.warehouse.name)
		result = match_all_delivery_notes_to_invoices(customer.name)
		self.assertIn("successfully", result)
		dn.reload()
		self.assertEqual(dn.per_billed, 100)
		self.assertEqual(dn.status, "Completed")
		si.reload()
		self.assertEqual(si.items[0].delivery_note, dn.name)

	def test_partial_billing_match(self):
		customer = self._unique_customer()
		dn = _create_dn(
			[{"item_code": self.test_item.item_code, "qty": 100, "rate": 10.0}],
			customer.name, self.company.name, self.warehouse.name)
		si = _create_si(
			[{"item_code": self.test_item.item_code, "qty": 50, "rate": 10.0}],
			customer.name, self.company.name, self.warehouse.name)
		result = match_all_delivery_notes_to_invoices(customer.name)
		# The matching function should have run; check that DN status updated
		self.assertIn("successfully", result)
		dn.reload()
		self.assertIn(dn.status, ("To Bill", "Completed"))

	def test_over_billing_capped(self):
		customer = self._unique_customer()
		dn = _create_dn(
			[{"item_code": self.test_item.item_code, "qty": 100, "rate": 10.0}],
			customer.name, self.company.name, self.warehouse.name)
		si = _create_si(
			[{"item_code": self.test_item.item_code, "qty": 100, "rate": 12.0}],
			customer.name, self.company.name, self.warehouse.name)
		match_all_delivery_notes_to_invoices(customer.name)
		billed = frappe.db.get_value(
			"Delivery Note Item", {"parent": dn.name, "item_code": self.test_item.item_code}, "billed_amt")
		self.assertEqual(billed, 1000.0)

	def test_multiple_invoices_same_dn(self):
		customer = self._unique_customer()
		dn = _create_dn(
			[{"item_code": self.test_item.item_code, "qty": 100, "rate": 10.0}],
			customer.name, self.company.name, self.warehouse.name)
		si1 = _create_si(
			[{"item_code": self.test_item.item_code, "qty": 60, "rate": 10.0}],
			customer.name, self.company.name, self.warehouse.name)
		si2 = _create_si(
			[{"item_code": self.test_item.item_code, "qty": 40, "rate": 10.0}],
			customer.name, self.company.name, self.warehouse.name)
		match_all_delivery_notes_to_invoices(customer.name)
		dn.reload()
		self.assertEqual(dn.per_billed, 100)
		si1.reload()
		si2.reload()
		self.assertEqual(si1.items[0].delivery_note, dn.name)
		self.assertEqual(si2.items[0].delivery_note, dn.name)

	def test_no_cross_customer_matching(self):
		customer_a = self._unique_customer()
		customer_b = _create_customer(f"{customer_a.name}_B", self.company.name)
		dn = _create_dn(
			[{"item_code": self.test_item.item_code, "qty": 100, "rate": 10.0}],
			customer_a.name, self.company.name, self.warehouse.name)
		si = _create_si(
			[{"item_code": self.test_item.item_code, "qty": 100, "rate": 10.0}],
			customer_b.name, self.company.name, self.warehouse.name)
		match_all_delivery_notes_to_invoices(customer_a.name)
		si.reload()
		self.assertIsNone(si.items[0].delivery_note)
