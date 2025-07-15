// Copyright (c) 2025, Optimusland and contributors
// For license information, please see license.txt

frappe.ui.form.on('Delivery Note Billing Wizard', {
	onload: function(frm) {
		// Set default filters if not set
		if (!frm.doc.company && frappe.defaults.get_user_default("Company")) {
			frm.set_value('company', frappe.defaults.get_user_default("Company"));
		}
		
		if (!frm.doc.from_date) {
			frm.set_value('from_date', frappe.datetime.add_months(frappe.datetime.get_today(), -1));
		}
		
		if (!frm.doc.to_date) {
			frm.set_value('to_date', frappe.datetime.get_today());
		}
		
		// Add custom buttons
		frm.add_custom_button(__('Load Unbilled Items'), function() {
			frm.call('load_unbilled_items').then(r => {
				frm.refresh();
			});
		}, __('Actions'));
		
		frm.add_custom_button(__('Find Matches'), function() {
			frm.call('find_invoice_matches').then(r => {
				frm.refresh();
			});
		}, __('Actions'));
		
		frm.add_custom_button(__('Create Assignments'), function() {
			frm.call('create_assignments').then(r => {
				frm.refresh();
			});
		}, __('Actions'));
		
		frm.add_custom_button(__('Process Assignments'), function() {
			frappe.confirm(
				__('This will update delivery note references in sales invoices. Are you sure?'),
				function() {
					frm.call('process_assignments').then(r => {
						frm.refresh();
					});
				}
			);
		}, __('Actions'));
		
		// Add select all / deselect all buttons
		frm.add_custom_button(__('Select All Items'), function() {
			frm.doc.unbilled_items.forEach(item => {
				item.selected = 1;
			});
			frm.refresh_field('unbilled_items');
			frm.call('update_selection');
		}, __('Selection'));
		
		frm.add_custom_button(__('Deselect All Items'), function() {
			frm.doc.unbilled_items.forEach(item => {
				item.selected = 0;
			});
			frm.refresh_field('unbilled_items');
			frm.call('update_selection');
		}, __('Selection'));
		
		// Add smart selection buttons
		frm.add_custom_button(__('Select High Variance'), function() {
			frm.doc.unbilled_items.forEach(item => {
				item.selected = Math.abs(item.billing_variance || 0) > 0 ? 1 : 0;
			});
			frm.refresh_field('unbilled_items');
			frm.call('update_selection');
		}, __('Smart Selection'));
		
		frm.add_custom_button(__('Select Perfect Matches'), function() {
			// This would require checking against matches - simplified for now
			frappe.msgprint(__('Please use Find Matches first, then manually select based on match quality'));
		}, __('Smart Selection'));
	},
	
	refresh: function(frm) {
		// Update button states based on data
		frm.page.btn_secondary.find('.btn-default').removeClass('btn-primary');
		
		if (frm.doc.unbilled_items && frm.doc.unbilled_items.length > 0) {
			frm.page.btn_secondary.find('.btn-default:contains("Find Matches")').addClass('btn-primary');
		}
		
		if (frm.doc.invoice_matches && frm.doc.invoice_matches.length > 0) {
			frm.page.btn_secondary.find('.btn-default:contains("Create Assignments")').addClass('btn-primary');
		}
		
		if (frm.doc.assignments && frm.doc.assignments.length > 0) {
			frm.page.btn_secondary.find('.btn-default:contains("Process Assignments")').addClass('btn-primary');
		}
		
		// Update status indicator
		if (frm.doc.processing_status) {
			let indicator_class = 'blue';
			switch(frm.doc.processing_status) {
				case 'Completed':
					indicator_class = 'green';
					break;
				case 'Failed':
					indicator_class = 'red';
					break;
				case 'Processing':
					indicator_class = 'orange';
					break;
			}
			frm.dashboard.set_indicator(__(frm.doc.processing_status), indicator_class);
		}
	},
	
	company: function(frm) {
		// Clear data when company changes
		frm.set_value('unbilled_items', []);
		frm.set_value('invoice_matches', []);
		frm.set_value('assignments', []);
		frm.set_value('processing_results', []);
		frm.call('update_selection');
	},
	
	customer: function(frm) {
		// Clear data when customer changes
		frm.set_value('unbilled_items', []);
		frm.set_value('invoice_matches', []);
		frm.set_value('assignments', []);
		frm.set_value('processing_results', []);
	},
	
	from_date: function(frm) {
		// Clear data when date range changes
		frm.set_value('unbilled_items', []);
		frm.set_value('invoice_matches', []);
		frm.set_value('assignments', []);
		frm.set_value('processing_results', []);
	},
	
	to_date: function(frm) {
		// Clear data when date range changes
		frm.set_value('unbilled_items', []);
		frm.set_value('invoice_matches', []);
		frm.set_value('assignments', []);
		frm.set_value('processing_results', []);
	}
});

