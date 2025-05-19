import frappe
from frappe.utils import (
	flt,
)

def fix_unpaid_overdue_purchase_invoices_status():
    default_company = frappe.defaults.get_user_default("Company")
    today = frappe.utils.nowdate()
    thirty_days_ago = frappe.utils.add_days(today, -365)
    
    filters = {
        "status": ["in", ["Unpaid", "Overdue"]],
        "posting_date": [">=", thirty_days_ago],
        "docstatus": 1
    }
    
    invoices = frappe.get_all("Purchase Invoice", filters=filters, fields=["name", "supplier"])
    
    invoices_by_supplier = {}
    for invoice in invoices:
        supplier = invoice.get("supplier")
        if supplier not in invoices_by_supplier:
            invoices_by_supplier[supplier] = []
        invoices_by_supplier[supplier].append(invoice)

    for supplier in invoices_by_supplier:
        company_wise_total_unpaid = frappe._dict(
		frappe.db.sql(
                """
            select party, sum(debit_in_account_currency) - sum(credit_in_account_currency)
            from `tabGL Entry`
            where party_type = 'Supplier' and party=%s and company=%s
            and is_cancelled = 0""",
                (supplier, default_company),
            )
        )
        total_unpaid = flt(company_wise_total_unpaid.get(supplier))
        total_unpaid = flt(total_unpaid) if total_unpaid else 0
        if -0.5 <= total_unpaid <= 0.5:
            invoices = invoices_by_supplier[supplier]
            for invoice in invoices:
                frappe.db.set_value("Purchase Invoice", invoice.get("name"), "status", "Paid")
    
    return True

def fix_unpaid_overdue_sales_invoices_status():
    default_company = frappe.defaults.get_user_default("Company")
    today = frappe.utils.nowdate()
    thirty_days_ago = frappe.utils.add_days(today, -365)
    
    filters = {
        "status": ["in", ["Unpaid", "Overdue"]],
        "posting_date": [">=", thirty_days_ago],
        "docstatus": 1
    }
    
    invoices = frappe.get_all("Sales Invoice", filters=filters, fields=["name", "customer"])
    
    invoices_by_customer = {}
    for invoice in invoices:
        customer = invoice.get("customer")
        if customer not in invoices_by_customer:
            invoices_by_customer[customer] = []
        invoices_by_customer[customer].append(invoice)

    for customer in invoices_by_customer:
        company_wise_total_unpaid = frappe._dict(
        frappe.db.sql(
                """
            select party, sum(debit_in_account_currency) - sum(credit_in_account_currency)
            from `tabGL Entry`
            where party_type = 'Customer' and party=%s and company=%s
            and is_cancelled = 0""",
                (customer, default_company),
            )
        )
        total_unpaid = flt(company_wise_total_unpaid.get(customer))
        total_unpaid = flt(total_unpaid) if total_unpaid else 0
        if -0.5 <= total_unpaid <= 0.5:
            invoices = invoices_by_customer[customer]
            for invoice in invoices:
                frappe.db.set_value("Sales Invoice", invoice.get("name"), "status", "Paid")
    
    return True

@frappe.whitelist()
def match_all_delivery_notes_to_invoices():
    delivery_note_items = frappe.db.sql("""
        SELECT dni.*, dn.customer
        FROM `tabDelivery Note Item` dni
        INNER JOIN `tabDelivery Note` dn ON dni.parent = dn.name
        WHERE dn.docstatus = 1
        AND dn.status = 'To Bill'
    """, as_dict=1)
    
    sales_invoice_items = frappe.db.sql("""
            SELECT sii.*, si.customer
            FROM `tabSales Invoice Item` sii
            INNER JOIN `tabSales Invoice` si ON sii.parent = si.name
            LEFT JOIN `tabSales Invoice` cn ON cn.return_against = si.name AND cn.docstatus = 1
            WHERE si.docstatus = 1
            AND (sii.delivery_note IS NULL OR sii.delivery_note = '')
            AND cn.name IS NULL
        """, as_dict=1)

    for delivery_note_item in delivery_note_items:

        if delivery_note_item.get("parent") == "MAT-DN-2025-00355":
            pass
        matching_invoice_items = [
            sii for sii in sales_invoice_items
            if sii.get("item_code") == delivery_note_item.get("item_code")
            and sii.get("customer") == delivery_note_item.get("customer")
        ]
        for invoice_item in matching_invoice_items:
            
            si_amount = invoice_item.get("amount")
            dn_amount = delivery_note_item.get("amount")
            dn_billed_amt = delivery_note_item.get("billed_amt")
            
            # Update the Delivery Note Item with the billed amount
            billed_amt = si_amount + dn_billed_amt
            if billed_amt > dn_amount:
                billed_amt = dn_amount
            frappe.db.set_value(
                "Delivery Note Item",
                delivery_note_item.get("name"),
                "billed_amt",
                billed_amt
            )
            delivery_note_item["billed_amt"] = billed_amt
            
            # Update the Sales Invoice Item with the Delivery Note
            if si_amount <= dn_amount - dn_billed_amt:
                frappe.db.set_value(
                    "Sales Invoice Item",
                    invoice_item.get("name"),
                    "delivery_note",
                    delivery_note_item.get("parent")
                )
                frappe.db.set_value(
                    "Sales Invoice Item",
                    invoice_item.get("name"),
                    "dn_detail",
                    delivery_note_item.get("name")
                )
                frappe.db.set_value(
                    "Sales Invoice Item",
                    invoice_item.get("name"),
                    "delivered_qty",
                    invoice_item.get("qty")
                )
                sales_invoice_items.remove(invoice_item)
          
    # Group the delivery note items by their parent delivery note
    delivery_note_items_by_parent = {}
    for item in delivery_note_items:
        parent = item.get("parent")
        if parent not in delivery_note_items_by_parent:
            delivery_note_items_by_parent[parent] = []
        delivery_note_items_by_parent[parent].append(item)

    for delivery_note, items in delivery_note_items_by_parent.items():
        # Calculate the total billed amount for each delivery note
        total_billed_amount = sum(item.get("billed_amt") for item in items)
        # Find the percentage of billed amount
        total_amount = sum(item.get("amount") for item in items)
        percentage_billed = (total_billed_amount / total_amount) * 100 if total_amount > 0 else 0
        if percentage_billed > 100:
            percentage_billed = 100
        # Update the delivery note with the percentage billed
        frappe.db.set_value(
            "Delivery Note",
            delivery_note,
            "per_billed",
            percentage_billed
        )
        if percentage_billed == 100:
            frappe.db.set_value("Delivery Note", delivery_note, "status", "Completed")
    
    return f"Delivery Note status updated successfully."
