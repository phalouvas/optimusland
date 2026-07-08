// Copyright (c) 2026, KAINOTOMO PH LTD and Contributors
// See license.txt

/**
 * Payment Reconciliation form script — prefill from route_options.
 *
 * When navigated from the Supplier/Customer "Payment Reconciliation" action,
 * reads frappe.route_options to prefill party_type and party fields,
 * which then auto-populates the receivable_payable_account.
 */

frappe.ui.form.on("Payment Reconciliation", {
    refresh: function (frm) {
        if (frappe.route_options && frappe.route_options.party_type && frappe.route_options.party) {
            const opts = frappe.route_options;
            // Clear route_options so they don't persist on subsequent refreshes
            frappe.route_options = null;

            // Set party_type first (triggers party_type() handler which clears party)
            // Then set party (triggers party() handler which auto-fetches receivable_payable_account)
            frm.set_value("party_type", opts.party_type).then(() => {
                frm.set_value("party", opts.party);
            });
        }
    },
});
