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
		},
		{
			"label": _("Purchase Receipt"),
			"fieldtype": "Link",
			"fieldname": "purchase_receipt",
			"options": "Purchase Receipt",
		},
		{
			"label": _("Status"),
			"fieldtype": "Data",
			"fieldname": "status",
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
		},
		{
			"label": _("Item Name"),
			"fieldtype": "Data",
			"fieldname": "item_name",
		},		
		{
			"label": _("Sales Invoice"),
			"fieldtype": "Link",
			"fieldname": "sales_invoice",
			"options": "Sales Invoice",
		},
		{
			"label": _("Customer"),
			"fieldtype": "Link",
			"fieldname": "customer",
			"options": "Customer",
		},
		{
			"label": _("Delivery Note"),
			"fieldtype": "Link",
			"fieldname": "delivery_note",
			"options": "Delivery Note",
		},
		{
			"label": _("Purchase Rate"),
			"fieldtype": "Currency",
			"fieldname": "purchase_rate",
			"options": "currency",
		},		
		{
			"label": _("Selling Rate"),
			"fieldtype": "Currency",
			"fieldname": "selling_rate",
			"options": "currency",
		},
		{
			"label": _("Incoming Rate"),
			"fieldtype": "Currency",
			"fieldname": "incoming_rate",
			"options": "currency",
		},
		{
			"label": _("Selling Qty"),
			"fieldtype": "Integer",
			"fieldname": "selling_qty",
		},
		{
			"label": _("Selling Amount"),
			"fieldtype": "Currency",
			"fieldname": "selling_amount",
			"options": "currency",
		},
		{
			"label": _("Incoming Profit Rate"),
			"fieldtype": "Currency",
			"fieldname": "incoming_profit_rate",
		},
		{
			"label": _("Incoming Profit Percentage"),
			"fieldtype": "Percent",
			"fieldname": "incoming_profit_percentage",
		},
		{
			"label": _("Incoming Profit Amount"),
			"fieldtype": "Currency",
			"fieldname": "incoming_profit_amount",
			"options": "currency",
		},
		{
			"label": _("Wished Profit Rate"),
			"fieldtype": "Currency",
			"fieldname": "wished_profit_rate",
		},
		{
			"label": _("Wished Profit Amount"),
			"fieldtype": "Currency",
			"fieldname": "wished_profit_amount",
			"options": "currency",
		},
		{
			"label": _("Supplier Rate"),
			"fieldtype": "Currency",
			"fieldname": "supplier_rate",
		},
		{
			"label": _("Supplier Amount"),
			"fieldtype": "Currency",
			"fieldname": "supplier_amount",
			"options": "currency",
		},
	]

	return columns

