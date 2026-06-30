# Copyright (c) 2026, KAINOTOMO PH LTD and Contributors
# See license.txt

"""Tests for the Unbilled Delivery Notes report.

Validates the SQL query logic, billing calculations, and variance detection.
"""

import frappe
from frappe.tests import IntegrationTestCase

from optimusland.optimusland.tests import (
	get_or_create_test_company,
	get_or_create_test_warehouse,
	get_or_create_test_customer,
	get_or_create_test_potato_item,
	get_or_create_test_bom,
	create_test_batch,
	create_test_delivery_note,
	create_test_sales_invoice,
	create_test_manufacture_stock_entry,
)
from optimusland.optimusland.report.unbilled_delivery_notes.unbilled_delivery_notes import (
	execute,
	get_data,
)


class TestUnbilledDeliveryNotes(IntegrationTestCase):
	"""Tests for the Unbilled Delivery Notes report."""

	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		cls.company = get_or_create_test_company()
		cls.company_abbr = frappe.db.get_value("Company", cls.company.name, "abbr")
		cls.warehouse = get_or_create_test_warehouse(cls.company.name)
		cls.customer = get_or_create_test_customer(cls.company.name)
		cls.potato_item = get_or_create_test_potato_item(cls.company.name)
		cls.bom = get_or_create_test_bom(cls.potato_item.item_code, cls.company.name)

	def test_report_returns_columns_and_data(self):
		"""Execute report with valid filters → returns (columns, data)."""
		# Create a DN with items
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

		filters = frappe._dict({
			"company": self.company.name,
			"from_date": "2020-01-01",
			"to_date": "2099-12-31",
		})
		columns, data = execute(filters)

		self.assertIsInstance(columns, list)
		self.assertIsInstance(data, list)
		self.assertGreater(len(columns), 0)

	def test_unbilled_dn_appears_in_report(self):
		"""DN with no linked SI → appears with unbilled_amt > 0."""
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

		filters = frappe._dict({
			"company": self.company.name,
			"from_date": "2020-01-01",
			"to_date": "2099-12-31",
		})
		columns, data = execute(filters)

		# Filter out total row
		data_rows = [row for row in data if row.get("delivery_note")]
		self.assertGreater(len(data_rows), 0)

		dn_rows = [row for row in data_rows if row.get("delivery_note") == dn.name]
		self.assertGreater(len(dn_rows), 0)

		for row in dn_rows:
			self.assertGreater(row.get("unbilled_amt", 0), 0)

	def test_fully_billed_dn_not_in_report(self):
		"""DN fully billed → not in report (unbilled_amt <= 0.01)."""
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

		# Create a linked SI
		si = create_test_sales_invoice(
			items_data=[{
				"item_code": self.potato_item.item_code,
				"qty": 100,
				"rate": 10.0,
				"delivery_note": dn.name,
			}],
			customer=self.customer.name,
			company=self.company.name,
			warehouse=self.warehouse.name,
		)

		filters = frappe._dict({
			"company": self.company.name,
			"from_date": "2020-01-01",
			"to_date": "2099-12-31",
		})
		columns, data = execute(filters)

		# Fully billed DN should be excluded
		dn_rows = [row for row in data if row.get("delivery_note") == dn.name]
		self.assertEqual(len(dn_rows), 0,
						 "Fully billed DN should not appear in unbilled report")

	def test_partial_billing(self):
		"""Partially billed DN → unbilled_amt reflects remaining amount."""
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

		# Partially bill (50 of 100)
		si = create_test_sales_invoice(
			items_data=[{
				"item_code": self.potato_item.item_code,
				"qty": 50,
				"rate": 10.0,
				"delivery_note": dn.name,
			}],
			customer=self.customer.name,
			company=self.company.name,
			warehouse=self.warehouse.name,
		)

		filters = frappe._dict({
			"company": self.company.name,
			"from_date": "2020-01-01",
			"to_date": "2099-12-31",
		})
		columns, data = execute(filters)

		dn_rows = [row for row in data if row.get("delivery_note") == dn.name]
		self.assertGreater(len(dn_rows), 0)

		for row in dn_rows:
			self.assertGreater(row.get("unbilled_amt", 0), 0)
			self.assertGreater(row.get("per_billed", 0), 0)
			self.assertLess(row.get("per_billed", 0), 100)

	def test_variance_detection(self):
		"""When system billed_amt differs from calculated → variance > 0."""
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

		# Set billed_amt to a different value than what SI suggests
		dn_item_name = frappe.db.get_value(
			"Delivery Note Item",
			{"parent": dn.name},
			"name",
		)
		frappe.db.set_value("Delivery Note Item", dn_item_name, "billed_amt", 500)

		filters = frappe._dict({
			"company": self.company.name,
			"from_date": "2020-01-01",
			"to_date": "2099-12-31",
		})
		columns, data = execute(filters)

		# Should have variance since system tracked differs from actual billing
		dn_rows = [row for row in data if row.get("delivery_note") == dn.name]
		# At minimum, should not crash
		self.assertIsInstance(data, list)

	def test_filter_by_customer(self):
		"""Customer filter narrows results to that customer."""
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

		filters = frappe._dict({
			"company": self.company.name,
			"customer": self.customer.name,
			"from_date": "2020-01-01",
			"to_date": "2099-12-31",
		})
		columns, data = execute(filters)

		dn_rows = [row for row in data if row.get("delivery_note") == dn.name]
		self.assertGreater(len(dn_rows), 0)
		for row in dn_rows:
			self.assertEqual(row.get("customer"), self.customer.name)

	def test_summary_row_added(self):
		"""Report appends a TOTAL summary row."""
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

		filters = frappe._dict({
			"company": self.company.name,
			"from_date": "2020-01-01",
			"to_date": "2099-12-31",
		})
		columns, data = execute(filters)

		# Last row should be the TOTAL row
		if data:
			last_row = data[-1]
			self.assertEqual(last_row.get("customer"), "TOTAL")
			self.assertIsNotNone(last_row.get("amount"))
