# Copyright (c) 2026, KAINOTOMO PH LTD and contributors
# For license information, please see license.txt

import frappe


def execute():
    """Repair Delivery Notes incorrectly marked as 100% billed by fix_to_bill_delivery_note_status() (Issue #47).

    The buggy function matched Sales Invoice Items to Delivery Note Items using only
    item_code + customer, without verifying sii.delivery_note == dni.parent. When an
    SI amount was larger than the DN item's remaining capacity, billed_amt was set to
    100% but the SI was never linked (the linking condition failed). The same unlinked
    SI then kept matching subsequent DNs, corrupting all of them.

    This patch:
    1. Finds all DNs with per_billed >= 100, status = 'Completed', but ZERO linked SI items
    2. Resets billed_amt to 0 on all their items
    3. Resets per_billed to 0 and restores status to 'To Bill' (or 'To Deliver and Bill')
    4. Unlinks Sales Invoice Items that were wrongly attached by the same bug
    """

    print("=" * 80)
    print("PATCH: Repair billing status corrupted by Issue #47")
    print("=" * 80)

    # Step 1: Find corrupted Delivery Notes
    corrupted_dns = frappe.db.sql("""
        SELECT dn.name, dn.customer, dn.per_billed, dn.status, dn.total
        FROM `tabDelivery Note` dn
        WHERE dn.docstatus = 1
          AND dn.per_billed >= 100
          AND dn.status = 'Completed'
          AND NOT EXISTS (
              SELECT 1 FROM `tabSales Invoice Item` sii
              WHERE sii.delivery_note = dn.name AND sii.docstatus = 1
          )
        ORDER BY dn.customer, dn.name
    """, as_dict=1)

    if not corrupted_dns:
        print("No corrupted Delivery Notes found. Nothing to repair.")
        return

    dn_names = [d.name for d in corrupted_dns]
    print(f"Found {len(corrupted_dns)} corrupted Delivery Notes.")

    # Count per customer
    by_customer = {}
    for d in corrupted_dns:
        by_customer.setdefault(d.customer, 0)
        by_customer[d.customer] += 1
    for cust, count in sorted(by_customer.items(), key=lambda x: -x[1]):
        print(f"  {cust:50s} : {count}")

    # Step 2: Reset billed_amt to 0 on all items of corrupted DNs
    print(f"\nResetting billed_amt to 0 on Delivery Note Items...")
    for dn_name in dn_names:
        frappe.db.sql("""
            UPDATE `tabDelivery Note Item`
            SET billed_amt = 0
            WHERE parent = %s
        """, dn_name)

    # Step 3: Reset per_billed and status on corrupted DNs
    print(f"Resetting per_billed and status on Delivery Notes...")
    for d in corrupted_dns:
        frappe.db.set_value("Delivery Note", d.name, {
            "per_billed": 0,
            "status": "To Bill"
        }, update_modified=False)

    # Step 4: Find and unlink wrongly-attached Sales Invoice Items
    # These are SI items whose delivery_note points to a DN that has no
    # legitimate SI items linked (i.e., the link was made by the buggy function)
    wrongly_linked = frappe.db.sql("""
        SELECT sii.name AS sii_name, sii.parent AS sales_invoice,
               sii.item_code, sii.delivery_note, sii.amount
        FROM `tabSales Invoice Item` sii
        WHERE sii.docstatus = 1
          AND sii.delivery_note IN %s
    """, (dn_names,), as_dict=1)

    if wrongly_linked:
        sii_names = [r.sii_name for r in wrongly_linked]
        print(f"Unlinking {len(wrongly_linked)} wrongly-attached Sales Invoice Items...")
        for r in wrongly_linked:
            print(f"  SI: {r.sales_invoice:25s} | Item: {r.item_code:20s} | DN: {r.delivery_note} | Amount: {r.amount:>10.2f}")

        frappe.db.sql("""
            UPDATE `tabSales Invoice Item`
            SET delivery_note = NULL,
                dn_detail = NULL,
                delivered_qty = 0
            WHERE name IN %s
        """, (sii_names,))
    else:
        print("No wrongly-attached Sales Invoice Items found.")

    frappe.db.commit()

    print(f"\n{'=' * 80}")
    print(f"REPAIR COMPLETE: {len(corrupted_dns)} Delivery Notes restored.")
    print(f"                 {len(wrongly_linked)} Sales Invoice Items unlinked.")
    print(f"{'=' * 80}")
