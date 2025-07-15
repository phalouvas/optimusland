# Copyright (c) 2025, Optimusland and contributors
# For license information, please see license.txt

import frappe
from frappe.model.document import Document
from frappe.utils import nowdate, flt, cint, now
from datetime import datetime
import json


class DeliveryNoteBillingWizard(Document):
	def __init__(self, *args, **kwargs):
		super().__init__(*args, **kwargs)
		# Virtual doctype - no database table
		pass

	def load_from_db(self):
		"""Load data for virtual doctype"""
		# This method is called when the document is loaded
		# We'll populate the fields with default values
		if not self.get('company'):
			# Set default company if user has access to only one
			companies = frappe.get_all("Company", pluck="name")
			if len(companies) == 1:
				self.company = companies[0]
		
		if not self.get('from_date'):
			self.from_date = frappe.utils.add_months(nowdate(), -1)
		
		if not self.get('to_date'):
			self.to_date = nowdate()
		
		self.processing_status = "Draft"

	def db_insert(self, *args, **kwargs):
		"""Override to prevent database insert"""
		pass

	def db_update(self, *args, **kwargs):
		"""Override to prevent database update"""
		pass

	def delete(self):
		"""Override to prevent database delete"""
		pass

	@frappe.whitelist()
	def load_unbilled_items(self):
		"""Load unbilled delivery note items based on filters"""
		if not self.company:
			frappe.throw("Company is required")
		
		# Clear existing data
		self.unbilled_items = []
		self.invoice_matches = []
		self.assignments = []
		self.processing_results = []
		
		# Get unbilled items using the same logic as the report
		unbilled_data = self.get_unbilled_delivery_notes()
		
		# Populate unbilled_items table
		for item in unbilled_data:
			if item.get('delivery_note') and item.get('item_code'):  # Skip summary rows
				self.append('unbilled_items', {
					'delivery_note': item.get('delivery_note'),
					'item_code': item.get('item_code'),
					'item_name': item.get('item_name'),
					'qty': item.get('qty'),
					'rate': item.get('rate'),
					'amount': item.get('amount'),
					'uom': item.get('uom'),
					'posting_date': item.get('posting_date'),
					'customer': item.get('customer'),
					'selected': 0,  # Default unselected
					'billing_variance': item.get('billing_variance', 0),
					'actual_billed_qty': item.get('actual_billed_qty', 0),
					'outstanding_qty': item.get('outstanding_qty', 0)
				})
		
		self.update_totals()
		frappe.msgprint(f"Loaded {len(self.unbilled_items)} unbilled items")
		return True

	@frappe.whitelist()
	def find_invoice_matches(self):
		"""Find potential sales invoice matches for selected items"""
		if not self.unbilled_items:
			frappe.throw("Please load unbilled items first")
		
		selected_items = [item for item in self.unbilled_items if item.selected]
		if not selected_items:
			frappe.throw("Please select at least one item to find matches")
		
		self.invoice_matches = []
		
		for item in selected_items:
			# Find potential matches in sales invoices
			matches = self.find_matches_for_item(item)
			for match in matches:
				self.append('invoice_matches', match)
		
		frappe.msgprint(f"Found {len(self.invoice_matches)} potential matches")
		return True

	@frappe.whitelist()
	def create_assignments(self):
		"""Create billing assignments based on matches"""
		if not self.invoice_matches:
			frappe.throw("Please find invoice matches first")
		
		self.assignments = []
		
		# Group matches by delivery note item
		item_matches = {}
		for match in self.invoice_matches:
			key = f"{match.sales_invoice}-{match.item_code}"
			if key not in item_matches:
				item_matches[key] = []
			item_matches[key].append(match)
		
		# Create automatic assignments for high-confidence matches
		for item in self.unbilled_items:
			if not item.selected:
				continue
			
			item_key = f"{item.delivery_note}-{item.item_code}"
			remaining_qty = item.outstanding_qty or item.qty
			
			# Find best matches for this item
			best_matches = self.get_best_matches_for_item(item)
			
			for match in best_matches:
				if remaining_qty <= 0:
					break
				
				assign_qty = min(remaining_qty, match.get('available_qty', 0))
				if assign_qty > 0:
					assignment = {
						'delivery_note_item': item_key,
						'sales_invoice_item': f"{match.get('sales_invoice')}-{match.get('item_code')}",
						'qty_to_assign': assign_qty,
						'rate_variance': abs(flt(item.rate) - flt(match.get('rate', 0))),
						'amount_to_assign': assign_qty * flt(item.rate),
						'assignment_type': 'Automatic' if match.get('compatibility_score', 0) >= 90 else 'Manual',
						'confidence_level': self.get_confidence_level(match.get('compatibility_score', 0)),
						'notes': f"Auto-assigned based on {match.get('status', 'Unknown')} match"
					}
					self.append('assignments', assignment)
					remaining_qty -= assign_qty
		
		frappe.msgprint(f"Created {len(self.assignments)} billing assignments")
		return True

	@frappe.whitelist()
	def process_assignments(self):
		"""Process the billing assignments and update delivery notes"""
		if not self.assignments:
			frappe.throw("No assignments to process")
		
		self.processing_status = "Processing"
		self.processing_results = []
		
		processed_count = 0
		error_count = 0
		
		for assignment in self.assignments:
			try:
				result = self.process_single_assignment(assignment)
				self.append('processing_results', result)
				
				if result.get('status') == 'Success':
					processed_count += 1
				else:
					error_count += 1
			
			except Exception as e:
				error_result = {
					'delivery_note': assignment.get('delivery_note_item', '').split('-')[0],
					'sales_invoice': assignment.get('sales_invoice_item', '').split('-')[0],
					'item_code': assignment.get('delivery_note_item', '').split('-')[1] if '-' in assignment.get('delivery_note_item', '') else '',
					'processed_qty': 0,
					'status': 'Failed',
					'error_message': str(e),
					'process_time': now()
				}
				self.append('processing_results', error_result)
				error_count += 1
		
		self.processing_status = "Completed" if error_count == 0 else "Failed"
		
		frappe.msgprint(f"Processing completed. Success: {processed_count}, Errors: {error_count}")
		return True

	def get_unbilled_delivery_notes(self):
		"""Get unbilled delivery notes using the same logic as the report"""
		conditions = ["dn.company = %(company)s"]
		values = {"company": self.company}
		
		if self.customer:
			conditions.append("dn.customer = %(customer)s")
			values["customer"] = self.customer
		
		if self.from_date:
			conditions.append("dn.posting_date >= %(from_date)s")
			values["from_date"] = self.from_date
		
		if self.to_date:
			conditions.append("dn.posting_date <= %(to_date)s")
			values["to_date"] = self.to_date
		
		conditions_str = " AND ".join(conditions)
		
		query = f"""
			SELECT 
				dn.name as delivery_note,
				dn.posting_date,
				dn.customer,
				dn.customer_name,
				dni.item_code,
				dni.item_name,
				dni.qty,
				dni.rate,
				dni.amount,
				dni.uom,
				dni.billed_amt,
				COALESCE(actual_billed.total_billed_qty, 0) as actual_billed_qty,
				COALESCE(actual_billed.total_billed_amount, 0) as actual_billed_amount,
				(dni.qty - COALESCE(actual_billed.total_billed_qty, 0)) as outstanding_qty,
				(dni.amount - COALESCE(actual_billed.total_billed_amount, 0)) as outstanding_amount,
				(dni.billed_amt - COALESCE(actual_billed.total_billed_amount, 0)) as billing_variance,
				CASE 
					WHEN COALESCE(actual_billed.total_billed_qty, 0) >= dni.qty THEN 'Fully Billed'
					WHEN COALESCE(actual_billed.total_billed_qty, 0) > 0 THEN 'Partially Billed'
					ELSE 'Not Billed'
				END as billing_status
			FROM `tabDelivery Note` dn
			INNER JOIN `tabDelivery Note Item` dni ON dn.name = dni.parent
			LEFT JOIN (
				SELECT 
					sii.delivery_note,
					sii.dn_detail,
					SUM(sii.qty) as total_billed_qty,
					SUM(sii.amount) as total_billed_amount
				FROM `tabSales Invoice Item` sii
				INNER JOIN `tabSales Invoice` si ON sii.parent = si.name
				WHERE si.docstatus = 1 
					AND sii.delivery_note IS NOT NULL 
					AND sii.delivery_note != ''
				GROUP BY sii.delivery_note, sii.dn_detail
			) actual_billed ON dn.name = actual_billed.delivery_note AND dni.name = actual_billed.dn_detail
			WHERE dn.docstatus = 1 
				AND {conditions_str}
				AND (dni.qty - COALESCE(actual_billed.total_billed_qty, 0)) > 0
			ORDER BY dn.posting_date DESC, dn.name, dni.item_code
		"""
		
		return frappe.db.sql(query, values, as_dict=True)

	def find_matches_for_item(self, item):
		"""Find potential sales invoice matches for a delivery note item"""
		# Look for sales invoices with matching item and customer
		query = """
			SELECT 
				si.name as sales_invoice,
				si.posting_date,
				si.customer,
				sii.item_code,
				sii.item_name,
				sii.qty,
				sii.rate,
				sii.amount,
				COALESCE(linked_qty.total_linked, 0) as already_linked_qty,
				(sii.qty - COALESCE(linked_qty.total_linked, 0)) as available_qty
			FROM `tabSales Invoice` si
			INNER JOIN `tabSales Invoice Item` sii ON si.name = sii.parent
			LEFT JOIN (
				SELECT 
					parent,
					item_code,
					SUM(qty) as total_linked
				FROM `tabSales Invoice Item`
				WHERE delivery_note IS NOT NULL AND delivery_note != ''
				GROUP BY parent, item_code
			) linked_qty ON sii.parent = linked_qty.parent AND sii.item_code = linked_qty.item_code
			WHERE si.docstatus = 1
				AND si.company = %(company)s
				AND si.customer = %(customer)s
				AND sii.item_code = %(item_code)s
				AND (sii.qty - COALESCE(linked_qty.total_linked, 0)) > 0
			ORDER BY si.posting_date DESC
		"""
		
		results = frappe.db.sql(query, {
			'company': self.company,
			'customer': item.customer,
			'item_code': item.item_code
		}, as_dict=True)
		
		matches = []
		for result in results:
			# Calculate compatibility score
			score = self.calculate_compatibility_score(item, result)
			status = self.get_match_status(score)
			
			matches.append({
				'sales_invoice': result.sales_invoice,
				'item_code': result.item_code,
				'item_name': result.item_name,
				'available_qty': result.available_qty,
				'rate': result.rate,
				'amount': result.amount,
				'posting_date': result.posting_date,
				'customer': result.customer,
				'already_linked_qty': result.already_linked_qty,
				'compatibility_score': score,
				'status': status
			})
		
		return matches

	def calculate_compatibility_score(self, dn_item, si_item):
		"""Calculate compatibility score between delivery note and sales invoice items"""
		score = 0
		
		# Item code match (40 points)
		if dn_item.item_code == si_item.item_code:
			score += 40
		
		# Customer match (30 points)
		if dn_item.customer == si_item.customer:
			score += 30
		
		# Rate similarity (20 points)
		dn_rate = flt(dn_item.rate)
		si_rate = flt(si_item.rate)
		if dn_rate > 0 and si_rate > 0:
			rate_diff = abs(dn_rate - si_rate) / max(dn_rate, si_rate)
			if rate_diff <= 0.01:  # 1% tolerance
				score += 20
			elif rate_diff <= 0.05:  # 5% tolerance
				score += 15
			elif rate_diff <= 0.10:  # 10% tolerance
				score += 10
		
		# Quantity compatibility (10 points)
		dn_qty = flt(dn_item.outstanding_qty or dn_item.qty)
		si_qty = flt(si_item.available_qty)
		if si_qty >= dn_qty:
			score += 10
		elif si_qty >= dn_qty * 0.8:  # 80% of required qty
			score += 7
		elif si_qty >= dn_qty * 0.5:  # 50% of required qty
			score += 5
		
		return min(score, 100)

	def get_match_status(self, score):
		"""Get match status based on compatibility score"""
		if score >= 90:
			return "Perfect Match"
		elif score >= 75:
			return "Good Match"
		elif score >= 50:
			return "Partial Match"
		else:
			return "Poor Match"

	def get_confidence_level(self, score):
		"""Get confidence level based on compatibility score"""
		if score >= 90:
			return "High"
		elif score >= 70:
			return "Medium"
		else:
			return "Low"

	def get_best_matches_for_item(self, item):
		"""Get best matches for a delivery note item"""
		item_key = f"{item.delivery_note}-{item.item_code}"
		matches = [m for m in self.invoice_matches if m.item_code == item.item_code]
		
		# Sort by compatibility score descending
		matches.sort(key=lambda x: x.get('compatibility_score', 0), reverse=True)
		
		return matches

	def process_single_assignment(self, assignment):
		"""Process a single billing assignment"""
		try:
			# Parse the assignment details
			dn_item_parts = assignment.delivery_note_item.split('-', 1)
			si_item_parts = assignment.sales_invoice_item.split('-', 1)
			
			delivery_note = dn_item_parts[0] if len(dn_item_parts) > 0 else ''
			sales_invoice = si_item_parts[0] if len(si_item_parts) > 0 else ''
			item_code = dn_item_parts[1] if len(dn_item_parts) > 1 else ''
			
			# Get delivery note item detail
			dn_item = frappe.db.get_value("Delivery Note Item", {
				"parent": delivery_note,
				"item_code": item_code
			}, ["name", "qty", "rate"], as_dict=True)
			
			if not dn_item:
				raise Exception(f"Delivery Note Item not found for {delivery_note} - {item_code}")
			
			# Get sales invoice item detail
			si_item = frappe.db.get_value("Sales Invoice Item", {
				"parent": sales_invoice,
				"item_code": item_code,
				"delivery_note": ["in", ["", None]]  # Not already linked
			}, ["name", "qty", "rate"], as_dict=True)
			
			if not si_item:
				raise Exception(f"Available Sales Invoice Item not found for {sales_invoice} - {item_code}")
			
			# Update the sales invoice item to link to delivery note
			frappe.db.set_value("Sales Invoice Item", si_item.name, {
				"delivery_note": delivery_note,
				"dn_detail": dn_item.name
			})
			
			# Create success result
			result = {
				'delivery_note': delivery_note,
				'sales_invoice': sales_invoice,
				'item_code': item_code,
				'processed_qty': assignment.qty_to_assign,
				'status': 'Success',
				'success_message': f"Successfully linked {assignment.qty_to_assign} qty",
				'process_time': now()
			}
			
			frappe.db.commit()
			return result
			
		except Exception as e:
			frappe.db.rollback()
			raise e

	def update_totals(self):
		"""Update summary totals"""
		selected_items = [item for item in self.unbilled_items if item.selected]
		self.total_selected_items = len(selected_items)
		self.total_selected_amount = sum(flt(item.amount) for item in selected_items)

	@frappe.whitelist()
	def update_selection(self):
		"""Update totals when selection changes"""
		self.update_totals()
		return True
