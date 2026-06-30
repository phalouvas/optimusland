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
    if purchase_invoice:
        purchase_invoice_link = f'<a href="/app/purchase-invoice/{purchase_invoice}" >{purchase_invoice}</a>'
    else:
        purchase_invoice_link = "N/A"
    doc.add_comment(
        "Info",
        f"Shipping cost of €{shipping_cost} added. Purchase Invoice: {purchase_invoice_link}"
    )

    return True


@frappe.whitelist()
def remove_shipping_cost(delivery_note_name: str):
    """Remove shipping cost from a Delivery Note"""

    doc = frappe.get_doc("Delivery Note", delivery_note_name)

    # Return if the delivery note is not found or is not submitted
    if not doc or doc.docstatus != 1:
        frappe.throw("Delivery Note not found or not submitted.")

    # Return if shipping cost was never added
    if not doc.custom_is_shipping_cost_added:
        frappe.throw("No shipping cost to remove.")

    frappe.db.set_value("Delivery Note", delivery_note_name, {
        "custom_shipping_cost": 0,
        "custom_shipping_rate": 0,
        "custom_shipping_purchase_invoice": None,
        "custom_is_shipping_cost_added": 0
    }, update_modified=False)

    frappe.db.commit()

    doc.add_comment("Info", "Shipping cost removed.")

    return True


def validate_batch_manufacture(delivery_note, method=None):
    """Validate that all Potato batches being delivered have a completed Manufacture Stock Entry.

    This prevents the Purchase Receipt Gross Profit report from using an understated
    incoming_rate that would miss BOM overhead costs incurred during manufacturing.
    """

    # Collect unique batch numbers from Potato items
    batches_to_check = set()
    for item in delivery_note.items:
        batch_no = item.batch_no

        # Handle serial_and_batch_bundle pattern (v15+)
        if not batch_no and item.serial_and_batch_bundle:
            result = frappe.db.sql(
                "SELECT batch_no FROM `tabSerial and Batch Entry` WHERE parent = %s",
                item.serial_and_batch_bundle,
                as_dict=True
            )
            if result:
                batch_no = result[0].batch_no

        if not batch_no:
            continue

        # Only check Potato items (matches existing convention)
        item_group = frappe.db.get_value("Item", item.item_code, "item_group")
        if item_group != "Potatoes":
            continue

        batches_to_check.add(batch_no)

    if not batches_to_check:
        return

    # Query for submitted Manufacture Stock Entries that produced these batches
    manufactured_batches = frappe.db.sql("""
        SELECT DISTINCT sed.batch_no
        FROM `tabStock Entry Detail` sed
        INNER JOIN `tabStock Entry` se ON se.name = sed.parent
        WHERE se.stock_entry_type = 'Manufacture'
          AND se.docstatus = 1
          AND sed.batch_no IN %(batch_nos)s
          AND sed.is_finished_item = 1
    """, {"batch_nos": tuple(batches_to_check)}, as_dict=True)

    manufactured_batch_set = {row.batch_no for row in manufactured_batches}

    missing_batches = batches_to_check - manufactured_batch_set
    if missing_batches:
        batch_list = ", ".join(sorted(missing_batches))
        frappe.throw(
            "The following batches have not completed the Manufacture process "
            "and cannot be delivered: {0}. Please ensure all batches have a "
            "completed Manufacture Stock Entry before submitting this Delivery Note.".format(batch_list)
        )
