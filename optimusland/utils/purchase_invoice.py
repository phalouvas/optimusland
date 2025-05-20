import frappe

@frappe.whitelist()
def mark_paid(invoice_name: str):
    frappe.db.sql("""
        UPDATE `tabPurchase Invoice`
        SET status = %s
        WHERE name = %s
    """, ("Paid", invoice_name))
    return True

def get_purchase_receipt_items(purchase_invoice, method):
    items_purchase_receipts = [
        item.purchase_receipt
        for item in purchase_invoice.items
        if item.purchase_receipt
    ]

    items = [
        item
        for item in purchase_invoice.items
        if not item.purchase_receipt
    ]

    if not items:
        return
    
    for item in items:
        purchase_receipt_items = frappe.db.sql("""
            SELECT dni.name, dni.parent
            FROM `tabPurchase Receipt Item` dni
            INNER JOIN `tabPurchase Receipt` dn ON dni.parent = dn.name
            WHERE dn.supplier = %s 
            AND dn.docstatus = 1
            AND dn.status = 'To Bill'
            AND dni.item_code = %s
            AND dni.parent NOT IN %s
            ORDER BY dn.posting_date
            LIMIT 1
        """, values=(purchase_invoice.supplier, item.item_code, tuple(items_purchase_receipts) if items_purchase_receipts else ("",)), as_dict=1)
        if not purchase_receipt_items:
            continue
        item.purchase_receipt = purchase_receipt_items[0].parent
        item.pr_detail = purchase_receipt_items[0].name