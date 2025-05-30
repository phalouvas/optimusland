
frappe.ui.form.on("Purchase Invoice", {
	refresh: function(frm) {        
		// Only if a new Purchase Invoice is being created
        if (frm.doc.__islocal) {
            frappe.msgprint("<p>This is a <b>Purchase Invoice</b>.</p><p>Rememeber to choose the correct <b>Naming Series<b>.</p>");            

            // Get emement with id "page-Purchase Invoice" and add a class to it
            var page = document.getElementById("page-Purchase Invoice");
            page.classList.add("bg-warning");
        } else {
            var page = document.getElementById("page-Purchase Invoice");
            if (page) {
                page.classList.remove("bg-warning");
            }
        }

        if (!frm.doc.__islocal && frm.doc.docstatus === 1 && frm.doc.status === 'Overdue') {
            frm.add_custom_button(__('Mark as Paid'), function () {
                // Ask for user confirmation
                if (confirm('Are you sure you want to mark this invoice as Paid? This action cannot be undone.')) {
                    frappe.call({
                        method: "optimusland.utils.purchase_invoice.mark_paid",
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

	},

})