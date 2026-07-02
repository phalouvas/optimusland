# Copyright (c) 2026, KAINOTOMO PH LTD and contributors
# For license information, please see license.txt

import json
import frappe
from frappe import _
from pathlib import Path


def after_migrate():
	"""Seed default data after migration."""
	_seed_default_reminder_templates()
	_seed_pipeline_dashboard_block()


def _seed_default_reminder_templates():
	"""Create 8 default payment reminder templates if none exist."""
	settings = frappe.get_single("Optimus General Settings")
	if settings.templates and len(settings.templates) > 0:
		return  # Already seeded

	defaults = [
		# Level 1 — Gentle (1 day after due)
		{
			"reminder_level": 1,
			"channel": "Email",
			"days_after_due": 1,
			"subject": _("Payment Reminder — {{ invoice_name }}"),
			"message": _(
				"<p>Dear {{ customer_name }},</p>"
				"<p>This is a friendly reminder that Sales Invoice "
				"<strong>{{ invoice_name }}</strong> for "
				"<strong>{{ outstanding_amount }}</strong> "
				"was due on <strong>{{ due_date }}</strong> "
				"({{ days_overdue }} day(s) overdue).</p>"
				"<p>We kindly request you to arrange payment at your earliest convenience.</p>"
				"<p>Thank you for your business!</p>"
				"<p>Best regards,<br>{{ company }}</p>"
			),
		},
		{
			"reminder_level": 1,
			"channel": "SMS",
			"days_after_due": 1,
			"message": _(
				"Dear {{ customer_name }}, invoice {{ invoice_name }} "
				"of {{ outstanding_amount }} is {{ days_overdue }} day(s) overdue "
				"(due: {{ due_date }}). Please arrange payment. - {{ company }}"
			),
		},
		# Level 2 — Follow-up (10 days after due)
		{
			"reminder_level": 2,
			"channel": "Email",
			"days_after_due": 10,
			"subject": _("Follow-up: Payment Reminder — {{ invoice_name }}"),
			"message": _(
				"<p>Dear {{ customer_name }},</p>"
				"<p>This is a follow-up reminder regarding Sales Invoice "
				"<strong>{{ invoice_name }}</strong> for "
				"<strong>{{ outstanding_amount }}</strong>, "
				"which is now <strong>{{ days_overdue }} days overdue</strong> "
				"(due: {{ due_date }}).</p>"
				"<p>We would appreciate your prompt attention to this matter.</p>"
				"<p>Best regards,<br>{{ company }}</p>"
			),
		},
		{
			"reminder_level": 2,
			"channel": "SMS",
			"days_after_due": 10,
			"message": _(
				"Follow-up: {{ customer_name }}, invoice {{ invoice_name }} "
				"of {{ outstanding_amount }} remains unpaid "
				"({{ days_overdue }} days overdue, due: {{ due_date }}). "
				"Kindly arrange payment. - {{ company }}"
			),
		},
		# Level 3 — Pressing (20 days after due)
		{
			"reminder_level": 3,
			"channel": "Email",
			"days_after_due": 20,
			"subject": _("URGENT: Payment Reminder — {{ invoice_name }}"),
			"message": _(
				"<p>Dear {{ customer_name }},</p>"
				"<p>This is an urgent reminder for Sales Invoice "
				"<strong>{{ invoice_name }}</strong> for "
				"<strong>{{ outstanding_amount }}</strong>, "
				"now <strong>{{ days_overdue }} days overdue</strong> "
				"(due: {{ due_date }}).</p>"
				"<p>We must insist on immediate payment to avoid any disruption in service.</p>"
				"<p>Please remit the amount at your earliest convenience.</p>"
				"<p>Best regards,<br>{{ company }}</p>"
			),
		},
		{
			"reminder_level": 3,
			"channel": "SMS",
			"days_after_due": 20,
			"message": _(
				"URGENT: {{ customer_name }}, invoice {{ invoice_name }} "
				"of {{ outstanding_amount }} is {{ days_overdue }} days overdue. "
				"Immediate payment required. - {{ company }}"
			),
		},
		# Level 4 — Final Warning (30 days after due)
		{
			"reminder_level": 4,
			"channel": "Email",
			"days_after_due": 30,
			"subject": _("FINAL WARNING: Payment Reminder — {{ invoice_name }}"),
			"message": _(
				"<p>Dear {{ customer_name }},</p>"
				"<p><strong>FINAL NOTICE</strong></p>"
				"<p>Sales Invoice <strong>{{ invoice_name }}</strong> for "
				"<strong>{{ outstanding_amount }}</strong> is now "
				"<strong>{{ days_overdue }} days overdue</strong> "
				"(due: {{ due_date }}).</p>"
				"<p>Unless payment is received within 7 days, we will be forced to "
				"take further collection actions, which may include involving a "
				"third-party collection agency.</p>"
				"<p>Please arrange immediate payment to avoid escalation.</p>"
				"<p>Best regards,<br>{{ company }}</p>"
			),
		},
		{
			"reminder_level": 4,
			"channel": "SMS",
			"days_after_due": 30,
			"message": _(
				"FINAL NOTICE: {{ customer_name }}, invoice {{ invoice_name }} "
				"of {{ outstanding_amount }} is {{ days_overdue }} days overdue. "
				"Pay within 7 days or further action will be taken. - {{ company }}"
			),
		},
	]

	for tmpl in defaults:
		settings.append("templates", tmpl)

	settings.save(ignore_permissions=True)


