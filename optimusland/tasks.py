import frappe

def daily():
    frappe.enqueue("optimusland.utils.invoices_status.fix_unpaid_overdue_purchase_invoices_status")
    frappe.enqueue("optimusland.utils.invoices_status.fix_unpaid_overdue_sales_invoices_status")

# You can also define other scheduled tasks here
# def all():
#     pass

# def hourly():
#     pass

# def weekly():
#     pass

# def monthly():
#     pass