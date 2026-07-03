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
                            description: __('Enter a custom shipping cost amount (set to zero to clear)'),
                            reqd: 0
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
                                    frappe.call({
                                        method: "optimusland.utils.delivery_note.get_purchase_invoice_grand_total",
                                        args: {
                                            purchase_invoice: purchase_invoice
                                        },
                                        callback: function(r) {
                                            if (r.message) {
                                                d.set_value('shipping_cost', r.message);
                                            }
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
                        
                        // Helper to call the server
                        const doAddShipping = function() {
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
                        };
                        
                        // Check for linked submitted Sales Invoices
                        frappe.call({
                            method: "optimusland.utils.delivery_note.check_linked_sales_invoices",
                            args: {
                                delivery_note_name: frm.doc.name
                            },
                            callback: function(r) {
                                const linkedSIs = r.message || [];
                                if (linkedSIs.length > 0) {
                                    let siNames = linkedSIs.join(', ');
                                    frappe.confirm(
                                        __('This Delivery Note already has the following Sales Invoice(s):<br><br>• {0}<br><br>If you add shipping cost now:<br><br>✅ <b>The Profit Report will still be correct</b> — it reads shipping directly from the Delivery Note<br><br>❌ <b>The Sales Invoice(s) above will NOT be updated</b> — their cost and profit figures will be missing the shipping cost<br><br><b>Recommended:</b> Cancel the invoice(s) first → add shipping cost → re-create the invoice(s).<br><br>Do you want to proceed anyway?', [siNames]),
                                        function() {
                                            doAddShipping();
                                        }
                                    );
                                } else {
                                    frappe.confirm(
                                        __('Are you sure you want to update shipping cost?'),
                                        function() {
                                            doAddShipping();
                                        }
                                    );
                                }
                            }
                        });
                    }
                });
                
                d.show();
            }).addClass("btn-danger");

            if (frm.doc.custom_is_shipping_cost_added) {
                frm.add_custom_button(__('Remove Shipping Cost'), function () {
                    frappe.confirm(
                        __('Are you sure you want to remove the shipping cost from this Delivery Note?'),
                        function() {
                            frappe.call({
                                method: "optimusland.utils.delivery_note.remove_shipping_cost",
                                args: {
                                    delivery_note_name: frm.doc.name
                                },
                                callback: function (response) {
                                    if (response.message) {
                                        frappe.show_alert({
                                            message: __('Shipping Cost removed successfully'),
                                            indicator: 'green'
                                        });
                                        frm.reload_doc();
                                    }
                                }
                            });
                        }
                    );
                }).addClass("btn-danger");
            }
        }
    }
});