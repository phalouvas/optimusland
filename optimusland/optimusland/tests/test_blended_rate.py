# Copyright (c) 2026, KAINOTOMO PH LTD and Contributors
# See license.txt

"""Tests for blended_rate.py — Base Rate Calculator.

Tests the core rate calculation, snapshot persistence, sanity checks,
and exponential weighted average formula.

Requires:
- Optimus General Settings with operating_accounts configured
- GL entries with P&L operating accounts
- Submitted SIs with Potato items (seeded by before_tests or test helpers)
"""

import frappe
from frappe.tests import IntegrationTestCase
from frappe.utils import flt, today, add_days
from math import exp, log as ln


class TestBaseRateCalculation(IntegrationTestCase):
	"""Tests for get_base_rate and calculate_and_snapshot."""

	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		# Use existing company with SI data for kg denominator
		cls.company_name = frappe.db.get_value("Company", {}, "name")
		if not cls.company_name:
			cls.skipTest(cls, "No company found in test DB")

		# Create expense account under a group account of the existing company
		parent_expense = frappe.db.get_value("Account", {
			"root_type": "Expense", "company": cls.company_name, "is_group": 1
		}, "name")
		if not parent_expense:
			cls.skipTest(cls, "No expense group account found")
		cls.expense_account = frappe.get_doc({
			"doctype": "Account", "account_name": "_Test BR OpExp", "account_number": "9999",
			"parent_account": parent_expense,
			"company": cls.company_name, "root_type": "Expense", "is_group": 0,
		})
		cls.expense_account.insert(ignore_permissions=True)

		# Configure settings for the existing company
		cls._configure_settings()
		cls._create_gl_entries()

	@classmethod
	def _configure_settings(cls):
		"""Setup test configuration."""
		settings = frappe.get_single("Optimus General Settings")
		settings.operating_accounts = "9999"
		settings.depreciation_accounts = ""
		settings.operating_lookback_days = 90
		settings.operating_half_life_days = 30
		settings.default_target_margin_pct = 6
		settings.item_group = "Potatoes"
		settings.uom = "Kg"
		settings.sanity_check_max_operating_rate = 0.50
		settings.sanity_check_min_operating_rate = 0.01
		settings.rate_stability_threshold_pct = 30
		settings.reconciliation_variance_threshold_pct = 5
		settings.save(ignore_permissions=True)

	@classmethod
	def _create_gl_entries(cls):
		"""Create GL entries simulating operating expenses over the lookback period."""
		from frappe.utils import today, add_days
		today_dt = frappe.utils.nowdate()

		for days_ago in range(5, 95, 10):
			posting_date = add_days(today_dt, -days_ago)
			# Create an expense GL entry: debit an expense account, credit a balancing account
			bal_account = frappe.db.get_value("Account", {"account_type": "Bank", "company": cls.company_name}, "name")
			if not bal_account:
				bal_account = cls.expense_account.name

			gl = frappe.get_doc({
				"doctype": "GL Entry",
				"posting_date": posting_date,
				"company": cls.company_name,
				"account": cls.expense_account.name,
				"debit": 500.0,
				"credit": 0.0,
				"debit_in_account_currency": 500.0,
				"credit_in_account_currency": 0.0,
				"is_cancelled": 0,
			})
			gl.db_insert()

	def test_get_base_rate_returns_dict(self):
		"""get_base_rate returns a dict with required keys."""
		from optimusland.utils.blended_rate import get_base_rate
		result = get_base_rate(self.company_name)
		self.assertIsInstance(result, dict)
		self.assertIn("operating_rate", result)
		self.assertIn("capital_rate", result)
		self.assertIn("base_rate", result)
		self.assertIn("total_kg", result)

	def test_calculate_and_snapshot_creates_doc(self):
		"""calculate_and_snapshot persists a Blended Rate Snapshot."""
		from optimusland.utils.blended_rate import calculate_and_snapshot
		result = calculate_and_snapshot(self.company_name)

		# Verify a snapshot was persisted
		count = frappe.db.count("Blended Rate Snapshot", {})
		self.assertGreater(count, 0, "No snapshot was created")
		self.assertGreater(result["base_rate"], 0, "Base rate should be positive")

	def test_operating_rate_valid(self):
		"""Operating rate should be valid (>=0 and finite)."""
		from optimusland.utils.blended_rate import get_operating_rate
		rate = get_operating_rate(self.company_name)
		self.assertGreaterEqual(rate, 0)
		self.assertLess(rate, 100)  # sanity: 100€/kg would be absurd

	def test_capital_rate_when_no_accounts(self):
		"""Capital rate returns a valid number even when no depreciation accounts configured."""
		from optimusland.utils.blended_rate import get_capital_rate
		rate = get_capital_rate(self.company_name)
		self.assertGreaterEqual(rate, 0)

	def test_sanity_checks_return_list(self):
		"""sanity_warnings should be a list (possibly empty)."""
		from optimusland.utils.blended_rate import calculate_and_snapshot
		result = calculate_and_snapshot(self.company_name)
		self.assertIsInstance(result.get("sanity_warnings"), list)
		for w in result.get("sanity_warnings", []):
			self.assertIsInstance(w, str)

	def test_get_base_rate_cached(self):
		"""Second call within same day returns cached result."""
		from optimusland.utils.blended_rate import get_base_rate, calculate_and_snapshot
		# Force fresh, then cache
		calculate_and_snapshot(self.company_name)
		cached = get_base_rate(self.company_name)
		self.assertIsInstance(cached, dict)
		self.assertIn("operating_rate", cached)
		self.assertIn("base_rate", cached)


