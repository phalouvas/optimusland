# Copyright (c) 2026, KAINOTOMO PH LTD and contributors
# For license information, please see license.txt

"""Grower Price Calculator.

Computes the recommended grower price per batch/item using the formula:

    grower_price = selling_price × (1 − margin%) − operating_rate
                   − capital_rate − additional_costs_per_kg

The result is a **recommendation** — users can override individual line prices
in the PI dialog.  Full audit trail of formula vs. actual.

Called from:
- Base Rate Report (management overview)
- Purchase Invoice form "Calculate Grower Price" button (PI creation)

See Issue #78 for full specification.
"""

import frappe
from frappe.utils import flt, today, add_days, now_datetime


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


@frappe.whitelist()
def calculate_grower_price(sales_invoice, margin_pct=None):
    """Calculate recommended grower price for all Potato items on an SI.

    Args:
        sales_invoice: Sales Invoice name (string)
        margin_pct: Target margin % (default from Optimus General Settings)

    Returns:
        List of dicts, one per Potato item:
        {item_code, batch_no, qty, selling_rate, operating_rate, capital_rate,
         base_rate, addl_costs_rate, margin_pct, recommended_price, total}
    """
    from optimusland.utils.blended_rate import get_base_rate

    si = frappe.get_doc("Sales Invoice", sales_invoice)
    if si.docstatus > 1:
        frappe.throw(f"Sales Invoice {sales_invoice} is cancelled.")

    cfg = _get_config()
    margin_pct = flt(margin_pct) or flt(cfg.default_target_margin_pct)
    base_rate_data = get_base_rate(si.company)
    op_rate = flt(base_rate_data.get("operating_rate", 0))
    cap_rate = flt(base_rate_data.get("capital_rate", 0))

    # Total additional costs for this SI
    total_addl_costs = sum(
        flt(row.amount) for row in si.get("additional_costs", [])
    )
    total_si_qty = sum(
        flt(item.qty) for item in si.items
    )
    addl_costs_per_kg = total_addl_costs / total_si_qty if total_si_qty else 0

    results = []
    for item in si.items:
        item_group = frappe.db.get_value("Item", item.item_code, "item_group")
        if item_group != "Potatoes":
            continue

        selling_rate = flt(item.net_rate)
        margin_amount = selling_rate * (margin_pct / 100)
        recommended_price = (
            selling_rate - margin_amount - op_rate - cap_rate - addl_costs_per_kg
        )
        recommended_price = round(max(recommended_price, 0), 6)

        # Get batch number
        batch_no = None
        if item.batch_no:
            batch_no = item.batch_no
        elif item.serial_and_batch_bundle:
            batch_no = _get_batch_from_bundle(item.serial_and_batch_bundle)

        results.append(
            frappe._dict(
                item_code=item.item_code,
                item_name=item.item_name,
                batch_no=batch_no,
                qty=flt(item.qty),
                selling_rate=selling_rate,
                operating_rate=op_rate,
                capital_rate=cap_rate,
                base_rate=op_rate + cap_rate,
                addl_costs_rate=round(addl_costs_per_kg, 6),
                margin_pct=margin_pct,
                margin_amount=round(margin_amount, 6),
                recommended_price=recommended_price,
                total=round(recommended_price * flt(item.qty), 2),
            )
        )

    return results


@frappe.whitelist()
def preview_grower_price(sales_invoice, margin_pct=None):
    """Read-only preview for Draft SI form.  Same as calculate_grower_price
    but returns a formatted summary for display."""
    results = calculate_grower_price(sales_invoice, margin_pct)
    if not results:
        return {"items": [], "summary": "No Potato items found on this invoice."}

    total_grower_amount = sum(r.total for r in results)
    total_qty = sum(r.qty for r in results)

    return {
        "items": results,
        "summary": frappe._dict(
            total_qty=total_qty,
            avg_selling_rate=round(
                sum(r.selling_rate * r.qty for r in results) / total_qty, 4
            )
            if total_qty
            else 0,
            avg_base_rate=round(
                sum(r.base_rate * r.qty for r in results) / total_qty, 4
            )
            if total_qty
            else 0,
            total_grower_amount=round(total_grower_amount, 2),
            margin_pct=results[0].margin_pct if results else 0,
        ),
        "warnings": _get_warnings(results),
    }


