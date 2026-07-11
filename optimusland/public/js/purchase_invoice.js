
frappe.ui.form.on("Purchase Invoice", {
	refresh: function(frm) {        
		// Only if a new Purchase Invoice is being created
        if (frm.doc.__islocal) {
            frappe.msgprint("<p>This is a <b>Purchase Invoice</b>.</p><p>Rememeber to choose the correct <b>Naming Series</b>.</p>");            

            // Get element with id "page-Purchase Invoice" and add a class to it
            var page = document.getElementById("page-Purchase Invoice");
            page.classList.add("bg-warning");
        } else {
            var page = document.getElementById("page-Purchase Invoice");
            if (page) {
                page.classList.remove("bg-warning");
            }
        }

        // "Calculate Grower Price" button on new PIs
        if (frm.doc.__islocal && frm.doc.supplier) {
            frm.add_custom_button(__('Calculate Grower Price'), function() {
                _show_grower_calculator(frm);
            });
        }
	},
});

// ── Show Grower Price Calculator Dialog ─────────────────────────────

let _selected_weight_slip = null;
let _margin_pct = null;
let _unpaid_batches = [];

function _show_grower_calculator(frm) {
    // Step 1: Select Weight Slip
    _show_weight_slip_selector(frm);
}

function _show_weight_slip_selector(frm) {
    let d = new frappe.ui.Dialog({
        title: __('Grower Price Calculator — Step 1'),
        fields: [
            {
                label: __('Weight Slip'),
                fieldname: 'weight_slip',
                fieldtype: 'Link',
                options: 'Weight Slip',
                reqd: 1,
                description: __('Select the Weight Slip to pay. One PI = one Weight Slip.'),
                get_query: function() {
                    return {
                        filters: {
                            'supplier': frm.doc.supplier
                        }
                    };
                }
            }
        ],
        primary_action_label: __('Next: Select Batches'),
        primary_action: function(values) {
            _selected_weight_slip = values.weight_slip;
            d.hide();
            _show_batch_selector(frm);
        }
    });
    
    // Pre-select if custom_weight_slip is already set
    if (frm.doc.custom_weight_slip) {
        d.set_value('weight_slip', frm.doc.custom_weight_slip);
    }
    
    d.show();
}

function _show_batch_selector(frm) {
    frappe.call({
        method: 'optimusland.utils.grower_calculator.get_weight_slip_unpaid_batches',
        args: {
            supplier: frm.doc.supplier,
            weight_slip: _selected_weight_slip
        },
        callback: function(r) {
            _unpaid_batches = r.message || [];
            
            if (_unpaid_batches.length === 0) {
                frappe.msgprint({
                    message: __('No unpaid batches found for this Weight Slip. All batches may already have Purchase Invoices.'),
                    title: __('All Paid'),
                    indicator: 'green'
                });
                return;
            }

            // Step 3: Show calculator with editable prices
            _show_calculator(frm);
        }
    });
}

function _show_calculator(frm) {
    let margin_pct = 6; // default
    let html = _build_calculator_html(_unpaid_batches, margin_pct);

    let d = new frappe.ui.Dialog({
        title: __('Grower Price Calculator — Weight Slip: ' + _selected_weight_slip),
        fields: [
            {
                fieldname: 'html_table',
                fieldtype: 'HTML',
                options: html
            },
            {
                fieldname: 'margin_pct',
                fieldtype: 'Float',
                label: __('Target Margin (%)'),
                default: margin_pct,
                description: __('Adjust margin and click Recalculate. Higher margin = lower grower price.')
            }
        ],
        primary_action_label: __('Create Purchase Invoice'),
        primary_action: function(values) {
            _margin_pct = values.margin_pct;
            _create_pi(frm, d);
        }
    });

    // Add Recalculate button
    d.set_secondary_action_label(__('Recalculate'));
    d.set_secondary_action(function() {
        let new_margin = d.get_value('margin_pct') || 6;
        _recalculate_and_refresh(d, new_margin);
    });

    d.show();
}

function _build_calculator_html(batches, margin_pct) {
    let rows = '';
    batches.forEach(function(b, idx) {
        // Recalculate with current margin
        let margin_amount = b.selling_rate * (margin_pct / 100);
        let recommended = Math.max(b.selling_rate - margin_amount - 0.08 - 0.02, 0).toFixed(3);
        let total = (recommended * b.qty).toFixed(2);

        rows += `<tr>
            <td>${b.batch_no}</td>
            <td>${b.item_code}</td>
            <td>${b.sales_invoice}</td>
            <td>${parseFloat(b.qty).toFixed(0)}</td>
            <td>€${parseFloat(b.selling_rate).toFixed(3)}</td>
            <td><b>€${recommended}</b></td>
            <td><input type="number" step="0.001" class="form-control grower-price-input"
                data-idx="${idx}" value="${recommended}" style="width:100px"></td>
            <td class="grower-total" data-idx="${idx}">€${total}</td>
            <td class="grower-diff" data-idx="${idx}">€0.000</td>
        </tr>`;
    });

    return `
        <p><strong>Supplier:</strong> ${frappe.user_info(frappe.boot.user).full_name || ''}
        <strong>Weight Slip:</strong> ${_selected_weight_slip}</p>
        <table class="table table-bordered table-condensed" id="grower-calc-table">
            <thead>
                <tr>
                    <th>Batch</th>
                    <th>Item</th>
                    <th>SI#</th>
                    <th>Qty</th>
                    <th>Selling</th>
                    <th>Formula</th>
                    <th>You Pay (€/kg)</th>
                    <th>Total</th>
                    <th>Diff</th>
                </tr>
            </thead>
            <tbody>
                ${rows}
            </tbody>
            <tfoot>
                <tr>
                    <td colspan="8"><strong>Total to pay:</strong></td>
                    <td id="grower-grand-total"><strong>€--</strong></td>
                </tr>
            </tfoot>
        </table>
        <p class="text-muted">Edit values in the <strong>You Pay</strong> column to override. Diff tracks formula vs. actual.</p>
    `;
}

function _recalculate_and_refresh(d, new_margin) {
    let html = _build_calculator_html(_unpaid_batches, new_margin);
    d.set_df_property('html_table', 'options', html);
}

function _create_pi(frm, dialog) {
    // Collect line items from the editable table
    let line_items = [];
    let inputs = document.querySelectorAll('.grower-price-input');
    inputs.forEach(function(input) {
        let idx = parseInt(input.dataset.idx);
        let batch = _unpaid_batches[idx];
        if (batch) {
            let rate = parseFloat(input.value) || 0;
            line_items.push({
                batch_no: batch.batch_no,
                item_code: batch.item_code,
                qty: batch.qty,
                rate: rate,
                amount: rate * batch.qty
            });
        }
    });

    if (line_items.length === 0) {
        frappe.msgprint({ message: __('No line items to create PI.'), title: __('Error'), indicator: 'red' });
        return;
    }

    dialog.hide();

    frappe.call({
        method: 'optimusland.utils.grower_calculator.create_purchase_invoice',
        args: {
            supplier: frm.doc.supplier,
            weight_slip: _selected_weight_slip,
            line_items: line_items,
            margin_pct: _margin_pct
        },
        callback: function(r) {
            if (r.message) {
                frappe.show_alert({
                    message: __('Purchase Invoice {0} created successfully.', [r.message]),
                    indicator: 'green'
                });
                // Navigate to the created PI
                frappe.set_route('Form', 'Purchase Invoice', r.message);
            }
        }
    });
}