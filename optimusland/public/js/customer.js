frappe.ui.form.on("Customer", {
    refresh: function(frm) {        		
        frm.add_custom_button(__('Update Delivery Notes Status'), function() {
            frappe.confirm(
                __('Are you sure you want to update all Delivery Notes statuses for this customer?'),
                function() {
                    frappe.call({
                        method: 'optimusland.utils.customer.match_all_delivery_notes_to_invoices',
                        args: {
                            customer_name: frm.doc.name,
                        },
                        freeze: true,
                        freeze_message: __('Reconciling Delivery Notes...'),
                        callback: function(r) {
                            if (r.message) {
                                frappe.msgprint({
                                    title: __('Success'),
                                    message: __('Delivery Notes reconciled successfully'),
                                    indicator: 'green'
                                });
                            }
                        }
                    });
                }
            );
        }, __('Actions'));
    },
})