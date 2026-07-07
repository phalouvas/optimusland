import frappe

def daily():
    frappe.enqueue("optimusland.utils.payment_reminder.send_payment_reminders")
    frappe.enqueue("optimusland.utils.pipeline_monitor.send_pipeline_digest")

# You can also define other scheduled tasks here
# def all():
#     pass

# def hourly():
#     pass

# def weekly():
#     pass

# def monthly():
#     pass