@frappe.whitelist()
def get_weight_slip_unpaid_batches(supplier, weight_slip):
    """Find unpaid batches for a given Weight Slip and supplier.

    An unpaid batch = batch on a submitted SI where no submitted PI
    for the same Weight Slip already covers that batch.

    Traces via: WS → Batch (custom_weight_slip) → DN → SI
    Excludes: batches where PI.custom_weight_slip = same WS
              AND PI item → PR item matches the batch

    Args:
        supplier: Supplier name (grower)
        weight_slip: Weight Slip name

    Returns:
        List of dicts: {batch_no, item_code, sales_invoice, qty, selling_rate}
    """
    # Find all batches for this WS and supplier
    batches = frappe.db.get_all(
        "Batch",
        filters={
            "custom_weight_slip": weight_slip,
            "custom_supplier_optimus": supplier,
            "disabled": 0,
        },
        fields=["name", "item"],
        pluck="name",
    )

    if not batches:
        return []

    # Find submitted PIs already covering this WS
    paid_batch_nos = frappe.db.sql(
        """
        SELECT DISTINCT sbe.batch_no
        FROM `tabPurchase Invoice` pi
        INNER JOIN `tabPurchase Invoice Item` pii ON pii.parent = pi.name
        INNER JOIN `tabPurchase Receipt Item` pri ON pri.name = pii.purchase_receipt_item
        INNER JOIN `tabSerial and Batch Entry` sbe ON sbe.parent = pri.serial_and_batch_bundle
        WHERE pi.custom_weight_slip = %s
          AND pi.docstatus = 1
          AND sbe.batch_no IN %(batch_nos)s
        """,
        (weight_slip, tuple(batches)),
        as_dict=True,
    )
    paid_set = {row.batch_no for row in paid_batch_nos}

    # Filter out paid batches
    unpaid = [b for b in batches if b not in paid_set]

    if not unpaid:
        return []

    # Find submitted SIs that delivered these batches
    return frappe.db.sql(
        """
        SELECT DISTINCT
            sbe.batch_no AS batch_no,
            sii.item_code,
            si.name AS sales_invoice,
            sii.qty,
            sii.net_rate AS selling_rate
        FROM `tabSerial and Batch Entry` sbe
        INNER JOIN `tabDelivery Note Item` dni ON dni.serial_and_batch_bundle = sbe.parent
        INNER JOIN `tabSales Invoice Item` sii ON sii.delivery_note = dni.parent
            AND sii.item_code = dni.item_code
        INNER JOIN `tabSales Invoice` si ON si.name = sii.parent AND si.docstatus = 1
        WHERE sbe.batch_no IN %(batch_nos)s
        ORDER BY si.name
        """,
        {"batch_nos": tuple(unpaid)},
        as_dict=True,
    )


