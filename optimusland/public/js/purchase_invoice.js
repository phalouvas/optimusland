
frappe.ui.form.on("Purchase Invoice", {
	refresh: function(frm) {        
		// Only if a new Purchase Invoice is being created
        if (frm.doc.__islocal) {
            frappe.msgprint("<p>This is a <b>Purchase Invoice</b>.</p><p>Rememeber to choose the correct Naming Series.</p>");            

            // Get emement with id "page-Purchase Invoice" and add a class to it
            var page = document.getElementById("page-Purchase Invoice");
            page.classList.add("bg-warning");

        }

	},

})