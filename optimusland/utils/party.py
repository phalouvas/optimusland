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

# ---------------------------------------------------------------------------
# Public — callable from client-side JS via frappe.call()
# ---------------------------------------------------------------------------


@frappe.whitelist()
def get_party_net_position(party_type: str, party_name: str) -> dict:
    """Return the net position for a dual-role party linked via Party Link.

    Args:
        party_type: ``"Supplier"`` or ``"Customer"``.
        party_name: Name of the party.

    Returns:
        A dict with keys:
        - ``has_party_link`` (bool) — whether a Party Link was found.
        - ``linked_party`` (str) — the linked party name.
        - ``linked_party_type`` (str) — ``"Supplier"`` or ``"Customer"``.
        - ``pi_outstanding`` (float) — total PI outstanding amount.
        - ``si_outstanding`` (float) — total SI outstanding amount.
        - ``net_position`` (float) — ``abs(PI − SI)``.
        - ``net_label`` (str) — ``"Owed to Supplier"`` or ``"Owed by Customer"``.
    """
    linked = _find_linked_party(party_type, party_name)
    if not linked:
        return {"has_party_link": False}

    supplier_name = linked["supplier_name"]
    customer_name = linked["customer_name"]

    pi_outstanding = _get_total_outstanding("Purchase Invoice", "supplier", supplier_name)
    si_outstanding = _get_total_outstanding("Sales Invoice", "customer", customer_name)

    net = pi_outstanding - si_outstanding

    if net >= 0:
        net_label = f"Owed to Supplier ({supplier_name})"
    else:
        net_label = f"Owed by Customer ({customer_name})"

    return {
        "has_party_link": True,
        "linked_party": linked["other_party"],
        "linked_party_type": linked["other_type"],
        "pi_outstanding": pi_outstanding,
        "si_outstanding": si_outstanding,
        "net_position": abs(net),
        "net_label": net_label,
    }


@frappe.whitelist()
def create_netting_journal_entry(party_type: str, party_name: str) -> dict:
    """Create a draft Journal Entry to net PI and SI outstanding amounts.

    The netting amount is the **smaller** of the two outstanding totals.
    The resulting JE is saved as a draft (not submitted) so the user can
    review, adjust, and submit manually.

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

    pi_outstanding = position["pi_outstanding"]
    si_outstanding = position["si_outstanding"]
    netting_amount = min(pi_outstanding, si_outstanding)

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

    # Determine the supplier and customer names from the position data
    linked = _find_linked_party(party_type, party_name)
    if not linked:
        return {"success": False, "error": "Could not resolve linked party."}

    # Build user-friendly remark
    remark = (
        f"Netting JE for {linked['other_party']}: "
        f"PI outstanding €{pi_outstanding:,.2f}, "
        f"SI outstanding €{si_outstanding:,.2f}, "
        f"netting €{netting_amount:,.2f}"
    )

    try:
        je = frappe.get_doc(
            {
                "doctype": "Journal Entry",
                "company": company,
                "posting_date": frappe.utils.today(),
                "user_remark": remark,
                "accounts": [
                    {
                        "account": payable_account,
                        "party_type": "Supplier",
                        "party": linked["supplier_name"],
                        "debit_in_account_currency": netting_amount,
                        "credit_in_account_currency": 0,
                    },
                    {
                        "account": receivable_account,
                        "party_type": "Customer",
                        "party": linked["customer_name"],
                        "debit_in_account_currency": 0,
                        "credit_in_account_currency": netting_amount,
                    },
                ],
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


def _get_total_outstanding(doctype: str, party_field: str, party_name: str) -> float:
    """Sum ``outstanding_amount`` for submitted, unpaid invoices."""
    result = frappe.db.sql(
        f"""
        SELECT COALESCE(SUM(outstanding_amount), 0)
        FROM `tab{doctype}`
        WHERE {party_field} = %s
            AND docstatus = 1
            AND status IN ('Unpaid', 'Overdue', 'Partly Paid')
        """,
        party_name,
    )
    return flt(result[0][0])
