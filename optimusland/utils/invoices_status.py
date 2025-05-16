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

def fix_to_bill_delivery_note_status():
    today = frappe.utils.nowdate()
    thirty_days_ago = frappe.utils.add_days(today, -30)
    
    # Find delivery notes that are:
    # 1. Older than 30 days
    # 2. Have "To Bill" status
    # 3. Are submitted (docstatus=1)
    filters = {
        "status": "To Bill",
        "posting_date": ["<", thirty_days_ago],
        "docstatus": 1
    }
    
    delivery_notes = frappe.get_all("Delivery Note", filters=filters, fields=["name"])
    
    count = 0
    for dn in delivery_notes:
        dn_name = dn.get("name")
        
        # Check if there are linked sales invoices that are submitted
        linked_invoices = frappe.get_all(
            "Sales Invoice Item",
            filters={
                "delivery_note": dn_name,
                "docstatus": 1
            },
            fields=["parent"],
            distinct=True
        )
        
        if linked_invoices:
            # Update status to "Completed" as there are submitted sales invoices
            frappe.db.set_value("Delivery Note", dn_name, "status", "Completed")
            count += 1
    
    return f"Updated {count} delivery notes from 'To Bill' to 'Completed' status"
