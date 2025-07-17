import frappe

@frappe.whitelist()
def mark_paid(invoice_name: str):
    frappe.db.sql("""
        UPDATE `tabSales Invoice`
        SET status = %s
        WHERE name = %s
    """, ("Paid", invoice_name))
    return True

def warn_unlinked_items(sales_invoice, method=None):
    unlinked_items = [item for item in sales_invoice.items if not item.delivery_note]
    if unlinked_items:
        item_list = "<ul>" + "".join([
            f"<li>{getattr(item, 'item_code', 'Unknown Item')} (Row #{getattr(item, 'idx', '?')})</li>"
            for item in unlinked_items
        ]) + "</ul>"
        frappe.msgprint(
            "Warning: The following items in this Sales Invoice are not linked to a Delivery Note:" + item_list,
            title="Unlinked Items",
            indicator="orange"
        )
        