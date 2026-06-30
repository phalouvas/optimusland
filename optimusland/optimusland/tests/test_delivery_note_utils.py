# Copyright (c) 2026, KAINOTOMO PH LTD and Contributors
# See license.txt

"""Tests for delivery_note.py: add_shipping_cost, remove_shipping_cost, validate_batch_manufacture.

Shipping cost tests use a non-stock item to avoid stock ledger complexity.
validate_batch_manufacture tests use the potato item with manufactured batch setup.
"""

import frappe
from frappe.tests import IntegrationTestCase

from optimusland.optimusland.tests import (
	get_or_create_test_company,
	get_or_create_test_warehouse,
	get_or_create_test_supplier,
	get_or_create_test_customer,
	get_or_create_test_potato_item,
	get_or_create_test_bom,
	get_or_create_test_packaging_item,
	setup_item_valuation,
	create_test_batch,
	create_test_manufacture_stock_entry,
	create_test_sales_invoice,
)
from optimusland.utils.delivery_note import (
	add_shipping_cost,
	remove_shipping_cost,
	validate_batch_manufacture,
)

# Non-stock item for shipping cost tests
_SHIP_ITEM = "_Test Shipping Item"


def _get_ship_item():
	if frappe.db.exists("Item", _SHIP_ITEM):
		return frappe.get_doc("Item", _SHIP_ITEM)
	item = frappe.get_doc({
		"doctype": "Item",
		"item_code": _SHIP_ITEM,
		"item_name": _SHIP_ITEM,
		"item_group": "Services",
		"is_stock_item": 0,
		"has_batch_no": 0,
		"stock_uom": "Nos",
	})
	item.insert(ignore_permissions=True)
	return item


def _create_dn(items_data, customer, company, warehouse, do_not_submit=False):
	"""Create a DN with the given items."""
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
			"batch_no": item.get("batch_no"),
		})
	dn.total = total
	dn.insert(ignore_permissions=True)
	if not do_not_submit:
		dn.submit()
	return dn


