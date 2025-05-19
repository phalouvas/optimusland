import frappe
from frappe import _, qb, throw
from collections import defaultdict

@frappe.whitelist()
def match_all_delivery_notes_to_invoices(customer_name: str):
    delivery_note_items = frappe.db.sql("""
        SELECT dni.*, dn.customer
        FROM `tabDelivery Note Item` dni
        INNER JOIN `tabDelivery Note` dn ON dni.parent = dn.name
        WHERE dn.customer = %s 
        AND dn.docstatus = 1
        AND dn.status <> 'Closed'
    """, customer_name, as_dict=1)

    sales_invoice_items = frappe.db.sql("""
        SELECT sii.*, si.customer
        FROM `tabSales Invoice Item` sii
        INNER JOIN `tabSales Invoice` si ON sii.parent = si.name
        LEFT JOIN `tabSales Invoice` cn ON cn.return_against = si.name AND cn.docstatus = 1
        WHERE si.customer = %s 
        AND si.docstatus = 1
        AND cn.name IS NULL
    """, customer_name, as_dict=1)

    for delivery_note_item in delivery_note_items:

        if delivery_note_item.get("parent") == "MAT-DN-2025-00355":
            pass
        matching_invoice_items = [
            sii for sii in sales_invoice_items
            if sii.get("item_code") == delivery_note_item.get("item_code")
            and sii.get("customer") == delivery_note_item.get("customer")
        ]
        for invoice_item in matching_invoice_items:
            
            si_amount = invoice_item.get("amount")
            dn_amount = delivery_note_item.get("amount")
            dn_billed_amt = delivery_note_item.get("billed_amt")
            
            # Update the Delivery Note Item with the billed amount
            billed_amt = si_amount + dn_billed_amt
            if billed_amt > dn_amount:
                billed_amt = dn_amount
            frappe.db.set_value(
                "Delivery Note Item",
                delivery_note_item.get("name"),
                "billed_amt",
                billed_amt
            )
            delivery_note_item["billed_amt"] = billed_amt
            
            # Update the Sales Invoice Item with the Delivery Note
            if si_amount <= dn_amount - dn_billed_amt:
                frappe.db.set_value(
                    "Sales Invoice Item",
                    invoice_item.get("name"),
                    "delivery_note",
                    delivery_note_item.get("parent")
                )
                frappe.db.set_value(
                    "Sales Invoice Item",
                    invoice_item.get("name"),
                    "dn_detail",
                    delivery_note_item.get("name")
                )
                frappe.db.set_value(
                    "Sales Invoice Item",
                    invoice_item.get("name"),
                    "delivered_qty",
                    invoice_item.get("qty")
                )
                sales_invoice_items.remove(invoice_item)
          
    # Group the delivery note items by their parent delivery note
    delivery_note_items_by_parent = {}
    for item in delivery_note_items:
        parent = item.get("parent")
        if parent not in delivery_note_items_by_parent:
            delivery_note_items_by_parent[parent] = []
        delivery_note_items_by_parent[parent].append(item)

    for delivery_note, items in delivery_note_items_by_parent.items():
        # Calculate the total billed amount for each delivery note
        total_billed_amount = sum(item.get("billed_amt") for item in items)
        # Find the percentage of billed amount
        total_amount = sum(item.get("amount") for item in items)
        percentage_billed = (total_billed_amount / total_amount) * 100 if total_amount > 0 else 0
        if percentage_billed > 100:
            percentage_billed = 100
        # Update the delivery note with the percentage billed
        frappe.db.set_value(
            "Delivery Note",
            delivery_note,
            "per_billed",
            percentage_billed
        )
        if percentage_billed == 100:
            frappe.db.set_value("Delivery Note", delivery_note, "status", "Completed")
        else:
            frappe.db.set_value("Delivery Note", delivery_note, "status", "To Bill")
    
    return f"Delivery Note status updated successfully."
