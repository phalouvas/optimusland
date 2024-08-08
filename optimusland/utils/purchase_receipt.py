import frappe

from erpnext.manufacturing.doctype.work_order.work_order import get_item_details, make_stock_entry
from frappe.utils import add_to_date, flt, getdate, now_datetime, nowdate

@frappe.whitelist()
def create_production_plan(purchase_receipt, method=None):
    purchase_receipt = frappe.get_doc("Purchase Receipt", purchase_receipt.name)
    batch_nos = []
    for item in purchase_receipt.items:
        if item.batch_no:
            batch_nos.append({"item_code": item.item_code, "batch_no": item.batch_no})

    pln = frappe.get_doc(
		{
			"doctype": "Production Plan",
			"posting_date": nowdate(),
		}
	)
    
    for purchase_receipt_item in purchase_receipt.items:
        item_details = get_item_details(purchase_receipt_item.item_code)
        purchase_receipt_item.bom_no = item_details.bom_no
        pln.append(
			"po_items",
			{
				"item_code": purchase_receipt_item.item_code,
				"bom_no": purchase_receipt_item.bom_no,
				"planned_qty": purchase_receipt_item.qty,
				"planned_start_date": now_datetime(),
				"stock_uom": purchase_receipt_item.uom,
				"warehouse": purchase_receipt_item.warehouse,
			},
		)

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
                break
    
        se = frappe.get_doc(make_stock_entry(wo.name, "Material Transfer for Manufacture", wo.qty))
        se.insert()
        se.submit()

        se = frappe.get_doc(make_stock_entry(wo.name, "Manufacture", wo.qty))
        se = fix_stock_entry(se, batch_no, wo.production_item)
        se.insert()
        se.submit()
        
    pass


def fix_stock_entry(se: dict, batch_no: str, item_code: str):
    
    source_item_exists = False
    for item in se.items:
        if item.item_code == item_code:
            item.batch_no = batch_no
            item.use_serial_batch_fields = 1
            source_item = {
                "item_code": item.item_code,
                "s_warehouse": item.t_warehouse,
                "qty": item.qty,
                "batch_no": item.batch_no,
                "use_serial_batch_fields": 1,
                "is_finished_item": 0,
            }
            if item.is_finished_item == 0:
                source_item_exists = True

    if not source_item_exists:
        se.append(
            "items", source_item
        )
    
    return se