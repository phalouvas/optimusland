import frappe

@frappe.whitelist()
def mark_paid(invoice_name: str):
    frappe.db.sql("""
        UPDATE `tabSales Invoice`
        SET status = %s
        WHERE name = %s
    """, ("Paid", invoice_name))
    return True

def get_delivery_note_items(sales_invoice, method=None):

    items_delivery_notes = [
        item.delivery_note
        for item in sales_invoice.items
        if item.delivery_note
    ]

    items = [
        item
        for item in sales_invoice.items
        if not item.delivery_note
    ]

    if not items:
        return
    
    for item in items:
        delivery_note_items = frappe.db.sql("""
            SELECT dni.name, dni.parent
            FROM `tabDelivery Note Item` dni
            INNER JOIN `tabDelivery Note` dn ON dni.parent = dn.name
            WHERE dn.customer = %s 
            AND dn.docstatus = 1
            AND dn.status = 'To Bill'
            AND dni.item_code = %s
            AND dni.parent NOT IN %s
            ORDER BY dn.posting_date
            LIMIT 1
        """, values=(sales_invoice.customer, item.item_code, tuple(items_delivery_notes) if items_delivery_notes else ("",)), as_dict=1)
        if not delivery_note_items:
            continue
        item.delivery_note = delivery_note_items[0].parent
        item.dn_detail = delivery_note_items[0].name
        