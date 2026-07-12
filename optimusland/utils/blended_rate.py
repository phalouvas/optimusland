# Copyright (c) 2026, KAINOTOMO PH LTD and contributors
# For license information, please see license.txt

"""Base Rate Calculator — Blended Rate from real P&L data.

Reads P&L accounts + Sales Invoice kg quantities for the lookback period
and computes two components:

- **Operating Rate** (€/kg):  Exponential time-decay weighted moving average
  of operating P&L accounts (52xx/53xx/54xx excluding depreciation) over a
  configurable lookback (default 90 days, min 30).
- **Capital Rate** (€/kg):  Simple average of P&L depreciation accounts only,
  divided by total SI kg sold over the last 365 days.

Both rates use **SI submitted quantities** (kg sold) as the denominator.

See Issue #78 for full specification.
"""

import frappe
from frappe.utils import flt, today, add_days, now_datetime, date_diff
from math import exp, log as ln



# ---------------------------------------------------------------------------
# Public API  (all @frappe.whitelist() — callable from JS via frappe.call)
# ---------------------------------------------------------------------------


@frappe.whitelist()
def get_base_rate(company=None):
    """Return current Base Rate (cached, compute if needed).

    Returns dict with operating_rate, capital_rate, base_rate, metadata.
    Caches the latest snapshot for 24 hours.
    """
    if not company:
        company = frappe.defaults.get_user_default("company")

    # Check cache first
    cached = _get_cached(company)
    if cached:
        return cached

    # Compute fresh
    return calculate_and_snapshot(company)


@frappe.whitelist()
def calculate_and_snapshot(company=None):
    """Force-recalculate and persist a Blended Rate Snapshot."""
    if not company:
        company = frappe.defaults.get_user_default("company")

    cfg = _get_config(company)
    op_rate = _get_operating_rate(company, cfg)
    cap_rate = _get_capital_rate(company, cfg)
    base_rate = flt(op_rate) + flt(cap_rate)

    result = {
        "company": company,
        "operating_rate": op_rate,
        "capital_rate": cap_rate,
        "base_rate": base_rate,
        "operating_lookback_days": cfg.operating_lookback_days,
        "capital_lookback_days": cfg.capital_lookback_days,
        "total_kg": _get_total_kg_sold(company, cfg.capital_lookback_days),
        "calculated_by": frappe.session.user,
        "timestamp": str(now_datetime()),
    }

    # Sanity checks
    result["sanity_warnings"] = _run_sanity_checks(result, cfg)

    # Persist snapshot
    _create_snapshot(company, result)

    return result


@frappe.whitelist()
def get_operating_rate(company=None, lookback_days=None):
    """Return just the operating rate (€/kg)."""
    if not company:
        company = frappe.defaults.get_user_default("company")
    cfg = _get_config(company)
    if lookback_days:
        cfg.operating_lookback_days = lookback_days
    return _get_operating_rate(company, cfg)


@frappe.whitelist()
def get_capital_rate(company=None, lookback_days=None):
    """Return just the capital rate (€/kg)."""
    if not company:
        company = frappe.defaults.get_user_default("company")
    cfg = _get_config(company)
    if lookback_days:
        cfg.capital_lookback_days = lookback_days
    return _get_capital_rate(company, cfg)


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _get_config(company):
    """Read blended rate configuration from Optimus General Settings.

    Operating and depreciation accounts must be configured manually in
    the settings (comma-separated account numbers).  No auto-detection —
    manual setup ensures you know exactly which accounts are included.
    """
    settings = frappe.get_single("Optimus General Settings")

    operating_accounts = _parse_account_list(settings.operating_accounts)
    depreciation_accounts = _parse_account_list(settings.depreciation_accounts)

    if not operating_accounts:
        frappe.msgprint(
            "Operating P&L Accounts are not configured in Optimus General Settings. "
            "The Operating Rate will be 0 until you add account numbers.",
            title="Operating Accounts Missing",
            indicator="orange",
        )

    if not depreciation_accounts:
        frappe.msgprint(
            "Depreciation P&L Accounts are not configured in Optimus General Settings. "
            "The Capital Rate will be 0 until you add account numbers.",
            title="Depreciation Accounts Missing",
            indicator="orange",
        )

    return frappe._dict(
        operating_lookback_days=max(settings.operating_lookback_days or 90, 30),
        operating_half_life_days=settings.operating_half_life_days or 30,
        capital_lookback_days=settings.capital_lookback_days or 365,
        operating_accounts=operating_accounts,
        depreciation_accounts=depreciation_accounts,
        default_target_margin_pct=settings.default_target_margin_pct or 6,
        item_group=settings.item_group or "Potatoes",
        uom=settings.uom or "Kg",
        sanity_check_max=settings.sanity_check_max_operating_rate or 0.20,
        sanity_check_min=settings.sanity_check_min_operating_rate or 0.02,
        stability_threshold=settings.rate_stability_threshold_pct or 30,
        reconciliation_threshold=settings.reconciliation_variance_threshold_pct or 5,
    )


