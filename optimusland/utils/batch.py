import frappe
from frappe import _

@frappe.whitelist()
def create_purchase_receipt(batch_names):
    """
    Create a Purchase Receipt from selected batches
    
    Args:
        batch_names (list): List of batch names to include in the Purchase Receipt
    
    Returns:
        dict: Information about the created Purchase Receipt
    """
    if isinstance(batch_names, str):
        batch_names = [d.strip() for d in batch_names.strip("[]").replace('"', '').split(",")]
    
    if not batch_names:
        frappe.throw(_("Please select at least one Batch"))
    
    pr_doc = frappe.new_doc("Purchase Receipt")
    pr_doc.set_posting_time = 1
    
    # Set default company and other required fields
    pr_doc.company = frappe.defaults.get_user_default("Company")
    default_warehouse = frappe.db.get_single_value("Stock Settings", "default_warehouse")
    
    # Get supplier from first batch (assuming all selected batches are from same supplier)
    first_batch = frappe.get_doc("Batch", batch_names[0])
    
    if hasattr(first_batch, "custom_supplier_optimus") and first_batch.custom_supplier_optimus:
        pr_doc.supplier = first_batch.custom_supplier_optimus
    else:
        # If no supplier in batch, set a default or ask user to select
        default_supplier = frappe.db.get_single_value("Buying Settings", "default_supplier")
        if default_supplier:
            pr_doc.supplier = default_supplier
    
    # Add items for each batch
    for batch_name in batch_names:
        batch = frappe.get_doc("Batch", batch_name)
        if not batch.item:
            continue
            
        # Get item details
        item_doc = frappe.get_doc("Item", batch.item)
        
        # Add item to Purchase Receipt
        pr_item = pr_doc.append("items", {
            "item_code": batch.item,
            "batch_no": batch_name,
            "qty": batch.batch_qty if hasattr(batch, "batch_qty") and batch.batch_qty > 0 else 1,
            "warehouse": default_warehouse,
            "uom": item_doc.stock_uom,
            "stock_uom": item_doc.stock_uom,
            "conversion_factor": 1.0,
            "rate": 0  # Set appropriate rate or fetch from Item Price
        })
    
    # Return the created document info without saving it
    # User will be redirected to the form to review and submit
    pr_doc.save()
    
    return {
        "name": pr_doc.name,
        "doctype": "Purchase Receipt"
    }