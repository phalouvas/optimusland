frappe.ui.form.on('Delivery Note', {
    refresh: function (frm) {
        if (!frm.doc.__islocal && frm.doc.status === 'Draft' && !frm.doc.custom_is_shipping_cost_added) {
            // Add the "Create Supplier Invoice" button under the "Create" dropdown
            frm.add_custom_button(__('Add Shipping Cost'), function () {
                // Ask for user confirmation
                if (confirm('Are you sure you want to add shipping cost? This action cannot be undone.')) {
                    frappe.call({
                        method: "optimusland.utils.delivery_note.add_shipping_cost",
                        args: {
                            delivery_note_name: frm.doc.name,
                            custom_shipping_cost: frm.doc.custom_shipping_cost
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
            }).addClass("btn-danger");
        }
    }
});