class GrossProfitGenerator:
	def __init__(self, filters):
		filters.wished_earning_percentage = filters.wished_earning_percentage or 0
		self.filters = frappe._dict(filters)
		self.validate_filters()
		self.sales_invoices_items =	[]
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
		if self.filters.batch_no:
			# Ensure batch_no is searched as a substring
			self.filters.batch_no = f"%{self.filters.batch_no}%"
			conditions += f" AND sbe.batch_no LIKE %(batch_no)s"

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

		if not purchase_receipts_items:
			return 

		batch_nos = ','.join([f"'{item.batch_no}'" for item in purchase_receipts_items])

		delivery_notes_items = frappe.db.sql(
			"""
			SELECT
				dn.name AS delivery_note,
				dn.customer,
				dni.item_code,
				sbe.incoming_rate,
				sbe.batch_no
			FROM
				`tabDelivery Note Item` dni
			LEFT JOIN `tabDelivery Note` dn ON dn.name = dni.parent
			LEFT JOIN `tabSerial and Batch Entry` sbe ON sbe.parent = dni.serial_and_batch_bundle
			WHERE
				dn.docstatus = 1
				AND dn.company = %(company)s
				AND sbe.batch_no IN ({batch_nos})
			""".format(batch_nos=batch_nos),
			self.filters,
			as_dict=1
		)

		delivery_notes_names = ','.join([f"'{item.delivery_note}'" for item in delivery_notes_items])

		for delivery_note_item in delivery_notes_items:
			for purchase_receipt_item in purchase_receipts_items:
				if delivery_note_item.batch_no == purchase_receipt_item.batch_no:
					delivery_note_item["purchase_receipt"] = purchase_receipt_item.purchase_receipt
					delivery_note_item["status"] = purchase_receipt_item.status
					delivery_note_item["posting_date"] = purchase_receipt_item.posting_date
					delivery_note_item["supplier"] = purchase_receipt_item.supplier
					delivery_note_item["purchase_qty"] = purchase_receipt_item.purchase_qty
					delivery_note_item["purchase_rate"] = purchase_receipt_item.purchase_rate
					delivery_note_item["purchase_amount"] = purchase_receipt_item.purchase_amount

		sales_invoices_items = frappe.db.sql(
			"""
			SELECT
				si.name AS sales_invoice,
				si.customer,
				sii.delivery_note AS delivery_note,
				sii.item_code,
				sii.item_name,
				sii.qty as selling_qty,
				sii.net_rate as selling_rate,
				sii.incoming_rate as incoming_rate,
				sii.amount as selling_amount
			FROM
				`tabSales Invoice Item` sii
			LEFT JOIN `tabSales Invoice` si ON si.name = sii.parent
			WHERE
				si.docstatus = 1
				AND si.company = %(company)s
				AND sii.delivery_note IN ({delivery_notes_names})
			""".format(delivery_notes_names=delivery_notes_names),
			self.filters,
			as_dict=1
		)

		for sales_invoices_item in sales_invoices_items:
			for delivery_note_item in delivery_notes_items:
				if sales_invoices_item.delivery_note == delivery_note_item.delivery_note and sales_invoices_item.item_code == delivery_note_item.item_code:
					sales_invoices_item["purchase_receipt"] = delivery_note_item.purchase_receipt
					sales_invoices_item["status"] = delivery_note_item.status
					sales_invoices_item["posting_date"] = delivery_note_item.posting_date
					sales_invoices_item["supplier"] = delivery_note_item.supplier
					sales_invoices_item["purchase_qty"] = delivery_note_item.purchase_qty
					sales_invoices_item["purchase_rate"] = delivery_note_item.purchase_rate
					sales_invoices_item["purchase_amount"] = delivery_note_item.purchase_amount
					sales_invoices_item["batch_no"] = delivery_note_item.batch_no
					sales_invoices_item["incoming_rate"] = delivery_note_item.incoming_rate
					incoming_profit_rate = sales_invoices_item.selling_rate - sales_invoices_item.incoming_rate
					sales_invoices_item["incoming_profit_rate"] = round(incoming_profit_rate, 3)
					sales_invoices_item["incoming_profit_percentage"] = round((incoming_profit_rate / sales_invoices_item.selling_rate) * 100)
					sales_invoices_item["incoming_profit_amount"] = round(sales_invoices_item.selling_qty * incoming_profit_rate, 3)
					wished_profit_rate = ( self.filters.wished_earning_percentage / 100 ) * sales_invoices_item.selling_rate
					sales_invoices_item["wished_profit_rate"] = round(wished_profit_rate, 3)
					sales_invoices_item["wished_profit_amount"] = round(sales_invoices_item.selling_qty * wished_profit_rate, 3)
					supplier_rate = sales_invoices_item.selling_rate + sales_invoices_item.purchase_rate - sales_invoices_item.incoming_rate - wished_profit_rate
					sales_invoices_item["supplier_rate"] = round(supplier_rate, 3)
					sales_invoices_item["supplier_amount"] = round(sales_invoices_item.selling_qty * supplier_rate, 3)

		sales_invoices_items.sort(key=lambda x: x.get('supplier', ''))
		self.sales_invoices_items = sales_invoices_items

		pass