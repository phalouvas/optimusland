# Invoice status is managed automatically via:
# - Journal Entry on_submit hook (optimusland.utils.invoices_status.on_journal_entry_submit)
# - Daily cron (optimusland.utils.invoices_status.fix_unpaid_overdue_sales_invoices_status)
# The manual mark_paid button has been removed as part of issue #64.
        