@frappe.whitelist()
def calculate_pi_prices(supplier, items, company=None):
    """Calculate grower prices for items on a Draft Purchase Invoice.

    Traces each item → PR item → batch → SI → selling price,
    then applies the grower price formula.

    Items are passed from the client (PI may not be saved yet).

    Returns dict with items (per-item breakdown) and base_rate.
    """
    from optimusland.utils.blended_rate import get_base_rate

    # Items arrive as JSON string from Frappe RPC
    if isinstance(items, str):
        items = frappe.parse_json(items)

    if not company:
        company = frappe.defaults.get_user_default("company")

    cfg = _get_config()
    margin_pct = flt(cfg.default_target_margin_pct) or 6
    base_rate_data = get_base_rate(company)
    op_rate = flt(base_rate_data.get("operating_rate", 0))
    cap_rate = flt(base_rate_data.get("capital_rate", 0))

    results = []
    first_ws = None

    for item in items:
        # Trace item → PR item → batch
        item_code = item.get("item_code")
        item_qty = flt(item.get("qty"))

        # batch_no may be directly on the PI item, or we trace via pr_detail
        batch_no = item.get("batch_no")
        if not batch_no:
            pr_detail = item.get("pr_detail")
            if pr_detail:
                try:
                    pr_item = frappe.get_doc("Purchase Receipt Item", pr_detail)
                    batch_no = _get_batch_from_pr_item(pr_item)
                except Exception:
                    pass

        if not batch_no:
            continue

        # Trace batch → SI to get selling price
        si_info = frappe.db.sql("""
            SELECT si.name, sii.qty, sii.net_rate, sii.item_code
            FROM `tabSerial and Batch Entry` sbe
            INNER JOIN `tabDelivery Note Item` dni ON dni.serial_and_batch_bundle = sbe.parent
            INNER JOIN `tabSales Invoice Item` sii ON sii.delivery_note = dni.parent
                AND sii.item_code = dni.item_code
            INNER JOIN `tabSales Invoice` si ON si.name = sii.parent AND si.docstatus = 1
            WHERE sbe.batch_no = %(batch_no)s
            LIMIT 1
        """, {"batch_no": batch_no}, as_dict=True)

        selling_rate = si_info[0].net_rate if si_info else 0
        si_name = si_info[0].name if si_info else None

        # Get Weight Slip from batch
        if not first_ws:
            batch_doc = frappe.get_doc("Batch", batch_no)
            first_ws = batch_doc.custom_weight_slip

        margin_amount = selling_rate * (margin_pct / 100)
        recommended_price = round(max(selling_rate - margin_amount - op_rate - cap_rate, 0), 6)

        results.append(frappe._dict(
            item_code=item_code,
            item_name=item.get("item_name"),
            batch_no=batch_no,
            qty=item_qty,
            purchase_rate=flt(item.get("rate")),
            selling_rate=selling_rate,
            sales_invoice=si_name,
            operating_rate=op_rate,
            capital_rate=cap_rate,
            base_rate=op_rate + cap_rate,
            margin_pct=margin_pct,
            recommended_price=recommended_price,
            total=round(recommended_price * item_qty, 2),
        ))

    return {
        "items": results,
        "margin_pct": margin_pct,
        "weight_slip": first_ws,
        "base_rate": {
            "operating_rate": op_rate,
            "capital_rate": cap_rate,
            "base_rate": op_rate + cap_rate,
        },
    }


def _get_batch_from_pr_item(pr_item):
    """Extract batch number from a Purchase Receipt Item."""
    if pr_item.batch_no:
        return pr_item.batch_no
    if pr_item.serial_and_batch_bundle:
        rows = frappe.db.get_all(
            "Serial and Batch Entry",
            filters={"parent": pr_item.serial_and_batch_bundle},
            fields=["batch_no"],
            limit=1,
        )
        return rows[0].batch_no if rows else None
    return None


@frappe.whitelist()
def update_pi_item_rates(purchase_invoice, item_updates, margin_pct=None):
    """Update item rates on a Draft Purchase Invoice with confirmed grower prices.

    Args:
        purchase_invoice: PI name
        item_updates: list of {idx, rate} — idx is 0-based item position
        margin_pct: Margin used (for audit trail)
    """
    pi = frappe.get_doc("Purchase Invoice", purchase_invoice)
    if pi.docstatus != 0:
        frappe.throw("Only Draft Purchase Invoices can be updated.")

    margin_pct = flt(margin_pct) or flt(_get_config().default_target_margin_pct)

    # Parse item_updates — arrives as JSON string from Frappe RPC
    if isinstance(item_updates, str):
        item_updates = frappe.parse_json(item_updates)

    # Update item rates
    for update in item_updates:
        idx = int(update.get("idx"))
        rate = flt(update.get("rate"))
        if idx < len(pi.items) and rate > 0:
            pi.items[idx].rate = rate

    # Get WS from first item's batch for audit trail
    first_ws = None
    if pi.items and pi.items[0].pr_detail:
        pr_item = frappe.get_doc("Purchase Receipt Item", pi.items[0].pr_detail)
        batch_no = _get_batch_from_pr_item(pr_item)
        if batch_no:
            batch_doc = frappe.get_doc("Batch", batch_no)
            first_ws = batch_doc.custom_weight_slip
    if first_ws:
        pi.custom_weight_slip = first_ws

    # Store calculation snapshot
    pi.custom_grower_price_calculation = frappe.as_json({
        "margin_pct": margin_pct,
        "updated_at": str(now_datetime()),
        "updated_by": frappe.session.user,
    })

    pi.save(ignore_permissions=True)

    pi.add_comment("Info", f"Grower price calculated with {margin_pct}% margin. User-confirmed.")

    return pi.name


