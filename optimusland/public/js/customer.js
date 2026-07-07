// Copyright (c) 2026, KAINOTOMO PH LTD and Contributors
// See license.txt

/**
 * Customer form script — Net Position section.
 *
 * When a Customer has a Party Link to a Supplier (dual-role party),
 * displays the net position between PI and SI outstanding amounts
 * and provides a "Create Netting Journal Entry" button.
 */

frappe.ui.form.on("Customer", {
    refresh: function (frm) {
        if (!frm.doc.__islocal) {
            _add_net_position_section(frm, "Customer");
        }
    },
});

function _add_net_position_section(frm, party_type) {
    frappe.call({
        method: "optimusland.utils.party.get_party_net_position",
        args: {
            party_type: party_type,
            party_name: frm.doc.name,
        },
        callback: function (r) {
            if (r.message && r.message.has_party_link) {
                const d = r.message;

                const html = `
                    <table class="table table-bordered table-sm" style="margin-bottom: 0; max-width: 500px;">
                        <tr>
                            <td style="width: 50%;"><strong>${__("Linked Supplier")}</strong></td>
                            <td><a href="/app/${d.linked_party_type.toLowerCase()}/${encodeURIComponent(d.linked_party)}">${d.linked_party}</a></td>
                        </tr>
                        <tr>
                            <td><strong>${__("SI Outstanding")}</strong></td>
                            <td>${frappe.format(d.si_outstanding, { fieldtype: "Currency" })}</td>
                        </tr>
                        <tr>
                            <td><strong>${__("PI Outstanding")}</strong></td>
                            <td>${frappe.format(d.pi_outstanding, { fieldtype: "Currency" })}</td>
                        </tr>
                        <tr style="font-weight: bold; background: #f0f7ff;">
                            <td><strong>${__("Net Position")}</strong></td>
                            <td>${frappe.format(d.net_position, { fieldtype: "Currency" })} (${d.net_label})</td>
                        </tr>
                    </table>
                `;

                frm.dashboard.show();
                frm.dashboard.add_section(html, __("Net Position"));

                frm.add_custom_button(
                    __("Create Netting Journal Entry"),
                    function () {
                        _create_netting_je(frm, party_type);
                    },
                    __("Net Position")
                );
            }
        },
    });
}

function _create_netting_je(frm, party_type) {
    frappe.call({
        method: "optimusland.utils.party.create_netting_journal_entry",
        args: {
            party_type: party_type,
            party_name: frm.doc.name,
        },
        callback: function (res) {
            if (res.message && res.message.success) {
                frappe.show_alert({
                    message: __("Netting JE {0} created successfully", [res.message.journal_entry]),
                    indicator: "green",
                });
                frappe.set_route("Form", "Journal Entry", res.message.journal_entry);
            } else {
                frappe.msgprint(res.message.error || __("Could not create Netting Journal Entry."));
            }
        },
    });
}
