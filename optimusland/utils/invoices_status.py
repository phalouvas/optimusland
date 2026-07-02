import frappe
from frappe.utils import flt


def reconcile_invoices_for_party(
    party: str,
    party_type: str,
    company: str,
    log_source: str = "reconciliation",
    max_age_days: int | None = 90,
) -> int:
    """Check GL balance for a party and mark unpaid invoices as Paid if balance ≈ 0.

    Args:
        party: Customer or Supplier name.
        party_type: "Customer" or "Supplier".
        company: Company name.
        log_source: Identifier for logging ("daily_cron" or "je_hook").
        max_age_days: Limit to invoices within N days (None = no limit).

    Returns:
        Number of invoices marked as Paid.
    """
    doctype = "Sales Invoice" if party_type == "Customer" else "Purchase Invoice"

    gl_balance = frappe.db.sql(
        """
        SELECT SUM(debit_in_account_currency) - SUM(credit_in_account_currency)
        FROM `tabGL Entry`
        WHERE party_type = %s AND party = %s AND company = %s
        AND is_cancelled = 0
        """,
        (party_type, party, company),
    )
    total_unpaid = flt(gl_balance[0][0]) if gl_balance and gl_balance[0][0] else 0

    if not (-0.5 <= total_unpaid <= 0.5):
        return 0

    party_field = "customer" if party_type == "Customer" else "supplier"

    filters = {
        "status": ["in", ["Unpaid", "Overdue"]],
        "docstatus": 1,
        party_field: party,
    }
    if max_age_days is not None:
        cutoff_date = frappe.utils.add_days(frappe.utils.nowdate(), -max_age_days)
        filters["posting_date"] = [">=", cutoff_date]

    invoices = frappe.get_all(
        doctype,
        filters=filters,
        fields=["name"],
    )

    count = 0
    for invoice in invoices:
        frappe.db.set_value(doctype, invoice.name, "status", "Paid")
        count += 1

    if count > 0:
        frappe.log_error(
            title=f"Invoice Status Fixed ({log_source})",
            message=(
                f"Marked {count} {doctype}(s) as Paid for {party_type} '{party}' "
                f"in company '{company}' (GL balance: {total_unpaid})"
            ),
        )

    return count


def on_journal_entry_submit(doc, method):
    """Hook on Journal Entry submit: reconcile invoice statuses for affected parties.

    When a Journal Entry is submitted, it may net a dual-role party's balance
    (e.g., same entity as both Supplier and Customer). This hook checks the
    GL balance for each affected party and marks their invoices as Paid if
    the balance is effectively zero.
    """
    seen = set()
    for account in doc.accounts:
        if account.party and account.party_type:
            key = (account.party_type, account.party, doc.company)
            if key not in seen:
                seen.add(key)
                reconcile_invoices_for_party(
                    party=account.party,
                    party_type=account.party_type,
                    company=doc.company,
                    log_source="je_hook",
                    max_age_days=None,  # JE hooks have no date limit
                )


def on_journal_entry_cancel(doc, method):
    """Hook on Journal Entry cancel: revert invoice statuses for affected parties.

    When a Journal Entry is cancelled, its GL entries are flagged as cancelled.
    This may reverse a previous balance netting, leaving parties with invoices
    that are incorrectly marked as Paid.
    """
    seen = set()
    for account in doc.accounts:
        if account.party and account.party_type:
            key = (account.party_type, account.party, doc.company)
            if key not in seen:
                seen.add(key)
                _revert_paid_invoices_for_party(
                    party=account.party,
                    party_type=account.party_type,
                    company=doc.company,
                )


def _revert_paid_invoices_for_party(party: str, party_type: str, company: str) -> int:
    """Revert invoices for a party from Paid back to Unpaid/Overdue.

    Called when a JE is cancelled. Checks the GL balance for the party;
    if the balance is no longer near zero, any 'Paid' invoices with
    outstanding amounts > €0.50 are reverted to their correct status.
    """
    doctype = "Sales Invoice" if party_type == "Customer" else "Purchase Invoice"

    gl_balance = frappe.db.sql(
        """
        SELECT SUM(debit_in_account_currency) - SUM(credit_in_account_currency)
        FROM `tabGL Entry`
        WHERE party_type = %s AND party = %s AND company = %s
        AND is_cancelled = 0
        """,
        (party_type, party, company),
    )
    total_unpaid = flt(gl_balance[0][0]) if gl_balance and gl_balance[0][0] else 0

    # If GL balance is still ≈ 0, no need to revert
    if -0.5 <= total_unpaid <= 0.5:
        return 0

    party_field = "customer" if party_type == "Customer" else "supplier"

    invoices = frappe.get_all(
        doctype,
        filters={
            "status": "Paid",
            "outstanding_amount": [">", 0.5],
            "docstatus": 1,
            party_field: party,
        },
        fields=["name", "due_date"],
    )

    today = frappe.utils.today()
    count = 0
    for invoice in invoices:
        due_date = invoice.due_date
        new_status = "Overdue" if due_date and str(due_date) < today else "Unpaid"
        frappe.db.set_value(doctype, invoice.name, "status", new_status)
        count += 1

    if count > 0:
        frappe.log_error(
            title="Invoice Status Reverted (JE cancel)",
            message=(
                f"Reverted {count} {doctype}(s) from Paid for {party_type} '{party}' "
                f"in company '{company}' (GL balance: {total_unpaid})"
            ),
        )

    return count


def fix_unpaid_overdue_purchase_invoices_status():
    """Daily cron: fix stuck Purchase Invoice statuses via GL reconciliation."""
    return _fix_unpaid_overdue_invoices("Purchase Invoice", "Supplier", "supplier")


def fix_unpaid_overdue_sales_invoices_status():
    """Daily cron: fix stuck Sales Invoice statuses via GL reconciliation."""
    return _fix_unpaid_overdue_invoices("Sales Invoice", "Customer", "customer")


def _fix_unpaid_overdue_invoices(doctype: str, party_type: str, party_field: str) -> bool:
    """Shared implementation for daily cron: group unpaid invoices by party and reconcile."""
    default_company = frappe.defaults.get_user_default("Company")
    ninety_days_ago = frappe.utils.add_days(frappe.utils.nowdate(), -90)

    filters = {
        "status": ["in", ["Unpaid", "Overdue"]],
        "posting_date": [">=", ninety_days_ago],
        "docstatus": 1,
    }

    invoices = frappe.get_all(doctype, filters=filters, fields=["name", party_field])

    invoices_by_party = {}
    for invoice in invoices:
        party = invoice.get(party_field)
        if not party:
            continue
        invoices_by_party.setdefault(party, []).append(invoice)

    total_fixed = 0
    for party in invoices_by_party:
        total_fixed += reconcile_invoices_for_party(
            party=party,
            party_type=party_type,
            company=default_company,
            log_source="daily_cron",
            max_age_days=90,  # Cron limits to recent invoices
        )

    if total_fixed > 0:
        frappe.log_error(
            title="Invoice Status Fix (daily cron)",
            message=(
                f"Daily cron marked {total_fixed} {doctype}(s) as Paid "
                f"across {len(invoices_by_party)} {party_type}(s)."
            ),
        )

    return True

