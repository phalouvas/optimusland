# Copyright (c) 2026, KAINOTOMO PH LTD and Contributors
# See license.txt

"""Net Position utilities for dual-role parties (Supplier + Customer).

Provides two ``@frappe.whitelist()`` functions callable from client-side JS:

1. ``get_party_net_position`` — Returns PI and SI outstanding totals plus
   the computed net position for a party linked via a ``Party Link``.
2. ``create_netting_journal_entry`` — Creates a draft Journal Entry that
   offsets the smaller of the two outstanding amounts.
"""

import frappe
from frappe.utils import flt
from erpnext.accounts.utils import get_balance_on

# ---------------------------------------------------------------------------
# Public — callable from client-side JS via frappe.call()
# ---------------------------------------------------------------------------


@frappe.whitelist()
def get_party_net_position(party_type: str, party_name: str) -> dict:
    """Return the net position for a dual-role party linked via Party Link.

    Uses GL balances (``tabGL Entry``) rather than invoice ``outstanding_amount``
    to give accurate positions even after Common Party Accounting has run its
    automatic netting Journal Entries.

    Args:
        party_type: ``"Supplier"`` or ``"Customer"``.
        party_name: Name of the party.

    Returns:
        A dict with keys:
        - ``has_party_link`` (bool) — whether a Party Link was found.
        - ``linked_party`` (str) — the linked party name.
        - ``linked_party_type`` (str) — ``"Supplier"`` or ``"Customer"``.
        - ``customer_gl`` (float) — Receivable GL balance (positive = customer owes us).
        - ``supplier_gl`` (float) — Payable GL balance (negative = we owe supplier).
        - ``net_position`` (float) — absolute net |we_owe − they_owe|.
        - ``net_label`` (str) — ``"Owed to Supplier"`` or ``"Owed by Customer"``.
    """
    linked = _find_linked_party(party_type, party_name)
    if not linked:
        return {"has_party_link": False}

    company = frappe.defaults.get_user_default("Company")

    # GL balances — these are the REAL numbers, not invoice outstanding
    customer_gl = get_balance_on(
        party_type="Customer",
        party=linked["customer_name"],
        account_type="Receivable",
        company=company,
    )
    supplier_gl = get_balance_on(
        party_type="Supplier",
        party=linked["supplier_name"],
        account_type="Payable",
        company=company,
    )

    # get_balance_on returns sum(debit) − sum(credit)
    # For Payable: negative = normal credit balance = we owe supplier
    # For Receivable: positive = normal debit balance = customer owes us
    # Flip supplier sign so positive means "we owe supplier"
    pi_gl = -supplier_gl
    si_gl = customer_gl

    net = pi_gl - si_gl

    if net >= 0:
        net_label = f"Owed to Supplier ({linked['supplier_name']})"
    else:
        net_label = f"Owed by Customer ({linked['customer_name']})"

    return {
        "has_party_link": True,
        "linked_party": linked["other_party"],
        "linked_party_type": linked["other_type"],
        "customer_gl": customer_gl,
        "supplier_gl": supplier_gl,
        "pi_gl": pi_gl,
        "si_gl": si_gl,
        "net_position": abs(net),
        "net_label": net_label,
    }


