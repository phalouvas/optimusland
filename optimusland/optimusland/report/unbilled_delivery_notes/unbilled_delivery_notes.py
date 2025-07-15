# Copyright (c) 2025, KAINOTOMO PH LTD and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.utils import flt, getdate


def execute(filters=None):
	"""
	Report to show unbilled delivery note items with optional filters for company, dates, and customer.
	Calculates billed and unbilled amounts for each delivery note item.
	"""
	if not filters:
		filters = {}
	
	columns = get_columns()
	data = get_data(filters)
	
	# Add summary row if there's data
	if data:
		summary_row = get_summary_row(data)
		data.append(summary_row)
	
	return columns, data


def get_columns():
	"""Define the columns for the report"""
	return [
		{
			"label": _("Delivery Note"),
			"fieldname": "delivery_note",
			"fieldtype": "Link",
			"options": "Delivery Note",
			"width": 120
		},
		{
			"label": _("Date"),
			"fieldname": "posting_date",
			"fieldtype": "Date",
			"width": 90
		},
		{
			"label": _("Customer"),
			"fieldname": "customer",
			"fieldtype": "Link",
			"options": "Customer",
			"width": 150
		},
		{
			"label": _("Item Code"),
			"fieldname": "item_code",
			"fieldtype": "Link",
			"options": "Item",
			"width": 120
		},
		{
			"label": _("Item Name"),
			"fieldname": "item_name",
			"fieldtype": "Data",
			"width": 150
		},
		{
			"label": _("Qty"),
			"fieldname": "qty",
			"fieldtype": "Float",
			"width": 80,
			"precision": 2
		},
		{
			"label": _("Rate"),
			"fieldname": "rate",
			"fieldtype": "Currency",
			"width": 100
		},
		{
			"label": _("Amount"),
			"fieldname": "amount",
			"fieldtype": "Currency",
			"width": 120
		},
		{
			"label": _("Billed Amount"),
			"fieldname": "billed_amt",
			"fieldtype": "Currency",
			"width": 120
		},
		{
			"label": _("Unbilled Amount"),
			"fieldname": "unbilled_amt",
			"fieldtype": "Currency",
			"width": 120
		},
		{
			"label": _("% Billed"),
			"fieldname": "per_billed",
			"fieldtype": "Percent",
			"width": 80
		},
		{
			"label": _("Status"),
			"fieldname": "dn_status",
			"fieldtype": "Data",
			"width": 100
		},
		{
			"label": _("System Billed Amt"),
			"fieldname": "system_billed_amt",
			"fieldtype": "Currency",
			"width": 120
		},
		{
			"label": _("Variance"),
			"fieldname": "variance",
			"fieldtype": "Currency",
			"width": 100
		},
		{
			"label": _("Company"),
			"fieldname": "company",
			"fieldtype": "Link",
			"options": "Company",
			"width": 120
		}
	]


