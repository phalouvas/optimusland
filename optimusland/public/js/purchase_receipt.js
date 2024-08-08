frappe.ui.form.on('Purchase Receipt', {
    refresh: function (frm) {
        if (!frm.doc.__islocal) {
            // Add the "Create Supplier Invoice" button under the "Create" dropdown
            frm.add_custom_button(__('Production Plan'), function () {
                frappe.call({
                    method: "optimusland.utils.purchase_receipt.create_production_plan",
                    args: {
                        purchase_receipt_name: frm.doc.name
                    },
                    callback: function (response) {
                        if (response.message) {
                            frappe.show_alert({
                                message: __('Reevaluation created successfully'),
                                indicator: 'green'
                            });
                        }
                    }
                });
            }, __('Create'));
        }
    }
});