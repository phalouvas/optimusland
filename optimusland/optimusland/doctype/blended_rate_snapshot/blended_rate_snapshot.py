# Copyright (c) 2026, KAINOTOMO PH LTD and contributors
# For license information, please see license.txt

from __future__ import unicode_literals
import frappe
from frappe.model.document import Document


class BlendedRateSnapshot(Document):
	"""Stores a single calculation result of the blended rate.

	Auto-created by blended_rate.calculate_and_snapshot() on each
	rate calculation (cached up to 24h).  Enables the Base Rate Report
	trend chart and monthly reconciliation without re-querying raw GL.
	"""

	def validate(self):
		if not self.operating_rate and not self.capital_rate:
			frappe.throw("At least one rate component must be provided.")

	def on_update(self):
		"""Keep the most recent 366 snapshots; auto-purge oldest."""
		pass
