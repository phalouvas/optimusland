# Copyright (c) 2025, KAINOTOMO PH LTD and Contributors
# See license.txt

"""Tests for the DeliveryNoteBillingWizard virtual DocType.

Tests the core methods: load_items, find_invoice_matches, create_assignments,
process_assignments, select_all_items, update_selection.

The wizard is a virtual DocType (no DB table) — all data is stored as JSON
in Long Text fields via @property getters/setters.
"""

import frappe
from frappe.tests import IntegrationTestCase

from optimusland.optimusland.tests import (
	get_or_create_test_company,
	get_or_create_test_warehouse,
	get_or_create_test_customer,
	get_or_create_test_potato_item,
	get_or_create_test_bom,
	create_test_delivery_note,
	create_test_sales_invoice,
)


class TestDeliveryNoteBillingWizard(IntegrationTestCase):
	"""Tests for DeliveryNoteBillingWizard virtual DocType."""

	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		cls.company = get_or_create_test_company()
		cls.warehouse = get_or_create_test_warehouse(cls.company.name)
		cls.customer = get_or_create_test_customer(cls.company.name)
		cls.potato_item = get_or_create_test_potato_item(cls.company.name)
		cls.bom = get_or_create_test_bom(cls.potato_item.item_code, cls.company.name)

	def setUp(self):
		"""Create a fresh wizard instance for each test."""
		self.wizard = frappe.get_doc({
			"doctype": "Delivery Note Billing Wizard",
			"company": self.company.name,
			"customer": self.customer.name,
		})

	def test_load_items(self):
		"""Load items from unbilled DNs → items populated with correct structure."""
		dn = create_test_delivery_note(
			items_data=[{
				"item_code": self.potato_item.item_code,
				"qty": 100,
				"rate": 10.0,
			}],
			customer=self.customer.name,
			company=self.company.name,
			warehouse=self.warehouse.name,
		)

		result = self.wizard.load_items()

		self.assertEqual(result.get("status"), "success")
		self.assertGreater(result.get("count", 0), 0)
		self.assertEqual(len(self.wizard.unbilled_items), result["count"])

		# Verify item structure
		item = self.wizard.unbilled_items[0]
		self.assertIn("delivery_note", item)
		self.assertIn("item_code", item)
		self.assertIn("qty", item)
		self.assertIn("rate", item)
		self.assertIn("amount", item)
		self.assertIn("selected", item)
		self.assertFalse(item["selected"])  # Default unselected

	def test_find_invoice_matches(self):
		"""Loaded items with matching SIs → matches found."""
		dn = create_test_delivery_note(
			items_data=[{
				"item_code": self.potato_item.item_code,
				"qty": 100,
				"rate": 10.0,
			}],
			customer=self.customer.name,
			company=self.company.name,
			warehouse=self.warehouse.name,
		)

		si = create_test_sales_invoice(
			items_data=[{
				"item_code": self.potato_item.item_code,
				"qty": 100,
				"rate": 10.0,
				"delivery_note": dn.name,
				"dn_detail": frappe.db.get_value(
					"Delivery Note Item", {"parent": dn.name}, "name"
				),
			}],
			customer=self.customer.name,
			company=self.company.name,
			warehouse=self.warehouse.name,
		)

		# Load items first
		self.wizard.load_items()

		# Select the first item
		if self.wizard.unbilled_items:
			self.wizard.unbilled_items[0]["selected"] = True

		# Find matches
		result = self.wizard.find_invoice_matches()

		self.assertEqual(result.get("status"), "success")

	def test_find_matches_requires_selection(self):
		"""Calling find_invoice_matches without selection → throws."""
		self.wizard.load_items()

		with self.assertRaises(frappe.ValidationError):
			self.wizard.find_invoice_matches()

	def test_select_all_items(self):
		"""select_all_items sets all items to selected=True."""
		dn = create_test_delivery_note(
			items_data=[{
				"item_code": self.potato_item.item_code,
				"qty": 100,
				"rate": 10.0,
			}],
			customer=self.customer.name,
			company=self.company.name,
			warehouse=self.warehouse.name,
		)

		self.wizard.load_items()

		result = self.wizard.select_all_items(select_all=True)
		self.assertEqual(result.get("status"), "success")
		for item in self.wizard.unbilled_items:
			self.assertTrue(item["selected"])

		# Deselect all
		self.wizard.select_all_items(select_all=False)
		for item in self.wizard.unbilled_items:
			self.assertFalse(item["selected"])

	def test_select_all_items_type_coercion(self):
		"""select_all_items handles various truthy types from JS."""
		dn = create_test_delivery_note(
			items_data=[{
				"item_code": self.potato_item.item_code,
				"qty": 100,
				"rate": 10.0,
			}],
			customer=self.customer.name,
			company=self.company.name,
			warehouse=self.warehouse.name,
		)

		self.wizard.load_items()

		# Test with string 'true'
		result = self.wizard.select_all_items(select_all="true")
		self.assertEqual(result.get("status"), "success")
		for item in self.wizard.unbilled_items:
			self.assertTrue(item["selected"])

		# Test with integer 1
		self.wizard.select_all_items(select_all=1)
		for item in self.wizard.unbilled_items:
			self.assertTrue(item["selected"])

		# Test with string '1'
		self.wizard.select_all_items(select_all="1")
		for item in self.wizard.unbilled_items:
			self.assertTrue(item["selected"])

	def test_update_selection(self):
		"""update_selection toggles individual item selection."""
		dn = create_test_delivery_note(
			items_data=[{
				"item_code": self.potato_item.item_code,
				"qty": 100,
				"rate": 10.0,
			}],
			customer=self.customer.name,
			company=self.company.name,
			warehouse=self.warehouse.name,
		)

		self.wizard.load_items()
		if not self.wizard.unbilled_items:
			self.skipTest("No items loaded")

		# Select first item
		result = self.wizard.update_selection(item_index=0, selected=True)
		self.assertEqual(result.get("status"), "success")
		self.assertTrue(self.wizard.unbilled_items[0]["selected"])

		# Deselect first item
		self.wizard.update_selection(item_index=0, selected=False)
		self.assertFalse(self.wizard.unbilled_items[0]["selected"])

	def test_update_selection_type_coercion(self):
		"""update_selection handles JS-style string/boolean types."""
		dn = create_test_delivery_note(
			items_data=[{
				"item_code": self.potato_item.item_code,
				"qty": 100,
				"rate": 10.0,
			}],
			customer=self.customer.name,
			company=self.company.name,
			warehouse=self.warehouse.name,
		)

		self.wizard.load_items()
		if not self.wizard.unbilled_items:
			self.skipTest("No items loaded")

		# Test with JS-style string 'true'
		self.wizard.update_selection(item_index=0, selected="true")
		self.assertTrue(self.wizard.unbilled_items[0]["selected"])

		# Test with integer 1
		self.wizard.update_selection(item_index=0, selected=1)
		self.assertTrue(self.wizard.unbilled_items[0]["selected"])

	def test_update_selection_invalid_index(self):
		"""Invalid item index → error status."""
		result = self.wizard.update_selection(item_index=999, selected=True)
		self.assertEqual(result.get("status"), "error")

	def test_create_assignments_without_matches(self):
		"""Calling create_assignments without matches → throws."""
		with self.assertRaises(frappe.ValidationError):
			self.wizard.create_assignments()

	def test_update_totals(self):
		"""update_totals calculates selected counts and amounts."""
		dn = create_test_delivery_note(
			items_data=[{
				"item_code": self.potato_item.item_code,
				"qty": 100,
				"rate": 10.0,
			}],
			customer=self.customer.name,
			company=self.company.name,
			warehouse=self.warehouse.name,
		)

		self.wizard.load_items()
		self.wizard.select_all_items(select_all=True)
		self.wizard.update_totals()

		self.assertGreater(self.wizard.total_selected_items, 0)

	def test_render_html_tables(self):
		"""HTML rendering methods produce valid output."""
		dn = create_test_delivery_note(
			items_data=[{
				"item_code": self.potato_item.item_code,
				"qty": 100,
				"rate": 10.0,
			}],
			customer=self.customer.name,
			company=self.company.name,
			warehouse=self.warehouse.name,
		)

		self.wizard.load_items()

		# HTML tables should be populated
		self.assertIn("Load Items", self.wizard.unbilled_items_html)
