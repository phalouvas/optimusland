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
    # Only warn for items not linked to a Delivery Note AND in group 'Potatoes'
    unlinked_potatoes = []
    for item in sales_invoice.items:
        if not item.delivery_note:
            # Check if item is in group 'Potatoes'
            item_group = getattr(item, 'item_group', None)
            if item_group is None:
                # Try to fetch item_group from Item doctype if not present
                item_group = frappe.db.get_value('Item', getattr(item, 'item_code', None), 'item_group')
            if item_group == 'Potatoes':
                unlinked_potatoes.append(item)
    if unlinked_potatoes:
        item_list = "<ul>" + "".join([
            f"<li>{getattr(item, 'item_code', 'Unknown Item')} (Row #{getattr(item, 'idx', '?')})</li>"
            for item in unlinked_potatoes
        ]) + "</ul>"
        frappe.msgprint(
            "Error: The following 'Potatoes' items in this Sales Invoice are not linked to a Delivery Note and cannot be saved:" + item_list,
            title="Unlinked Potatoes Items",
            indicator="red"
        )
        from frappe import ValidationError
        raise ValidationError("Unlinked 'Potatoes' items found. Please link all 'Potatoes' items to a Delivery Note before saving.")
        