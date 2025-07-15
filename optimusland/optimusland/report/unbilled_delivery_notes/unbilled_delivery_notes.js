// Copyright (c) 2025, KAINOTOMO PH LTD and contributors
// For license information, please see license.txt

frappe.query_reports["Unbilled Delivery Notes"] = {
	"filters": [
		{
			"fieldname": "company",
			"label": __("Company"),
			"fieldtype": "Link",
			"options": "Company",
			"default": frappe.defaults.get_user_default("Company"),
			"reqd": 1
		},
		{
			"fieldname": "from_date",
			"label": __("From Date"),
			"fieldtype": "Date",
			"default": frappe.datetime.add_months(frappe.datetime.get_today(), -1),
			"reqd": 0
		},
		{
			"fieldname": "to_date",
			"label": __("To Date"),
			"fieldtype": "Date",
			"default": frappe.datetime.get_today(),
			"reqd": 0
		},
		{
			"fieldname": "customer",
			"label": __("Customer"),
			"fieldtype": "Link",
			"options": "Customer",
			"reqd": 0
		}
	],
	
	"formatter": function (value, row, column, data, default_formatter) {
		value = default_formatter(value, row, column, data);
		
		// Handle summary row formatting
		if (data && data.customer === 'TOTAL') {
			if (column.fieldname == "customer") {
				return value;  // Already has <b> tags
			}
			if (["amount", "billed_amt", "unbilled_amt", "per_billed"].includes(column.fieldname)) {
				value = `<b>${value}</b>`;
			}
			return value;
		}
		
		// Color coding for unbilled amounts
		if (column.fieldname == "unbilled_amt" && data && flt(data.unbilled_amt) > 0) {
			value = `<span style="color: red; font-weight: bold;">${value}</span>`;
		}
		
		// Color coding for delivery note status
		if (column.fieldname == "dn_status" && data) {
			if (data.dn_status === "To Bill") {
				value = `<span style="color: orange;">${value}</span>`;
			} else if (data.dn_status === "Completed") {
				value = `<span style="color: green;">${value}</span>`;
			} else if (data.dn_status === "Closed") {
				value = `<span style="color: red; font-weight: bold;">${value}</span>`;
			}
		}
		
		// Color coding for variance (difference between calculated and system billed amounts)
		if (column.fieldname == "variance" && data) {
			let variance = flt(data.variance);
			if (Math.abs(variance) > 0.01) {
				if (variance > 0) {
					value = `<span style="color: blue; font-weight: bold;">+${value}</span>`;
				} else {
					value = `<span style="color: purple; font-weight: bold;">${value}</span>`;
				}
			}
		}
		
		// Color coding for billing percentage
		if (column.fieldname == "per_billed" && data) {
			let percent = flt(data.per_billed);
			if (percent == 100) {
				value = `<span style="color: green; font-weight: bold;">${value}</span>`;
			} else if (percent > 50) {
				value = `<span style="color: orange; font-weight: bold;">${value}</span>`;
			} else if (percent > 0) {
				value = `<span style="color: darkorange; font-weight: bold;">${value}</span>`;
			} else {
				value = `<span style="color: red; font-weight: bold;">${value}</span>`;
			}
		}
		
		return value;
	},
	
	onload: function(report) {
		// Add custom button to refresh data
		report.page.add_inner_button(__("Refresh"), function() {
			report.refresh();
		});
		
		// Show total count in status bar
		report.page.wrapper.find('.form-message').remove();
		let message = __("This report shows delivery note items that have unbilled amounts. Use filters to narrow down results. Variance column shows difference between calculated and system billed amounts.");
		$(`<div class="form-message blue">
			<div class="ellipsis">${message}</div>
		</div>`).prependTo(report.page.wrapper.find('.layout-main-section'));
	}
};