def _seed_pipeline_dashboard_block():
	"""Create the Pipeline Dashboard Custom HTML Block if it doesn't exist.

	The block is embedded in the Optimus workspace as a custom block,
	rendering the three-tier pipeline table and alerts panel.
	"""
	block_name = "Pipeline Dashboard"
	if frappe.db.exists("Custom HTML Block", block_name):
		return

	base_path = Path(__file__).resolve().parent.parent / "public" / "html"
	html_path = base_path / "pipeline_table.html"
	js_path = base_path / "pipeline_table.js"

	if not html_path.exists():
		frappe.log_error(
			message=f"Pipeline dashboard HTML not found at {html_path}",
			title="Seed Pipeline Dashboard",
		)
		return

	html_content = html_path.read_text(encoding="utf-8")
	script_content = js_path.read_text(encoding="utf-8") if js_path.exists() else ""

	block = frappe.get_doc({
		"doctype": "Custom HTML Block",
		"name": block_name,
		"html": html_content,
		"script": script_content,
		"style": None,
		"private": 0,
	})
	block.insert(ignore_permissions=True)

	# Add the block to the Optimus workspace if not already present
	workspace_name = "Optimus"
	if not frappe.db.exists("Workspace", workspace_name):
		return

	workspace = frappe.get_doc("Workspace", workspace_name)
	already_added = any(cb.block == block_name for cb in workspace.custom_blocks)
	if not already_added:
		workspace.append("custom_blocks", {
			"custom_block_name": block_name,
			"label": block_name,
		})

		# Also add Pipeline shortcuts if not already present
		pipeline_shortcut_labels = {"Failed PRs", "Stuck WOs", "Unbilled DNs"}
		existing_labels = {s.label for s in workspace.shortcuts}
		missing = pipeline_shortcut_labels - existing_labels

		if missing:
			shortcut_defs = [
				{
					"label": "Failed PRs",
					"type": "DocType",
					"link_to": "Purchase Receipt",
					"doc_view": "List",
					"color": "Red",
					"format": "{} Failed",
					"stats_filter": json.dumps([
						["Purchase Receipt", "custom_production_plan", "is", "not set", False],
						["Purchase Receipt", "docstatus", "=", 1, False],
					]),
				},
				{
					"label": "Stuck WOs",
					"type": "DocType",
					"link_to": "Work Order",
					"doc_view": "List",
					"color": "Orange",
					"format": "{} Draft",
					"stats_filter": json.dumps([
						["Work Order", "status", "=", "Draft", False],
						["Work Order", "docstatus", "=", 0, False],
					]),
				},
				{
					"label": "Unbilled DNs",
					"type": "DocType",
					"link_to": "Delivery Note",
					"doc_view": "List",
					"color": "Yellow",
					"format": "{} To Bill",
					"stats_filter": json.dumps([
						["Delivery Note", "status", "=", "To Bill", False],
						["Delivery Note", "docstatus", "=", 1, False],
					]),
				},
			]
			for sd in shortcut_defs:
				if sd["label"] not in existing_labels:
					workspace.append("shortcuts", sd)

		workspace.save(ignore_permissions=True)

	# Export fixtures after seeding so the JSON file is updated
	try:
		frappe.enqueue(
			"frappe.core.doctype.fixture.export_fixtures",
			app="optimusland",
			queue="short",
		)
	except Exception:
		pass
