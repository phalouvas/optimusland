frappe.listview_settings['Batch'] = frappe.listview_settings['Batch'] || {};

frappe.listview_settings['Batch'].onload = function(listview) {
    // Add "Create Purchase Receipt" button under Actions
    if (frappe.model.can_create("Purchase Receipt")) {
        listview.page.add_action_item(__("Create Purchase Receipt"), function() {
            const selected_docs = listview.get_checked_items();
            const docnames = listview.get_checked_items(true);

            if (selected_docs.length === 0) {
                frappe.throw(__("Please select at least one Batch"));
                return;
            }

            frappe.call({
                method: "optimusland.utils.batch.create_purchase_receipt",
                args: {
                    batch_names: docnames
                },
                freeze: true,
                freeze_message: __("Creating Purchase Receipt..."),
                callback: function(r) {
                    if (!r.exc) {
                        frappe.msgprint({
                            title: __("Success"),
                            indicator: "green",
                            message: __("Purchase Receipt created successfully")
                        });

                        if (r.message && r.message.name) {
                            frappe.set_route("Form", "Purchase Receipt", r.message.name);
                        }
                        
                        listview.refresh();
                    }
                }
            });
        });
    }
};