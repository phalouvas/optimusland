# Copyright (c) 2026, KAINOTOMO PH LTD and contributors
# For license information, please see license.txt

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

	The block is embedded in the Manufacturing Pipeline workspace,
	rendering the three-tier pipeline table and alerts panel.
	"""
	block_name = "Pipeline Dashboard"
	if frappe.db.exists("Custom HTML Block", block_name):
		return

	base_path = Path(__file__).resolve().parent.parent / "public" / "html"
	html_path = base_path / "pipeline_table.html"
	js_path = base_path / "pipeline_table.js"
	css_path = base_path / "pipeline_table.css"

	if not html_path.exists():
		frappe.log_error(
			message=f"Pipeline dashboard HTML not found at {html_path}",
			title="Seed Pipeline Dashboard",
		)
		return

	html_content = html_path.read_text(encoding="utf-8")
	script_content = js_path.read_text(encoding="utf-8") if js_path.exists() else ""
	style_content = css_path.read_text(encoding="utf-8") if css_path.exists() else ""

	block = frappe.get_doc({
		"doctype": "Custom HTML Block",
		"name": block_name,
		"html": html_content,
		"script": script_content,
		"style": style_content,
		"private": 0,
	})
	block.insert(ignore_permissions=True)
