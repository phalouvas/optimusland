"""Manufacturing Pipeline Dashboard — data queries and actions.

Provides the backend for the full-cycle pipeline visibility in the
Optimus workspace.  All public functions are ``@frappe.whitelist()``
so they can be called from the Custom HTML Block on the workspace.

Pipeline tiers
--------------
- **Sourcing**: Weight Slip → Batch → Purchase Receipt
- **Manufacturing**: Purchase Receipt → Production Plan → Work Order → Stock Entry
- **Fulfillment**: Delivery Note → Sales Invoice → Purchase Invoice
"""

import frappe
from frappe.utils import flt, today, add_days


# ---------------------------------------------------------------------------
# Public — callable from the Custom HTML Block via frappe.call()
# ---------------------------------------------------------------------------


@frappe.whitelist()
def get_pipeline_data(from_date=None, to_date=None, supplier=None, customer=None):
    """Return pipeline data for all three tiers within the date range.

    Parameters are passed as strings from the JS frontend.  The
    frontend filter bar passes ``null`` when a filter is cleared.
    """
    flt = _build_filters(from_date, to_date, supplier, customer)
    return {
        "sourcing": _get_sourcing_data(flt),
        "manufacturing": _get_manufacturing_data(flt),
        "fulfillment": _get_fulfillment_data(flt),
    }


@frappe.whitelist()
def get_alerts(from_date=None, to_date=None):
    """Return all pipeline alerts, sorted by severity."""
    flt = _build_filters(from_date, to_date)
    alerts = []
    alerts.extend(_alert_pr_no_pp(flt))
    alerts.extend(_alert_bom_skipped(flt))
    alerts.extend(_alert_wo_stuck(flt))
    alerts.extend(_alert_manufactured_batch_no_dn(flt))
    alerts.extend(_alert_dn_unbilled(flt))
    alerts.extend(_alert_pi_not_linked(flt))
    alerts.extend(_alert_supplier_unlinked_jv(flt))

    _sort_by_severity(alerts)
    return alerts


@frappe.whitelist()
def get_kpi_counts():
    """Return summary KPI counts for Number Cards on the workspace."""
    alerts = get_alerts(from_date=add_days(today(), -30))
    return {
        "prs_today": _count_prs_today(),
        "open_wos": _count_open_wos(),
        "ready_to_ship": _count_ready_to_ship(),
        "total_alerts": len(alerts),
    }


@frappe.whitelist()
def retry_production_plan(pr_name):
    """Re-run ``create_production_plan`` for a specific PR.

    Useful when a PR was submitted but the Production Plan failed
    (e.g., a BOM was missing at the time and has since been added).
    """
    from optimusland.utils.purchase_receipt import create_production_plan

    if not frappe.db.exists("Purchase Receipt", pr_name):
        return _result(False, f"Purchase Receipt {pr_name} not found.")

    pr = frappe.get_doc("Purchase Receipt", pr_name)
    if pr.docstatus != 1:
        return _result(False, "Purchase Receipt is not submitted.")

    if pr.get("custom_production_plan"):
        # Check if it already has a valid PP
        if frappe.db.exists("Production Plan", pr.custom_production_plan):
            return _result(False, f"Production Plan {pr.custom_production_plan} already exists.")

    try:
        create_production_plan(pr)
        pp = frappe.db.get_value("Purchase Receipt", pr_name, "custom_production_plan")
        return _result(True, f"Production Plan {pp} created successfully.")
    except Exception as e:
        frappe.log_error(
            message=f"Pipeline retry failed for PR {pr_name}: {e}",
            title="Pipeline — Retry Production Plan",
        )
        return _result(False, str(e))


