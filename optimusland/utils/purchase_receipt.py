import frappe

from erpnext.manufacturing.doctype.work_order.work_order import get_item_details, make_stock_entry
from frappe.utils import add_to_date, flt, getdate, now_datetime, nowdate

@frappe.whitelist()
def create_production_plan(purchase_receipt, method=None):
    purchase_receipt = frappe.get_doc("Purchase Receipt", purchase_receipt.name)
    batch_nos = []
    for item in purchase_receipt.items:
        batch_no = None
        if item.batch_no == None and item.serial_and_batch_bundle:
                batch_no = frappe.db.sql(f"SELECT batch_no FROM `tabSerial and Batch Entry` WHERE parent = '{item.serial_and_batch_bundle}'", as_dict=True)[0].batch_no
        else:
            batch_no = item.batch_no
        if batch_no:
            batch_nos.append({"item_code": item.item_code, "batch_no": batch_no, "purchase_rate": item.rate})

    pln = frappe.get_doc(
		{
			"doctype": "Production Plan",
			"posting_date": purchase_receipt.posting_date,
		}
	)
    
    for purchase_receipt_item in purchase_receipt.items:
        has_batch_no = frappe.db.get_value("Item", purchase_receipt_item.item_code, "has_batch_no")
        if has_batch_no:
            try:
                item_details = get_item_details(purchase_receipt_item.item_code)
            except Exception:
                continue
            purchase_receipt_item.bom_no = item_details.bom_no
            pln.append(
                "po_items",
                {
                    "item_code": purchase_receipt_item.item_code,
                    "bom_no": purchase_receipt_item.bom_no,
                    "planned_qty": purchase_receipt_item.qty,
                    "planned_start_date": purchase_receipt.posting_date,
                    "stock_uom": purchase_receipt_item.uom,
                    "warehouse": purchase_receipt_item.warehouse,
                },
            )

    if not pln.po_items:
        return

    pln.insert()
    pln.submit()

    pln.make_work_order()
    work_orders = frappe.get_all(
        "Work Order", fields=["name"], filters={"production_plan": pln.name}, as_list=1
    )
    for work_order in work_orders:
        wo = frappe.get_doc("Work Order", work_order[0])        
        wo.submit()
        
        batch_no = None
        for batch in batch_nos:
            if batch["item_code"] == wo.production_item:
                batch_no = batch["batch_no"]
                purchase_rate = batch["purchase_rate"]
                break
    
        se1 = frappe.get_doc(make_stock_entry(wo.name, "Material Transfer for Manufacture", wo.qty))
        se1.set_posting_time = 1
        se1.posting_date = purchase_receipt.posting_date
        se1.posting_time = purchase_receipt.posting_time
        se1.insert()
        se1.submit()

        se2 = frappe.get_doc(make_stock_entry(wo.name, "Manufacture", wo.qty))
        se2 = fix_stock_entry(se2, batch_no, wo.production_item, purchase_rate)
        se2.set_posting_time = 1
        se2.posting_date = purchase_receipt.posting_date
        se2.posting_time = purchase_receipt.posting_time
        se2.insert()
        se2.submit()
        
    pass

def fix_stock_entry(se: dict, batch_no: str, item_code: str, purchase_rate: float):
    
    source_item_exists = False
    for item in se.items:
        if item.item_code == item_code:
            item.batch_no = batch_no
            item.use_serial_batch_fields = 1
            source_item = {
                "item_code": item.item_code,
                "s_warehouse": item.t_warehouse,
                "bom_no": item.bom_no,
                "qty": item.qty,
                "batch_no": item.batch_no,
                "use_serial_batch_fields": 1,
                "is_finished_item": 0,
                "basic_rate": purchase_rate,
            }
            if item.is_finished_item == 0:
                source_item_exists = True

    if not source_item_exists:
        se.append(
            "items", source_item
        )

    se.items.reverse()
            
    return se

def set_batch_no(purchase_receipt, method=None):
    
    # Get items with empty batch_no
    items_without_batch = []
    for item in purchase_receipt.items:
        if not item.batch_no:
            items_without_batch.append(item)
    
    # Filter for items that should have batch numbers (has_batch_no=1)
    batch_required_items = []
    for item in items_without_batch:
        has_batch_no = frappe.db.get_value("Item", item.item_code, "has_batch_no")
        if has_batch_no == 1:
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
            new_batch.insert()
            
            # Assign the new batch to the item
            item.batch_no = new_batch.name
    
    frappe.db.commit()
