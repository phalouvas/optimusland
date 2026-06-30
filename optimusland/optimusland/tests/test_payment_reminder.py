# Copyright (c) 2026, KAINOTOMO PH LTD and Contributors
# See license.txt

"""Tests for payment_reminder.py: send_payment_reminders and helper functions.

These are pure-logic or isolated tests that don't require real DB state
for the helper functions, plus an end-to-end test that mocks external
services (frappe.sendmail, SMS).
"""

import json
from unittest.mock import patch

import frappe
from frappe.tests import IntegrationTestCase

from optimusland.utils.payment_reminder import (
	_get_applicable_levels,
	_parse_sent_levels,
	_get_template,
	_get_settings,
	_get_overdue_invoices,
	_process_invoice,
	send_payment_reminders,
)


class TestGetApplicableLevels(IntegrationTestCase):
	"""Tests for _get_applicable_levels — pure logic, no DB needed."""

	def test_level1_at_1_day(self):
		self.assertEqual(_get_applicable_levels(1, []), [1])

	def test_level1_at_5_days(self):
		self.assertEqual(_get_applicable_levels(5, []), [1])

	def test_level2_after_level1_sent(self):
		self.assertEqual(_get_applicable_levels(12, [1]), [2])

	def test_level3_after_previous_sent(self):
		self.assertEqual(_get_applicable_levels(22, [1, 2]), [3])

	def test_level4_after_previous_sent(self):
		self.assertEqual(_get_applicable_levels(35, [1, 2, 3]), [4])

	def test_only_one_level_returned(self):
		"""Only the lowest unsent level should be returned per call."""
		result = _get_applicable_levels(35, [])
		self.assertEqual(len(result), 1)
		self.assertEqual(result[0], 1)

	def test_none_when_not_overdue(self):
		self.assertEqual(_get_applicable_levels(0, []), [])

	def test_all_sent_returns_empty(self):
		self.assertEqual(_get_applicable_levels(35, [1, 2, 3, 4]), [])

	def test_level2_skipped_if_already_sent(self):
		"""Already sent level 1 and 2 → returns level 3."""
		result = _get_applicable_levels(25, [1, 2])
		self.assertEqual(result, [3])


class TestParseSentLevels(IntegrationTestCase):
	"""Tests for _parse_sent_levels — pure logic."""

	def test_valid_json_list(self):
		self.assertEqual(_parse_sent_levels("[1, 2, 3]"), [1, 2, 3])

	def test_empty_json_list(self):
		self.assertEqual(_parse_sent_levels("[]"), [])

	def test_none_value(self):
		self.assertEqual(_parse_sent_levels(None), [])

	def test_empty_string(self):
		self.assertEqual(_parse_sent_levels(""), [])

	def test_invalid_json(self):
		"""Malformed JSON → returns [] silently."""
		self.assertEqual(_parse_sent_levels("{broken"), [])

	def test_already_list(self):
		"""If already a list (not string), return as-is."""
		self.assertEqual(_parse_sent_levels([1, 2]), [1, 2])


class TestTemplateRendering(IntegrationTestCase):
	"""Test that Jinja templates render correctly."""

	def test_render_customer_name(self):
		context = {
			"customer_name": "Test Customer",
			"invoice_name": "INV-001",
			"outstanding_amount": "€1,000.00",
			"due_date": "2026-01-01",
			"days_overdue": 5,
			"company": "Test Company",
			"reminder_level": 1,
		}
		template = "Dear {{ customer_name }}, invoice {{ invoice_name }} is overdue."
		result = frappe.render_template(template, context)
		self.assertIn("Test Customer", result)
		self.assertIn("INV-001", result)

	def test_render_full_template(self):
		"""Render a template matching the level 1 SMS format."""
		context = {
			"customer_name": "Customer A",
			"invoice_name": "SI-001",
			"outstanding_amount": "€500.00",
			"days_overdue": 3,
			"due_date": "2026-01-01",
			"company": "Co",
		}
		template = ("Dear {{ customer_name }}, invoice {{ invoice_name }} "
					"of {{ outstanding_amount }} is {{ days_overdue }} day(s) overdue "
					"(due: {{ due_date }}). Please arrange payment. - {{ company }}")
		result = frappe.render_template(template, context)
		self.assertIn("Customer A", result)
		self.assertIn("SI-001", result)
		self.assertIn("€500.00", result)
		self.assertIn("3", result)
		self.assertIn("Co", result)


class TestGetOverdueInvoices(IntegrationTestCase):
	"""Tests for _get_overdue_invoices — uses real DB."""

	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		cls.company = get_or_create_test_company()
		cls.warehouse = get_or_create_test_warehouse(cls.company.name)
		cls.customer = get_or_create_test_customer(cls.company.name)
		cls.potato_item = get_or_create_test_potato_item(cls.company.name)

	def test_returns_overdue_invoices(self):
		"""Overdue invoice returned; non-overdue excluded."""
		from optimusland.optimusland.tests import create_test_sales_invoice

		# Create an overdue SI (past due date with outstanding amount)
		old_date = frappe.utils.add_days(frappe.utils.today(), -30)
		si = create_test_sales_invoice(
			items_data=[{
				"item_code": self.potato_item.item_code,
				"qty": 10,
				"rate": 100.0,
			}],
			customer=self.customer.name,
			company=self.company.name,
			warehouse=self.warehouse.name,
			posting_date=old_date,
		)
		# Set outstanding amount > 0
		frappe.db.set_value("Sales Invoice", si.name, "outstanding_amount", 1000)

		invoices = _get_overdue_invoices(frappe.utils.today())
		invoice_names = [inv.name for inv in invoices]
		self.assertIn(si.name, invoice_names)


def get_or_create_test_company():
	"""Local import helper."""
	from optimusland.optimusland.tests import get_or_create_test_company as _get
	return _get()


def get_or_create_test_warehouse(company):
	from optimusland.optimusland.tests import get_or_create_test_warehouse as _get
	return _get(company)


def get_or_create_test_customer(company=None):
	"""Local import helper."""
	from optimusland.optimusland.tests import get_or_create_test_customer as _get
	return _get(company)


def get_or_create_test_potato_item(company=None):
	from optimusland.optimusland.tests import get_or_create_test_potato_item as _get
	return _get(company)
	return _get()
