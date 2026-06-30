# Copyright (c) 2026, KAINOTOMO PH LTD and Contributors
# See license.txt

"""Tests for batch.py: create_purchase_receipt.
"""

import frappe
from frappe.tests import IntegrationTestCase

from optimusland.optimusland.tests import (
	get_or_create_test_company,
	get_or_create_test_warehouse,
	get_or_create_test_supplier,
	get_or_create_test_potato_item,
	create_test_batch,
)
from optimusland.utils.batch import create_purchase_receipt


class TestCreatePurchaseReceipt(IntegrationTestCase):
	"""Tests for create_purchase_receipt from selected batches."""

	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		cls.company = get_or_create_test_company()
		cls.warehouse = get_or_create_test_warehouse(cls.company.name)
		cls.supplier = get_or_create_test_supplier(cls.company.name)
		cls.potato_item = get_or_create_test_potato_item(cls.company.name)

	def test_create_pr_from_single_batch(self):
		"""Single batch → PR created in Draft with correct supplier and item."""
		batch = create_test_batch(self.potato_item.item_code, self.supplier.name,
								  prefix="BATCHPR")

		result = create_purchase_receipt([batch.name])

		self.assertIn("name", result)
		self.assertIn("doctype", result)
		self.assertEqual(result["doctype"], "Purchase Receipt")

		pr = frappe.get_doc("Purchase Receipt", result["name"])
		self.assertEqual(pr.docstatus, 0)  # Draft
		self.assertEqual(pr.supplier, self.supplier.name)
		self.assertEqual(len(pr.items), 1)
		self.assertEqual(pr.items[0].item_code, self.potato_item.item_code)
		self.assertEqual(pr.items[0].batch_no, batch.name)

	def test_create_pr_from_multiple_batches(self):
		"""Two batches → PR with 2 items."""
		batch1 = create_test_batch(self.potato_item.item_code, self.supplier.name,
								   prefix="BATCHPR2A")
		batch2 = create_test_batch(self.potato_item.item_code, self.supplier.name,
								   prefix="BATCHPR2B")

		result = create_purchase_receipt([batch1.name, batch2.name])

		pr = frappe.get_doc("Purchase Receipt", result["name"])
		self.assertEqual(len(pr.items), 2)

	def test_create_pr_string_parsing(self):
		"""String input '[\"BATCH-001\"]' → correctly parsed to list."""
		batch = create_test_batch(self.potato_item.item_code, self.supplier.name,
								  prefix="BATCHPRSTR")
		names_str = f'["{batch.name}"]'

		result = create_purchase_receipt(names_str)
		self.assertIn("name", result)

	def test_create_pr_empty_input_raises(self):
		"""Empty list → throws."""
		with self.assertRaises(frappe.ValidationError):
			create_purchase_receipt([])

	def test_create_pr_missing_supplier_fallback(self):
		"""Batch without custom_supplier_optimus and no Buying Settings default → throws."""
		batch = create_test_batch(self.potato_item.item_code, None, prefix="BATCHPRNOSUP")

		# Clear the batch's supplier
		frappe.db.set_value("Batch", batch.name, "custom_supplier_optimus", None)

		# Without a default supplier in Buying Settings, the function will try to
		# access frappe.db.get_single_value("Buying Settings", "default_supplier")
		# which raises a ValidationError since that field doesn't exist.
		with self.assertRaises(frappe.ValidationError):
			create_purchase_receipt([batch.name])
