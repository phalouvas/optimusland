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
	
	# Add totals and averages row
	if data:
		total_row = calculate_totals_and_averages(data)
		data.append(total_row)

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

		batch_no_list = [item.batch_no for item in purchase_receipts_items]
		if not batch_no_list:
			return

		self.filters["batch_no_list"] = batch_no_list

		# Add customer filter to sales_invoices_items query
		customer_condition = ""
		if self.filters.customer:
			customer_condition = "AND dn.customer = %(customer)s"

		delivery_notes_items = frappe.db.sql(
			"""
			SELECT
				dn.name AS delivery_note,
				dn.customer,
				dn.custom_shipping_rate,
				dni.item_code,
				(COALESCE(dn.custom_shipping_rate, 0) + COALESCE(sbe.incoming_rate, 0)) AS incoming_rate,
				sbe.batch_no
			FROM
				`tabDelivery Note Item` dni
			LEFT JOIN `tabDelivery Note` dn ON dn.name = dni.parent
			LEFT JOIN `tabSerial and Batch Entry` sbe ON sbe.parent = dni.serial_and_batch_bundle
			WHERE
				dn.docstatus = 1
				AND dn.company = %(company)s
				AND sbe.batch_no IN %(batch_no_list)s
				{customer_condition}
			""".format(customer_condition=customer_condition),
			self.filters,
			as_dict=1
		)

		# Add safety check here
		if not delivery_notes_items:
			return

		delivery_notes_names = ','.join([f"'{item.delivery_note}'" for item in delivery_notes_items])

		# Build a lookup for batch_no to purchase_receipt_item
		batch_no_to_pr_item = {item.batch_no: item for item in purchase_receipts_items}

		for delivery_note_item in delivery_notes_items:
			batch_no = delivery_note_item.batch_no
			purchase_receipt_item = batch_no_to_pr_item.get(batch_no)
			if purchase_receipt_item:
				delivery_note_item["purchase_receipt"] = purchase_receipt_item.purchase_receipt
				delivery_note_item["status"] = purchase_receipt_item.status
				delivery_note_item["posting_date"] = purchase_receipt_item.posting_date
				delivery_note_item["supplier"] = purchase_receipt_item.supplier
				delivery_note_item["purchase_qty"] = purchase_receipt_item.purchase_qty
				delivery_note_item["purchase_rate"] = purchase_receipt_item.purchase_rate
				delivery_note_item["purchase_amount"] = purchase_receipt_item.purchase_amount

		# Add customer filter to sales_invoices_items query
		customer_condition = ""
		if self.filters.customer:
			customer_condition = "AND si.customer = %(customer)s"

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
				{customer_condition}
			""".format(
				delivery_notes_names=delivery_notes_names,
				customer_condition=customer_condition
			),
			self.filters,
			as_dict=1
		)

		# Build a lookup for delivery_note + item_code
		delivery_note_lookup = {
			(item.delivery_note, item.item_code): item
			for item in delivery_notes_items
		}

		for sales_invoices_item in sales_invoices_items:
			key = (sales_invoices_item.delivery_note, sales_invoices_item.item_code)
			delivery_note_item = delivery_note_lookup.get(key)
			if delivery_note_item:
				sales_invoices_item["purchase_receipt"] = delivery_note_item.purchase_receipt
				sales_invoices_item["status"] = delivery_note_item.status
				sales_invoices_item["posting_date"] = delivery_note_item.posting_date
				sales_invoices_item["supplier"] = delivery_note_item.supplier
				sales_invoices_item["purchase_qty"] = delivery_note_item.purchase_qty
				sales_invoices_item["purchase_rate"] = delivery_note_item.purchase_rate
				sales_invoices_item["purchase_amount"] = delivery_note_item.purchase_amount
				sales_invoices_item["batch_no"] = delivery_note_item.batch_no
				sales_invoices_item["incoming_rate"] = delivery_note_item.incoming_rate
				incoming_profit_rate = sales_invoices_item.selling_rate - delivery_note_item.incoming_rate
				sales_invoices_item["incoming_profit_rate"] = round(incoming_profit_rate, 3)
				sales_invoices_item["incoming_profit_percentage"] = round((incoming_profit_rate / sales_invoices_item.selling_rate) * 100)
				sales_invoices_item["incoming_profit_amount"] = round(sales_invoices_item.selling_qty * incoming_profit_rate, 3)
				wished_profit_rate = (self.filters.wished_earning_percentage / 100) * sales_invoices_item.selling_rate
				sales_invoices_item["wished_profit_rate"] = round(wished_profit_rate, 3)
				sales_invoices_item["wished_profit_amount"] = round(sales_invoices_item.selling_qty * wished_profit_rate, 3)
				supplier_rate = sales_invoices_item.selling_rate + sales_invoices_item.purchase_rate - delivery_note_item.incoming_rate - wished_profit_rate
				sales_invoices_item["supplier_rate"] = round(supplier_rate, 3)
				sales_invoices_item["supplier_amount"] = round(sales_invoices_item.selling_qty * supplier_rate, 3)

		# Remove any sales invoice items not found (i.e., without a matching delivery_note_item)
		sales_invoices_items = [
			item for item in sales_invoices_items
			if (item.delivery_note, item.item_code) in delivery_note_lookup
		]

		self.sales_invoices_items = sales_invoices_items
		self.sales_invoices_items.sort(key=lambda x: x.get('supplier', ''))

		pass

def calculate_totals_and_averages(data):
	"""Calculate totals for money/quantity columns and averages for rate/percentage columns"""
	if not data:
		return {}
	
	total_row = {
		"supplier": "Total",
		"purchase_receipt": "",
		"status": "",
		"posting_date": "",
		"batch_no": "",
		"currency": "",
		"item_code": "",
		"item_name": "",
		"sales_invoice": "",
		"customer": "",
		"delivery_note": "",
	}
	
	# Money and quantity columns to sum
	sum_columns = [
		"selling_qty", "selling_amount", "incoming_profit_amount", "wished_profit_amount", "supplier_amount"
	]
	
	# Calculate sums
	for col in sum_columns:
		total_value = sum(float(row.get(col, 0) or 0) for row in data)
		total_row[col] = round(total_value, 3)
	
	# Calculate rates as total amount / total quantity
	total_selling_qty = total_row.get("selling_qty", 0)
	total_selling_amount = total_row.get("selling_amount", 0)
	total_incoming_profit_amount = total_row.get("incoming_profit_amount", 0)
	total_wished_profit_amount = total_row.get("wished_profit_amount", 0)
	total_supplier_amount = total_row.get("supplier_amount", 0)
	
	if total_selling_qty and total_selling_qty != 0:
		# Calculate effective rates by dividing total amounts by total quantity
		total_row["selling_rate"] = round(total_selling_amount / total_selling_qty, 3)
		total_row["incoming_profit_rate"] = round(total_incoming_profit_amount / total_selling_qty, 3)
		total_row["wished_profit_rate"] = round(total_wished_profit_amount / total_selling_qty, 3)
		total_row["supplier_rate"] = round(total_supplier_amount / total_selling_qty, 3)
		# Calculate incoming_rate as selling_rate - incoming_profit_rate
		total_row["incoming_rate"] = round(total_row["selling_rate"] - total_row["incoming_profit_rate"], 3)
		# Calculate purchase_rate as simple average
		purchase_rates = [float(row.get("purchase_rate", 0) or 0) for row in data if row.get("purchase_rate") is not None]
		if purchase_rates:
			total_row["purchase_rate"] = round(sum(purchase_rates) / len(purchase_rates), 3)
		else:
			total_row["purchase_rate"] = 0
	else:
		# If total quantity is zero, set rates to zero
		for col in ["selling_rate", "incoming_rate", "purchase_rate", "incoming_profit_rate", "wished_profit_rate", "supplier_rate"]:
			total_row[col] = 0
	
	# Calculate percentage based on totals
	if total_selling_amount and total_selling_amount != 0:
		total_row["incoming_profit_percentage"] = round((total_incoming_profit_amount / total_selling_amount) * 100, 0)
	else:
		total_row["incoming_profit_percentage"] = 0
	
	return total_row