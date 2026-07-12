frappe.ui.form.on("Purchase Invoice", {
    refresh: function(frm) {
        if (frm.doc.__islocal) {
            frappe.msgprint("<p>This is a <b>Purchase Invoice</b>.</p><p>Remember to choose the correct <b>Naming Series</b>.</p>");
            var page = document.getElementById("page-Purchase Invoice");
            if (page) page.classList.add("bg-warning");
        } else {
            var page = document.getElementById("page-Purchase Invoice");
            if (page) page.classList.remove("bg-warning");
        }

        // "Calculate Grower Price" only on saved Draft PIs (not before first save)
        if (!frm.doc.__islocal && frm.doc.docstatus === 0 && frm.doc.supplier && frm.doc.items && frm.doc.items.length > 0
            && frm.doc.items.some(function(i) { return parseFloat(i.qty) > 0; })) {
            frm.add_custom_button(__('Calculate Grower Price'), function() {
                _show_calculator(frm);
            });
        }
    },
});

let _calc_data = null;
let _margin_pct = 6;

function _show_calculator(frm) {
    // Read items from the form directly (PI may not be saved yet)
    let pi_items = (frm.doc.items || [])
        .filter(function(item) { return parseFloat(item.qty) > 0; })
        .map(function(item) {
            return {
                item_code: item.item_code,
                item_name: item.item_name,
                qty: item.qty,
                rate: item.rate,
                batch_no: item.batch_no,
                pr_detail: item.pr_detail
            };
        });

    if (pi_items.length === 0) {
        frappe.msgprint({ message: __('Add items to the Purchase Invoice first.'), title: __('No Items'), indicator: 'orange' });
        return;
    }

    frappe.call({
        method: 'optimusland.utils.grower_calculator.calculate_pi_prices',
        args: {
            supplier: frm.doc.supplier,
            items: pi_items,
            company: frm.doc.company
        },
        callback: function(r) {
            if (!r.message || !r.message.items || r.message.items.length === 0) {
                frappe.msgprint({ message: __('Could not calculate grower prices. Ensure items reference Purchase Receipts with Potato batches.'), title: __('No Prices'), indicator: 'orange' });
                return;
            }
            _calc_data = r.message;
            _margin_pct = r.message.margin_pct || 6;
            _show_prices_dialog(frm);
        }
    });
}

function _show_prices_dialog(frm) {
    let html = _build_html(_calc_data, _margin_pct);
    let d = new frappe.ui.Dialog({
        title: __('Grower Price Calculator'),
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
                default: _margin_pct,
                description: __('Higher margin = lower grower price.')
            }
        ],
        primary_action_label: __('Update PI Item Rates'),
        primary_action: function(values) {
            _margin_pct = values.margin_pct;
            d.hide();
            _update_pi_rates(frm);
        }
    });

    // Make dialog wider for the table
    d.$wrapper.find('.modal-dialog').css('width', '90%').css('max-width', '1200px');
    d.$wrapper.find('.modal-body').css('overflow-x', 'auto');

    d.set_secondary_action_label(__('Recalculate'));
    d.set_secondary_action(function() {
        let new_margin = d.get_value('margin_pct') || 6;
        _margin_pct = new_margin;
        let html = _build_html(_calc_data, new_margin);
        d.set_df_property('html_table', 'options', html);
    });

    d.show();
}

function _build_html(data, margin_pct) {
    let rows = '';
    let total_proposed = 0;

    (data.items || []).forEach(function(item, idx) {
        let proposed = item.recommended_price || 0;
        let total = (proposed * item.qty).toFixed(2);
        total_proposed += parseFloat(total);

        rows += `<tr>
            <td>${item.item_code}</td>
            <td>${item.batch_no || '-'}</td>
            <td>${parseFloat(item.qty).toFixed(0)}</td>
            <td>€${parseFloat(item.selling_rate).toFixed(3)}</td>
            <td>${item.margin_pct || margin_pct}%</td>
            <td><b>€${proposed.toFixed(3)}</b></td>
            <td><input type="number" step="0.001" class="form-control grower-price-input"
                data-idx="${idx}" value="${proposed.toFixed(3)}" style="width:100px"></td>
            <td class="grower-total" data-idx="${idx}">€${total}</td>
        </tr>`;
    });

    let base = data.base_rate || {};
    return `
        <p><strong>Base Rate:</strong> Operating €${(base.operating_rate || 0).toFixed(4)}/kg
        + Capital €${(base.capital_rate || 0).toFixed(4)}/kg
        = €${(base.base_rate || 0).toFixed(4)}/kg</p>
        <p><strong>Weight Slip:</strong> ${data.weight_slip || '-'}</p>
        <table class="table table-bordered table-condensed">
            <thead>
                <tr><th>Item</th><th>Batch</th><th>Qty</th><th>Selling</th><th>Margin</th><th>Formula</th><th>You Pay (€/kg)</th><th>Total</th></tr>
            </thead>
            <tbody>${rows}</tbody>
        </table>
        <p class="text-muted">Edit the <strong>You Pay</strong> column to override. Click Update PI Item Rates to apply.</p>
    `;
}

function _update_pi_rates(frm) {
    let updates = [];
    let inputs = document.querySelectorAll('.grower-price-input');
    inputs.forEach(function(input) {
        let idx = parseInt(input.dataset.idx);
        let rate = parseFloat(input.value) || 0;
        let item = _calc_data.items[idx];
        if (item && rate > 0) {
            updates.push({ idx: idx, rate: rate });
        }
    });

    if (updates.length === 0) {
        frappe.msgprint({ message: __('No valid prices to update.'), title: __('Error'), indicator: 'red' });
        return;
    }

    frappe.call({
        method: 'optimusland.utils.grower_calculator.update_pi_item_rates',
        args: {
            purchase_invoice: frm.doc.name,
            item_updates: updates,
            margin_pct: _margin_pct
        },
        callback: function(r) {
            if (r.message) {
                frappe.show_alert({ message: __('PI item rates updated.'), indicator: 'green' });
                frm.reload_doc();
            }
        }
    });
}