def _parse_account_list(text):
    """Parse comma-separated account numbers into a list."""
    if not text:
        return []
    return [a.strip() for a in text.split(",") if a.strip()]


def _get_operating_rate(company, cfg):
    """Calculate operating rate: exponential weighted average of daily P&L ÷ kg."""
    if not cfg.operating_accounts:
        frappe.msgprint("No operating accounts configured in Optimus General Settings. Operating Rate = 0.")
        return 0.0

    from_date = add_days(today(), -cfg.operating_lookback_days)
    daily_gl = _get_daily_gl_totals(company, cfg.operating_accounts, from_date, today())
    daily_kg = _get_daily_kg(company, from_date, today(), cfg)

    # Merge GL and kg data into daily rates
    daily_rates = _build_daily_rates(daily_gl, daily_kg)

    if not daily_rates:
        return 0.0

    return _exponential_weighted_average(daily_rates, cfg.operating_half_life_days)


def _get_capital_rate(company, cfg):
    """Calculate capital rate: annual depreciation ÷ annual kg.

    Uses a simple average (fixed cost ÷ annual volume).  If no depreciation
    accounts are configured, returns 0.0.
    """
    if not cfg.depreciation_accounts:
        return 0.0

    from_date = add_days(today(), -cfg.capital_lookback_days)
    total_depreciation = _get_gl_sum(company, cfg.depreciation_accounts, from_date, today())
    total_kg = _get_total_kg_sold(company, cfg.capital_lookback_days, cfg)

    if not total_kg or total_kg == 0:
        return 0.0

    return round(total_depreciation / total_kg, 6)


def _get_daily_gl_totals(company, account_numbers, from_date, to_date):
    """Get sum of debit - credit per day for given account numbers.

    Returns dict { 'YYYY-MM-DD': total_amount }.
    """
    if not account_numbers:
        return {}

    placeholders = ", ".join(["%s"] * len(account_numbers))
    rows = frappe.db.sql(
        f"""
        SELECT
            DATE(gl.posting_date) AS day,
            GREATEST(SUM(gl.debit - gl.credit), 0) AS total
        FROM `tabGL Entry` gl
        INNER JOIN `tabAccount` acc ON acc.name = gl.account
        WHERE acc.company = %s
          AND acc.account_number IN ({placeholders})
          AND gl.posting_date BETWEEN %s AND %s
          AND gl.is_cancelled = 0
        GROUP BY DATE(gl.posting_date)
        ORDER BY day
        """,
        [company] + account_numbers + [from_date, to_date],
        as_dict=True,
    )

    return {row.day: row.total for row in rows}


def _get_gl_sum(company, account_numbers, from_date, to_date):
    """Get total sum of debit - credit for given accounts over period."""
    if not account_numbers:
        return 0.0

    placeholders = ", ".join(["%s"] * len(account_numbers))
    row = frappe.db.sql(
        f"""
        SELECT GREATEST(SUM(gl.debit - gl.credit), 0) AS total
        FROM `tabGL Entry` gl
        INNER JOIN `tabAccount` acc ON acc.name = gl.account
        WHERE acc.company = %s
          AND acc.account_number IN ({placeholders})
          AND gl.posting_date BETWEEN %s AND %s
          AND gl.is_cancelled = 0
        """,
        [company] + account_numbers + [from_date, to_date],
        as_dict=True,
    )

    return flt(row[0].total) if row else 0.0