class TestAddRemoveShippingCost(IntegrationTestCase):
	"""Tests for add_shipping_cost and remove_shipping_cost."""

	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		cls.company = get_or_create_test_company()
		cls.warehouse = get_or_create_test_warehouse(cls.company.name)
		cls.customer = get_or_create_test_customer(cls.company.name)
		cls.ship_item = _get_ship_item()

	def test_add_shipping_cost_basic(self):
		dn = _create_dn(
			[{"item_code": self.ship_item.item_code, "qty": 1000, "rate": 0.50}],
			self.customer.name, self.company.name, self.warehouse.name)
		self.assertTrue(add_shipping_cost(dn.name, 100.0))
		dn.reload()
		self.assertEqual(dn.custom_shipping_cost, 100.0)
		self.assertEqual(dn.custom_shipping_rate, 0.10)
		self.assertEqual(dn.custom_is_shipping_cost_added, 1)

	def test_add_shipping_cost_cumulative(self):
		dn = _create_dn(
			[{"item_code": self.ship_item.item_code, "qty": 1000, "rate": 0.50}],
			self.customer.name, self.company.name, self.warehouse.name)
		add_shipping_cost(dn.name, 100.0)
		add_shipping_cost(dn.name, 50.0)
		dn.reload()
		self.assertEqual(dn.custom_shipping_rate, 0.15)

	def test_add_shipping_cost_with_purchase_invoice(self):
		dn = _create_dn(
			[{"item_code": self.ship_item.item_code, "qty": 100, "rate": 10.0}],
			self.customer.name, self.company.name, self.warehouse.name)
		add_shipping_cost(dn.name, 50.0, purchase_invoice="PI-TEST-001")
		dn.reload()
		self.assertEqual(dn.custom_shipping_purchase_invoice, "PI-TEST-001")

	def test_add_shipping_cost_zero_cost_raises(self):
		dn = _create_dn(
			[{"item_code": self.ship_item.item_code, "qty": 100, "rate": 10.0}],
			self.customer.name, self.company.name, self.warehouse.name)
		with self.assertRaises(frappe.ValidationError):
			add_shipping_cost(dn.name, 0)

	def test_add_shipping_cost_unsubmitted_dn_raises(self):
		dn = _create_dn(
			[{"item_code": self.ship_item.item_code, "qty": 100, "rate": 10.0}],
			self.customer.name, self.company.name, self.warehouse.name, do_not_submit=True)
		with self.assertRaises(frappe.ValidationError):
			add_shipping_cost(dn.name, 50.0)

	def test_remove_shipping_cost(self):
		dn = _create_dn(
			[{"item_code": self.ship_item.item_code, "qty": 100, "rate": 10.0}],
			self.customer.name, self.company.name, self.warehouse.name)
		add_shipping_cost(dn.name, 100.0)
		self.assertTrue(remove_shipping_cost(dn.name))
		dn.reload()
		self.assertEqual(dn.custom_shipping_cost, 0)
		self.assertEqual(dn.custom_shipping_rate, 0)
		self.assertEqual(dn.custom_is_shipping_cost_added, 0)
		self.assertIsNone(dn.custom_shipping_purchase_invoice)

	def test_remove_without_add_raises(self):
		dn = _create_dn(
			[{"item_code": self.ship_item.item_code, "qty": 100, "rate": 10.0}],
			self.customer.name, self.company.name, self.warehouse.name)
		with self.assertRaises(frappe.ValidationError):
			remove_shipping_cost(dn.name)

	def test_add_shipping_cost_with_linked_sales_invoice(self):
		"""Shipping cost can still be added when linked SI exists, but warning comment is logged."""
		dn = _create_dn(
			[{"item_code": self.ship_item.item_code, "qty": 1000, "rate": 0.50}],
			self.customer.name, self.company.name, self.warehouse.name)

		# Create a submitted Sales Invoice linked to the DN
		create_test_sales_invoice(
			[{"item_code": self.ship_item.item_code, "qty": 1000, "rate": 1.00,
			  "delivery_note": dn.name}],
			customer=self.customer.name, company=self.company.name,
			warehouse=self.warehouse.name)

		# Adding shipping should still succeed despite the linked SI
		self.assertTrue(add_shipping_cost(dn.name, 100.0))

		# Verify shipping was applied
		dn.reload()
		self.assertEqual(dn.custom_shipping_cost, 100.0)
		self.assertEqual(dn.custom_shipping_rate, 0.10)
		self.assertEqual(dn.custom_is_shipping_cost_added, 1)

		# Verify a warning comment was logged about the linked SI not being updated
		comments = frappe.get_all("Comment",
			filters={
				"reference_doctype": "Delivery Note",
				"reference_name": dn.name,
				"comment_type": "Info",
			},
			fields=["content"],
			order_by="creation desc",
			limit=1,
		)
		self.assertTrue(
			any("NOT updated" in c.content for c in comments),
			"Expected warning comment about linked SI not being updated",
		)

	def test_add_shipping_cost_without_linked_sales_invoice(self):
		"""Adding shipping cost without linked SI should work normally (no warning comment)."""
		dn = _create_dn(
			[{"item_code": self.ship_item.item_code, "qty": 1000, "rate": 0.50}],
			self.customer.name, self.company.name, self.warehouse.name)

		self.assertTrue(add_shipping_cost(dn.name, 100.0))

		# Verify no warning about linked SIs in the comment
		comments = frappe.get_all("Comment",
			filters={
				"reference_doctype": "Delivery Note",
				"reference_name": dn.name,
				"comment_type": "Info",
			},
			fields=["content"],
			order_by="creation desc",
			limit=1,
		)
		self.assertFalse(
			any("NOT updated" in c.content for c in comments),
			"Expected no warning comment about linked SI",
		)