@frappe.whitelist()
def force_submit_work_order(wo_name):
    """Submit a stuck Draft Work Order.

    Returns an error if the WO is already submitted, cancelled, or
    if submission fails validation.
    """
    if not frappe.db.exists("Work Order", wo_name):
        return _result(False, f"Work Order {wo_name} not found.")

    wo = frappe.get_doc("Work Order", wo_name)
    if wo.docstatus != 0:
        return _result(False, "Work Order is not in Draft.")

    try:
        wo.submit()
        return _result(True, f"Work Order {wo_name} submitted.")
    except Exception as e:
        frappe.log_error(
            message=f"Force submit failed for WO {wo_name}: {e}",
            title="Pipeline — Force Submit Work Order",
        )
        return _result(False, str(e))


# ---------------------------------------------------------------------------
# Internal helpers — shared between pipeline data and alert queries
# ---------------------------------------------------------------------------


def _build_filters(from_date=None, to_date=None, supplier=None, customer=None):
    """Normalise filter parameters into a dict safe for SQL queries."""
    return {
        "from_date": from_date or add_days(today(), -30),
        "to_date": to_date or today(),
        "supplier": supplier or None,
        "customer": customer or None,
    }


def _result(success, message):
    return {"success": success, "message": message}


_SEVERITY = {"critical": 0, "warning": 1, "info": 2}


def _sort_by_severity(alerts):
    alerts.sort(key=lambda a: (_SEVERITY.get(a["severity"], 99), a.get("entity", "")))


def _format_alert(severity, title, message, entity=None, doctype=None, action=None):
    """Build a standardised alert dict."""
    alert = {
        "severity": severity,
        "title": title,
        "message": message,
    }
    if entity:
        alert["entity"] = entity
    if doctype:
        alert["doctype"] = doctype
    if action:
        alert["action"] = action
    return alert


# ---------------------------------------------------------------------------
# Sourcing tier — data queries
# ---------------------------------------------------------------------------


def _get_sourcing_data(flt):
    """Return PR items with their linked Batch and Weight Slip info."""
    return frappe.db.sql(
        """
        SELECT
            pri.parent                          AS pr,
            pr.posting_date                     AS pr_date,
            pr.supplier                         AS pr_supplier,
            pr.status                           AS pr_status,
            pri.item_code,
            pri.qty,
            pri.rate,
            pri.batch_no,
            bat.batch_id,
            bat.custom_weight_slip              AS batch_weight_slip,
            ws.name                             AS weight_slip,
            ws.slip_number                      AS weight_slip_number,
            pr.custom_production_plan           AS production_plan
        FROM `tabPurchase Receipt Item` pri
        INNER JOIN `tabPurchase Receipt` pr
            ON pr.name = pri.parent
        LEFT JOIN `tabBatch` bat
            ON bat.name = pri.batch_no
        LEFT JOIN `tabWeight Slip` ws
            ON ws.name = bat.custom_weight_slip
        WHERE pr.docstatus = 1
            AND pr.posting_date BETWEEN %(from_date)s AND %(to_date)s
            AND (%(supplier)s IS NULL OR pr.supplier = %(supplier)s)
        ORDER BY pr.posting_date DESC, pr.name
        """,
        flt,
        as_dict=True,
    )


def _get_manufacturing_data(flt):
    """Return the PR→PP→WO→SE chain for PRs in the date range."""
    return frappe.db.sql(
        """
        SELECT
            pr.name                             AS pr,
            pr.custom_production_plan           AS pp,
            pp.status                           AS pp_status,
            pp.posting_date                     AS pp_date,
            wo.name                             AS wo,
            wo.status                           AS wo_status,
            wo.qty                              AS wo_qty,
            wo.produced_qty                     AS wo_produced_qty,
            wo.bom_no                           AS wo_bom,
            se_tr.name                          AS se_transfer,
            se_tr.docstatus                     AS se_transfer_status,
            se_mf.name                          AS se_manufacture,
            se_mf.docstatus                     AS se_manufacture_status
        FROM `tabPurchase Receipt` pr
        LEFT JOIN `tabProduction Plan` pp
            ON pp.name = pr.custom_production_plan
        LEFT JOIN `tabWork Order` wo
            ON wo.production_plan = pp.name
        LEFT JOIN `tabStock Entry` se_tr
            ON se_tr.work_order = wo.name
            AND se_tr.stock_entry_type = 'Material Transfer for Manufacture'
        LEFT JOIN `tabStock Entry` se_mf
            ON se_mf.work_order = wo.name
            AND se_mf.stock_entry_type = 'Manufacture'
        WHERE pr.docstatus = 1
            AND pr.posting_date BETWEEN %(from_date)s AND %(to_date)s
            AND (%(supplier)s IS NULL OR pr.supplier = %(supplier)s)
        ORDER BY pr.posting_date DESC, pr.name
        """,
        flt,
        as_dict=True,
    )


