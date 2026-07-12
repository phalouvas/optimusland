# Copyright (c) 2026, KAINOTOMO PH LTD and Contributors
# See license.txt

"""Tests for grower_calculator.py — Supplier Price Calculator.

Tests the grower price formula, preview, and PI price calculation.
"""

import frappe
from frappe.tests import IntegrationTestCase
from frappe.utils import flt


class TestCalculateGrowerPrice(IntegrationTestCase):
	"""Tests for calculate_grower_price — the SI-level calculator."""

	@classmethod
	def setUpClass(cls):
		super().setUpClass()

	def test_calculate_grower_price_returns_list(self):
		"""calculate_grower_price returns a list for a valid SI."""
		from optimusland.utils.grower_calculator import calculate_grower_price

		# Find a submitted SI with Potato items
		si_name = frappe.db.sql("""
			SELECT si.name FROM `tabSales Invoice` si
			INNER JOIN `tabSales Invoice Item` sii ON sii.parent = si.name
			INNER JOIN `tabItem` item ON item.name = sii.item_code
			WHERE si.docstatus = 1 AND item.item_group = 'Potatoes'
			LIMIT 1
		""")
		if not si_name:
			self.skipTest("No submitted SI with Potato items found in test DB")

		result = calculate_grower_price(si_name[0][0])
		self.assertIsInstance(result, list)
		if result:
			item = result[0]
			self.assertIn("item_code", item)
			self.assertIn("recommended_price", item)
			self.assertIn("margin_pct", item)
			self.assertIn("selling_rate", item)
			self.assertIn("total", item)

	def test_calculate_grower_price_margin_non_negative(self):
		"""Recommended price should not be negative."""
		from optimusland.utils.grower_calculator import calculate_grower_price

		si_name = frappe.db.sql("""
			SELECT si.name FROM `tabSales Invoice` si
			INNER JOIN `tabSales Invoice Item` sii ON sii.parent = si.name
			INNER JOIN `tabItem` item ON item.name = sii.item_code
			WHERE si.docstatus = 1 AND item.item_group = 'Potatoes'
			LIMIT 1
		""")
		if not si_name:
			self.skipTest("No submitted SI with Potato items found")

		result = calculate_grower_price(si_name[0][0])
		for item in result:
			self.assertGreaterEqual(item.recommended_price, 0)

	def test_calculate_grower_price_split_si_returns_items(self):
		"""A valid SI returns at least one Potato item row."""
		from optimusland.utils.grower_calculator import calculate_grower_price

		si_name = frappe.db.sql("""
			SELECT si.name FROM `tabSales Invoice` si
			INNER JOIN `tabSales Invoice Item` sii ON sii.parent = si.name
			INNER JOIN `tabItem` item ON item.name = sii.item_code
			WHERE si.docstatus = 1 AND item.item_group = 'Potatoes'
			LIMIT 1
		""")
		if not si_name:
			self.skipTest("No submitted SI with Potato items found in test DB")

		result = calculate_grower_price(si_name[0][0])
		self.assertGreaterEqual(len(result), 1)

	def test_calculate_grower_price_cancelled_si_raises(self):
		"""Cancelled SI raises an error."""
		from optimusland.utils.grower_calculator import calculate_grower_price

		# Find a cancelled SI
		si_name = frappe.db.sql("""
			SELECT name FROM `tabSales Invoice` WHERE docstatus = 2 LIMIT 1
		""")
		if not si_name:
			self.skipTest("No cancelled SI found in test DB")

		with self.assertRaises(frappe.ValidationError):
			calculate_grower_price(si_name[0][0])


class TestPreviewGrowerPrice(IntegrationTestCase):
	"""Tests for preview_grower_price."""

	def _find_si_with_potatoes(self):
		"""Find a submitted SI with Potato items."""
		si = frappe.db.sql("""
			SELECT si.name FROM `tabSales Invoice` si
			INNER JOIN `tabSales Invoice Item` sii ON sii.parent = si.name
			INNER JOIN `tabItem` item ON item.name = sii.item_code
			WHERE si.docstatus = 1 AND item.item_group = 'Potatoes'
			LIMIT 1
		""")
		return si[0][0] if si else None

	def test_preview_returns_dict(self):
		"""preview_grower_price always returns a dict."""
		from optimusland.utils.grower_calculator import preview_grower_price

		si_name = self._find_si_with_potatoes()
		if not si_name:
			self.skipTest("No submitted SI with Potato items found")

		result = preview_grower_price(si_name)
		self.assertIsInstance(result, dict)

	def test_preview_with_items_has_summary(self):
		"""When items exist, result has items list and summary dict."""
		from optimusland.utils.grower_calculator import preview_grower_price

		si_name = self._find_si_with_potatoes()
		if not si_name:
			self.skipTest("No submitted SI with Potato items found")

		result = preview_grower_price(si_name)
		if result.get("items"):
			# Has items → summary is a dict with expected fields
			s = result["summary"]
			self.assertIsInstance(s, dict)
			self.assertIn("total_qty", s)
			self.assertIn("total_grower_amount", s)
			self.assertIn("avg_selling_rate", s)
			self.assertIn("margin_pct", s)


class TestCalculatePiPrices(IntegrationTestCase):
	"""Tests for calculate_pi_prices (PI-level calculator)."""

	def test_calculate_pi_prices_returns_dict(self):
		"""calculate_pi_prices returns a dict with items and base_rate."""
		from optimusland.utils.grower_calculator import calculate_pi_prices

		# Find a Draft PI with items that have batch info
		pi_data = frappe.db.sql("""
			SELECT pi.name, pii.item_code, pii.qty, pii.batch_no, pii.pr_detail
			FROM `tabPurchase Invoice` pi
			INNER JOIN `tabPurchase Invoice Item` pii ON pii.parent = pi.name
			WHERE pi.docstatus = 0 AND pii.batch_no IS NOT NULL
			LIMIT 1
		""", as_dict=True)
		if not pi_data:
			self.skipTest("No Draft PI with batch items found in test DB")

		pi = pi_data[0]
		supplier = frappe.db.get_value("Purchase Invoice", pi.name, "supplier")
		items = [{"item_code": pi.item_code, "qty": pi.qty, "batch_no": pi.batch_no, "pr_detail": pi.pr_detail}]

		result = calculate_pi_prices(supplier, items)
		self.assertIn("items", result)
		self.assertIn("base_rate", result)
		self.assertIn("margin_pct", result)
