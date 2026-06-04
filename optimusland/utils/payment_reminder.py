# Copyright (c) 2026, KAINOTOMO PH LTD and contributors
# For license information, please see license.txt

import json

import frappe
from frappe import _
from frappe.utils import date_diff, today, flt


def send_payment_reminders():
	"""Daily scheduled task: send payment reminders for overdue Sales Invoices.

	Fetches enabled reminders from Optimus General Settings, queries overdue unpaid
	Sales Invoices, and sends email/SMS reminders at levels 1-4 based on days
	since due_date. Tracks sent levels on each invoice to prevent duplicates.
	"""
	settings = _get_settings()
	if not settings or not settings.payment_reminders_enabled:
		return

	email_enabled = settings.payment_reminders_email
	sms_enabled = settings.payment_reminders_sms

	if not email_enabled and not sms_enabled:
		return

	today_date = today()
	invoices = _get_overdue_invoices(today_date)

	for invoice in invoices:
		try:
			_process_invoice(invoice, settings, today_date, email_enabled, sms_enabled)
		except Exception as e:
			frappe.log_error(
				title=_("Payment Reminder Error"),
				message=_("Failed to process invoice {0}: {1}").format(
					invoice.get("name"), str(e)
				),
			)


def _get_settings():
	"""Fetch Optimus General Settings, cached for the duration of the task."""
	return frappe.get_cached_doc("Optimus General Settings")


def _get_overdue_invoices(today_date):
	"""Query submitted, unpaid, overdue Sales Invoices."""
	return frappe.db.sql(
		"""
		SELECT
			si.name,
			si.customer,
			si.customer_name,
			si.posting_date,
			si.due_date,
			si.grand_total,
			si.outstanding_amount,
			si.contact_email,
			si.contact_mobile,
			si.company,
			si.custom_payment_reminders_sent
		FROM `tabSales Invoice` si
		WHERE si.docstatus = 1
			AND si.due_date < %(today)s
			AND si.status NOT IN ('Paid', 'Credit Note Issued', 'Return', 'Cancelled')
			AND si.outstanding_amount > 0
		ORDER BY si.due_date ASC
		""",
		{"today": today_date},
		as_dict=1,
	)


def _process_invoice(invoice, settings, today_date, email_enabled, sms_enabled):
	"""Evaluate and send reminders for a single invoice."""
	days_overdue = date_diff(today_date, invoice.due_date)
	already_sent = _parse_sent_levels(invoice.custom_payment_reminders_sent)
	applicable_levels = _get_applicable_levels(days_overdue, already_sent)

	if not applicable_levels:
		return

	# Resolve recipients
	recipient_email = invoice.contact_email or _get_customer_email(invoice.customer)
	recipient_mobile = invoice.contact_mobile or _get_customer_mobile(invoice.customer)

	channels_to_send = []
	if email_enabled and recipient_email:
		channels_to_send.append(("Email", recipient_email))
	if sms_enabled and recipient_mobile:
		channels_to_send.append(("SMS", recipient_mobile))

	if not channels_to_send:
		frappe.log_error(
			title=_("Payment Reminder - No Contact Info"),
			message=_(
				"Invoice {0} (Customer: {1}) has no contact email or mobile. "
				"Skipping reminders."
			).format(invoice.name, invoice.customer_name or invoice.customer),
		)
		return

	# Common context for template rendering
	base_context = {
		"invoice_name": invoice.name,
		"customer_name": invoice.customer_name or invoice.customer,
		"due_date": str(invoice.due_date or ""),
		"posting_date": str(invoice.posting_date or ""),
		"total": flt(invoice.grand_total),
		"outstanding_amount": flt(invoice.outstanding_amount),
		"days_overdue": days_overdue,
		"company": invoice.company or "",
	}

	sent_levels = []
	for level in applicable_levels:
		level_sent_channels = []

		for channel, recipient in channels_to_send:
			template = _get_template(settings, level, channel)
			if not template:
				continue

			context = {**base_context, "reminder_level": level}
			rendered_message = frappe.render_template(template.message, context)

			try:
				if channel == "Email":
					rendered_subject = frappe.render_template(
						template.subject or _("Payment Reminder - Level {0}").format(level),
						context,
					)
					frappe.sendmail(
						recipients=[recipient],
						subject=rendered_subject,
						message=rendered_message,
						reference_doctype="Sales Invoice",
						reference_name=invoice.name,
					)
					level_sent_channels.append("Email")
				elif channel == "SMS":
					_send_sms(recipient, rendered_message)
					level_sent_channels.append("SMS")
			except Exception as e:
				frappe.log_error(
					title=_("Payment Reminder Send Failed"),
					message=_(
						"Failed to send {0} reminder for invoice {1}: {2}"
					).format(channel, invoice.name, str(e)),
				)

		if level_sent_channels:
			sent_levels.append(level)
			_comment_on_invoice(invoice.name, level, level_sent_channels)

	if sent_levels:
		updated_sent = sorted(set(already_sent + sent_levels))
		frappe.db.set_value(
			"Sales Invoice",
			invoice.name,
			"custom_payment_reminders_sent",
			json.dumps(updated_sent),
		)
		frappe.db.commit()


def _parse_sent_levels(raw_value):
	"""Parse the JSON sent-levels field from a Sales Invoice."""
	if not raw_value:
		return []
	try:
		return json.loads(raw_value) if isinstance(raw_value, str) else list(raw_value)
	except (json.JSONDecodeError, TypeError):
		return []


def _get_applicable_levels(days_overdue, already_sent):
	"""Determine which reminder levels should fire, skipping already-sent ones."""
	thresholds = {1: 1, 2: 10, 3: 20, 4: 30}
	applicable = []
	for level, threshold in sorted(thresholds.items()):
		if days_overdue >= threshold and level not in already_sent:
			applicable.append(level)
	return applicable


def _get_template(settings, level, channel):
	"""Find the matching template row in settings for the given level and channel."""
	if not settings.templates:
		return None
	for t in settings.templates:
		if int(t.reminder_level or 0) == level and t.channel == channel:
			return t
	return None


def _get_customer_email(customer_name):
	"""Fallback: fetch email_id from the Customer doctype."""
	return frappe.db.get_value("Customer", customer_name, "email_id")


def _get_customer_mobile(customer_name):
	"""Fallback: fetch mobile_no from the Customer doctype."""
	return frappe.db.get_value("Customer", customer_name, "mobile_no")


def _send_sms(recipient, message):
	"""Send SMS via Frappe's SMS Center if configured.

	If SMS Settings are not configured, this is skipped silently.
	"""
	try:
		from frappe.core.doctype.sms_center.sms_center import send_sms
		send_sms([recipient], message)
	except Exception:
		# SMS gateway not configured — skip gracefully
		pass


def _comment_on_invoice(invoice_name, level, channels):
	"""Add an activity comment to the Sales Invoice tracking which reminder was sent."""
	channel_str = " & ".join(channels)
	comment = _("Payment Reminder Level {0} sent via {1}").format(level, channel_str)
	try:
		doc = frappe.get_doc("Sales Invoice", invoice_name)
		doc.add_comment("Info", comment)
	except Exception:
		pass
