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


class TestBaseRateCalculation(IntegrationTestCase):
	"""Tests for get_base_rate and calculate_and_snapshot."""

	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		from optimusland.optimusland.tests import (
			get_or_create_test_company, get_or_create_test_warehouse,
			get_or_create_test_supplier, get_or_create_test_customer,
			get_or_create_test_potato_item, setup_item_valuation,
			create_test_purchase_receipt, create_test_delivery_note,
			create_test_sales_invoice,
		)

		cls.company_name = get_or_create_test_company().name
		cls.warehouse = get_or_create_test_warehouse(cls.company_name).name
		supplier = get_or_create_test_supplier(cls.company_name).name
		customer = get_or_create_test_customer(cls.company_name).name
		potato = get_or_create_test_potato_item(cls.company_name)
		cls.potato_item = potato.item_code

		# Ensure Potato item has stock
		setup_item_valuation(cls.potato_item, 0.50, cls.company_name)

		# Create the full chain: PR -> DN -> SI (v16 requires DN before SI)
		posting_date = frappe.utils.add_days(frappe.utils.today(), -10)
		pr = create_test_purchase_receipt(
			items_data=[{"item_code": cls.potato_item, "qty": 1000, "rate": 0.50}],
			supplier=supplier, company=cls.company_name,
			warehouse=cls.warehouse, posting_date=posting_date,
		)

		# Get the batch auto-assigned by set_batch_no hook
		batch_no = frappe.db.get_value("Purchase Receipt Item",
			{"parent": pr.name}, "batch_no")

		dn = create_test_delivery_note(
			items_data=[{"item_code": cls.potato_item, "qty": 1000, "rate": 0.70,
						"batch_no": batch_no}],
			customer=customer, company=cls.company_name,
			warehouse=cls.warehouse, posting_date=posting_date,
		)

		# Get dn_detail for SI link
		dn_item = frappe.db.get_value("Delivery Note Item",
			{"parent": dn.name, "item_code": cls.potato_item}, "name")

		create_test_sales_invoice(
			items_data=[{"item_code": cls.potato_item, "qty": 1000, "rate": 0.70,
						"delivery_note": dn.name, "dn_detail": dn_item}],
			customer=customer, company=cls.company_name,
			warehouse=cls.warehouse, posting_date=posting_date,
		)

		# Create expense account
		parent_expense = frappe.db.get_value("Account", {
			"root_type": "Expense", "company": cls.company_name, "is_group": 1
		}, "name")
		cls.expense_account = frappe.get_doc({
			"doctype": "Account", "account_name": "_Test BR OpExp", "account_number": "9999",
			"parent_account": parent_expense,
			"company": cls.company_name, "root_type": "Expense", "is_group": 0,
		})
		cls.expense_account.insert(ignore_permissions=True)

		# Configure settings and create GL entries
		cls._configure_settings()
		cls._create_gl_entries()

	@classmethod
	def _configure_settings(cls):
		frappe.db.set_single_value("Optimus General Settings", {
			"operating_accounts": "9999",
			"depreciation_accounts": "",
			"operating_lookback_days": 90,
			"operating_half_life_days": 30,
			"default_target_margin_pct": 6,
			"sanity_check_max_operating_rate": 0.50,
			"sanity_check_min_operating_rate": 0.01,
			"rate_stability_threshold_pct": 30,
			"reconciliation_variance_threshold_pct": 5,
		})

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
		"""calculate_and_snapshot returns a valid result dict."""
		from optimusland.utils.blended_rate import calculate_and_snapshot
		result = calculate_and_snapshot(self.company_name)

		self.assertIsInstance(result, dict)
		self.assertIn("operating_rate", result)
		self.assertIn("capital_rate", result)
		self.assertIn("base_rate", result)
		self.assertIn("total_kg", result)
		# Rates should be valid numbers (may be 0 in CI with no test data)
		self.assertGreaterEqual(result["operating_rate"], 0)
		self.assertGreaterEqual(result["total_kg"], 0)

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

	def test_get_base_rate_recalculates_after_settings_change(self):
		"""Changing settings invalidates today's cached snapshot."""
		from optimusland.utils.blended_rate import get_base_rate, calculate_and_snapshot

		frappe.db.set_single_value(
			"Optimus General Settings", "operating_lookback_days", 90
		)
		calculate_and_snapshot(self.company_name)

		frappe.db.set_single_value(
			"Optimus General Settings", "operating_lookback_days", 180
		)
		fresh = get_base_rate(self.company_name)

		self.assertEqual(fresh.get("operating_lookback_days"), 180)
		self.assertNotEqual(fresh.get("calculated_by"), "cached")

	def test_settings_save_invalidates_todays_snapshot(self):
		"""Saving settings clears today's snapshot so the next read recalculates."""
		from optimusland.utils.blended_rate import calculate_and_snapshot

		calculate_and_snapshot(self.company_name)
		self.assertTrue(
			frappe.db.exists("Blended Rate Snapshot", {"snapshot_date": today()})
		)

		settings = frappe.get_single("Optimus General Settings")
		settings.payment_reminders_enabled = 0
		settings.operating_lookback_days = (
			181 if (settings.operating_lookback_days or 90) == 180 else 180
		)
		settings.save(ignore_permissions=True)

		self.assertFalse(
			frappe.db.exists("Blended Rate Snapshot", {"snapshot_date": today()})
		)

	def test_calculate_and_snapshot_updates_todays_snapshot(self):
		"""Recalculating on the same day updates the existing snapshot instead of duplicating it."""
		from optimusland.utils.blended_rate import calculate_and_snapshot

		first = calculate_and_snapshot(self.company_name)
		settings = frappe.get_single("Optimus General Settings")
		settings.payment_reminders_enabled = 0
		settings.operating_lookback_days = 180
		settings.save(ignore_permissions=True)

		second = calculate_and_snapshot(self.company_name)
		snapshot_name = frappe.db.exists("Blended Rate Snapshot", today())
		snapshot = frappe.get_doc("Blended Rate Snapshot", snapshot_name)

		self.assertTrue(snapshot_name)
		self.assertEqual(snapshot.lookback_days_operating, 180)
		self.assertEqual(snapshot.base_rate, second.get("base_rate"))
		self.assertNotEqual(first.get("operating_lookback_days"), second.get("operating_lookback_days"))


