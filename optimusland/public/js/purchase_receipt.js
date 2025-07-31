frappe.ui.form.on('Purchase Receipt', {
    
    before_save: function(frm) {
        // Sort items in descending order by quantity
        if (frm.doc.items && frm.doc.items.length > 0) {
            frm.doc.items.sort(function(a, b) {
                return (b.qty || 0) - (a.qty || 0);
            });
            // Update idx field to maintain the order after save
            frm.doc.items.forEach(function(item, index) {
                item.idx = index + 1;
            });
            // Mark the document as dirty to ensure changes are saved
            frm.dirty();
            // Refresh the items table to reflect the new order
            frm.refresh_field('items');
        }
    },

    refresh: function(frm) {
        frm.set_query('custom_weight_slip', function() {
            return {
                filters: {
                    supplier: frm.doc.supplier || '',
                    disabled: 0
                }
            };
        });
    }
});