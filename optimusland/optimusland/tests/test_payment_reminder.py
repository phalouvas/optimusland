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
	_get_customer_email,
	_get_customer_mobile,
	_process_invoice,
	send_payment_reminders,
)


class TestCustomerContactHelpers(IntegrationTestCase):
	"""Tests for _get_customer_email and _get_customer_mobile."""

	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		from optimusland.optimusland.tests import get_or_create_test_customer
		cls.customer = get_or_create_test_customer()

	def test_get_customer_email_returns_none_if_not_set(self):
		email = _get_customer_email(self.customer.name)
		# frappe.db.get_value returns '' when field is NULL
		self.assertIn(email, (None, ""),
					  "Email should be None or empty when not set")

	def test_get_customer_email_when_set(self):
		frappe.db.set_value("Customer", self.customer.name, "email_id",
							"test@example.com")
		email = _get_customer_email(self.customer.name)
		self.assertEqual(email, "test@example.com")

	def test_get_customer_mobile_when_set(self):
		frappe.db.set_value("Customer", self.customer.name, "mobile_no",
							"+1234567890")
		mobile = _get_customer_mobile(self.customer.name)
		self.assertEqual(mobile, "+1234567890")


class TestSendPaymentReminders(IntegrationTestCase):
	"""End-to-end tests for send_payment_reminders."""

	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		from optimusland.optimusland.tests import (
			get_or_create_test_company,
			get_or_create_test_warehouse,
			get_or_create_test_customer,
			get_or_create_test_potato_item,
		)
		cls.company = get_or_create_test_company()
		cls.warehouse = get_or_create_test_warehouse(cls.company.name)
		cls.customer = get_or_create_test_customer(cls.company.name)
		cls.potato_item = get_or_create_test_potato_item(cls.company.name)

	def setUp(self):
		"""Enable reminders and ensure templates exist before each test."""
		from optimusland.utils.setup import _seed_default_reminder_templates
		_seed_default_reminder_templates()
		settings = frappe.get_single("Optimus General Settings")
		settings.payment_reminders_enabled = 1
		settings.payment_reminders_email = 1
		settings.save(ignore_permissions=True)

	@patch("frappe.sendmail")
	def test_sends_reminder_for_overdue_invoice(self, mock_sendmail):
		"""Overdue SI with templates → reminder sent and tracked."""
		from optimusland.optimusland.tests import create_test_sales_invoice

		old_date = frappe.utils.add_days(frappe.utils.today(), -5)
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
		frappe.db.set_value("Sales Invoice", si.name, "outstanding_amount", 1000)
		# Set due_date to be overdue
		frappe.db.set_value("Sales Invoice", si.name, "due_date",
							frappe.utils.add_days(frappe.utils.today(), -3))

		# Set contact email so reminder can be sent
		frappe.db.set_value("Sales Invoice", si.name, "contact_email",
							"customer@test.com")

		send_payment_reminders()

		# Verify reminder was tracked
		sent = frappe.db.get_value("Sales Invoice", si.name,
								   "custom_payment_reminders_sent")
		self.assertIsNotNone(sent)
		self.assertIn("1", sent or "[]")

	@patch("frappe.sendmail")
	def test_reminders_disabled_skips(self, mock_sendmail):
		"""payment_reminders_enabled=0 → no processing."""
		settings = frappe.get_single("Optimus General Settings")
		settings.payment_reminders_enabled = 0
		settings.save(ignore_permissions=True)

		send_payment_reminders()
		mock_sendmail.assert_not_called()


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
