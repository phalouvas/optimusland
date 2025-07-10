// Copyright (c) 2024, KAINOTOMO PH LTD and contributors
// For license information, please see license.txt

frappe.query_reports["Purchase Receipt Gross Profit"] = {
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
			default: erpnext.utils.get_fiscal_year(frappe.datetime.get_today(), true)[1],
			reqd: 1,
		},
		{
			fieldname: "to_date",
			label: __("To Date"),
			fieldtype: "Date",
			default: erpnext.utils.get_fiscal_year(frappe.datetime.get_today(), true)[2],
			reqd: 1,
		},
		{
			fieldname: "status",
			label: __("Status"),
			fieldtype: "Select",
			options:
				"\nTo Bill\nCompleted\nReturn Issued\nCancelled\nClosed",
			default: "To Bill",
		},
		{
			fieldname: "purchase_receipt",
			label: __("Purchase Receipt"),
			fieldtype: "Link",
			options: "Purchase Receipt",	
			get_query: function () {
				var company = frappe.query_report.get_filter_value("company");
				return {
					filters: [
						["Purchase Receipt", "company", "=", company],
						["Purchase Receipt", "docstatus", "=", 1]
					],
				};
			},		
		},
		{
			fieldname: "supplier",
			label: __("Supplier"),
			fieldtype: "Link",
			options: "Supplier",
		},
		{
			fieldname: "batch_no",
			label: __("Batch No"),
			fieldtype: "Data",
		},
		{
			fieldname: "customer",
			label: __("Customer"),
			fieldtype: "Link",
			options: "Customer",
		},
		{
			fieldname: "wished_earning_percentage",
			label: __("Wished Earning %"),
			fieldtype: "Int",
			default: 5,
		}
	],
	formatter: function(value, row, column, data, default_formatter) {
		value = default_formatter(value, row, column, data);
		if (data && data.supplier === "Total") {
			return `<b>${value}</b>`;
		}
		return value;
	},
};
