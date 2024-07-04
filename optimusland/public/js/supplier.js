
frappe.ui.form.on("Supplier", {
	refresh: function(frm) {        
		// Only if a not new Customer is being created
        if (!frm.doc.__islocal) {
            frappe.call({
                method: "optimusland.utils.supplier.get_supplier_unlinked_journal_entries",
                args: {
                    supplier_name: frm.doc.name
                },
                callback: function(response) {
                    if (response.message) {
                        if (response.message.length > 0) {
                            console.log(response.message);
                            frappe.show_alert({
                                message:__(response.message),
                                indicator:'yellow'
                            }, 15);
                        }
                    }
                }
            });
        }

	},

})