class TestValidateBatchManufacture(IntegrationTestCase):
	"""Tests for validate_batch_manufacture (Delivery Note before_submit hook)."""

	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		cls.company = get_or_create_test_company()
		cls.warehouse = get_or_create_test_warehouse(cls.company.name)
		cls.customer = get_or_create_test_customer(cls.company.name)
		cls.supplier = get_or_create_test_supplier(cls.company.name)
		cls.potato_item = get_or_create_test_potato_item(cls.company.name)
		cls.bom = get_or_create_test_bom(cls.potato_item.item_code, cls.company.name)
		cls.packaging_item = get_or_create_test_packaging_item(cls.company.name)
		# Ensure packaging item has stock for BOM-based manufacturing
		setup_item_valuation(cls.packaging_item.item_code, 0.50, cls.company.name)
		# Create a non-potato batch item
		if not frappe.db.exists("Item", "_Test Non Potato"):
			np = frappe.get_doc({
				"doctype": "Item",
				"item_code": "_Test Non Potato",
				"item_name": "_Test Non Potato",
				"item_group": "Raw Material",
				"is_stock_item": 0,
				"has_batch_no": 1,
				"stock_uom": "Nos",
			})
			np.insert(ignore_permissions=True)
		cls.non_potato_item = frappe.get_doc("Item", "_Test Non Potato")

	def _setup_manufactured_batch(self, prefix="BATCH"):
		"""Create a batch with a Manufacture SE so DN submission passes."""
		batch = create_test_batch(
			self.potato_item.item_code, self.supplier.name, prefix=prefix)
		# Create a PR that brings stock into the specific batch
		pr = frappe.get_doc({
			"doctype": "Purchase Receipt",
			"supplier": self.supplier.name,
			"company": self.company.name,
			"posting_date": frappe.utils.today(),
			"set_posting_time": 1,
			"items": [{
				"item_code": self.potato_item.item_code,
				"qty": 100,
				"rate": 0.50,
				"uom": self.potato_item.stock_uom,
				"stock_uom": self.potato_item.stock_uom,
				"conversion_factor": 1.0,
				"warehouse": self.warehouse.name,
				"batch_no": batch.name,
			}],
		})
		pr.insert(ignore_permissions=True)
		pr.submit()
		# Create the Manufacture SE consuming from this batch
		create_test_manufacture_stock_entry(
			self.potato_item.item_code, batch.name, 90,
			company=self.company.name, warehouse=self.warehouse.name)
		return batch

	def test_manufactured_batch_passes(self):
		batch = self._setup_manufactured_batch("PASS")
		dn = _create_dn(
			[{"item_code": self.potato_item.item_code, "qty": 10, "rate": 1.0,
			  "batch_no": batch.name}],
			self.customer.name, self.company.name, self.warehouse.name, do_not_submit=True)
		try:
			validate_batch_manufacture(dn)
		except Exception as e:
			self.fail(f"validate_batch_manufacture raised: {e}")

	def test_unmanufactured_batch_blocked(self):
		batch = create_test_batch(
			self.potato_item.item_code, self.supplier.name, prefix="BLOCK")
		dn = _create_dn(
			[{"item_code": self.potato_item.item_code, "qty": 10, "rate": 1.0,
			  "batch_no": batch.name}],
			self.customer.name, self.company.name, self.warehouse.name, do_not_submit=True)
		with self.assertRaises(frappe.ValidationError):
			validate_batch_manufacture(dn)

	def test_non_potato_item_skipped(self):
		batch = create_test_batch(
			self.non_potato_item.item_code, self.supplier.name, prefix="SKIP")
		dn = _create_dn(
			[{"item_code": self.non_potato_item.item_code, "qty": 10, "rate": 1.0,
			  "batch_no": batch.name}],
			self.customer.name, self.company.name, self.warehouse.name, do_not_submit=True)
		try:
			validate_batch_manufacture(dn)
		except Exception as e:
			self.fail(f"validate_batch_manufacture raised for non-potato: {e}")