@frappe.whitelist()
def create_purchase_invoice(supplier, weight_slip, line_items, margin_pct=None):
    """Create a Purchase Invoice for a grower with confirmed prices.

    Args:
        supplier: Supplier name
        weight_slip: Weight Slip name
        line_items: List of dicts [{batch_no, item_code, qty, rate, amount}]
        margin_pct: Margin used (for audit trail)

    Returns:
        Created Purchase Invoice name
    """
    from frappe.model.mapper import get_mapped_doc

    if not line_items:
        frappe.throw("No line items provided for Purchase Invoice.")

    margin_pct = flt(margin_pct) or flt(_get_config().default_target_margin_pct)

    # Get calculation breakdown for audit
    first_item = line_items[0]
    si_name = frappe.db.get_value(
        "Sales Invoice Item",
        {"item_code": first_item["item_code"]},
        "parent",
    )
    calc_data = calculate_grower_price(si_name, margin_pct) if si_name else []

    pi = frappe.get_doc(
        {
            "doctype": "Purchase Invoice",
            "supplier": supplier,
            "custom_weight_slip": weight_slip,
            "posting_date": today(),
            "items": [],
        }
    )

    for line in line_items:
        pi.append(
            "items",
            {
                "item_code": line["item_code"],
                "qty": flt(line["qty"]),
                "rate": flt(line["rate"]),
                "custom_batch_no": line.get("batch_no"),
            },
        )

    # Store calculation as JSON for audit trail
    pi.custom_grower_price_calculation = frappe.as_json(
        {
            "weight_slip": weight_slip,
            "line_items": line_items,
            "calculation": calc_data,
            "margin_pct": margin_pct,
            "created_at": str(now_datetime()),
            "created_by": frappe.session.user,
        }
    )

    pi.insert(ignore_permissions=True)
    pi.submit()

    # Add a comment for audit trail
    pi.add_comment(
        "Info",
        f"Grower price calculated from {weight_slip} with {margin_pct}% margin. "
        f"User-verified and confirmed.",
    )

    return pi.name


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _get_config():
    """Get configuration from Optimus General Settings."""
    settings = frappe.get_single("Optimus General Settings")
    return frappe._dict(
        default_target_margin_pct=flt(settings.default_target_margin_pct) or 6,
        operating_lookback_days=settings.operating_lookback_days or 90,
    )


def _get_batch_from_bundle(bundle_name):
    """Extract batch number from a Serial and Batch Bundle."""
    rows = frappe.db.get_all(
        "Serial and Batch Entry",
        filters={"parent": bundle_name},
        fields=["batch_no"],
        limit=1,
    )
    return rows[0].batch_no if rows else None


def _get_warnings(results):
    """Check for warning conditions in the results."""
    warnings = []
    for r in results:
        if r.recommended_price <= 0:
            warnings.append(
                f"Grower price for {r.item_code} is €0 — negative before floor applied. "
                "Check costs or consider adjusting margin."
            )
        elif r.recommended_price < 0.10:
            warnings.append(
                f"Grower price for {r.item_code} is €{r.recommended_price:.3f}/kg "
                "(below €0.10 threshold). Consider manual review."
            )
    return warnings
