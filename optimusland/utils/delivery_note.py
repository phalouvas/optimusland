import frappe
import datetime

@frappe.whitelist()
def add_shipping_cost(delivery_note_name: str, shipping_cost: float, purchase_invoice: str = None):

    # Return if not shipping cost is provided
    if not shipping_cost and not purchase_invoice:
        frappe.throw("Please provide shipping cost.")

    doc = frappe.get_doc("Delivery Note", delivery_note_name)

    # Return if the delivery note is not found or is not submitted
    if not doc or doc.docstatus != 1:
        frappe.throw("Delivery Note not found or not submitted.")
    
    # Update the shipping cost field if provided
    if shipping_cost:
        doc.custom_shipping_cost = float(shipping_cost)
    
    # Update the purchase invoice field if provided
    if purchase_invoice:
        doc.custom_shipping_purchase_invoice = purchase_invoice
        
    if doc.custom_shipping_cost:
        total_qty = sum(item.qty for item in doc.items)
        shipping_cost_per_qty = doc.custom_shipping_rate  + ( doc.custom_shipping_cost / total_qty )

    frappe.db.set_value("Delivery Note", delivery_note_name, {
        "custom_shipping_cost": float(shipping_cost),
        "custom_shipping_rate": shipping_cost_per_qty if doc.custom_shipping_cost else 0.0,
        "custom_shipping_purchase_invoice": purchase_invoice if purchase_invoice else None,
        "custom_is_shipping_cost_added": 1
    }, update_modified=False)
    
    frappe.db.commit()

    # Log the shipping cost addition using standard Frappe comment logging
    doc.add_comment(
        "Info",
        f"Shipping cost of €{shipping_cost} added. Purchase Invoice: {purchase_invoice if purchase_invoice else 'N/A'}"
    )

    return True
