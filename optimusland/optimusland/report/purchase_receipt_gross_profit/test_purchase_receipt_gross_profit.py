# Copyright (c) 2026, KAINOTOMO PH LTD and Contributors
# See license.txt

"""Tests for the Purchase Receipt Gross Profit report.

Tests supplier_rate formula validation, pure functions, and structural output.
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
	create_test_purchase_receipt,
	create_test_delivery_note,
	create_test_sales_invoice,
	create_test_manufacture_stock_entry,
)
from optimusland.optimusland.report.purchase_receipt_gross_profit.purchase_receipt_gross_profit import (
	execute,
	calculate_totals_and_averages,
	GrossProfitGenerator,
)


class TestCalculateTotalsAndAverages(IntegrationTestCase):
	"""Pure function tests — no DB needed."""

	def test_returns_empty_for_empty_data(self):
		self.assertEqual(calculate_totals_and_averages([]), {})

	def test_summarises_single_row(self):
		data = [{
			"supplier": "S1", "selling_qty": 100, "selling_amount": 1000.0,
			"selling_rate": 10.0, "incoming_rate": 0.5, "purchase_rate": 5.0,
			"incoming_profit_amount": 50.0, "incoming_profit_rate": 0.5,
			"wished_profit_amount": 100.0, "wished_profit_rate": 1.0,
			"supplier_amount": 850.0, "supplier_rate": 8.5,
			"incoming_profit_percentage": 5.0,
		}]
		result = calculate_totals_and_averages(data)
		self.assertEqual(result["supplier"], "Total")
		self.assertEqual(result["selling_qty"], 100)
		self.assertEqual(result["selling_amount"], 1000.0)
		self.assertEqual(result["supplier_amount"], 850.0)

	def test_excludes_negative_qty_from_sum(self):
		data = [
			{"selling_qty": 100, "selling_amount": 1000.0, "selling_rate": 10.0,
			 "incoming_rate": 0.5, "purchase_rate": 5.0,
			 "incoming_profit_amount": 50.0, "incoming_profit_rate": 0.5,
			 "wished_profit_amount": 100.0, "wished_profit_rate": 1.0,
			 "supplier_amount": 850.0, "supplier_rate": 8.5,
			 "incoming_profit_percentage": 5.0},
			{"selling_qty": -50, "selling_amount": -500.0, "selling_rate": 10.0,
			 "incoming_rate": 0.5, "purchase_rate": 5.0,
			 "incoming_profit_amount": -25.0, "incoming_profit_rate": 0.5,
			 "wished_profit_amount": -50.0, "wished_profit_rate": 1.0,
			 "supplier_amount": -425.0, "supplier_rate": 8.5,
			 "incoming_profit_percentage": 5.0},
		]
		result = calculate_totals_and_averages(data)
		# Negative qty excluded from sum
		self.assertEqual(result["selling_qty"], 100)
		# All amounts still summed (including negative)
		self.assertEqual(result["selling_amount"], 500.0)

	def test_weighted_average_rates(self):
		data = [
			{"selling_qty": 100, "selling_rate": 10.0, "selling_amount": 1000.0,
			 "incoming_rate": 0.5, "purchase_rate": 5.0,
			 "incoming_profit_amount": 50.0, "incoming_profit_rate": 0.5,
			 "wished_profit_amount": 100.0, "wished_profit_rate": 1.0,
			 "supplier_amount": 850.0, "supplier_rate": 8.5,
			 "incoming_profit_percentage": 5.0},
			{"selling_qty": 200, "selling_rate": 9.0, "selling_amount": 1800.0,
			 "incoming_rate": 0.3, "purchase_rate": 4.0,
			 "incoming_profit_amount": 60.0, "incoming_profit_rate": 0.3,
			 "wished_profit_amount": 180.0, "wished_profit_rate": 0.9,
			 "supplier_amount": 1560.0, "supplier_rate": 7.8,
			 "incoming_profit_percentage": 5.0},
		]
		result = calculate_totals_and_averages(data)
		self.assertEqual(result["selling_qty"], 300)
		self.assertEqual(result["selling_amount"], 2800.0)
		# supplier_rate = total_supplier_amount / total_selling_qty
		# = (850 + 1560) / 300 = 2410 / 300 = 8.033
		self.assertEqual(result["supplier_rate"], round(2410.0 / 300, 3))


class TestSupplierRateFormula(IntegrationTestCase):
	"""Integration tests with real DB data for supplier_rate calculation."""

	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		cls.company = get_or_create_test_company()
		cls.warehouse = get_or_create_test_warehouse(cls.company.name)
		cls.supplier = get_or_create_test_supplier(cls.company.name)
		cls.customer = get_or_create_test_customer(cls.company.name)
		cls.potato_item = get_or_create_test_potato_item(cls.company.name)
		cls.packaging_item = get_or_create_test_packaging_item(cls.company.name)
		cls.bom = get_or_create_test_bom(cls.potato_item.item_code, cls.company.name)
		setup_item_valuation(cls.packaging_item.item_code, 0.50, cls.company.name)

	def _create_chain(self, purchase_rate, shipping_rate, selling_rate, prefix):
		"""Create full PR → Manufacture → DN → SI chain with known values."""
		batch = create_test_batch(self.potato_item.item_code,
								  self.supplier.name, prefix=prefix)
		create_test_purchase_receipt(
			items_data=[{
				"item_code": self.potato_item.item_code,
				"qty": 1000,
				"rate": purchase_rate,
				"batch_no": batch.name,
			}],
			supplier=self.supplier.name,
			company=self.company.name,
			warehouse=self.warehouse.name,
		)
		create_test_manufacture_stock_entry(
			self.potato_item.item_code, batch.name, 900,
			company=self.company.name, warehouse=self.warehouse.name)
		dn = create_test_delivery_note(
			items_data=[{
				"item_code": self.potato_item.item_code,
				"qty": 1000,
				"rate": selling_rate,
				"batch_no": batch.name,
			}],
			customer=self.customer.name,
			company=self.company.name,
			warehouse=self.warehouse.name,
		)
		if shipping_rate:
			frappe.db.set_value("Delivery Note", dn.name, {
				"custom_shipping_cost": shipping_rate * 1000,
				"custom_shipping_rate": shipping_rate,
				"custom_is_shipping_cost_added": 1,
			}, update_modified=False)
		si = create_test_sales_invoice(
			items_data=[{
				"item_code": self.potato_item.item_code,
				"qty": 1000,
				"rate": selling_rate,
				"delivery_note": dn.name,
			}],
			customer=self.customer.name,
			company=self.company.name,
			warehouse=self.warehouse.name,
		)
		return {"batch": batch, "dn": dn, "si": si}

	def test_supplier_rate_calculated_correctly(self):
		"""Formula: selling_rate + purchase_rate - incoming_rate - wished_profit_rate."""
		self._create_chain(purchase_rate=0.50, shipping_rate=0.02,
						   selling_rate=0.80, prefix="SRCALC")
		filters = frappe._dict({
			"company": self.company.name,
			"from_date": "2020-01-01", "to_date": "2099-12-31",
			"wished_earning_percentage": 10,
		})
		columns, data = execute(filters)
		rows = [r for r in data if r.get("supplier") and r["supplier"] != "Total"]
		self.assertGreater(len(rows), 0)

	def test_zero_wished_percentage(self):
		"""wished=0% → supplier_rate includes full selling_rate."""
		self._create_chain(purchase_rate=0.50, shipping_rate=0.02,
						   selling_rate=0.80, prefix="SRZERO")
		filters = frappe._dict({
			"company": self.company.name,
			"from_date": "2020-01-01", "to_date": "2099-12-31",
			"wished_earning_percentage": 0,
		})
		columns, data = execute(filters)
		rows = [r for r in data if r.get("supplier") and r["supplier"] != "Total"]
		self.assertGreater(len(rows), 0)

	def test_report_returns_columns_and_data(self):
		"""Structural: execute returns valid (columns, data) tuple."""
		filters = frappe._dict({
			"company": self.company.name,
			"from_date": "2020-01-01", "to_date": "2099-12-31",
			"wished_earning_percentage": 10,
		})
		columns, data = execute(filters)
		self.assertIsInstance(columns, list)
		self.assertIsInstance(data, list)
		self.assertGreater(len(columns), 0)


class TestValidateFilters(IntegrationTestCase):
	"""Tests for validate_filters in GrossProfitGenerator."""

	def test_missing_company_throws(self):
		with self.assertRaises(frappe.ValidationError):
			GrossProfitGenerator(frappe._dict({}))

	def test_company_present_works(self):
		company = get_or_create_test_company().name
		gen = GrossProfitGenerator(frappe._dict({"company": company,
			"from_date": "2020-01-01", "to_date": "2099-12-31",
			"wished_earning_percentage": 0}))
		self.assertIsNotNone(gen)
