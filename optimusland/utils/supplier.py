import frappe
from frappe import _, qb, throw
from collections import defaultdict

@frappe.whitelist()
def get_supplier_unlinked_journal_entries(supplier_name: str):
	
	supplier_jv = frappe.db.sql(f"""
		SELECT 
			T1.`parent`
		FROM `tabJournal Entry Account` AS `T1`
		WHERE T1.`party` = '{supplier_name}'
			AND T1.`party_type` = 'Supplier'
			AND T1.`docstatus` < 2;
	""", as_dict=False)

	# if no unlinked journal entries return true
	if not supplier_jv:
		return True
	
	customer_jv = frappe.db.sql(f"""
		SELECT 
			T1.`parent`
		FROM `tabJournal Entry Account` AS `T1`
		WHERE T1.`party` = '{supplier_name}'
			AND T1.`party_type` = 'Customer'
			AND T1.`reference_type` IS NULL
			AND T1.`reference_name` IS NULL
			AND T1.`docstatus` < 2
			AND T1.`parent` IN ({','.join([f"'{row[0]}'" for row in supplier_jv])});
	""", as_dict=True)

	if customer_jv:
		non_empty_parents = [row['parent'] for row in customer_jv if row['parent']]
		message = f"Possible false balance. <br/>There are unlinked journal entries for supplier {supplier_name} with Voucher No:<br/> {', '.join(non_empty_parents)}"
		#frappe.msgprint(message, title="Warning")
		return message
	
	return True
	
	pass

@frappe.whitelist()
def create_purchase_invoice(production_plan_name: str):
	work_orders = frappe.get_all("Work Order", filters={"production_plan": production_plan_name, "status": "Completed"}, fields=["name"])
	completed_work_orders = [wo.name for wo in work_orders]
	stock_entries = frappe.get_all("Stock Entry", filters={"stock_entry_type": "Manufacture", "work_order": ["in", completed_work_orders]}, fields=["name"])
	serial_batch_bundle = []
	for stock_entry in stock_entries:
		stock_entry_details = frappe.get_all("Stock Entry Detail", filters={"parent": stock_entry.name, "serial_and_batch_bundle": ["Not Like", None]}, fields=["item_code", "is_finished_item", "serial_and_batch_bundle", "qty"])
		for stock_entry_detail in stock_entry_details:
			if stock_entry_detail.is_finished_item:
				item_description = stock_entry_detail.item_code
				rate = frappe.db.get_value("Item", item_description, "valuation_rate")
			else:
				qty = stock_entry_detail.qty
				item_code = stock_entry_detail.item_code
				batch_nos = frappe.get_all("Serial and Batch Entry", filters={"parent": stock_entry_detail.serial_and_batch_bundle}, fields=["batch_no"])
				if len(batch_nos) == 1:
					batch_no = batch_nos[0]['batch_no']
					purchase_receipts = frappe.get_all("Serial and Batch Bundle", 
										filters=[
											["Serial and Batch Entry","batch_no","=","ps_2"],
											["Serial and Batch Bundle","voucher_type","=","Purchase Receipt"],
											["Serial and Batch Bundle","docstatus","=","1"]
										], 
										fields=["name", "voucher_no"])
					if len(purchase_receipts) == 1:
						voucher_type = "Purchase Receipt"
						voucher_no = purchase_receipts[0]['voucher_no']
						supplier = frappe.db.get_value(voucher_type, voucher_no, "supplier")
					else:
						raise Exception("Multiple purchase receipts found.")
				else:
					raise Exception("Multiple batch numbers found.")
		result = {
			"supplier": supplier,
			"purchase_receipt": voucher_no,
			"item_code": item_code,
			"item_description": item_description,
			"batch_no": batch_no,
			"qty": qty,
			"rate": rate
		}
		serial_batch_bundle.append(result)
		supplier_bundle = defaultdict(list)

		for bundle in serial_batch_bundle:
			supplier = bundle['supplier']
			supplier_bundle[supplier].append(bundle)

		for supplier, bundles in supplier_bundle.items():
			purchase_invoice = frappe.new_doc("Purchase Invoice")
			purchase_invoice.supplier = supplier
			
			for bundle in bundles:
				item_code = bundle['item_code']
				description = bundle['item_description']
				batch_no = bundle['batch_no']
				qty = bundle['qty']
				rate = bundle['rate']
				purchase_receipt = bundle['purchase_receipt']
				
				purchase_invoice.append("items", {
					"item_code": item_code,
					"description": description,
					"batch_no": batch_no,
					"qty": qty,
					"rate": rate,
					"purchase_receipt": purchase_receipt
				})
			
			purchase_invoice.insert()
			#purchase_invoice.submit()
	return True
