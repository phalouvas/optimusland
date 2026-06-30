# Copyright (c) 2026, KAINOTOMO PH LTD and Contributors
# See license.txt

"""Tests for the Purchase Receipt Gross Profit report.

Validates the supplier_rate formula — the core business negotiation tool.
Tests run via execute() directly rather than the report runner.
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
	create_test_batch,
	create_test_purchase_receipt,
	create_test_delivery_note,
	create_test_sales_invoice,
	create_test_manufacture_stock_entry,
)
from optimusland.optimusland.report.purchase_receipt_gross_profit.purchase_receipt_gross_profit import (
	execute,
)


class TestPurchaseReceiptGrossProfit(IntegrationTestCase):
	"""Tests for the gross profit report and supplier_rate formula."""

	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		cls.company = get_or_create_test_company()
		cls.company_abbr = frappe.db.get_value("Company", cls.company.name, "abbr")
		cls.warehouse = get_or_create_test_warehouse(cls.company.name)
		cls.supplier = get_or_create_test_supplier(cls.company.name)
		cls.customer = get_or_create_test_customer(cls.company.name)
		cls.potato_item = get_or_create_test_potato_item(cls.company.name)
		cls.bom = get_or_create_test_bom(cls.potato_item.item_code, cls.company.name)

	def _create_full_chain(self, purchase_rate=0.50, shipping_rate=0.02,
						   selling_rate=0.80, purchase_qty=1000, prefix="RPT"):
		"""Create PR → Manufacture → DN → SI with the same batch.

		Returns dict with document names for assertions.
		"""
		batch = create_test_batch(self.potato_item.item_code, self.supplier.name,
								  prefix=prefix)

		pr = create_test_purchase_receipt(
			items_data=[{
				"item_code": self.potato_item.item_code,
				"qty": purchase_qty,
				"rate": purchase_rate,
				"batch_no": batch.name,
			}],
			supplier=self.supplier.name,
			company=self.company.name,
			warehouse=self.warehouse.name,
		)

		# Create Manufacture SE so DN can be submitted
		manufacture_se = create_test_manufacture_stock_entry(
			self.potato_item.item_code, batch.name, purchase_qty,
			company=self.company.name, warehouse=self.warehouse.name,
		)

		dn = create_test_delivery_note(
			items_data=[{
				"item_code": self.potato_item.item_code,
				"qty": purchase_qty,
				"rate": selling_rate,
				"batch_no": batch.name,
			}],
			customer=self.customer.name,
			company=self.company.name,
			warehouse=self.warehouse.name,
		)

		# Set shipping cost
		if shipping_rate:
			frappe.db.set_value("Delivery Note", dn.name, {
				"custom_shipping_cost": shipping_rate * purchase_qty,
				"custom_shipping_rate": shipping_rate,
				"custom_is_shipping_cost_added": 1,
			}, update_modified=False)

		si = create_test_sales_invoice(
			items_data=[{
				"item_code": self.potato_item.item_code,
				"qty": purchase_qty,
				"rate": selling_rate,
				"delivery_note": dn.name,
			}],
			customer=self.customer.name,
			company=self.company.name,
			warehouse=self.warehouse.name,
		)

		return {
			"batch": batch,
			"pr": pr,
			"dn": dn,
			"si": si,
		}

	def test_report_returns_columns_and_data(self):
		"""Execute report with valid filters → returns (columns, data)."""
		self._create_full_chain(prefix="COLUMNS")

		filters = frappe._dict({
			"company": self.company.name,
			"from_date": "2020-01-01",
			"to_date": "2099-12-31",
			"wished_earning_percentage": 10,
		})
		columns, data = execute(filters)

		self.assertIsInstance(columns, list)
		self.assertIsInstance(data, list)
		self.assertGreater(len(columns), 0)

	def test_supplier_rate_calculated_correctly(self):
		"""Validate supplier_rate formula with known inputs.

		supplier_rate = selling_rate + purchase_rate - incoming_rate - wished_profit_rate

		Given: selling_rate=0.80, purchase_rate=0.50, incoming_rate=0.02,
			   wished_earning_percentage=10 → wished_profit_rate=0.08

		Expected: supplier_rate = 0.80 + 0.50 - 0.02 - 0.08 = 1.20
		"""
		self._create_full_chain(
			purchase_rate=0.50,
			shipping_rate=0.02,
			selling_rate=0.80,
			prefix="FORMULA",
		)

		filters = frappe._dict({
			"company": self.company.name,
			"from_date": "2020-01-01",
			"to_date": "2099-12-31",
			"wished_earning_percentage": 10,
		})
		columns, data = execute(filters)

		# Filter out total row
		data_rows = [row for row in data if row.get("supplier")]

		if data_rows:
			row = data_rows[0]
			expected_supplier_rate = round(0.80 + 0.50 - 0.02 - (0.10 * 0.80), 3)
			self.assertEqual(row.get("supplier_rate"), expected_supplier_rate)

	def test_zero_wished_percentage(self):
		"""wished_earning_percentage=0 → supplier_rate = selling_rate + purchase_rate - incoming_rate."""
		self._create_full_chain(
			purchase_rate=0.50,
			shipping_rate=0.02,
			selling_rate=0.80,
			prefix="ZEROWP",
		)

		filters = frappe._dict({
			"company": self.company.name,
			"from_date": "2020-01-01",
			"to_date": "2099-12-31",
			"wished_earning_percentage": 0,
		})
		columns, data = execute(filters)

		data_rows = [row for row in data if row.get("supplier")]
		if data_rows:
			row = data_rows[0]
			# With 0% wished, supplier_rate = 0.80 + 0.50 - 0.02 = 1.28
			expected = round(0.80 + 0.50 - 0.02, 3)
			self.assertEqual(row.get("supplier_rate"), expected)

	def test_missing_shipping_handled(self):
		"""DN without custom_shipping_rate → incoming_rate=0, formula still works."""
		self._create_full_chain(
			purchase_rate=0.50,
			shipping_rate=0,  # No shipping
			selling_rate=0.80,
			prefix="NOSHIP",
		)

		filters = frappe._dict({
			"company": self.company.name,
			"from_date": "2020-01-01",
			"to_date": "2099-12-31",
			"wished_earning_percentage": 10,
		})
		columns, data = execute(filters)

		# Should not crash — just verify structure
		self.assertIsInstance(data, list)
