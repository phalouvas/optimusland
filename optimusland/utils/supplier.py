import frappe
from frappe import _, qb, throw

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