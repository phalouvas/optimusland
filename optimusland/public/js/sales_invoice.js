frappe.ui.form.on('Sales Invoice', {
    refresh: function(frm) {
        if (frm.doc.__islocal) {
            frappe.msgprint("<p>This is a <b>Sales Invoice</b>.</p><p>Rememeber to choose the correct <b>Incoterm</b>.</p>");            

            // Get emement with id "page-Purchase Invoice" and add a class to it
            var page = document.getElementById("page-Sales Invoice");
            page.classList.add("bg-info");
        } else {
            var page = document.getElementById("page-Sales Invoice");
            if (page) {
                page.classList.remove("bg-info");
            }
        }
    }
});