import frappe


def set_batch_no(purchase_receipt, method=None):

    # Get items with empty batch_no
    items_without_batch = []
    for item in purchase_receipt.items:
        if not item.batch_no:
            items_without_batch.append(item)

    # Filter for items that should have batch numbers (has_batch_no=1) and belong to "Potatoes" item group
    batch_required_items = []
    for item in items_without_batch:
        has_batch_no = frappe.db.get_value("Item", item.item_code, "has_batch_no")
        item_group = frappe.db.get_value("Item", item.item_code, "item_group")
        if has_batch_no == 1 and item_group == "Potatoes":
            batch_required_items.append(item)

    # Loop through items that require batch numbers
    for item in batch_required_items:

        # Search for existing batches that match our criteria
        batches = frappe.get_all(
            "Batch",
            filters={
                "item": item.item_code,
                "custom_supplier_optimus": purchase_receipt.supplier,
                "manufacturing_date": purchase_receipt.posting_date,
                "custom_prefix": item.custom_batch_prefix,
            },
            fields=["name", "batch_id"]
        )

        date_format = frappe.utils.get_user_date_format()
        manufactured_date = frappe.utils.formatdate(purchase_receipt.posting_date, date_format)

        if batches:
            # Use the first matching batch
            batch_no = batches[0].name
            # Assign the batch number to the item
            item.batch_no = batch_no
            # Link the Weight Slip to the Batch for traceability
            if purchase_receipt.get("custom_weight_slip"):
                frappe.db.set_value("Batch", batch_no, "custom_weight_slip", purchase_receipt.custom_weight_slip)
        else:
            # Create a new batch if none exists
            new_batch = frappe.new_doc("Batch")
            if item.custom_batch_prefix:
                new_batch.batch_id = item.item_code + " * " + item.custom_batch_prefix + " * " + manufactured_date + " * " + purchase_receipt.supplier
            else:
                new_batch.batch_id = item.item_code + " * " + manufactured_date + " * " + purchase_receipt.supplier
            new_batch.item = item.item_code
            new_batch.manufacturing_date = purchase_receipt.posting_date
            new_batch.custom_supplier_optimus = purchase_receipt.supplier
            new_batch.custom_prefix = item.custom_batch_prefix
            new_batch.custom_weight_slip = purchase_receipt.get("custom_weight_slip")
            new_batch.insert()

            # Assign the new batch to the item
            item.batch_no = new_batch.name


def update_weight_slip_status(doc, method=None):
    """Update Weight Slip status when Purchase Receipt is submitted or cancelled."""
    if not doc.get("custom_weight_slip"):
        return

    ws_name = doc.custom_weight_slip

    if method == "on_submit":
        # Mark Weight Slip as Completed when PR is submitted
        frappe.db.set_value("Weight Slip", ws_name, "status", "Completed")

    elif method == "on_cancel":
        # Revert to Pending — but only if no other submitted PR still references this WS
        other_active = frappe.get_all(
            "Purchase Receipt",
            filters={
                "custom_weight_slip": ws_name,
                "docstatus": 1,
                "name": ["!=", doc.name],
            },
            limit=1,
        )
        if not other_active:
            frappe.db.set_value("Weight Slip", ws_name, "status", "Pending")