// Child table events
frappe.ui.form.on('Delivery Note Billing Wizard Item', {
	selected: function(frm, cdt, cdn) {
		// Update totals when selection changes
		frm.call('update_selection');
	},
	
	unbilled_items_add: function(frm, cdt, cdn) {
		frm.call('update_selection');
	},
	
	unbilled_items_remove: function(frm, cdt, cdn) {
		frm.call('update_selection');
	}
});

frappe.ui.form.on('Delivery Note Billing Wizard Assignment', {
	qty_to_assign: function(frm, cdt, cdn) {
		let row = locals[cdt][cdn];
		// Recalculate amount when quantity changes
		let dn_item_key = row.delivery_note_item;
		let dn_item = frm.doc.unbilled_items.find(item => 
			`${item.delivery_note}-${item.item_code}` === dn_item_key
		);
		
		if (dn_item) {
			frappe.model.set_value(cdt, cdn, 'amount_to_assign', 
				row.qty_to_assign * dn_item.rate);
		}
	}
});

// Custom formatting for child tables
frappe.ui.form.on('Delivery Note Billing Wizard Item', {
	form_render: function(frm, cdt, cdn) {
		let row = locals[cdt][cdn];
		let grid_row = frm.fields_dict.unbilled_items.grid.get_row(cdn);
		
		// Color code based on billing status
		if (row.billing_variance && Math.abs(row.billing_variance) > 0) {
			grid_row.wrapper.css('background-color', '#fff2cd'); // Light yellow for variance
		}
		
		if (row.outstanding_qty && row.outstanding_qty <= 0) {
			grid_row.wrapper.css('background-color', '#d4edda'); // Light green for fully billed
		}
	}
});

frappe.ui.form.on('Delivery Note Billing Wizard Match', {
	form_render: function(frm, cdt, cdn) {
		let row = locals[cdt][cdn];
		let grid_row = frm.fields_dict.invoice_matches.grid.get_row(cdn);
		
		// Color code based on match quality
		switch(row.status) {
			case 'Perfect Match':
				grid_row.wrapper.css('background-color', '#d4edda'); // Green
				break;
			case 'Good Match':
				grid_row.wrapper.css('background-color', '#cce5ff'); // Light blue
				break;
			case 'Partial Match':
				grid_row.wrapper.css('background-color', '#fff2cd'); // Yellow
				break;
			case 'Poor Match':
				grid_row.wrapper.css('background-color', '#f8d7da'); // Light red
				break;
		}
	}
});

frappe.ui.form.on('Delivery Note Billing Wizard Result', {
	form_render: function(frm, cdt, cdn) {
		let row = locals[cdt][cdn];
		let grid_row = frm.fields_dict.processing_results.grid.get_row(cdn);
		
		// Color code based on processing status
		switch(row.status) {
			case 'Success':
				grid_row.wrapper.css('background-color', '#d4edda'); // Green
				break;
			case 'Failed':
				grid_row.wrapper.css('background-color', '#f8d7da'); // Red
				break;
			case 'Warning':
				grid_row.wrapper.css('background-color', '#fff2cd'); // Yellow
				break;
			case 'Skipped':
				grid_row.wrapper.css('background-color', '#e2e3e5'); // Gray
				break;
		}
	}
});
