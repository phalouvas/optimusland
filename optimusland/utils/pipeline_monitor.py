"""Daily pipeline health digest email.

Sends a summary of critical and warning-level pipeline alerts to
configured recipients via email.

Follows the same pattern as ``payment_reminder.py``.
"""

import frappe
from frappe.utils import today, add_days
from frappe import _


@frappe.whitelist()
def send_pipeline_digest():
    """Send the daily pipeline health digest if there are alerts."""
    from optimusland.utils.pipeline import get_alerts

    recipients = _get_recipients()
    if not recipients:
        return {"sent": False, "reason": "No recipients configured"}

    alerts = get_alerts(from_date=add_days(today(), -30), to_date=today())
    critical = [a for a in alerts if a["severity"] == "critical"]
    warnings = [a for a in alerts if a["severity"] == "warning"]

    if not critical and not warnings:
        return {"sent": False, "reason": "No critical or warning alerts"}

    subject = _(
        "Pipeline Health Digest — {critical} critical, {warning} warnings"
    ).format(critical=len(critical), warning=len(warnings))

    message = _build_digest_html(critical, warnings)

    try:
        frappe.sendmail(
            recipients=recipients,
            subject=subject,
            message=message,
            reference_doctype=None,
            reference_name=None,
        )
        frappe.log_error(
            message=(
                f"Pipeline digest sent to {len(recipients)} recipient(s): "
                f"{len(critical)} critical, {len(warnings)} warnings"
            ),
            title="Pipeline Digest — Sent",
        )
        return {"sent": True, "recipients": len(recipients)}
    except Exception as e:
        frappe.log_error(
            message=f"Failed to send pipeline digest: {e}",
            title="Pipeline Digest — Error",
        )
        return {"sent": False, "reason": str(e)}


def _get_recipients():
    """Get the list of email recipients from Optimus General Settings."""
    recipients_str = frappe.db.get_single_value(
        "Optimus General Settings", "pipeline_alert_recipients"
    )
    if not recipients_str:
        return []
    return [r.strip() for r in recipients_str.split(",") if r.strip()]


def _build_digest_html(critical, warnings):
    """Build the HTML email body from alert lists."""
    rows = ""

    for alert in critical:
        rows += _alert_row("🔴", alert)

    for alert in warnings:
        rows += _alert_row("🟠", alert)

    return f"""
    <h2>Pipeline Health Digest</h2>
    <p>Date: {today()}</p>
    <table style="border-collapse:collapse;width:100%;max-width:700px;font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,sans-serif;font-size:13px;">
        <thead>
            <tr style="background:#f8f9fa;">
                <th style="padding:8px 12px;border:1px solid #d1d8dd;text-align:left;">Severity</th>
                <th style="padding:8px 12px;border:1px solid #d1d8dd;text-align:left;">Alert</th>
                <th style="padding:8px 12px;border:1px solid #d1d8dd;text-align:left;">Entity</th>
                <th style="padding:8px 12px;border:1px solid #d1d8dd;text-align:left;">Detail</th>
            </tr>
        </thead>
        <tbody>
            {rows}
        </tbody>
    </table>
    <p style="color:#687178;font-size:12px;margin-top:16px;">
        This is an automated digest from Optimusland. Configure recipients in
        Optimus General Settings → Pipeline Alert Recipients.
    </p>
    """


def _alert_row(icon, alert):
    return (
        f"<tr>"
        f"<td style='padding:8px 12px;border:1px solid #d1d8dd;'>{icon}</td>"
        f"<td style='padding:8px 12px;border:1px solid #d1d8dd;'><b>{alert['title']}</b></td>"
        f"<td style='padding:8px 12px;border:1px solid #d1d8dd;'>{alert.get('entity', '—')}</td>"
        f"<td style='padding:8px 12px;border:1px solid #d1d8dd;'>{alert.get('message', '')}</td>"
        f"</tr>"
    )
