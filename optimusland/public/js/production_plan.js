frappe.ui.form.on('Production Plan', {
    refresh: function (frm) {
        if (!frm.doc.__islocal && frm.doc.status === 'Completed') {
            // Add the "Create Supplier Invoice" button under the "Create" dropdown
            frm.add_custom_button(__('Purchase Invoice'), function () {
                frappe.call({
                    method: "optimusland.utils.supplier.create_purchase_invoice",
                    args: {
                        production_plan_name: frm.doc.name
                    },
                    callback: function (response) {
                        if (response.message) {
                            frappe.show_alert({
                                message: __('Purchase Invoice created successfully'),
                                indicator: 'green'
                            });
                        }
                    }
                });
            }, __('Create'));
        }
    }
});