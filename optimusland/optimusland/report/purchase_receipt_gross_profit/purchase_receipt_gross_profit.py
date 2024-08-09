# Copyright (c) 2024, KAINOTOMO PH LTD and contributors
# For license information, please see license.txt

import frappe
from frappe import _

def execute(filters=None):
	if not filters:
		filters = frappe._dict()
	filters.currency = frappe.get_cached_value("Company", filters.company, "default_currency")

	gross_profit_data = GrossProfitGenerator(filters)

	columns, data = [], []

	return columns, data

class GrossProfitGenerator:
	def __init__(self, filters):
		self.filters = filters
		self.validate_filters()
		self.get_purchase_receipt_items()

	def validate_filters(self):
		if not self.filters.company:
			frappe.throw(_("Company is required"))

	def get_purchase_receipt_items(self):

		purchase_receipts_items = frappe.db.sql(
			"""
			SELECT
				pr.name AS purchase_receipt,
				pr.supplier,
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
			""",
			{
				"company": self.filters.company,
				"from_date": self.filters.from_date,
				"to_date": self.filters.to_date
			},
			as_dict=1
		)

		sales_invoices_items = frappe.db.sql(
			"""
			SELECT
				dn.name AS delivery_note,
				si.customer,
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
				)
			""",
			{
				"company": self.filters.company,
				"from_date": self.filters.from_date,
				"to_date": self.filters.to_date
			},
			as_dict=1
		)

		for sales_invoices_item in sales_invoices_items:
			for purchase_receipt_item in purchase_receipts_items:
				if sales_invoices_item.batch_no == purchase_receipt_item.batch_no:
					sales_invoices_item["purchase_receipt"] = purchase_receipt_item.purchase_receipt
					sales_invoices_item["supplier"] = purchase_receipt_item.supplier
					sales_invoices_item["purchase_qty"] = purchase_receipt_item.purchase_qty
					sales_invoices_item["purchase_rate"] = purchase_receipt_item.purchase_rate
					sales_invoices_item["purchase_amount"] = purchase_receipt_item.purchase_amount
					sales_invoices_item["gross_profit_rate"] = round(sales_invoices_item.selling_rate - sales_invoices_item.cost_rate, 3)
					sales_invoices_item["gross_profit_percentage"] = round(((sales_invoices_item.selling_rate - sales_invoices_item.cost_rate) / sales_invoices_item.selling_rate) * 100)
					sales_invoices_item["gross_profit_amount"] = sales_invoices_item.selling_amount - (sales_invoices_item.selling_qty * sales_invoices_item.cost_rate)

		pass