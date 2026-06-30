# Copyright (c) 2026, KAINOTOMO PH LTD and Contributors
# See license.txt

"""Tests for purchase_invoice.py: get_purchase_receipt_items.
"""

import frappe
from frappe.tests import IntegrationTestCase

from optimusland.optimusland.tests import (
	get_or_create_test_company,
	get_or_create_test_warehouse,
	get_or_create_test_supplier,
	get_or_create_test_potato_item,
	get_or_create_test_bom,
	get_or_create_test_packaging_item,
	setup_item_valuation,
	create_test_batch,
)
from optimusland.utils.purchase_invoice import get_purchase_receipt_items


class TestGetPurchaseReceiptItems(IntegrationTestCase):
	"""Tests for get_purchase_receipt_items (Purchase Invoice hook)."""

	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		cls.company = get_or_create_test_company()
		cls.warehouse = get_or_create_test_warehouse(cls.company.name)
		cls.supplier = get_or_create_test_supplier(cls.company.name)
		cls.potato_item = get_or_create_test_potato_item(cls.company.name)
		cls.bom = get_or_create_test_bom(cls.potato_item.item_code, cls.company.name)
		cls.packaging_item = get_or_create_test_packaging_item(cls.company.name)
		# Ensure BOM component has stock
		setup_item_valuation(cls.packaging_item.item_code, 0.50, cls.company.name)
		# Use a non-batch/non-potato item for simpler PR creation
		if not frappe.db.exists("Item", "_Test Invoice Item"):
			item = frappe.get_doc({
				"doctype": "Item",
				"item_code": "_Test Invoice Item",
				"item_name": "_Test Invoice Item",
				"item_group": "All Item Groups",
				"is_stock_item": 0,
				"has_batch_no": 0,
				"stock_uom": "Nos",
			})
			item.insert(ignore_permissions=True)
		cls.test_item = frappe.get_doc("Item", "_Test Invoice Item")

	def test_links_unbilled_pr_to_pi(self):
		"""PI item without PR link → matched to unbilled PR."""
		pr = frappe.get_doc({
			"doctype": "Purchase Receipt",
			"supplier": self.supplier.name,
			"company": self.company.name,
			"posting_date": frappe.utils.today(),
			"set_posting_time": 1,
			"items": [{
				"item_code": self.test_item.item_code,
				"qty": 100,
				"rate": 0.50,
				"uom": "Nos",
				"stock_uom": "Nos",
				"conversion_factor": 1.0,
				"warehouse": self.warehouse.name,
			}],
		})
		pr.insert(ignore_permissions=True)
		pr.submit()

		pi = frappe.get_doc({
			"doctype": "Purchase Invoice",
			"supplier": self.supplier.name,
			"company": self.company.name,
			"posting_date": frappe.utils.today(),
			"due_date": frappe.utils.today(),
			"items": [{
				"item_code": self.test_item.item_code,
				"qty": 100,
				"rate": 0.50,
				"warehouse": self.warehouse.name,
				"uom": "Nos",
				"stock_uom": "Nos",
				"conversion_factor": 1.0,
			}],
		})
		pi.insert(ignore_permissions=True)

		get_purchase_receipt_items(pi, method=None)

		self.assertEqual(pi.items[0].purchase_receipt, pr.name)

	def test_skips_already_linked_items(self):
		"""Item with existing purchase_receipt → skipped."""
		pr = frappe.get_doc({
			"doctype": "Purchase Receipt",
			"supplier": self.supplier.name,
			"company": self.company.name,
			"posting_date": frappe.utils.today(),
			"set_posting_time": 1,
			"items": [{
				"item_code": self.test_item.item_code,
				"qty": 100,
				"rate": 0.50,
				"uom": "Nos",
				"stock_uom": "Nos",
				"conversion_factor": 1.0,
				"warehouse": self.warehouse.name,
			}],
		})
		pr.insert(ignore_permissions=True)
		pr.submit()

		pi = frappe.get_doc({
			"doctype": "Purchase Invoice",
			"supplier": self.supplier.name,
			"company": self.company.name,
			"posting_date": frappe.utils.today(),
			"due_date": frappe.utils.today(),
			"items": [{
				"item_code": self.test_item.item_code,
				"qty": 100,
				"rate": 0.50,
				"warehouse": self.warehouse.name,
				"uom": "Nos",
				"stock_uom": "Nos",
				"conversion_factor": 1.0,
				"purchase_receipt": pr.name,
			}],
		})
		pi.insert(ignore_permissions=True)

		try:
			get_purchase_receipt_items(pi, method=None)
		except Exception as e:
			self.fail(f"get_purchase_receipt_items raised: {e}")

		self.assertEqual(pi.items[0].purchase_receipt, pr.name)
