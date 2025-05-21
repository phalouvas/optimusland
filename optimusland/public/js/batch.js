frappe.ui.form.on("Batch", {
    refresh: function(frm) {
        if(frm.doc.__islocal) {
            update_batch_id(frm);
        }
    },
    
    item: function(frm) {
        if(frm.doc.__islocal) {
            update_batch_id(frm);
        }
    },
    
    manufacturing_date: function(frm) {
        if(frm.doc.__islocal) {
            update_batch_id(frm);
        }
    },
    
    custom_supplier_optimus: function(frm) {
        if(frm.doc.__islocal) {
            update_batch_id(frm);
        }
    }
});

function update_batch_id(frm) {
    if(!frm.doc.item || !frm.doc.manufacturing_date || !frm.doc.custom_supplier_optimus) {
        return;
    }
    
    // Format the date as dd/mm
    let date_obj = frappe.datetime.str_to_obj(frm.doc.manufacturing_date);
    let formatted_date = "";
    
    if(date_obj) {
        let day = date_obj.getDate().toString().padStart(2, '0');
        let month = (date_obj.getMonth() + 1).toString().padStart(2, '0');
        formatted_date = `${day}/${month}`;
    }
    
    // Get the item code
    frappe.db.get_value("Item", frm.doc.item, "item_code", (item_data) => {
        if(!item_data || !item_data.item_code) return;
        
        // Get the supplier name
        frappe.db.get_value("Supplier", frm.doc.custom_supplier_optimus, "supplier_name", (supplier_data) => {
            if(!supplier_data || !supplier_data.supplier_name) return;
            
            // Set the batch_id field
            let batch_id = `${item_data.item_code} - LOT:${formatted_date} - ${supplier_data.supplier_name}`;
            frm.set_value("batch_id", batch_id);
        });
    });
}