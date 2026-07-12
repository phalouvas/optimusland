import frappe

def daily():
    frappe.enqueue("optimusland.utils.payment_reminder.send_payment_reminders")
    # Pipeline health digest removed — see Issue #78 design decision #4.
    # Users check the dashboard manually.

# You can also define other scheduled tasks here
# def all():
#     pass

# def hourly():
#     pass

# def weekly():
#     pass

# def monthly():
#     pass