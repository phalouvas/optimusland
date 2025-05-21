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
    },

    custom_prefix: function(frm) {
        if(frm.doc.__islocal) {
            update_batch_id(frm);
        }
    }
});

function update_batch_id(frm) {
    if(!frm.doc.item || !frm.doc.manufacturing_date || !frm.doc.custom_supplier_optimus) {
        return;
    }
    
    // Use frappe's built-in date formatting
    let formatted_date = frappe.datetime.str_to_user(frm.doc.manufacturing_date);

    prefix = frm.doc.custom_prefix ? " * " + frm.doc.custom_prefix : " ";

    let batch_id = `${frm.doc.item}${prefix}* ${formatted_date} * ${frm.doc.custom_supplier_optimus}`;
    frm.set_value("batch_id", batch_id);
    
}