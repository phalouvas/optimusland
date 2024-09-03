import frappe

@frappe.whitelist()
def mark_paid(invoice_name: str):
    frappe.db.sql("""
        UPDATE `tabPurchase Invoice`
        SET status = %s
        WHERE name = %s
    """, ("Paid", invoice_name))
    return True