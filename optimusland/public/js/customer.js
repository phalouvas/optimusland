// Copyright (c) 2026, KAINOTOMO PH LTD and Contributors
// See license.txt

frappe.ui.form.on("Customer", {
    refresh: function (frm) {
        if (!frm.doc.__islocal) {
            _add_net_position_section(frm, "Customer");
            _add_payment_reconciliation_action(frm, "Customer");
            _add_party_statement_button(frm, "Customer");
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
                            <td><strong>${__("Receivable GL")}</strong></td>
                            <td>${frappe.format(d.si_gl, { fieldtype: "Currency" })}</td>
                        </tr>
                        <tr>
                            <td><strong>${__("Payable GL")}</strong></td>
                            <td>${frappe.format(d.pi_gl, { fieldtype: "Currency" })}</td>
                        </tr>
                        <tr style="font-weight: bold; background: #f0f7ff;">
                            <td><strong>${__("Net Position")}</strong></td>
                            <td>${frappe.format(d.net_position, { fieldtype: "Currency" })} (${d.net_label})</td>
                        </tr>
                    </table>
                `;

                frm.dashboard.show();
                frm.dashboard.add_section(html, __("Net Position"));
            }
        },
    });
}

function _add_party_statement_button(frm, party_type) {
	frappe.db.get_value("Party Link", {
		primary_party: frm.doc.name,
		primary_role: party_type
	}, "name", (r) => {
		if (r && r.name) {
			_add_button(frm, r.name);
			return;
		}
		// Also check as secondary party
		frappe.db.get_value("Party Link", {
			secondary_party: frm.doc.name,
			secondary_role: party_type
		}, "name", (r2) => {
			if (r2 && r2.name) {
				_add_button(frm, r2.name);
			}
		});
	});
}

function _add_button(frm, party_link_name) {
	frm.add_custom_button(
		__("Party Statement"),
		function () {
			frappe.route_options = {
				party_link: party_link_name,
			};
			frappe.set_route("query-report", "Party Accounting Ledger");
		},
		__("View")
	);
}

function _add_payment_reconciliation_action(frm, party_type) {
    frm.add_custom_button(__("Payment Reconciliation"), function () {
        frappe.route_options = {
            party_type: party_type,
            party: frm.doc.name,
        };
        frappe.set_route("Form", "Payment Reconciliation");
    }, __("Actions"));
}
