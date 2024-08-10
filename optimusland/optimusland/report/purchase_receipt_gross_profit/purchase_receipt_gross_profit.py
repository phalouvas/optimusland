# Copyright (c) 2024, KAINOTOMO PH LTD and contributors
# For license information, please see license.txt

import frappe
from frappe import _, scrub

def execute(filters=None):
	if not filters:
		filters = frappe._dict()

	gross_profit_data = GrossProfitGenerator(filters)

	data = []

	columns = get_columns(filters)
	data = gross_profit_data.sales_invoices_items

	return columns, data

def get_columns(filters):
	columns = [		
		{
			"label": _("Supplier"),
			"fieldtype": "Link",
			"fieldname": "supplier",
			"options": "Supplier",
			"width": 100,
		},
		{
			"label": _("Purchase Receipt"),
			"fieldtype": "Link",
			"fieldname": "purchase_receipt",
			"options": "Purchase Receipt",
			"width": 120,
		},
		{
			"label": _("Status"),
			"fieldtype": "Data",
			"fieldname": "status",
			"width": 100
		},
		{
			"label": _("Posting Date"),
			"fieldtype": "Date",
			"fieldname": "posting_date",
		},
		{
			"label": _("Batch No"),
			"fieldtype": "Link",
			"fieldname": "batch_no",
			"options": "Batch",
			"width": 100,
		},
		{
			"label": _("Currency"),
			"fieldtype": "Link",
			"fieldname": "currency",
			"options": "Currency",
			"hidden": 1,
			"width": 50,
		},		
		{
			"label": _("Item Code"),
			"fieldtype": "Link",
			"fieldname": "item_code",
			"options": "Item",
			"width": 100,
		},
		{
			"label": _("Item Name"),
			"fieldtype": "Data",
			"fieldname": "item_name",
			"width": 200,
		},
		{
			"label": _("Purchase Qty"),
			"fieldtype": "Float",
			"fieldname": "purchase_qty",
			"width": 100,
		},
		{
			"label": _("Purchase Rate"),
			"fieldtype": "Currency",
			"fieldname": "purchase_rate",
			"options": "currency",
			"width": 100,
		},
		{
			"label": _("Purchase Amount"),
			"fieldtype": "Currency",
			"fieldname": "purchase_amount",
			"options": "currency",
			"width": 100,
		},
		{
			"label": _("Sales Invoice"),
			"fieldtype": "Link",
			"fieldname": "sales_invoice",
			"options": "Sales Invoice",
			"width": 120,
		},
		{
			"label": _("Delivery Note"),
			"fieldtype": "Link",
			"fieldname": "delivery_note",
			"options": "Delivery Note",
			"width": 120,
		},
		{
			"label": _("Selling Qty"),
			"fieldtype": "Float",
			"fieldname": "selling_qty",
			"width": 100,
		},
		{
			"label": _("Selling Rate"),
			"fieldtype": "Currency",
			"fieldname": "selling_rate",
			"options": "currency",
			"width": 100,
		},
		{
			"label": _("Cost Rate"),
			"fieldtype": "Currency",
			"fieldname": "cost_rate",
			"options": "currency",
			"width": 100,
		},
		{
			"label": _("Selling Amount"),
			"fieldtype": "Currency",
			"fieldname": "selling_amount",
			"options": "currency",
			"width": 100,
		},
		{
			"label": _("Gross Profit Rate"),
			"fieldtype": "Percent",
			"fieldname": "gross_profit_rate",
			"width": 100,
		},
		{
			"label": _("Gross Profit Percentage"),
			"fieldtype": "Percent",
			"fieldname": "gross_profit_percentage",
			"width": 100,
		},
		{
			"label": _("Gross Profit Amount"),
			"fieldtype": "Currency",
			"fieldname": "gross_profit_amount",
			"options": "currency",
			"width": 100,
		},
	]

	return columns

