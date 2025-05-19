import frappe
from frappe import _, qb, throw
from collections import defaultdict


@frappe.whitelist()
def reconcile_customer_to_bill_delivery_notes(customer_name: str):
    delivery_note_items = frappe.db.sql("""
        SELECT dni.*
        FROM `tabDelivery Note Item` dni
        INNER JOIN `tabDelivery Note` dn ON dni.parent = dn.name
        WHERE dn.customer = %s 
        AND dn.docstatus = 1
        AND dn.status = 'To Bill'
    """, customer_name, as_dict=1)

    sales_invoice_items = frappe.db.sql("""
        SELECT sii.*
        FROM `tabSales Invoice Item` sii
        INNER JOIN `tabSales Invoice` si ON sii.parent = si.name
        LEFT JOIN `tabSales Invoice` cn ON cn.return_against = si.name AND cn.docstatus = 1
        WHERE si.customer = %s 
        AND si.docstatus = 1
        AND (sii.delivery_note IS NULL OR sii.delivery_note = '')
        AND cn.name IS NULL
    """, customer_name, as_dict=1)

    for delivery_note_item in delivery_note_items:
        matching_invoice_items = [
            sii for sii in sales_invoice_items
            if sii.get("item_code") == delivery_note_item.get("item_code")
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
                
    pass