def _get_fulfillment_data(flt):
    """Return the DN→SI→PI chain for DNs in the date range.

    Notes
    -----
    The PI→PR link hook (``get_purchase_receipt_items``) is commented
    out in ``hooks.py``, so there is no reliable direct link from a DN
    item's batch to a Purchase Invoice.  The PI information here is
    approximate: we look for any PI Item that references a Purchase
    Receipt whose items include the same batch.
    """
    return frappe.db.sql(
        """
        SELECT
            dn.name                             AS dn,
            dn.posting_date                     AS dn_date,
            dn.customer,
            dn.status                           AS dn_status,
            dn.per_billed,
            dn.custom_shipping_rate,
            si.name                             AS si,
            si.status                           AS si_status,
            COALESCE(si_pi.parent, pi.name)     AS pi,
            pi.status                           AS pi_status,
            dni.item_code,
            dni.batch_no,
            dni.qty
        FROM `tabDelivery Note` dn
        INNER JOIN `tabDelivery Note Item` dni
            ON dni.parent = dn.name
        LEFT JOIN `tabSales Invoice Item` sii
            ON sii.delivery_note = dn.name
            AND sii.dn_detail = dni.name
        LEFT JOIN `tabSales Invoice` si
            ON si.name = sii.parent
        LEFT JOIN `tabPurchase Invoice Item` si_pi
            ON si_pi.purchase_receipt = (
                SELECT pri.parent
                FROM `tabPurchase Receipt Item` pri
                WHERE pri.batch_no = dni.batch_no
                LIMIT 1
            )
        LEFT JOIN `tabPurchase Invoice` pi
            ON pi.name = si_pi.parent
        WHERE dn.docstatus = 1
            AND dn.posting_date BETWEEN %(from_date)s AND %(to_date)s
            AND (%(customer)s IS NULL OR dn.customer = %(customer)s)
        ORDER BY dn.posting_date DESC, dn.name
        """,
        flt,
        as_dict=True,
    )


# ---------------------------------------------------------------------------
# KPI counts
# ---------------------------------------------------------------------------


def _count_prs_today():
    return flt(
        frappe.db.count("Purchase Receipt", {"docstatus": 1, "posting_date": today()})
    )


def _count_open_wos():
    return flt(
        frappe.db.count("Work Order", {"status": ["!=", "Completed"], "docstatus": 1})
    )


def _count_ready_to_ship():
    """Count unique batches with a submitted Manufacture SE but no DN item."""
    result = frappe.db.sql(
        """
        SELECT COUNT(DISTINCT sed.batch_no)
        FROM `tabStock Entry Detail` sed
        INNER JOIN `tabStock Entry` se
            ON se.name = sed.parent
            AND se.docstatus = 1
            AND se.stock_entry_type = 'Manufacture'
            AND sed.is_finished_item = 1
        WHERE sed.batch_no IS NOT NULL
            AND sed.batch_no != ''
            AND sed.batch_no NOT IN (
                SELECT dni.batch_no
                FROM `tabDelivery Note Item` dni
                INNER JOIN `tabDelivery Note` dn
                    ON dn.name = dni.parent
                    AND dn.docstatus = 1
                WHERE dni.batch_no IS NOT NULL
                    AND dni.batch_no != ''
            )
        """
    )
    return flt(result[0][0]) if result else 0