class GrossProfitGenerator:
	def __init__(self, filters):
		self.filters = frappe._dict(filters)
		self.validate_filters()
		self.get_sales_invoices_items()

	def validate_filters(self):
		if not self.filters.company:
			frappe.throw(_("Company is required"))

	def get_sales_invoices_items(self):

		conditions = ""
		if self.filters.status:
			conditions += f" AND pr.status = %(status)s"
		if self.filters.supplier:
			conditions += f" AND pr.supplier = %(supplier)s"
		if self.filters.purchase_receipt:
			conditions += f" AND pr.name = %(purchase_receipt)s"

		purchase_receipts_items = frappe.db.sql(
			"""
			SELECT
				pr.name AS purchase_receipt,
				pr.supplier,
				pr.status,
				pr.posting_date,
				pri.item_code,
				pri.item_name,
				pri.qty as purchase_qty,
				pri.rate as purchase_rate,
				pri.amount as purchase_amount,
				sbe.batch_no
			FROM
				`tabPurchase Receipt Item` pri
			LEFT JOIN `tabPurchase Receipt` pr ON pr.name = pri.parent
			LEFT JOIN `tabSerial and Batch Entry` sbe ON sbe.parent = pri.serial_and_batch_bundle
			WHERE
				pr.docstatus = 1
				AND pr.company = %(company)s
				AND pr.posting_date BETWEEN %(from_date)s AND %(to_date)s
				AND sbe.batch_no IS NOT NULL
				AND sbe.batch_no != ''
				{conditions}
			""".format(conditions=conditions),
			self.filters,
			as_dict=1
		)

		sales_invoices_items = frappe.db.sql(
			"""
			SELECT
				si.name AS sales_invoice,
				si.customer,
				dn.name AS delivery_note,
				sii.item_code,
				sii.item_name,
				sii.qty as selling_qty,
				sii.net_rate as selling_rate,
				sii.incoming_rate as cost_rate,
				sii.amount as selling_amount,
				sbe.batch_no
			FROM
				`tabSales Invoice Item` sii
			LEFT JOIN `tabSales Invoice` si ON si.name = sii.parent
			LEFT JOIN `tabDelivery Note` dn ON dn.name = sii.delivery_note
			LEFT JOIN `tabDelivery Note Item` dni ON dn.name = dni.parent
			LEFT JOIN `tabSerial and Batch Entry` sbe ON sbe.parent = dni.serial_and_batch_bundle
			WHERE
				si.docstatus = 1
				AND si.company = %(company)s
				AND sbe.batch_no IN (
					SELECT DISTINCT sbe.batch_no
					FROM
						`tabPurchase Receipt Item` pri
					LEFT JOIN `tabPurchase Receipt` pr ON pr.name = pri.parent
					LEFT JOIN `tabSerial and Batch Entry` sbe ON sbe.parent = pri.serial_and_batch_bundle
					WHERE
						pr.docstatus = 1
						AND pr.company = %(company)s
						AND pr.posting_date BETWEEN %(from_date)s AND %(to_date)s
						AND sbe.batch_no IS NOT NULL
						AND sbe.batch_no != ''
						{conditions}
				)
			""".format(conditions=conditions),
			self.filters,
			as_dict=1
		)

		for sales_invoices_item in sales_invoices_items:
			for purchase_receipt_item in purchase_receipts_items:
				if sales_invoices_item.batch_no == purchase_receipt_item.batch_no:
					sales_invoices_item["purchase_receipt"] = purchase_receipt_item.purchase_receipt
					sales_invoices_item["status"] = purchase_receipt_item.status
					sales_invoices_item["posting_date"] = purchase_receipt_item.posting_date
					sales_invoices_item["supplier"] = purchase_receipt_item.supplier
					sales_invoices_item["purchase_qty"] = purchase_receipt_item.purchase_qty
					sales_invoices_item["purchase_rate"] = purchase_receipt_item.purchase_rate
					sales_invoices_item["purchase_amount"] = purchase_receipt_item.purchase_amount
					sales_invoices_item["gross_profit_rate"] = round(sales_invoices_item.selling_rate - sales_invoices_item.cost_rate, 3)
					sales_invoices_item["gross_profit_percentage"] = round(((sales_invoices_item.selling_rate - sales_invoices_item.cost_rate) / sales_invoices_item.selling_rate) * 100)
					sales_invoices_item["gross_profit_amount"] = sales_invoices_item.selling_amount - (sales_invoices_item.selling_qty * sales_invoices_item.cost_rate)

		sales_invoices_items.sort(key=lambda x: x.get('supplier', ''))
		self.sales_invoices_items = sales_invoices_items
		

		pass