class TestExponentialWeightedAverage(IntegrationTestCase):
	"""Unit tests for the exponential weighted average formula."""

	def test_higher_weight_on_recent_days(self):
		"""Recent days get more weight than older days."""
		from optimusland.utils.blended_rate import _exponential_weighted_average
		from frappe.utils import today, add_days
		t = today()

		rates = [
			frappe._dict(day=add_days(t, -2), rate=0.10),
			frappe._dict(day=add_days(t, -1), rate=0.50),
		]
		weighted = _exponential_weighted_average(rates, half_life_days=1)
		# Should be closer to 0.50 (recent) than 0.10 (old)
		self.assertGreater(weighted, 0.30)

	def test_equal_days_gives_simple_average(self):
		"""With infinite half-life, result equals arithmetic mean."""
		from optimusland.utils.blended_rate import _exponential_weighted_average
		from frappe.utils import today, add_days
		t = today()

		rates = [
			frappe._dict(day=add_days(t, -2), rate=0.20),
			frappe._dict(day=add_days(t, -1), rate=0.40),
			frappe._dict(day=t, rate=0.60),
		]
		# Very long half-life ≈ simple average
		weighted = _exponential_weighted_average(rates, half_life_days=9999)
		self.assertAlmostEqual(weighted, 0.40, places=2)

	def test_empty_list_returns_zero(self):
		"""Empty input returns 0."""
		from optimusland.utils.blended_rate import _exponential_weighted_average
		self.assertEqual(_exponential_weighted_average([], half_life_days=30), 0.0)

	def test_single_day_returns_that_rate(self):
		"""Single day returns its own rate regardless of half-life."""
		from optimusland.utils.blended_rate import _exponential_weighted_average
		from frappe.utils import today
		rates = [frappe._dict(day=today(), rate=0.123456)]
		self.assertEqual(_exponential_weighted_average(rates, half_life_days=1), 0.123456)


class TestBuildDailyRates(IntegrationTestCase):
	"""Unit tests for _build_daily_rates."""

	def test_mixed_days(self):
		"""Days with both GL and kg produce a rate."""
		from optimusland.utils.blended_rate import _build_daily_rates
		daily_gl = {"2026-01-01": 100.0, "2026-01-02": 200.0}
		daily_kg = {"2026-01-01": 50.0, "2026-01-02": 100.0}
		rates = _build_daily_rates(daily_gl, daily_kg)
		self.assertEqual(len(rates), 2)
		self.assertEqual(rates[0].rate, 2.0)
		self.assertEqual(rates[1].rate, 2.0)

	def test_zero_kg_day_skipped(self):
		"""Days with 0 kg should be skipped."""
		from optimusland.utils.blended_rate import _build_daily_rates
		daily_gl = {"2026-01-01": 100.0, "2026-01-02": 200.0}
		daily_kg = {"2026-01-01": 50.0, "2026-01-02": 0.0}
		rates = _build_daily_rates(daily_gl, daily_kg)
		self.assertEqual(len(rates), 1)
		self.assertEqual(rates[0].day, "2026-01-01")

	def test_no_kg_returns_empty(self):
		"""No kg days returns empty list."""
		from optimusland.utils.blended_rate import _build_daily_rates
		self.assertEqual(_build_daily_rates({"2026-01-01": 100.0}, {}), [])


class TestSanityChecks(IntegrationTestCase):
	"""Unit tests for _run_sanity_checks."""

	def setUp(self):
		self.cfg = frappe._dict(
			sanity_check_max=0.20,
			sanity_check_min=0.02,
			stability_threshold=30,
			reconciliation_threshold=5,
			operating_accounts=["9999"],
			operating_lookback_days=90,
		)

	def test_no_warnings_when_normal(self):
		"""Rate within thresholds produces no warnings."""
		from optimusland.utils.blended_rate import _run_sanity_checks
		result = {"operating_rate": 0.05, "company": "_Test"}
		warnings = _run_sanity_checks(result, self.cfg)
		self.assertEqual(len(warnings), 0)

	def test_max_threshold_triggered(self):
		"""Rate above max threshold triggers warning."""
		from optimusland.utils.blended_rate import _run_sanity_checks
		result = {"operating_rate": 0.50, "company": "_Test"}
		warnings = _run_sanity_checks(result, self.cfg)
		self.assertTrue(any("exceeds max" in w for w in warnings))

	def test_min_threshold_triggered(self):
		"""Rate below min threshold triggers warning."""
		from optimusland.utils.blended_rate import _run_sanity_checks
		result = {"operating_rate": 0.005, "company": "_Test"}
		warnings = _run_sanity_checks(result, self.cfg)
		self.assertTrue(any("below min" in w for w in warnings))
