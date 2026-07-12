// Copyright (c) 2026, KAINOTOMO PH LTD and contributors
// For license information, please see license.txt

frappe.query_reports["Supplier Profitability"] = {
	"filters": [
		{
			fieldname: "company",
			label: __("Company"),
			fieldtype: "Link",
			options: "Company",
			default: frappe.defaults.get_user_default("Company"),
			reqd: 1,
		},
		{
			fieldname: "from_date",
			label: __("From Date"),
			fieldtype: "Date",
			default: frappe.datetime.add_months(frappe.datetime.get_today(), -1),
			reqd: 1,
		},
		{
			fieldname: "to_date",
			label: __("To Date"),
			fieldtype: "Date",
			default: frappe.datetime.get_today(),
			reqd: 1,
		},
		{
			fieldname: "supplier",
			label: __("Supplier"),
			fieldtype: "Link",
			options: "Supplier",
		},
		{
			fieldname: "customer",
			label: __("Customer"),
			fieldtype: "Link",
			options: "Customer",
		},
	],
	"formatter": function(value, row, column, data, default_formatter) {
		value = default_formatter(value, row, column, data);
		if (data && data.supplier === "Total") {
			value = "<b>" + value + "</b>";
		}
		if (column.fieldname === "margin_achieved" && data && data.margin_achieved != null && data.supplier !== "Total") {
			var color = data.margin_achieved >= 0 ? "green" : "red";
			value = "<span style='color:" + color + ";font-weight:bold'>" + value + "</span>";
		}
		if (column.fieldname === "profit_amount" && data && data.profit_amount != null && data.supplier !== "Total") {
			var color = data.profit_amount >= 0 ? "green" : "red";
			value = "<span style='color:" + color + ";font-weight:bold'>" + value + "</span>";
		}
		return value;
	}
};
