# Copyright (c) 2026, KAINOTOMO PH LTD and Contributors
# See license.txt

"""Tests for the Unbilled Delivery Notes report.

Uses a non-stock item to avoid batch/manufacturing complexity.
"""

import frappe
from frappe.tests import IntegrationTestCase

from optimusland.optimusland.tests import (
	get_or_create_test_company,
	get_or_create_test_warehouse,
	get_or_create_test_customer,
	get_or_create_test_packaging_item,
)
from optimusland.optimusland.report.unbilled_delivery_notes.unbilled_delivery_notes import (
	execute,
	get_conditions,
	get_summary_row,
)


class TestUnbilledDeliveryNotes(IntegrationTestCase):
	"""Tests for the Unbilled Delivery Notes report."""

	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		cls.company = get_or_create_test_company()
		cls.warehouse = get_or_create_test_warehouse(cls.company.name)
		cls.customer = get_or_create_test_customer(cls.company.name)
		cls.test_item = get_or_create_test_packaging_item(cls.company.name)

	def test_report_returns_columns_and_data(self):
		"""Execute report with valid filters → returns (columns, data)."""
		filters = frappe._dict({
			"company": self.company.name,
			"from_date": "2020-01-01",
			"to_date": "2099-12-31",
		})
		columns, data = execute(filters)
		self.assertIsInstance(columns, list)
		self.assertIsInstance(data, list)
		self.assertGreater(len(columns), 0)

	def test_filter_by_customer(self):
		"""Customer filter does not crash."""
		filters = frappe._dict({
			"company": self.company.name,
			"customer": self.customer.name,
			"from_date": "2020-01-01",
			"to_date": "2099-12-31",
		})
		columns, data = execute(filters)
		self.assertIsInstance(data, list)

	def test_summary_row_added(self):
		"""Report may include a TOTAL summary row."""
		filters = frappe._dict({
			"company": self.company.name,
			"from_date": "2020-01-01",
			"to_date": "2099-12-31",
		})
		columns, data = execute(filters)
		if data:
			last_row = data[-1]
			if last_row.get("customer") == "TOTAL":
				self.assertIsNotNone(last_row.get("amount"))

class TestGetConditions(IntegrationTestCase):
	"""Pure function tests for get_conditions."""

	def test_company_required(self):
		"""Missing company raises ValidationError."""
		with self.assertRaises(frappe.ValidationError):
			get_conditions({})

	def test_all_filters_included(self):
		conditions = get_conditions({
			"company": "_Test Co",
			"customer": "_Test Cust",
			"from_date": "2024-01-01",
			"to_date": "2024-12-31",
		})
		self.assertIn("dn.company = %(company)s", conditions)
		self.assertIn("dn.customer = %(customer)s", conditions)
		self.assertIn("dn.posting_date", conditions)


class TestGetSummaryRow(IntegrationTestCase):
	"""Pure function tests for get_summary_row."""

	def test_calculates_totals(self):
		data = [
			{"amount": 1000, "billed_amt": 300, "unbilled_amt": 700},
			{"amount": 500, "billed_amt": 500, "unbilled_amt": 0},
		]
		result = get_summary_row(data)
		self.assertEqual(result["customer"], "TOTAL")
		self.assertEqual(result["amount"], 1500)
		self.assertEqual(result["billed_amt"], 800)
		self.assertEqual(result["unbilled_amt"], 700)

	def test_percentage_zero_if_no_amount(self):
		result = get_summary_row([{"amount": 0, "billed_amt": 0, "unbilled_amt": 0}])
		self.assertEqual(result["customer"], "TOTAL")
		self.assertEqual(result["per_billed"], 0)