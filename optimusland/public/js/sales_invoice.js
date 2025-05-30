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

        if (frm.doc.__islocal) {
            frappe.msgprint("<p>This is a <b>Sales Invoice</b>.</p><p>Rememeber to choose the correct <b>Incoterm</b>.</p>");            

            // Get emement with id "page-Purchase Invoice" and add a class to it
            var page = document.getElementById("page-Sales Invoice");
            page.classList.add("bg-info");
        } else {
            var page = document.getElementById("page-Sales Invoice");
            if (page) {
                page.classList.remove("bg-info");
            }
        }
    }
});