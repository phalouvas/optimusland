# Copyright (c) 2026, KAINOTOMO PH LTD and contributors
# For license information, please see license.txt

import frappe
from frappe.model.document import Document
from frappe.utils import today


class OptimusGeneralSettings(Document):
	def on_update(self):
		frappe.db.delete("Blended Rate Snapshot", {"snapshot_date": today()})
