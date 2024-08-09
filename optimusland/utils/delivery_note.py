import frappe

@frappe.whitelist()
#def add_shipping_cost(doc, method=None):
def add_shipping_cost(delivery_note_name: str):
    doc = frappe.get_doc("Delivery Note", delivery_note_name)
    if doc.custom_shipping_cost:
        
        stock_entry = frappe.new_doc("Stock Entry")

        default_fg_warehouse = frappe.get_value("Manufacturing Settings", None, "default_fg_warehouse")
        stock_entry.stock_entry_type = "Repack"
        stock_entry.to_warehouse = default_fg_warehouse

        expense_account = frappe.get_value("Company", doc.company, "stock_received_but_not_billed")
        stock_entry.append("additional_costs", {
            "expense_account": expense_account,
            "description": "Shipping",
            "amount": doc.custom_shipping_cost
        })

        batch_nos = []
        for item in doc.items:
            stock_entry.append("items", {
                "item_code": item.item_code,
                "s_warehouse": item.warehouse,
                "batch_no": item.batch_no,
                "qty": item.qty,
                "use_serial_batch_fields": 1,
                "is_finished_item": 0,
            })

            stock_entry.append("items", {
                "item_code": item.item_code,
                "t_warehouse": item.warehouse,
                "batch_no": item.batch_no,
                "qty": item.qty,
                "use_serial_batch_fields": 1,
                "is_finished_item": 1,
            })
            stock_entry.insert()
            stock_entry.submit()
            doc.custom_is_shipping_cost_added = 1
            doc.save()
    else:
        frappe.throw("No shipping cost defined. Either select a Purchase Invoice or enter a custom shipping cost.")

    return True
