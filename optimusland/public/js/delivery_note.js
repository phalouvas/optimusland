frappe.ui.form.on('Delivery Note', {
    refresh: function (frm) {
        if (!frm.doc.__islocal && frm.doc.docstatus === 1 ) {
            frm.add_custom_button(__('Add Shipping Cost'), function () {
                // Create a dialog with the required fields
                let d = new frappe.ui.Dialog({
                    title: __('Add Shipping Cost'),
                    fields: [
                        {
                            label: __('Custom Shipping Cost'),
                            fieldname: 'shipping_cost',
                            fieldtype: 'Currency',
                            description: __('Enter a custom shipping cost amount (must be greater than zero)'),
                            reqd: 1,
                            min: 0.01
                        },
                        {
                            label: __('Purchase Invoice'),
                            fieldname: 'purchase_invoice',
                            fieldtype: 'Link',
                            options: 'Purchase Invoice',
                            description: __('Select an existing Purchase Invoice for shipping costs'),
                            reqd: 0,
                            onchange: function() {
                                // Get the selected Purchase Invoice
                                const purchase_invoice = d.get_value('purchase_invoice');
                                
                                if (purchase_invoice) {
                                    // Fetch the grand_total from the selected Purchase Invoice
                                    frappe.db.get_value('Purchase Invoice', purchase_invoice, 'grand_total')
                                        .then(r => {
                                            if (r.message && r.message.grand_total) {
                                                // Update the shipping_cost field with the grand_total
                                                d.set_value('shipping_cost', r.message.grand_total);
                                            }
                                        });
                                }
                            }
                        }                        
                    ],
                    primary_action_label: __('Apply'),
                    primary_action: function(values) {
                        
                        // Close the dialog
                        d.hide();
                        
                        // Ask for confirmation
                        frappe.confirm(
                            __('Are you sure you want to add shipping cost? This action cannot be undone.'),
                            function() {
                                // Call the server method with the form values
                                frappe.call({
                                    method: "optimusland.utils.delivery_note.add_shipping_cost",
                                    args: {
                                        delivery_note_name: frm.doc.name,
                                        shipping_cost: values.shipping_cost,
                                        purchase_invoice: values.purchase_invoice
                                    },
                                    callback: function (response) {
                                        if (response.message) {
                                            frappe.show_alert({
                                                message: __('Shipping Cost updated successfully'),
                                                indicator: 'green'
                                            });
                                            frm.reload_doc();
                                        }
                                    }
                                });
                            }
                        );
                    }
                });
                
                d.show();
            }).addClass("btn-danger");
        }
    }
});