# ---------------------------------------------------------------------------
# Alert detection
# ---------------------------------------------------------------------------


def _alert_pr_no_pp(flt):
    """PRs that are submitted but have no Production Plan linked."""
    rows = frappe.db.sql(
        """
        SELECT pr.name AS entity
        FROM `tabPurchase Receipt` pr
        WHERE pr.docstatus = 1
            AND (pr.custom_production_plan IS NULL OR pr.custom_production_plan = '')
            AND pr.posting_date BETWEEN %(from_date)s AND %(to_date)s
        """,
        flt,
        as_dict=True,
    )
    return [
        _format_alert(
            severity="critical",
            title="PR has no Production Plan",
            message=f"Purchase Receipt {r.entity} was submitted but no Production Plan was created. "
            "Possible causes: missing BOM, missing item, or an error during creation.",
            entity=r.entity,
            doctype="Purchase Receipt",
            action="retry",
        )
        for r in rows
    ]


def _alert_bom_skipped(flt):
    """Items that were skipped during PP creation due to missing BOMs.

    Detection relies on the comment added by the #61 fix —
    ``create_production_plan`` now writes a comment to the PR timeline
    when an item is skipped.
    """
    rows = frappe.db.sql(
        """
        SELECT DISTINCT
            c.reference_name AS entity
        FROM `tabComment` c
        WHERE c.reference_doctype = 'Purchase Receipt'
            AND c.comment_type = 'Comment'
            AND c.content LIKE '%%Failed to create Production Plan for item%%'
            AND c.creation BETWEEN %(from_date)s AND %(to_date)s
        """,
        flt,
        as_dict=True,
    )
    return [
        _format_alert(
            severity="critical",
            title="Item skipped — BOM missing",
            message=f"Purchase Receipt {r.entity} had items skipped during Production Plan "
            "creation because their Bill of Materials could not be found. Check the PR timeline "
            "for details.",
            entity=r.entity,
            doctype="Purchase Receipt",
            action="retry",
        )
        for r in rows
    ]


def _alert_wo_stuck(flt):
    """Work Orders stuck in Draft for more than 24h / 48h."""
    rows = frappe.db.sql(
        """
        SELECT wo.name AS entity, wo.creation,
               DATEDIFF(NOW(), wo.creation) AS days_stuck
        FROM `tabWork Order` wo
        WHERE wo.docstatus = 0
            AND wo.creation < DATE_SUB(NOW(), INTERVAL 24 HOUR)
        ORDER BY wo.creation
        """,
        as_dict=True,
    )
    alerts = []
    for r in rows:
        is_critical = r.days_stuck >= 2
        alerts.append(
            _format_alert(
                severity="critical" if is_critical else "warning",
                title=f"WO stuck in Draft for {int(r.days_stuck)} day(s)",
                message=f"Work Order {r.entity} has been in Draft status since {r.creation.date()}. "
                "Submit or cancel it to unblock the pipeline.",
                entity=r.entity,
                doctype="Work Order",
                action="submit",
            )
        )
    return alerts


