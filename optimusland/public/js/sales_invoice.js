frappe.ui.form.on('Sales Invoice', {
    refresh: function(frm) {
        if (!frm.doc.__islocal && frm.doc.docstatus === 1 && frm.doc.status === 'Overdue') {
            frm.add_custom_button(__('Mark as Paid'), function () {
                // Ask for user confirmation
                if (confirm('Are you sure you want to mark this invoice as Paid? This action cannot be undone.')) {
                    frappe.call({
                        method: "optimusland.utils.sales_invoice.mark_paid",
                        args: {
                            invoice_name: frm.doc.name
                        },
                        callback: function (response) {
                            if (response.message) {
                                frappe.show_alert({
                                    message: __('Invoice updated successfully'),
                                    indicator: 'green'
                                });
                                frm.reload_doc();
                            }
                        }
                    });
                }
            }, __('Actions'));
        }
    }
});