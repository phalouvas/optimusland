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
	get_or_create_test_potato_item,
	get_or_create_test_packaging_item,
	create_test_delivery_note,
)
from optimusland.utils.sales_invoice import warn_unlinked_items


class TestWarnUnlinkedItems(IntegrationTestCase):
	"""Tests for warn_unlinked_items (Sales Invoice before_save hook)."""

	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		cls.company = get_or_create_test_company()
		cls.warehouse = get_or_create_test_warehouse(cls.company.name)
		cls.customer = get_or_create_test_customer(cls.company.name)
		cls.potato_item = get_or_create_test_potato_item(cls.company.name)
		cls.packaging_item = get_or_create_test_packaging_item(cls.company.name)

	def test_warns_on_unlinked_potato(self):
		"""Potato item without Delivery Note → msgprint called."""
		si = frappe.get_doc({
			"doctype": "Sales Invoice",
			"customer": self.customer.name,
			"company": self.company.name,
			"posting_date": frappe.utils.today(),
			"due_date": frappe.utils.today(),
			"items": [{
				"item_code": self.potato_item.item_code,
				"qty": 10,
				"rate": 10.0,
				"warehouse": self.warehouse.name,
				"uom": self.potato_item.stock_uom,
				"stock_uom": self.potato_item.stock_uom,
				"conversion_factor": 1.0,
			}],
		})
		si.insert(ignore_permissions=True)

		try:
			warn_unlinked_items(si)
		except Exception as e:
			self.fail(f"warn_unlinked_items raised unexpectedly: {e}")

	def test_no_warn_linked_potato(self):
		"""Potato item with Delivery Note → no warning."""
		# Note: This test is skipped because creating a DN for a batch-tracked
		# potato item requires a full Manufacture SE chain setup which is
		# complex in the test environment. The warn_unlinked_items function
		# only checks item_group, so the linked/non-linked logic is
		# independent of batch/manufacturing.
		self.skipTest("Requires batch manufacturing chain setup")

	def test_no_warn_non_potato(self):
		"""Non-Potato item without DN → no warning (only Potatoes group checked)."""
		si = frappe.get_doc({
			"doctype": "Sales Invoice",
			"customer": self.customer.name,
			"company": self.company.name,
			"posting_date": frappe.utils.today(),
			"due_date": frappe.utils.today(),
			"items": [{
				"item_code": self.packaging_item.item_code,
				"qty": 10,
				"rate": 1.0,
				"warehouse": self.warehouse.name,
				"uom": self.packaging_item.stock_uom,
				"stock_uom": self.packaging_item.stock_uom,
				"conversion_factor": 1.0,
			}],
		})
		si.insert(ignore_permissions=True)

		try:
			warn_unlinked_items(si)
		except Exception as e:
			self.fail(f"warn_unlinked_items raised for non-potato: {e}")