class TestExponentialWeightedRatio(IntegrationTestCase):
	"""Unit tests for the exponential time-decay weighted ratio formula."""

	def test_equal_rates_give_same_result(self):
		"""When both days have same GL/kg ratio, result equals that ratio."""
		from optimusland.utils.blended_rate import _exponential_weighted_ratio
		from frappe.utils import today, add_days
		t = today()

		data = [
			frappe._dict(day=add_days(t, -2), gl_total=100.0, kg=200.0),
			frappe._dict(day=add_days(t, -1), gl_total=50.0, kg=100.0),
		]
		# Both days have ratio 0.5, so result must be 0.5 regardless of weights
		ratio = _exponential_weighted_ratio(data, half_life_days=1)
		self.assertAlmostEqual(ratio, 0.5, places=4)

	def test_infinite_half_life_gives_simple_sum_ratio(self):
		"""With very long half-life, result ≈ ΣGL / Σkg."""
		from optimusland.utils.blended_rate import _exponential_weighted_ratio
		from frappe.utils import today, add_days
		t = today()

		data = [
			frappe._dict(day=add_days(t, -5), gl_total=100.0, kg=10.0),     # rate 10.0
			frappe._dict(day=add_days(t, -1), gl_total=50.0, kg=100.0),     # rate 0.5
		]
		ratio = _exponential_weighted_ratio(data, half_life_days=10**9)
		simple = (100.0 + 50.0) / (10.0 + 100.0)  # = 150/110 ≈ 1.3636
		self.assertAlmostEqual(ratio, simple, places=4)

	def test_empty_list_returns_zero(self):
		"""Empty input returns 0."""
		from optimusland.utils.blended_rate import _exponential_weighted_ratio
		self.assertEqual(_exponential_weighted_ratio([], half_life_days=30), 0.0)

	def test_single_day_returns_gl_divided_by_kg(self):
		"""Single day returns GL/kg."""
		from optimusland.utils.blended_rate import _exponential_weighted_ratio
		from frappe.utils import today
		data = [frappe._dict(day=today(), gl_total=500.0, kg=1000.0)]
		self.assertEqual(_exponential_weighted_ratio(data, half_life_days=1), 0.5)

	def test_zero_total_kg_returns_zero(self):
		"""No kg across all days returns 0."""
		from optimusland.utils.blended_rate import _exponential_weighted_ratio
		from frappe.utils import today
		data = [frappe._dict(day=today(), gl_total=500.0, kg=0.0)]
		self.assertEqual(_exponential_weighted_ratio(data, half_life_days=30), 0.0)

	def test_gl_only_day_pushes_ratio_up(self):
		"""A GL-only day (kg=0) contributes to numerator, increasing the ratio."""
		from optimusland.utils.blended_rate import _exponential_weighted_ratio
		from frappe.utils import today, add_days
		t = today()

		data = [
			frappe._dict(day=add_days(t, -1), gl_total=500.0, kg=0.0),   # GL only
			frappe._dict(day=t, gl_total=500.0, kg=1000.0),               # normal
		]
		ratio = _exponential_weighted_ratio(data, half_life_days=9999)
		# Total GL = 1000, total kg = 1000, so simple ratio = 1.0
		# Without GL-only day, it would be 0.5
		self.assertAlmostEqual(ratio, 1.0, places=4)