@frappe.whitelist()
def create_netting_journal_entry(party_type: str, party_name: str) -> dict:
    """Create a draft Journal Entry to net PI and SI outstanding amounts.

    The netting amount is the **smaller** of the two outstanding totals.
    The resulting JE references specific Purchase Invoices and Sales
    Invoices via ``reference_type`` / ``reference_name`` on each account
    row, so ERPNext's Payment Ledger Entry mechanism correctly reduces
    ``outstanding_amount`` on the referenced invoices.

    The JE is saved as a draft (not submitted) so the user can review,
    adjust, and submit manually.

    Args:
        party_type: ``"Supplier"`` or ``"Customer"``.
        party_name: Name of the party.

    Returns:
        A dict with ``success`` (bool) and either ``journal_entry`` (str,
        the name of the new draft JE) or ``error`` (str).
    """
    position = get_party_net_position(party_type, party_name)
    if not position.get("has_party_link"):
        return {"success": False, "error": "No Party Link found for this party."}

    pi_gl = position["pi_gl"]
    si_gl = position["si_gl"]
    netting_amount = min(abs(pi_gl), abs(si_gl))

    if netting_amount <= 0:
        return {
            "success": False,
            "error": "Nothing to net — one or both outstanding amounts are zero.",
        }

    company = frappe.defaults.get_user_default("Company")
    if not company:
        return {"success": False, "error": "No default Company found."}

    payable_account = frappe.db.get_value(
        "Account", {"company": company, "account_type": "Payable", "is_group": 0}, "name"
    )
    receivable_account = frappe.db.get_value(
        "Account", {"company": company, "account_type": "Receivable", "is_group": 0}, "name"
    )

    if not payable_account or not receivable_account:
        return {
            "success": False,
            "error": "Could not find Receivable/Payable accounts for the company.",
        }

    linked = _find_linked_party(party_type, party_name)
    if not linked:
        return {"success": False, "error": "Could not resolve linked party."}

    # Fetch specific unpaid invoices (oldest first) to reference in the JE
    unpaid_pis = _get_outstanding_invoices("Purchase Invoice", "supplier", linked["supplier_name"])
    unpaid_sis = _get_outstanding_invoices("Sales Invoice", "customer", linked["customer_name"])

    # Distribute the netting amount across the invoices
    pi_rows = _allocate_invoice_rows(unpaid_pis, netting_amount, "debit")
    si_rows = _allocate_invoice_rows(unpaid_sis, netting_amount, "credit")

    # Build user-friendly remark listing which invoices are being netted
    pi_refs = ", ".join(r["reference_name"] for r in pi_rows)
    si_refs = ", ".join(r["reference_name"] for r in si_rows)
    remark = (
        f"Netting JE for {linked['other_party']}: "
        f"PIs ({pi_refs}) ↔ SIs ({si_refs}), "
        f"netting €{netting_amount:,.2f}"
    )

    try:
        accounts = []

        # PI side: Debit Payable referencing each PI
        for row in pi_rows:
            accounts.append(
                {
                    "account": payable_account,
                    "party_type": "Supplier",
                    "party": linked["supplier_name"],
                    "reference_type": "Purchase Invoice",
                    "reference_name": row["reference_name"],
                    "debit_in_account_currency": row["amount"],
                    "credit_in_account_currency": 0,
                }
            )

        # SI side: Credit Receivable referencing each SI
        for row in si_rows:
            accounts.append(
                {
                    "account": receivable_account,
                    "party_type": "Customer",
                    "party": linked["customer_name"],
                    "reference_type": "Sales Invoice",
                    "reference_name": row["reference_name"],
                    "debit_in_account_currency": 0,
                    "credit_in_account_currency": row["amount"],
                }
            )

        je = frappe.get_doc(
            {
                "doctype": "Journal Entry",
                "company": company,
                "posting_date": frappe.utils.today(),
                "user_remark": remark,
                "accounts": accounts,
            }
        )
        je.insert()

        return {"success": True, "journal_entry": je.name}

    except Exception as e:
        frappe.log_error(
            title="Netting JE creation failed",
            message=f"party_type={party_type}, party_name={party_name}: {e}",
        )
        return {"success": False, "error": f"Failed to create Journal Entry: {e!s}"}


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _get_outstanding_invoices(doctype: str, party_field: str, party_name: str) -> list[dict]:
    """Fetch individual unpaid invoices for a party, ordered oldest first.

    Returns a list of dicts with ``name`` and ``outstanding_amount``.
    """
    return frappe.db.sql(
        f"""
        SELECT name AS invoice_name, outstanding_amount
        FROM `tab{doctype}`
        WHERE {party_field} = %s
            AND docstatus = 1
            AND outstanding_amount > 0.5
            AND status IN ('Unpaid', 'Overdue', 'Partly Paid')
        ORDER BY posting_date ASC, name ASC
        """,
        party_name,
        as_dict=True,
    )


def _allocate_invoice_rows(
    invoices: list[dict], total_amount: float, dr_or_cr: str
) -> list[dict]:
    """Distribute ``total_amount`` across invoices, oldest first.

    Args:
        invoices: List of dicts with ``invoice_name`` and ``outstanding_amount``.
        total_amount: Total amount to allocate.
        dr_or_cr: ``"debit"`` or ``"credit"`` — passed through to the result.

    Returns:
        A list of dicts with ``reference_name`` and ``amount``, one per invoice
        that receives a non-zero allocation.  The sum of all amounts equals
        ``total_amount``.
    """
    remaining = total_amount
    rows = []
    for inv in invoices:
        if remaining <= 0:
            break
        alloc = min(inv.outstanding_amount, remaining)
        rows.append({"reference_name": inv.invoice_name, "amount": alloc})
        remaining -= alloc
    return rows


def _find_linked_party(party_type: str, party_name: str) -> dict | None:
    """Look up the linked party via ``Party Link`` doctype.

    Returns a dict with ``other_party``, ``other_type``, ``supplier_name``,
    ``customer_name``, or ``None`` if no link exists.
    """
    # Try primary role match first
    link = frappe.db.get_value(
        "Party Link",
        {"primary_party": party_name, "primary_role": party_type},
        ["secondary_party", "secondary_role"],
        as_dict=True,
    )
    if link:
        if party_type == "Supplier":
            return {
                "other_party": link.secondary_party,
                "other_type": link.secondary_role,
                "supplier_name": party_name,
                "customer_name": link.secondary_party,
            }
        else:
            return {
                "other_party": link.secondary_party,
                "other_type": link.secondary_role,
                "supplier_name": link.secondary_party,
                "customer_name": party_name,
            }

    # Try secondary role match
    link = frappe.db.get_value(
        "Party Link",
        {"secondary_party": party_name, "secondary_role": party_type},
        ["primary_party", "primary_role"],
        as_dict=True,
    )
    if link:
        if party_type == "Supplier":
            return {
                "other_party": link.primary_party,
                "other_type": link.primary_role,
                "supplier_name": party_name,
                "customer_name": link.primary_party,
            }
        else:
            return {
                "other_party": link.primary_party,
                "other_type": link.primary_role,
                "supplier_name": link.primary_party,
                "customer_name": party_name,
            }

    return None
