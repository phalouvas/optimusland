// Copyright (c) 2026, KAINOTOMO PH LTD and contributors
// For license information, please see license.txt

frappe.query_reports["Party Accounting Ledger"] = {
	"filters": [
		{
			"fieldname": "party_link",
			"label": __("Party Link"),
			"fieldtype": "Link",
			"options": "Party Link",
			"reqd": 1,
		},
		{
			"fieldname": "company",
			"label": __("Company"),
			"fieldtype": "Link",
			"options": "Company",
			"default": frappe.defaults.get_user_default("Company"),
			"reqd": 0,
		},
		{
			"fieldname": "from_date",
			"label": __("From Date"),
			"fieldtype": "Date",
			"default": frappe.datetime.year_start(),
			"reqd": 0,
		},
		{
			"fieldname": "to_date",
			"label": __("To Date"),
			"fieldtype": "Date",
			"default": frappe.datetime.get_today(),
			"reqd": 0,
		},
	],

	"formatter": function (value, row, column, data, default_formatter) {
		value = default_formatter(value, row, column, data);

		if (!data) return value;

		// Opening balance row
		if (data.is_opening) {
			if (column.fieldname === "balance") {
				value = `<b>${value}</b>`;
			}
			if (column.fieldname === "remarks") {
				value = `<b>${__(value)}</b>`;
			}
			return value;
		}

		// Closing balance row
		if (data.is_closing) {
			if (["debit", "credit", "balance"].includes(column.fieldname)) {
				value = `<b>${value}</b>`;
			}
			if (column.fieldname === "remarks") {
				value = `<b>${__(value)}</b>`;
			}
			return value;
		}

		// Net position row
		if (data.is_net_position) {
			if (column.fieldname === "balance") {
				value = `<span style="font-weight: bold; color: #2c3e50;">${value}</span>`;
			}
			if (column.fieldname === "remarks") {
				const is_positive = flt(data.balance) >= 0;
				const color = is_positive ? "#c0392b" : "#27ae60";
				value = `<span style="font-weight: bold; color: ${color};">${value}</span>`;
			}
			return value;
		}

		// Highlight negative balances in red
		if (column.fieldname === "balance" && flt(data.balance) < 0) {
			value = `<span style="color: #e74c3c;">${value}</span>`;
		}

		// Role column styling
		if (column.fieldname === "role") {
			if (data.role === __("As Customer")) {
				value = `<span style="color: #27ae60;">${value}</span>`;
			} else if (data.role === __("As Supplier")) {
				value = `<span style="color: #2980b9;">${value}</span>`;
			}
		}

		return value;
	},
};
