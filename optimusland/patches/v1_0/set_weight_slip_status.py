# Copyright (c) 2026, KAINOTOMO PH LTD and contributors
# For license information, please see license.txt

"""Set status field on existing Weight Slips.

- Weight Slips linked to a submitted Purchase Receipt → Completed
- Weight Slips with disabled=1 → Cancelled
- All others → Pending
"""


import frappe


def execute():
    # Weight Slips linked to submitted, non-cancelled Purchase Receipts
    completed_ws = frappe.get_all(
        "Purchase Receipt",
        filters={
            "custom_weight_slip": ["!=", ""],
            "docstatus": 1,
        },
        pluck="custom_weight_slip",
        distinct=True,
    )

    for ws_name in completed_ws:
        frappe.db.set_value("Weight Slip", ws_name, "status", "Completed")

    # Weight Slips with disabled=1
    cancelled_ws = frappe.get_all(
        "Weight Slip",
        filters={"disabled": 1},
        pluck="name",
    )

    for ws_name in cancelled_ws:
        frappe.db.set_value("Weight Slip", ws_name, "status", "Cancelled")

    # All remaining Weight Slips → Pending
    all_ws = frappe.get_all("Weight Slip", pluck="name")
    done = set(completed_ws) | set(cancelled_ws)
    pending = [n for n in all_ws if n not in done]

    for ws_name in pending:
        frappe.db.set_value("Weight Slip", ws_name, "status", "Pending")