def _get_daily_kg(company, from_date, to_date, cfg=None):
    """Get total kg sold per day from submitted Sales Invoices,
    filtered by configured Item Group and UOM.

    Returns dict { 'YYYY-MM-DD': total_qty }.
    """
    if not cfg:
        cfg = _get_config(company)
    rows = frappe.db.sql(
        """
        SELECT
            DATE(si.posting_date) AS day,
            SUM(sii.qty) AS total_qty
        FROM `tabSales Invoice Item` sii
        INNER JOIN `tabSales Invoice` si ON si.name = sii.parent
        INNER JOIN `tabItem` item ON item.name = sii.item_code
        WHERE si.docstatus = 1
          AND si.company = %s
          AND si.posting_date BETWEEN %s AND %s
          AND item.item_group = %s
          AND sii.uom = %s
        GROUP BY DATE(si.posting_date)
        ORDER BY day
        """,
        values=[company, from_date, to_date, cfg.item_group, cfg.uom],
        as_dict=True,
    )

    return {row.day: row.total_qty for row in rows}


def _get_total_kg_sold(company, lookback_days, cfg=None):
    """Get total kg from all submitted SIs in the lookback period,
    filtered by configured Item Group and UOM."""
    if not cfg:
        cfg = _get_config(company)
    row = frappe.db.sql(
        """
        SELECT SUM(sii.qty) AS total
        FROM `tabSales Invoice Item` sii
        INNER JOIN `tabSales Invoice` si ON si.name = sii.parent
        INNER JOIN `tabItem` item ON item.name = sii.item_code
        WHERE si.docstatus = 1
          AND si.company = %s
          AND si.posting_date >= %s
          AND item.item_group = %s
          AND sii.uom = %s
          AND sii.qty > 0
        """,
        values=[company, add_days(today(), -lookback_days), cfg.item_group, cfg.uom],
        as_dict=True,
    )
    return flt(row[0].total) if row else 0.0


def _build_daily_rates(daily_gl, daily_kg):
    """Merge GL totals and kg into per-day rates.

    Skips days with 0 kg.  Returns list of dicts: {day, gl_total, kg, rate}.
    """
    all_days = set(list(daily_gl.keys()) + list(daily_kg.keys()))
    rates = []
    for day in sorted(all_days):
        kg = daily_kg.get(day, 0)
        gl = daily_gl.get(day, 0)
        if kg <= 0:
            continue  # Skip zero/negative kg days (credit notes, returns)
        rates.append(
            frappe._dict(
                day=day,
                gl_total=gl,
                kg=kg,
                rate=gl / kg,
            )
        )
    return rates


def _exponential_weighted_average(daily_rates, half_life_days):
    """Calculate exponential time-decay weighted average.

    Formula:
        weighted_rate = Σ(rate_day × e^(−λ × days_ago)) / Σ(e^(−λ × days_ago))
        where λ = ln(2) / half_life_days

    More recent days get higher weight.
    """
    if not daily_rates:
        return 0.0

    lam = ln(2) / max(half_life_days, 1)
    latest_day = daily_rates[-1].day

    numerator = 0.0
    denominator = 0.0

    for dr in daily_rates:
        days_ago = date_diff(latest_day, dr.day)
        weight = exp(-lam * max(days_ago, 0))
        numerator += dr.rate * weight
        denominator += weight

    return round(numerator / denominator, 6) if denominator else 0.0


