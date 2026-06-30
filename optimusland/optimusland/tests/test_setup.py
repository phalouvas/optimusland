# Copyright (c) 2026, KAINOTOMO PH LTD and Contributors
# See license.txt

"""Tests for setup.py: _seed_default_reminder_templates.
"""

import frappe
from frappe.tests import IntegrationTestCase

from optimusland.utils.setup import _seed_default_reminder_templates


class TestSeedDefaultReminderTemplates(IntegrationTestCase):
	"""Tests for _seed_default_reminder_templates (after_migrate hook)."""

	def test_seeds_8_templates(self):
		"""After migrate → 8 default templates exist (idempotent)."""
		from optimusland.utils.setup import _seed_default_reminder_templates

		# Test that calling the function is idempotent and produces 8 templates
		_seed_default_reminder_templates()

		# Reload from DB to get fresh data
		settings = frappe.get_doc("Optimus General Settings", "Optimus General Settings")
		self.assertEqual(len(settings.templates), 8)

		# Check all levels are present
		levels = {int(t.reminder_level) for t in settings.templates}
		self.assertSetEqual(levels, {1, 2, 3, 4})

		# Check both channels present
		channels = {t.channel for t in settings.templates}
		self.assertSetEqual(channels, {"Email", "SMS"})

	def test_idempotent_no_duplicates(self):
		"""Calling twice → still 8 templates, not 16."""
		from optimusland.utils.setup import _seed_default_reminder_templates

		_seed_default_reminder_templates()
		_seed_default_reminder_templates()

		settings = frappe.get_doc("Optimus General Settings", "Optimus General Settings")
		self.assertEqual(len(settings.templates), 8)