def _alert_manufactured_batch_no_dn(flt):
    """Batches that have been manufactured but have no Delivery Note."""
    rows = frappe.db.sql(
        """
        SELECT DISTINCT sed.batch_no AS entity
        FROM `tabStock Entry Detail` sed
        INNER JOIN `tabStock Entry` se
            ON se.name = sed.parent
            AND se.docstatus = 1
            AND se.stock_entry_type = 'Manufacture'
            AND sed.is_finished_item = 1
        WHERE sed.batch_no IS NOT NULL
            AND sed.batch_no != ''
            AND sed.batch_no NOT IN (
                SELECT dni.batch_no
                FROM `tabDelivery Note Item` dni
                INNER JOIN `tabDelivery Note` dn
                    ON dn.name = dni.parent
                    AND dn.docstatus = 1
                WHERE dni.batch_no IS NOT NULL
                    AND dni.batch_no != ''
            )
            AND se.posting_date BETWEEN %(from_date)s AND %(to_date)s
        """,
        flt,
        as_dict=True,
    )
    return [
        _format_alert(
            severity="info",
            title="Manufactured batch ready to ship",
            message=f"Batch {r.entity} has a completed Manufacture Stock Entry but no "
            "Delivery Note yet.",
            entity=r.entity,
            doctype="Batch",
        )
        for r in rows
    ]


def _alert_dn_unbilled(flt):
    """Delivery Notes submitted >7 days ago that are still not fully billed."""
    rows = frappe.db.sql(
        """
        SELECT dn.name AS entity, dn.posting_date,
               dn.per_billed, dn.customer
        FROM `tabDelivery Note` dn
        WHERE dn.docstatus = 1
            AND dn.status != 'Closed'
            AND dn.per_billed < 100
            AND dn.posting_date < DATE_SUB(%(to_date)s, INTERVAL 7 DAY)
            AND dn.posting_date >= %(from_date)s
        ORDER BY dn.per_billed
        """,
        flt,
        as_dict=True,
    )
    return [
        _format_alert(
            severity="warning",
            title=f"DN unbilled ({r.per_billed:.0f}% billed)",
            message=f"Delivery Note {r.entity} for {r.customer} was created on "
            f"{r.posting_date} and is only {r.per_billed:.0f}% billed after 7+ days.",
            entity=r.entity,
            doctype="Delivery Note",
        )
        for r in rows
    ]


def _alert_pi_not_linked(flt):
    """Purchase Invoices whose items have no Purchase Receipt reference."""
    rows = frappe.db.sql(
        """
        SELECT pi.name AS entity, pi.supplier
        FROM `tabPurchase Invoice` pi
        INNER JOIN `tabPurchase Invoice Item` pii
            ON pii.parent = pi.name
        WHERE pi.docstatus = 1
            AND (pii.purchase_receipt IS NULL OR pii.purchase_receipt = '')
            AND pi.posting_date BETWEEN %(from_date)s AND %(to_date)s
        GROUP BY pi.name
        """,
        flt,
        as_dict=True,
    )
    return [
        _format_alert(
            severity="info",
            title="PI not linked to any Purchase Receipt",
            message=f"Purchase Invoice {r.entity} for {r.supplier} has items with no "
            "Purchase Receipt reference. The farmer payment cannot be traced back to a PR.",
            entity=r.entity,
            doctype="Purchase Invoice",
        )
        for r in rows
    ]


def _alert_supplier_unlinked_jv(flt):
    """Suppliers with unlinked Journal Entries.

    Reuses the existing detection in ``supplier.py`` but scoped to
    the date range and returns a flat list of alerts.
    """
    # First find suppliers who were active in the date range
    suppliers = frappe.db.sql(
        """
        SELECT DISTINCT pr.supplier AS entity
        FROM `tabPurchase Receipt` pr
        WHERE pr.docstatus = 1
            AND pr.posting_date BETWEEN %(from_date)s AND %(to_date)s
        """,
        flt,
        as_dict=True,
    )
    alerts = []
    for s in suppliers:
        try:
            # Import here to avoid circular imports
            from optimusland.utils.supplier import get_supplier_unlinked_journal_entries

            warning = get_supplier_unlinked_journal_entries(s.entity)
            if warning and warning is not True:
                alerts.append(
                    _format_alert(
                        severity="warning",
                        title="Supplier has unlinked Journal Entries",
                        message=f"Supplier {s.entity}: {warning}",
                        entity=s.entity,
                        doctype="Supplier",
                    )
                )
        except Exception:
            continue
    return alerts
