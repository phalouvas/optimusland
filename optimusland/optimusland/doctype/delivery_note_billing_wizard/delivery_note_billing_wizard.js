// Copyright (c) 2025, Optimusland and contributors
// For license information, please see license.txt

frappe.ui.form.on('Delivery Note Billing Wizard', {
	onload: function(frm) {

		frm.set_df_property('unbilled_items_html', 'options', " ");
		frm.set_df_property('invoice_matches_html', 'options', " ");
		frm.set_df_property('assignments_html', 'options', " ");
		frm.set_df_property('processing_results_html', 'options', " ");

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
		
		// Add JavaScript functions for HTML interactions
		function bindSelectAllCheckbox() {
			setTimeout(function() {
				var selectAll = document.getElementById('select-all-items');
				if (selectAll) {
					selectAll.onchange = function() {
						window.select_all_items_toggle(this.checked);
					};
				}
			}, 100);
		}

		window.update_item_selection = function(item_index, selected) {
			frm.call('update_selection', {
				item_index: item_index,
				selected: selected
			}).then(r => {
				if (r.message) {
					// Update the HTML table with backend response
					if (r.message.unbilled_items_html) {
						frm.set_df_property('unbilled_items_html', 'options', r.message.unbilled_items_html);
						frm.refresh_field('unbilled_items_html');
						// Re-bind the select-all checkbox after updating HTML
						setTimeout(function() {
							bindSelectAllCheckbox();
						}, 100);
					}
					// Update totals
					if (r.message.total_selected_items !== undefined) {
						frm.set_value('total_selected_items', r.message.total_selected_items);
						frm.refresh_field('total_selected_items');
					}
					if (r.message.total_selected_amount !== undefined) {
						frm.set_value('total_selected_amount', r.message.total_selected_amount);
						frm.refresh_field('total_selected_amount');
					}
				}
			});
		};
		
		window.select_all_items_toggle = function(select_all) {
			frm.call('select_all_items', {select_all: select_all}).then(r => {
				if (r.message) {
					// Update the HTML table with backend response
					if (r.message.unbilled_items_html) {
						frm.set_df_property('unbilled_items_html', 'options', r.message.unbilled_items_html);
						frm.refresh_field('unbilled_items_html');
						// Re-bind the select-all checkbox after updating HTML
						setTimeout(function() {
							bindSelectAllCheckbox();
						}, 100);
					}
					// Update totals
					if (r.message.total_selected_items !== undefined) {
						frm.set_value('total_selected_items', r.message.total_selected_items);
						frm.refresh_field('total_selected_items');
					}
					if (r.message.total_selected_amount !== undefined) {
						frm.set_value('total_selected_amount', r.message.total_selected_amount);
						frm.refresh_field('total_selected_amount');
					}
				}
			});
		};
		
		// Add CSS for better table styling
		// Bind select-all checkbox after initial table render
		bindSelectAllCheckbox();
		$('head').append(`
			<style>
				.wizard-table {
					font-size: 12px;
				}
				.wizard-table th {
					background-color: #f8f9fa;
					font-weight: bold;
					padding: 8px;
				}
				.wizard-table td {
					padding: 6px 8px;
					vertical-align: middle;
				}
				.table-success {
					background-color: #d4edda !important;
				}
				.table-info {
					background-color: #cce5ff !important;
				}
				.table-warning {
					background-color: #fff2cd !important;
				}
				.table-danger {
					background-color: #f8d7da !important;
				}
				.table-secondary {
					background-color: #e2e3e5 !important;
				}
			</style>
		`);
	},
	
	refresh: function(frm) {

		frm.disable_save();
		
		// Clear existing custom buttons to avoid duplicates
		frm.clear_custom_buttons();
		
		// Add buttons based on current processing status
		switch(frm.doc.processing_status) {
			case 'Draft':
				frm.add_custom_button(__('Load Items'), function() {
					frm.call('load_items').then(r => {
						if (r.message && r.message.status === 'success') {
							frm.set_value('wizard_tab', '1. Load Items');
							if (r.message.unbilled_items_html) {
								frm.set_df_property('unbilled_items_html', 'options', r.message.unbilled_items_html);
								frm.refresh_field('unbilled_items_html');
								setTimeout(function() {
									var selectAll = document.getElementById('select-all-items');
									if (selectAll) {
										selectAll.onchange = function() {
											window.select_all_items_toggle(this.checked);
										};
									}
								}, 100);
							}
							frm.refresh();
						}
					});
				}).addClass("btn-primary");
				break;
			case 'Items Loaded':
				frm.add_custom_button(__('Find Invoice Matches'), function() {
					frm.call('find_invoice_matches').then(r => {
						if (r.message && r.message.status === 'success') {
							frm.set_value('wizard_tab', '2. Find Matches');
							frm.set_df_property('invoice_matches_html', 'options', r.message.invoice_matches_html);
							frm.refresh();
						}
					});
				}).addClass("btn-primary");
				break;
			case 'Matches Found':
				frm.add_custom_button(__('Create Assignments'), function() {
					frm.call('create_assignments').then(r => {
						if (r.message && r.message.status === 'success') {
							frm.set_value('wizard_tab', '3. Create Assignments');
							frm.set_df_property('assignments_html', 'options', r.message.assignments_html);
							frm.refresh();
						}
					});
				}).addClass("btn-primary");
				break;
			case 'Assignments Created':
				frm.add_custom_button(__('Process Assignments'), function() {
					frappe.confirm(
						__('This will update delivery note references in sales invoices. Are you sure?'),
						function() {
							frm.call('process_assignments').then(r => {
								if (r.message && r.message.status === 'success') {
									frm.set_value('wizard_tab', '4. Process Results');
									frm.set_df_property('processing_results_html', 'options', r.message.processing_results_html);
									frm.refresh();
								}
							});
						}
					);
				}).addClass("btn-danger");
				break;
		}
		
		// Show status in page title for virtual doctypes (no dashboard)
		if (frm.doc.processing_status) {
			let status_text = frm.doc.processing_status;
			if (frm.doc.total_items_found) {
				status_text += ` (${frm.doc.total_items_found} items found`;
				if (frm.doc.total_selected_items) {
					status_text += `, ${frm.doc.total_selected_items} selected`;
				}
				status_text += ')';
			}
			
			// Set page title subtitle to show status
			if (frm.page && frm.page.set_title_sub) {
				frm.page.set_title_sub(status_text);
			}
		}
	},
	
	wizard_tab: function(frm) {
		// Refresh to show/hide sections based on tab selection
		frm.refresh();
	},
	
	company: function(frm) {
		// Clear data when company changes
		frm.set_value('processing_status', 'Draft');
		frm.set_value('wizard_tab', '1. Load Items');
		frm.set_value('total_items_found', 0);
		frm.set_value('total_selected_items', 0);
		frm.set_value('total_selected_amount', 0);
		frm.set_value('unbilled_items_data', '');
		frm.set_value('invoice_matches_data', '');
		frm.set_value('assignments_data', '');
		frm.set_value('processing_results_data', '');
		frm.refresh();
	},
	
	customer: function(frm) {
		// Clear data when customer changes
		frm.set_value('processing_status', 'Draft');
		frm.set_value('wizard_tab', '1. Load Items');
		frm.set_value('total_items_found', 0);
		frm.set_value('total_selected_items', 0);
		frm.set_value('total_selected_amount', 0);
		frm.set_value('unbilled_items_data', '');
		frm.set_value('invoice_matches_data', '');
		frm.set_value('assignments_data', '');
		frm.set_value('processing_results_data', '');
	},
	
	from_date: function(frm) {
		// Clear items when date range changes
		if (frm.doc.processing_status !== 'Draft') {
			frm.set_value('processing_status', 'Draft');
			frm.set_value('wizard_tab', '1. Load Items');
			frm.set_value('unbilled_items_data', '');
		}
	},
	
	to_date: function(frm) {
		// Clear items when date range changes
		if (frm.doc.processing_status !== 'Draft') {
			frm.set_value('processing_status', 'Draft');
			frm.set_value('wizard_tab', '1. Load Items');
			frm.set_value('unbilled_items_data', '');
		}
	}
});
