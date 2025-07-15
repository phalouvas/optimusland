# Copyright (c) 2025, Optimusland and contributors
# For license information, please see license.txt

import frappe
from frappe.model.document import Document
from frappe.utils import nowdate, flt, cint, now
import json


class DeliveryNoteBillingWizard(Document):
	def __init__(self, *args, **kwargs):
		super().__init__(*args, **kwargs)
		# Initialize table fieldnames for virtual doctype
		self._table_fieldnames = []
		
		# Set required attributes for virtual doctype
		if not hasattr(self, 'modified'):
			self.modified = now()
		if not hasattr(self, '_original_modified'):
			self._original_modified = now()
		if not hasattr(self, 'creation'):
			self.creation = now()
		if not hasattr(self, 'owner'):
			self.owner = frappe.session.user
		if not hasattr(self, 'modified_by'):
			self.modified_by = frappe.session.user

	@staticmethod
	def get_doc(doctype, name=None):
		"""Return a default in-memory document for new virtual doctype forms."""
		if name and name.startswith('new-'):
			# Create a new in-memory document
			doc = frappe.new_doc(doctype)
			doc.name = name
			return doc
		else:
			# For single doctypes, always return the singleton instance
			doc = frappe.new_doc(doctype)
			doc.name = doctype
			return doc

	def db_insert(self, *args, **kwargs):
		pass

	# Override load_from_db to prevent DB access
	def load_from_db(self):
		"""Do nothing for virtual doctype."""
		return
	
	def db_update(self):
		pass

	@staticmethod
	def get_list(args):
		pass

	@staticmethod
	def get_count(args):
		pass

	@staticmethod
	def get_stats(args):
		pass

	def check_if_latest(self):
		"""Override to prevent version check for virtual doctype"""
		pass

	def delete(self):
		"""Override to prevent database delete"""
		pass

	@property
	def unbilled_items(self):
		"""Get unbilled items from JSON data"""
		if self.unbilled_items_data:
			return json.loads(self.unbilled_items_data)
		return []

	@unbilled_items.setter
	def unbilled_items(self, value):
		"""Set unbilled items as JSON data"""
		self.unbilled_items_data = json.dumps(value) if value else ""

	@property
	def invoice_matches(self):
		"""Get invoice matches from JSON data"""
		if self.invoice_matches_data:
			return json.loads(self.invoice_matches_data)
		return []

	@invoice_matches.setter
	def invoice_matches(self, value):
		"""Set invoice matches as JSON data"""
		self.invoice_matches_data = json.dumps(value) if value else ""

	@property
	def assignments(self):
		"""Get assignments from JSON data"""
		if self.assignments_data:
			return json.loads(self.assignments_data)
		return []

	@assignments.setter
	def assignments(self, value):
		"""Set assignments as JSON data"""
		self.assignments_data = json.dumps(value) if value else ""

	@property
	def processing_results(self):
		"""Get processing results from JSON data"""
		if self.processing_results_data:
			return json.loads(self.processing_results_data)
		return []

	@processing_results.setter
	def processing_results(self, value):
		"""Set processing results as JSON data"""
		self.processing_results_data = json.dumps(value) if value else ""

	@frappe.whitelist()
	def load_unbilled_items(self):
		"""Load unbilled delivery note items based on filters"""
		if not self.company:
			frappe.throw("Company is required")
		
		# Get unbilled items using the same logic as the report
		unbilled_data = self.get_unbilled_delivery_notes()
		
		# Store data as JSON
		items = []
		for item in unbilled_data:
			if item.get('delivery_note') and item.get('item_code'):  # Skip summary rows
				items.append({
					'delivery_note': item.get('delivery_note'),
					'item_code': item.get('item_code'),
					'item_name': item.get('item_name'),
					'qty': item.get('qty'),
					'rate': item.get('rate'),
					'amount': item.get('amount'),
					'uom': item.get('uom'),
					'posting_date': str(item.get('posting_date')) if item.get('posting_date') else '',
					'customer': item.get('customer'),
					'selected': False,  # Default unselected
					'billing_variance': item.get('billing_variance', 0),
					'actual_billed_qty': item.get('actual_billed_qty', 0),
					'outstanding_qty': item.get('outstanding_qty', 0)
				})
		
		self.unbilled_items = items
		self.total_items_found = len(items)
		self.processing_status = "Items Loaded"
		self.wizard_tab = "1. Load Items"
		self.update_totals()
		html_displays = self.update_html_displays()
		
		frappe.msgprint(f"Loaded {len(items)} unbilled items")
		return {**{"status": "success", "count": len(items)}, **html_displays}

	@frappe.whitelist()
	def find_invoice_matches(self):
		"""Find potential sales invoice matches for selected items"""
		items = self.unbilled_items
		if not items:
			frappe.throw("Please load unbilled items first")
		
		selected_items = [item for item in items if item.get('selected')]
		if not selected_items:
			frappe.throw("Please select at least one item to find matches")
		
		matches = []
		for item in selected_items:
			item_matches = self.find_matches_for_item(item)
			matches.extend(item_matches)
		
		self.invoice_matches = matches
		self.processing_status = "Matches Found"
		self.wizard_tab = "2. Find Matches"
		html_displays = self.update_html_displays()
		
		frappe.msgprint(f"Found {len(matches)} potential matches")
		return {**{"status": "success", "count": len(matches)}, **html_displays}

	@frappe.whitelist()
	def create_assignments(self):
		"""Create billing assignments based on matches"""
		matches = self.invoice_matches
		if not matches:
			frappe.throw("Please find invoice matches first")
		
		assignments = []
		items = self.unbilled_items
		
		# Create automatic assignments for high-confidence matches
		for item in items:
			if not item.get('selected'):
				continue
			
			remaining_qty = item.get('outstanding_qty') or item.get('qty', 0)
			item_key = f"{item['delivery_note']}-{item['item_code']}"
			
			# Find best matches for this item
			best_matches = [m for m in matches if m.get('item_code') == item['item_code']]
			best_matches.sort(key=lambda x: x.get('compatibility_score', 0), reverse=True)
			
			for match in best_matches:
				if remaining_qty <= 0:
					break
				
				assign_qty = min(remaining_qty, match.get('available_qty', 0))
				if assign_qty > 0:
					assignment = {
						'delivery_note_item': item_key,
						'sales_invoice_item': f"{match.get('sales_invoice')}-{match.get('item_code')}",
						'qty_to_assign': assign_qty,
						'rate_variance': abs(flt(item.get('rate', 0)) - flt(match.get('rate', 0))),
						'amount_to_assign': assign_qty * flt(item.get('rate', 0)),
						'assignment_type': 'Automatic' if match.get('compatibility_score', 0) >= 90 else 'Manual',
						'confidence_level': self.get_confidence_level(match.get('compatibility_score', 0)),
						'notes': f"Auto-assigned based on {match.get('status', 'Unknown')} match"
					}
					assignments.append(assignment)
					remaining_qty -= assign_qty
		
		self.assignments = assignments
		self.processing_status = "Assignments Created"
		self.wizard_tab = "3. Create Assignments"
		html_displays = self.update_html_displays()
		
		frappe.msgprint(f"Created {len(assignments)} billing assignments")
		return {**{"status": "success", "count": len(assignments)}, **html_displays}

	@frappe.whitelist()
	def process_assignments(self):
		"""Process the billing assignments and update delivery notes"""
		assignments = self.assignments
		if not assignments:
			frappe.throw("No assignments to process")
		
		self.processing_status = "Processing"
		results = []
		
		processed_count = 0
		error_count = 0
		
		for assignment in assignments:
			try:
				result = self.process_single_assignment(assignment)
				results.append(result)
				
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
				results.append(error_result)
				error_count += 1
		
		self.processing_results = results
		self.processing_status = "Completed" if error_count == 0 else "Failed"
		self.wizard_tab = "4. Process Results"
		html_displays = self.update_html_displays()
		
		frappe.msgprint(f"Processing completed. Success: {processed_count}, Errors: {error_count}")
		return {**{"status": "success", "processed": processed_count, "errors": error_count}, **html_displays}

	@frappe.whitelist()
	def update_selection(self, item_index=None, selected=None):
		"""Update item selection status (fix type conversion and always refresh HTML)"""
		# Convert types from JS (which may send strings)
		try:
			idx = int(item_index) if item_index is not None else None
			# Accept true/false, 'true'/'false', 1/0
			sel = selected in (True, 'true', 'True', 1, '1')
		except Exception:
			return {"status": "error", "message": "Invalid arguments"}

		items = self.unbilled_items
		html_displays = {}
		if idx is not None and 0 <= idx < len(items):
			items[idx]['selected'] = sel
			self.unbilled_items = items
			self.update_totals()
			html_displays = self.update_html_displays()
		else:
			html_displays = self.update_html_displays()
			return {**{"status": "error", "message": "Invalid item index"}, **html_displays}
		return {**{"status": "success"}, **html_displays}

	@frappe.whitelist()
	def select_all_items(self, select_all=True):
		"""Select or deselect all items (fix type conversion from JS)"""
		# Accept true/false, 'true'/'false', 1/0
		sel = select_all in (True, 'true', 'True', 1, '1')
		items = self.unbilled_items
		for item in items:
			item['selected'] = sel
		self.unbilled_items = items
		self.update_totals()
		html_displays = self.update_html_displays()
		return {**{"status": "success"}, **html_displays}

	def update_totals(self):
		"""Update summary totals"""
		items = self.unbilled_items
		selected_items = [item for item in items if item.get('selected')]
		self.total_selected_items = len(selected_items)
		self.total_selected_amount = sum(flt(item.get('amount', 0)) for item in selected_items)

	def update_html_displays(self):
		"""Update HTML displays for all tables"""
		try:
			self.unbilled_items_html = self.render_unbilled_items_table()
			self.invoice_matches_html = self.render_invoice_matches_table()
			self.assignments_html = self.render_assignments_table()
			self.processing_results_html = self.render_processing_results_table()
		except Exception:
			# If there's an error during HTML rendering, set default messages
			self.unbilled_items_html = "<p>Click 'Load Unbilled Items' to begin.</p>"
			self.invoice_matches_html = "<p>No matches found yet.</p>"
			self.assignments_html = "<p>No assignments created yet.</p>"
			self.processing_results_html = "<p>No processing results yet.</p>"

		return {
			'status': 'success',
			'unbilled_items_html': self.unbilled_items_html,
			'invoice_matches_html': self.invoice_matches_html,
			'assignments_html': self.assignments_html,
			'processing_results_html': self.processing_results_html,
			'total_selected_items': getattr(self, 'total_selected_items', 0),
			'total_selected_amount': getattr(self, 'total_selected_amount', 0)
		}

	def render_unbilled_items_table(self):
		"""Render unbilled items as HTML table"""
		items = self.unbilled_items
		if not items:
			return "<p>No items loaded. Click 'Load Unbilled Items' to begin.</p>"
		
		# Check if all items are selected for select-all checkbox state
		selected_items = [item for item in items if item.get('selected')]
		all_selected = len(selected_items) == len(items) and len(items) > 0
		select_all_checked = "checked" if all_selected else ""
		
		html = f"""
		<div class="table-responsive">
			<table class="table table-bordered table-striped">
				<thead>
					<tr>
						<th><input type="checkbox" id="select-all-items" {select_all_checked}></th>
						<th>Delivery Note</th>
						<th>Item Code</th>
						<th>Item Name</th>
						<th>Qty</th>
						<th>Rate</th>
						<th>Amount</th>
						<th>Outstanding Qty</th>
						<th>Billing Variance</th>
					</tr>
				</thead>
				<tbody>
		"""
		
		for i, item in enumerate(items):
			variance_class = ""
			if abs(flt(item.get('billing_variance', 0))) > 0:
				variance_class = "table-warning"
			
			checked = "checked" if item.get('selected') else ""
			
			html += f"""
				<tr class="{variance_class}">
					<td><input type="checkbox" {checked} onchange="update_item_selection({i}, this.checked)"></td>
					<td>{item.get('delivery_note', '')}</td>
					<td>{item.get('item_code', '')}</td>
					<td>{item.get('item_name', '')}</td>
					<td>{item.get('qty', 0)}</td>
					<td>{frappe.format(item.get('rate', 0), {'fieldtype': 'Currency'})}</td>
					<td>{frappe.format(item.get('amount', 0), {'fieldtype': 'Currency'})}</td>
					<td>{item.get('outstanding_qty', 0)}</td>
					<td>{frappe.format(item.get('billing_variance', 0), {'fieldtype': 'Currency'})}</td>
				</tr>
			"""
		
		html += """
				</tbody>
			</table>
		</div>
		"""
		
		return html

	def render_invoice_matches_table(self):
		"""Render invoice matches as HTML table"""
		matches = self.invoice_matches
		if not matches:
			return "<p>No matches found. Select items and click 'Find Invoice Matches'.</p>"
		
		html = """
		<div class="table-responsive">
			<table class="table table-bordered table-striped">
				<thead>
					<tr>
						<th>Sales Invoice</th>
						<th>Item Code</th>
						<th>Available Qty</th>
						<th>Rate</th>
						<th>Compatibility Score</th>
						<th>Match Status</th>
					</tr>
				</thead>
				<tbody>
		"""
		
		for match in matches:
			status_class = ""
			if match.get('status') == 'Perfect Match':
				status_class = "table-success"
			elif match.get('status') == 'Good Match':
				status_class = "table-info"
			elif match.get('status') == 'Partial Match':
				status_class = "table-warning"
			else:
				status_class = "table-danger"
			
			html += f"""
				<tr class="{status_class}">
					<td>{match.get('sales_invoice', '')}</td>
					<td>{match.get('item_code', '')}</td>
					<td>{match.get('available_qty', 0)}</td>
					<td>{frappe.format(match.get('rate', 0), {'fieldtype': 'Currency'})}</td>
					<td>{match.get('compatibility_score', 0)}%</td>
					<td>{match.get('status', '')}</td>
				</tr>
			"""
		
		html += """
				</tbody>
			</table>
		</div>
		"""
		
		return html

	def render_assignments_table(self):
		"""Render assignments as HTML table"""
		assignments = self.assignments
		if not assignments:
			return "<p>No assignments created. Create assignments from matches.</p>"
		
		html = """
		<div class="table-responsive">
			<table class="table table-bordered table-striped">
				<thead>
					<tr>
						<th>DN Item</th>
						<th>SI Item</th>
						<th>Qty to Assign</th>
						<th>Amount</th>
						<th>Type</th>
						<th>Confidence</th>
						<th>Notes</th>
					</tr>
				</thead>
				<tbody>
		"""
		
		for assignment in assignments:
			confidence_class = ""
			if assignment.get('confidence_level') == 'High':
				confidence_class = "table-success"
			elif assignment.get('confidence_level') == 'Medium':
				confidence_class = "table-warning"
			else:
				confidence_class = "table-danger"
			
			html += f"""
				<tr class="{confidence_class}">
					<td>{assignment.get('delivery_note_item', '')}</td>
					<td>{assignment.get('sales_invoice_item', '')}</td>
					<td>{assignment.get('qty_to_assign', 0)}</td>
					<td>{frappe.format(assignment.get('amount_to_assign', 0), {'fieldtype': 'Currency'})}</td>
					<td>{assignment.get('assignment_type', '')}</td>
					<td>{assignment.get('confidence_level', '')}</td>
					<td>{assignment.get('notes', '')}</td>
				</tr>
			"""
		
		html += """
				</tbody>
			</table>
		</div>
		"""
		
		return html

	def render_processing_results_table(self):
		"""Render processing results as HTML table"""
		results = self.processing_results
		if not results:
			return "<p>No processing results yet. Process assignments to see results.</p>"
		
		html = """
		<div class="table-responsive">
			<table class="table table-bordered table-striped">
				<thead>
					<tr>
						<th>Delivery Note</th>
						<th>Sales Invoice</th>
						<th>Item Code</th>
						<th>Processed Qty</th>
						<th>Status</th>
						<th>Message</th>
						<th>Process Time</th>
					</tr>
				</thead>
				<tbody>
		"""
		
		for result in results:
			status_class = ""
			if result.get('status') == 'Success':
				status_class = "table-success"
			elif result.get('status') == 'Failed':
				status_class = "table-danger"
			elif result.get('status') == 'Warning':
				status_class = "table-warning"
			else:
				status_class = "table-secondary"
			
			message = result.get('success_message') or result.get('error_message', '')
			
			html += f"""
				<tr class="{status_class}">
					<td>{result.get('delivery_note', '')}</td>
					<td>{result.get('sales_invoice', '')}</td>
					<td>{result.get('item_code', '')}</td>
					<td>{result.get('processed_qty', 0)}</td>
					<td>{result.get('status', '')}</td>
					<td>{message}</td>
					<td>{result.get('process_time', '')}</td>
				</tr>
			"""
		
		html += """
				</tbody>
			</table>
		</div>
		"""
		
		return html

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
			'customer': item.get('customer'),
			'item_code': item.get('item_code')
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
				'posting_date': str(result.posting_date) if result.posting_date else '',
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
		if dn_item.get('item_code') == si_item.get('item_code'):
			score += 40
		
		# Customer match (30 points)
		if dn_item.get('customer') == si_item.get('customer'):
			score += 30
		
		# Rate similarity (20 points)
		dn_rate = flt(dn_item.get('rate', 0))
		si_rate = flt(si_item.get('rate', 0))
		if dn_rate > 0 and si_rate > 0:
			rate_diff = abs(dn_rate - si_rate) / max(dn_rate, si_rate)
			if rate_diff <= 0.01:  # 1% tolerance
				score += 20
			elif rate_diff <= 0.05:  # 5% tolerance
				score += 15
			elif rate_diff <= 0.10:  # 10% tolerance
				score += 10
		
		# Quantity compatibility (10 points)
		dn_qty = flt(dn_item.get('outstanding_qty') or dn_item.get('qty', 0))
		si_qty = flt(si_item.get('available_qty', 0))
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

	def process_single_assignment(self, assignment):
		"""Process a single billing assignment"""
		try:
			# Parse the assignment details
			dn_item_parts = assignment.get('delivery_note_item', '').split('-', 1)
			si_item_parts = assignment.get('sales_invoice_item', '').split('-', 1)
			
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
				'processed_qty': assignment.get('qty_to_assign', 0),
				'status': 'Success',
				'success_message': f"Successfully linked {assignment.get('qty_to_assign', 0)} qty",
				'process_time': now()
			}
			
			frappe.db.commit()
			return result
			
		except Exception as e:
			frappe.db.rollback()
			raise e
