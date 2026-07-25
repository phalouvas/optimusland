# Copyright (c) 2026, KAINOTOMO PH LTD and Contributors
# See license.txt

"""Net Position view for dual-role parties (Supplier + Customer).

Provides ``get_party_net_position`` — a ``@frappe.whitelist()`` function
callable from client-side JS that returns PI and SI outstanding totals
plus the computed net position for a party linked via a ``Party Link``.
"""

import frappe
from erpnext.accounts.utils import get_balance_on


@frappe.whitelist()
def get_party_net_position(party_type: str, party_name: str) -> dict:
    """Return the net position for a dual-role party linked via Party Link.

    Uses GL balances (``tabGL Entry``) rather than invoice ``outstanding_amount``
    to give accurate positions.

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


def _find_linked_party(party_type: str, party_name: str) -> dict | None:
    """Look up the linked party via ``Party Link`` doctype.

    Returns a dict with ``other_party``, ``other_type``, ``supplier_name``,
    ``customer_name``, or ``None`` if no link exists.
    """
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