def get_data(filters):
	"""Get delivery note items data with billing information by matching actual sales invoice items"""
	conditions = get_conditions(filters)
	
	# Enhanced query to get delivery note items with actual billed amounts from sales invoices
	# Improvements:
	# 1. Handles delivery notes with ZERO sales invoice items (LEFT JOIN ensures all DN items are included)
	# 2. Properly aggregates partial billing across multiple sales invoices
	# 3. Adds customer validation to prevent incorrect linkages
	# 4. Includes closed delivery notes to catch billing discrepancies
	query = """
		SELECT 
			dn.name as delivery_note,
			dn.posting_date,
			dn.customer,
			dn.company,
			dn.status as dn_status,
			dni.name as dn_item_id,
			dni.item_code,
			dni.item_name,
			dni.qty,
			dni.rate,
			dni.amount,
			IFNULL(dni.billed_amt, 0) as system_billed_amt,
			COALESCE(invoice_totals.billed_amt, 0) as billed_amt
		FROM `tabDelivery Note` dn
		INNER JOIN `tabDelivery Note Item` dni ON dn.name = dni.parent
		LEFT JOIN (
			SELECT 
				sii.delivery_note,
				sii.dn_detail,
				SUM(
					CASE 
						WHEN si.docstatus = 1 AND si.is_return = 0 AND si.customer = sii_dn.customer
						THEN sii.amount
						WHEN si.docstatus = 1 AND si.is_return = 1 AND si.customer = sii_dn.customer
						THEN -sii.amount
						ELSE 0
					END
				) as billed_amt
			FROM `tabSales Invoice Item` sii
			INNER JOIN `tabSales Invoice` si ON sii.parent = si.name
			INNER JOIN `tabDelivery Note` sii_dn ON sii.delivery_note = sii_dn.name
			WHERE si.docstatus = 1
			AND sii.delivery_note IS NOT NULL
			AND sii.dn_detail IS NOT NULL
			GROUP BY sii.delivery_note, sii.dn_detail
		) invoice_totals ON (
			invoice_totals.delivery_note = dn.name 
			AND invoice_totals.dn_detail = dni.name
		)
		WHERE dn.docstatus = 1
		{conditions}
		ORDER BY dn.posting_date DESC, dn.name, dni.idx
	""".format(conditions=conditions)
	
	try:
		data = frappe.db.sql(query, filters, as_dict=1)
		
		# Filter and calculate unbilled amounts and percentages
		unbilled_data = []
		for row in data:
			# Ensure numeric values are properly formatted
			row.qty = flt(row.qty, 2)
			row.rate = flt(row.rate, 2)
			row.amount = flt(row.amount, 2)
			row.billed_amt = flt(row.billed_amt, 2)
			row.system_billed_amt = flt(row.system_billed_amt, 2)
			
			# Calculate unbilled amount
			row.unbilled_amt = flt(row.amount - row.billed_amt, 2)
			
			# Calculate variance between calculated and system billed amounts
			row.variance = flt(row.billed_amt - row.system_billed_amt, 2)
			
			# Calculate billing percentage
			if row.amount > 0:
				row.per_billed = flt((row.billed_amt / row.amount) * 100, 2)
			else:
				row.per_billed = 0.0
			
			# Ensure we don't show negative unbilled amounts due to rounding
			if row.unbilled_amt < 0:
				row.unbilled_amt = 0.0
				row.per_billed = 100.0
			
			# Only include items with unbilled amounts > 0.01 (to handle rounding)
			if row.unbilled_amt > 0.01:
				unbilled_data.append(row)
		
		return unbilled_data
		
	except Exception as e:
		frappe.log_error(f"Error in Unbilled Delivery Notes report: {str(e)}")
		frappe.throw(_("Error retrieving data. Please check your filters and try again."))


def get_conditions(filters):
	"""Build WHERE conditions based on filters"""
	conditions = []
	
	if filters.get("company"):
		conditions.append("AND dn.company = %(company)s")
	
	if filters.get("customer"):
		conditions.append("AND dn.customer = %(customer)s")
	
	if filters.get("from_date"):
		conditions.append("AND dn.posting_date >= %(from_date)s")
	
	if filters.get("to_date"):
		conditions.append("AND dn.posting_date <= %(to_date)s")
	
	return " ".join(conditions)


def get_summary_row(data):
	"""Calculate and return summary totals"""
	total_amount = sum(flt(row.get('amount', 0)) for row in data)
	total_billed = sum(flt(row.get('billed_amt', 0)) for row in data)
	total_unbilled = sum(flt(row.get('unbilled_amt', 0)) for row in data)
	
	overall_billed_percentage = (total_billed / total_amount * 100) if total_amount > 0 else 0
	
	return {
		'delivery_note': '',
		'posting_date': '',
		'customer': 'TOTAL',
		'item_code': '',
		'item_name': '',
		'qty': '',
		'rate': '',
		'amount': flt(total_amount, 2),
		'billed_amt': flt(total_billed, 2),
		'unbilled_amt': flt(total_unbilled, 2),
		'per_billed': flt(overall_billed_percentage, 2),
		'dn_status': '',
		'system_billed_amt': '',
		'variance': '',
		'company': ''
	}
