import frappe
import datetime

@frappe.whitelist()
def add_shipping_cost(delivery_note_name: str, shipping_cost: float, purchase_invoice: str = None):
    doc = frappe.get_doc("Delivery Note", delivery_note_name)
    
    # Update the shipping cost field if provided
    if shipping_cost:
        doc.custom_shipping_cost = float(shipping_cost)
    
    # Update the purchase invoice field if provided
    if purchase_invoice:
        doc.custom_shipping_purchase_invoice = purchase_invoice
        
    if doc.custom_shipping_cost:
        total_qty = sum(item.qty for item in doc.items)
        shipping_cost_per_qty = doc.custom_shipping_cost / total_qty

    else:
        frappe.throw("No shipping cost defined. Either select a Purchase Invoice or enter a custom shipping cost.")

    frappe.db.set_value("Delivery Note", delivery_note_name, {
        "custom_shipping_cost": float(shipping_cost),
        "custom_shipping_rate": shipping_cost_per_qty if doc.custom_shipping_cost else 0.0,
        "custom_shipping_purchase_invoice": purchase_invoice if purchase_invoice else None,
        "custom_is_shipping_cost_added": 1
    }, update_modified=False)
    
    frappe.db.commit()
    
    return True
