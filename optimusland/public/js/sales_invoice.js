frappe.ui.form.on('Sales Invoice', {
    refresh: function(frm) {
        if (frm.doc.__islocal) {
            frappe.msgprint("<p>This is a <b>Sales Invoice</b>.</p><p>Rememeber to choose the correct <b>Incoterm</b>.</p>");            

            // Get element with id "page-Sales Invoice" and add a class to it
            var page = document.getElementById("page-Sales Invoice");
            page.classList.add("bg-info");
        } else {
            var page = document.getElementById("page-Sales Invoice");
            if (page) {
                page.classList.remove("bg-info");
            }

            // Add cost management buttons on Draft SIs only
            if (frm.doc.docstatus === 0) {
                frm.add_custom_button(__('Add Cost'), function() {
                    _show_add_cost_dialog(frm);
                });

                frm.add_custom_button(__('Preview Grower Price'), function() {
                    _preview_grower_price(frm);
                });
            }
        }
    },

    // Before submit: warn if Potato items have no additional costs
    before_submit: function(frm) {
        if (_has_potato_items(frm) && _has_no_costs(frm)) {
            frappe.msgprint({
                message: __('This invoice has Potato items but no Additional Costs added. '
                    + 'Consider adding costs (shipping, cold storage, etc.) before submitting.'),
                title: __('No Additional Costs'),
                indicator: 'orange',
                alert: true
            });
        }
    }
});

// ── Helper: Show "Add Cost" dialog ──────────────────────────────────

function _show_add_cost_dialog(frm) {
    let d = new frappe.ui.Dialog({
        title: __('Add Cost'),
        fields: [
            {
                label: __('Description'),
                fieldname: 'description',
                fieldtype: 'Data',
                reqd: 1
            },
            {
                label: __('Amount'),
                fieldname: 'amount',
                fieldtype: 'Currency',
                reqd: 1
            },
            {
                label: __('Cost Type'),
                fieldname: 'cost_type',
                fieldtype: 'Select',
                options: '\nShipping\nCold Storage\nMaterials\nOther',
                default: 'Shipping'
            },
            {
                label: __('Cost Purchase Invoice'),
                fieldname: 'cost_purchase_invoice',
                fieldtype: 'Link',
                options: 'Purchase Invoice',
                description: __('Link to a cost-related PI (shipping, cold storage). NOT the grower PI.'),
                onchange: function() {
                    const pi = d.get_value('cost_purchase_invoice');
                    if (pi) {
                        frappe.call({
                            method: 'frappe.client.get_value',
                            args: {
                                doctype: 'Purchase Invoice',
                                name: pi,
                                fieldname: 'grand_total'
                            },
                            callback: function(r) {
                                if (r.message && r.message.grand_total) {
                                    d.set_value('amount', r.message.grand_total);
                                }
                            }
                        });
                    }
                }
            }
        ],
        primary_action_label: __('Add'),
        primary_action: function(values) {
            // Check duplicate cost_purchase_invoice
            if (values.cost_purchase_invoice) {
                let existing = frm.doc.additional_costs || [];
                let duplicate = existing.find(function(row) {
                    return row.cost_purchase_invoice === values.cost_purchase_invoice;
                });
                if (duplicate) {
                    frappe.msgprint({
                        message: __('This Purchase Invoice is already linked as a cost.'),
                        title: __('Duplicate Cost'),
                        indicator: 'red'
                    });
                    return;
                }
            }

            // Add row to child table
            let child = frm.add_child('additional_costs');
            child.description = values.description;
            child.amount = values.amount;
            child.cost_type = values.cost_type;
            child.cost_purchase_invoice = values.cost_purchase_invoice || null;
            frm.refresh_field('additional_costs');
            _recompute_total_cost_rate(frm);
            d.hide();
            frappe.show_alert({ message: __('Cost added'), indicator: 'green' });
        }
    });
    d.show();
}

// ── Helper: Preview Grower Price ────────────────────────────────────

function _preview_grower_price(frm) {
    frappe.call({
        method: 'optimusland.utils.grower_calculator.preview_grower_price',
        args: {
            sales_invoice: frm.doc.name,
            margin_pct: null  // uses default from settings
        },
        callback: function(r) {
            if (!r.message || !r.message.items || r.message.items.length === 0) {
                frappe.msgprint({
                    message: __('No Potato items found on this invoice.'),
                    title: __('Grower Price'),
                    indicator: 'orange'
                });
                return;
            }

            let data = r.message;
            let html = _build_preview_html(data);
            let d = new frappe.ui.Dialog({
                title: __('Grower Price Preview'),
                fields: [
                    {
                        fieldname: 'html_preview',
                        fieldtype: 'HTML',
                        options: html
                    }
                ],
                primary_action_label: __('Close'),
                primary_action: function() {
                    d.hide();
                }
            });
            d.show();
        }
    });
}

// ── Helper: Build preview HTML table ────────────────────────────────

function _build_preview_html(data) {
    let rows = '';
    data.items.forEach(function(item) {
        rows += `<tr>
            <td>${item.item_code}</td>
            <td>${item.qty}</td>
            <td>€${item.selling_rate.toFixed(3)}</td>
            <td>€${item.base_rate.toFixed(3)}</td>
            <td>€${item.addl_costs_rate.toFixed(3)}</td>
            <td>${item.margin_pct}%</td>
            <td><b>€${item.recommended_price.toFixed(3)}</b></td>
            <td><b>€${item.total.toFixed(2)}</b></td>
        </tr>`;
    });

    let warnings = '';
    if (data.warnings && data.warnings.length > 0) {
        warnings = '<div class="alert alert-warning">';
        data.warnings.forEach(function(w) {
            warnings += '<p>' + w + '</p>';
        });
        warnings += '</div>';
    }

    let summary = data.summary || {};
    return `
        ${warnings}
        <p><strong>Base Rate:</strong> Operating €${data.items[0].operating_rate.toFixed(4)}/kg
        + Capital €${data.items[0].capital_rate.toFixed(4)}/kg
        = €${data.items[0].base_rate.toFixed(4)}/kg</p>
        <p><strong>Total grower amount (recommended):</strong> €${summary.total_grower_amount?.toFixed(2) || '0.00'}</p>
        <table class="table table-bordered table-condensed">
            <thead>
                <tr>
                    <th>Item</th>
                    <th>Qty (kg)</th>
                    <th>Selling</th>
                    <th>Base Rate</th>
                    <th>Addl Costs</th>
                    <th>Margin</th>
                    <th>Grower Price</th>
                    <th>Total</th>
                </tr>
            </thead>
            <tbody>
                ${rows}
            </tbody>
        </table>
    `;
}

// ── Helper: Recompute total cost rate ───────────────────────────────

function _recompute_total_cost_rate(frm) {
    let costs = frm.doc.additional_costs || [];
    let items = frm.doc.items || [];
    let total_cost = costs.reduce(function(sum, row) { return sum + (row.amount || 0); }, 0);
    let total_qty = items.reduce(function(sum, row) { return sum + (row.qty || 0); }, 0);
    if (total_qty > 0) {
        frm.set_value('custom_total_additional_cost_rate', total_cost / total_qty);
    }
}

// ── Helper: Check if invoice has Potato items ──────────────────────

function _has_potato_items(frm) {
    let items = frm.doc.items || [];
    return items.some(function(item) {
        // item_group check would need a server call; simplified check
        return item.item_name && item.item_name.toLowerCase().includes('potato');
    });
}

// ── Helper: Check if no costs added ─────────────────────────────────

function _has_no_costs(frm) {
    let costs = frm.doc.additional_costs || [];
    return costs.length === 0;
}