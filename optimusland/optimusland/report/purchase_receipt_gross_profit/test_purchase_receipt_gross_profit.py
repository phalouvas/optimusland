# Copyright (c) 2026, KAINOTOMO PH LTD and Contributors
# See license.txt

"""Tests for the Purchase Receipt Gross Profit report.

Validates report structure (columns, no crash). Full formula validation
requires a complete batch manufacturing chain.
"""

import frappe
from frappe.tests import IntegrationTestCase

from optimusland.optimusland.tests import (
	get_or_create_test_company,
)
from optimusland.optimusland.report.purchase_receipt_gross_profit.purchase_receipt_gross_profit import (
	execute,
)


class TestPurchaseReceiptGrossProfit(IntegrationTestCase):
	"""Tests for the gross profit report."""

	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		cls.company = get_or_create_test_company()

	def test_report_returns_columns_and_data(self):
		"""Execute report with valid filters → returns (columns, data)."""
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

	def test_missing_shipping_handled(self):
		"""Report handles missing data gracefully — no crash."""
		filters = frappe._dict({
			"company": self.company.name,
			"from_date": "2020-01-01",
			"to_date": "2099-12-31",
			"wished_earning_percentage": 10,
		})
		columns, data = execute(filters)
		self.assertIsInstance(data, list)
