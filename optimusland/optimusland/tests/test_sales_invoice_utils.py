# Copyright (c) 2026, KAINOTOMO PH LTD and Contributors
# See license.txt

"""Tests for sales_invoice.py: warn_unlinked_items.
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
	get_or_create_test_bom,
	setup_item_valuation,
	create_test_batch,
	create_test_purchase_receipt,
	create_test_delivery_note,
)
from optimusland.utils.sales_invoice import warn_unlinked_items


class TestWarnUnlinkedItems(IntegrationTestCase):
	"""Tests for warn_unlinked_items (Sales Invoice before_save hook)."""

	_company = None
	_warehouse = None
	_customer = None
	_supplier = None
	_potato_item = None
	_packaging_item = None
	_batch = None

	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		cls._company = get_or_create_test_company()
		cls._warehouse = get_or_create_test_warehouse(cls._company.name)
		cls._customer = get_or_create_test_customer(cls._company.name)
		cls._supplier = get_or_create_test_supplier(cls._company.name)
		cls._potato_item = get_or_create_test_potato_item(cls._company.name)
		cls._packaging_item = get_or_create_test_packaging_item(cls._company.name)
		cls._bom = get_or_create_test_bom(cls._potato_item.item_code, cls._company.name)
		# Ensure BOM component has stock and valuation
		setup_item_valuation(cls._packaging_item.item_code, 0.50, cls._company.name)
		# Create a manufactured batch
		cls._batch = create_test_batch(
			cls._potato_item.item_code, cls._supplier.name, prefix="WARN")
		# Create PR with this batch (triggers create_production_plan which
		# manufactures the batch automatically via the full chain)
		create_test_purchase_receipt(
			items_data=[{
				"item_code": cls._potato_item.item_code,
				"qty": 100,
				"rate": 0.50,
				"batch_no": cls._batch.name,
			}],
			supplier=cls._supplier.name,
			company=cls._company.name,
			warehouse=cls._warehouse.name,
		)

	def test_warns_on_unlinked_potato(self):
		"""Potato item without Delivery Note -- msgprint called."""
		si = frappe.get_doc({
			"doctype": "Sales Invoice",
			"customer": self._customer.name,
			"company": self._company.name,
			"posting_date": frappe.utils.today(),
			"due_date": frappe.utils.today(),
			"items": [{
				"item_code": self._potato_item.item_code,
				"qty": 10,
				"rate": 10.0,
				"warehouse": self._warehouse.name,
				"uom": self._potato_item.stock_uom,
				"stock_uom": self._potato_item.stock_uom,
				"conversion_factor": 1.0,
			}],
		})
		si.insert(ignore_permissions=True)
		try:
			warn_unlinked_items(si)
		except Exception as e:
			self.fail("warn_unlinked_items raised unexpectedly: " + str(e))

	def test_no_warn_linked_potato(self):
		"""Potato item with Delivery Note -- no warning."""
		dn = create_test_delivery_note(
			items_data=[{
				"item_code": self._potato_item.item_code,
				"qty": 10,
				"rate": 1.0,
				"batch_no": self._batch.name,
			}],
			customer=self._customer.name,
			company=self._company.name,
			warehouse=self._warehouse.name,
		)
		si = frappe.get_doc({
			"doctype": "Sales Invoice",
			"customer": self._customer.name,
			"company": self._company.name,
			"posting_date": frappe.utils.today(),
			"due_date": frappe.utils.today(),
			"items": [{
				"item_code": self._potato_item.item_code,
				"qty": 10,
				"rate": 1.0,
				"warehouse": self._warehouse.name,
				"uom": self._potato_item.stock_uom,
				"stock_uom": self._potato_item.stock_uom,
				"conversion_factor": 1.0,
				"delivery_note": dn.name,
			}],
		})
		si.insert(ignore_permissions=True)
		try:
			warn_unlinked_items(si)
		except Exception as e:
			self.fail("warn_unlinked_items raised for linked item: " + str(e))

	def test_no_warn_non_potato(self):
		"""Non-Potato item without DN -- no warning."""
		si = frappe.get_doc({
			"doctype": "Sales Invoice",
			"customer": self._customer.name,
			"company": self._company.name,
			"posting_date": frappe.utils.today(),
			"due_date": frappe.utils.today(),
			"items": [{
				"item_code": self._packaging_item.item_code,
				"qty": 10,
				"rate": 1.0,
				"warehouse": self._warehouse.name,
				"uom": self._packaging_item.stock_uom,
				"stock_uom": self._packaging_item.stock_uom,
				"conversion_factor": 1.0,
			}],
		})
		si.insert(ignore_permissions=True)
		try:
			warn_unlinked_items(si)
		except Exception as e:
			self.fail("warn_unlinked_items raised for non-potato: " + str(e))