def _run_sanity_checks(result, cfg):
    """Run configured sanity checks on the calculated rate.

    Returns list of warning messages (empty = all checks passed).
    """
    warnings = []
    op = result.get("operating_rate", 0)

    # Ceiling check
    if cfg.sanity_check_max and op > cfg.sanity_check_max:
        warnings.append(
            f"Operating rate ({op:.4f}€/kg) exceeds max threshold "
            f"({cfg.sanity_check_max:.2f}€/kg). Check account configuration."
        )

    # Floor check
    if cfg.sanity_check_min and op > 0 and op < cfg.sanity_check_min:
        warnings.append(
            f"Operating rate ({op:.4f}€/kg) is below min threshold "
            f"({cfg.sanity_check_min:.2f}€/kg). Possible missing GL data."
        )

    # Stability check vs trailing 3-month average
    if cfg.stability_threshold and op > 0:
        prev_rate = _get_previous_month_operating_rate(result.get("company"), cfg)
        if prev_rate and prev_rate > 0:
            change_pct = abs(op - prev_rate) / prev_rate * 100
            if change_pct > cfg.stability_threshold:
                warnings.append(
                    f"Operating rate changed {change_pct:.1f}% month-over-month "
                    f"(threshold: {cfg.stability_threshold}%). Flagged for review."
                )

    # Reconciliation check: imputed total vs actual GL over the operating lookback period.
    # Uses only the operating rate (not capital) since the lookback windows differ.
    if cfg.reconciliation_threshold and result.get("operating_rate", 0) > 0:
        company = result.get("company")
        from_date = add_days(today(), -cfg.operating_lookback_days)
        lookback_kg = _get_total_kg_sold(company, cfg.operating_lookback_days, cfg)
        if cfg.operating_accounts and lookback_kg > 0:
            actual_gl = _get_gl_sum(company, cfg.operating_accounts, from_date, today())
            imputed = result["operating_rate"] * lookback_kg
            if actual_gl > 0:
                variance_pct = abs(imputed - actual_gl) / actual_gl * 100
                if variance_pct > cfg.reconciliation_threshold:
                    warnings.append(
                        f"Reconciliation variance: imputed ({imputed:.2f}€) vs actual GL "
                        f"({actual_gl:.2f}€) differs by {variance_pct:.1f}% "
                        f"(threshold: {cfg.reconciliation_threshold}%). Review account configuration."
                    )

    return warnings


def _get_previous_month_operating_rate(company, cfg):
    """Get operating rate from previous month's snapshot for stability check."""
    last_month = add_days(today(), -30)
    snapshot = frappe.db.get_value(
        "Blended Rate Snapshot",
        {"snapshot_date": ["<=", last_month], "calculated_by": ["!=", ""]},
        "operating_rate",
        order_by="snapshot_date DESC",
    )
    return flt(snapshot) if snapshot else None


def _get_cached(company):
    """Return cached rate if less than 24 hours old."""
    snapshots = frappe.get_all(
        "Blended Rate Snapshot",
        filters={},
        fields=["*"],
        order_by="snapshot_date DESC",
        limit=1,
    )
    if not snapshots:
        return None

    snap = snapshots[0]
    # Check if snapshot is from today (cached)
    if str(snap.snapshot_date) == str(today()):
        return {
            "company": company,
            "operating_rate": snap.operating_rate,
            "capital_rate": snap.capital_rate,
            "base_rate": snap.base_rate,
            "operating_lookback_days": snap.lookback_days_operating,
            "capital_lookback_days": snap.lookback_days_capital,
            "total_kg": snap.total_kg,
            "calculated_by": "cached",
            "timestamp": str(snap.timestamp) if snap.timestamp else "",
            "sanity_warnings": [],
        }

    return None


def _create_snapshot(company, result):
    """Create a Blended Rate Snapshot document."""
    try:
        snap = frappe.get_doc(
            {
                "doctype": "Blended Rate Snapshot",
                "snapshot_date": today(),
                "operating_rate": result.get("operating_rate", 0),
                "capital_rate": result.get("capital_rate", 0),
                "base_rate": result.get("base_rate", 0),
                "total_kg": result.get("total_kg", 0),
                "lookback_days_operating": result.get("operating_lookback_days", 90),
                "lookback_days_capital": result.get("capital_lookback_days", 365),
                "calculated_by": frappe.session.user,
                "timestamp": now_datetime(),
            }
        )
        snap.insert(ignore_permissions=True)
    except Exception as e:
        frappe.log_error(
            message=f"Failed to create Blended Rate Snapshot: {e}",
            title="Blended Rate Snapshot Error",
        )