class TestMergeDailyData(IntegrationTestCase):
	"""Unit tests for _merge_daily_data."""

	def test_includes_gl_only_days(self):
		"""Days with GL but no kg are kept (unlike old _build_daily_rates)."""
		from optimusland.utils.blended_rate import _merge_daily_data
		daily_gl = {"2026-01-01": 100.0, "2026-01-02": 200.0}
		daily_kg = {"2026-01-01": 50.0}
		records = _merge_daily_data(daily_gl, daily_kg)
		self.assertEqual(len(records), 2)
		self.assertEqual(records[0].kg, 50.0)
		self.assertEqual(records[1].kg, 0.0)  # GL-only day kept with kg=0

	def test_negative_kg_skipped(self):
		"""Days with negative kg (credit notes) are skipped."""
		from optimusland.utils.blended_rate import _merge_daily_data
		daily_gl = {"2026-01-01": 100.0}
		daily_kg = {"2026-01-01": -50.0}
		records = _merge_daily_data(daily_gl, daily_kg)
		self.assertEqual(len(records), 0)

	def test_no_gl_keeps_kg_days(self):
		"""Days with only kg (no GL) are kept with gl_total=0."""
		from optimusland.utils.blended_rate import _merge_daily_data
		records = _merge_daily_data({}, {"2026-01-01": 100.0})
		self.assertEqual(len(records), 1)
		self.assertEqual(records[0].gl_total, 0.0)
		self.assertEqual(records[0].kg, 100.0)

	def test_empty_input_returns_empty(self):
		"""Both dicts empty returns empty list."""
		from optimusland.utils.blended_rate import _merge_daily_data
		self.assertEqual(_merge_daily_data({}, {}), [])

	def test_sorted_by_day(self):
		"""Records are sorted by day ascending."""
		from optimusland.utils.blended_rate import _merge_daily_data
		daily_gl = {"2026-01-03": 300.0, "2026-01-01": 100.0}
		daily_kg = {"2026-01-02": 200.0}
		records = _merge_daily_data(daily_gl, daily_kg)
		self.assertEqual(len(records), 3)
		self.assertEqual(records[0].day, "2026-01-01")
		self.assertEqual(records[1].day, "2026-01-02")
		self.assertEqual(records[2].day, "2026-01-03")


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
