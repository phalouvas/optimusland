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
        
        default_fg_warehouse = frappe.get_value("Manufacturing Settings", None, "default_fg_warehouse")
    
        expense_account = frappe.get_value("Company", doc.company, "stock_received_but_not_billed")

        total_qty = sum(item.qty for item in doc.items)
        shipping_cost_per_qty = doc.custom_shipping_cost / total_qty

        for item in doc.items:
            if item.qty == 0:
                continue
            item_shipping_cost = item.qty * shipping_cost_per_qty
            stock_entry = frappe.new_doc("Stock Entry")
            stock_entry.stock_entry_type = "Repack"
            stock_entry.to_warehouse = default_fg_warehouse
            stock_entry.posting_date = doc.posting_date
            stock_entry.posting_time = doc.posting_time - datetime.timedelta(seconds=1)
            stock_entry.set_posting_time = 1
            stock_entry.append("additional_costs", {
                "expense_account": expense_account,
                "description": "Shipping",
                "amount": item_shipping_cost
            })

            if item.batch_no is None or item.batch_no == "":
                if item.serial_and_batch_bundle is None:
                    frappe.throw("Serial and Batch Bundle is required for item: {}".format(item.item_code))
                batch_no = frappe.db.sql(f"SELECT batch_no FROM `tabSerial and Batch Entry` WHERE parent = '{item.serial_and_batch_bundle}'", as_dict=True)[0].batch_no
            else:
                batch_no = item.batch_no

            stock_entry.append("items", {
                "item_code": item.item_code,
                "s_warehouse": item.warehouse,
                "batch_no": batch_no,
                "qty": item.qty,
                "use_serial_batch_fields": 1,
                "is_finished_item": 0,
            })

            stock_entry.append("items", {
                "item_code": item.item_code,
                "t_warehouse": item.warehouse,
                "batch_no": batch_no,
                "qty": item.qty,
                "use_serial_batch_fields": 1,
                "is_finished_item": 1,
            })
            stock_entry.insert()
            stock_entry.submit()        

    else:
        frappe.throw("No shipping cost defined. Either select a Purchase Invoice or enter a custom shipping cost.")

    frappe.db.set_value("Delivery Note", delivery_note_name, {
        "custom_shipping_cost": float(shipping_cost),
        "custom_shipping_purchase_invoice": purchase_invoice if purchase_invoice else None,
        "custom_is_shipping_cost_added": 1
    }, update_modified=False)
    
    frappe.db.commit()
    
    return True
