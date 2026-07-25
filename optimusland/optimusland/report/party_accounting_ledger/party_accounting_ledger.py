# Copyright (c) 2026, KAINOTOMO PH LTD and contributors
# For license information, please see license.txt

"""Party Accounting Ledger Report.

A consolidated chronological ledger for dual-role parties (Supplier + Customer)
that are linked via ``Party Link``. Shows all transactions on both sides
as a single running-balance statement, plus an opening/closing balance summary.

For parties *without* a Party Link, the report falls back gracefully to a
standard single-sided AR or AP ledger.
"""

import frappe
from frappe import _
from frappe.utils import flt, getdate, today
from erpnext.accounts.utils import get_balance_on


def execute(filters=None):
	if not filters:
		filters = frappe._dict()

	columns = get_columns()
	data = get_data(filters)
	return columns, data


def get_columns():
	"""Define the columns for the report."""
	return [
		{
			"label": _("Posting Date"),
			"fieldname": "posting_date",
			"fieldtype": "Date",
			"width": 100,
		},
		{
			"label": _("Voucher Type"),
			"fieldname": "voucher_type",
			"fieldtype": "Data",
			"width": 140,
		},
		{
			"label": _("Voucher No"),
			"fieldname": "voucher_no",
			"fieldtype": "Dynamic Link",
			"options": "voucher_type",
			"width": 160,
		},
		{
			"label": _("Party"),
			"fieldname": "party",
			"fieldtype": "Data",
			"width": 180,
		},
		{
			"label": _("Role"),
			"fieldname": "role",
			"fieldtype": "Data",
			"width": 100,
		},
		{
			"label": _("Debit (€)"),
			"fieldname": "debit",
			"fieldtype": "Currency",
			"options": "currency",
			"width": 120,
		},
		{
			"label": _("Credit (€)"),
			"fieldname": "credit",
			"fieldtype": "Currency",
			"options": "currency",
			"width": 120,
		},
		{
			"label": _("Balance (€)"),
			"fieldname": "balance",
			"fieldtype": "Currency",
			"options": "currency",
			"width": 130,
		},
		{
			"label": _("Against Voucher"),
			"fieldname": "against_voucher",
			"fieldtype": "Data",
			"width": 160,
		},
		{
			"label": _("Remarks"),
			"fieldname": "remarks",
			"fieldtype": "Data",
			"width": 250,
		},
	]


def get_data(filters):
	"""Build the report data rows."""
	party_link_name = filters.get("party_link")
	from_date = filters.get("from_date")
	to_date = filters.get("to_date", today())
	company = filters.get("company") or frappe.defaults.get_user_default("Company")

	if not party_link_name:
		return []

	# Resolve the Party Link to get supplier and customer names
	link = frappe.db.get_value(
		"Party Link",
		party_link_name,
		["primary_role", "primary_party", "secondary_role", "secondary_party"],
		as_dict=True,
	)

	if not link:
		return []

	supplier_name = None
	customer_name = None
	display_party = ""

	if link.primary_role == "Supplier":
		supplier_name = link.primary_party
		customer_name = link.secondary_party
		display_party = f"{link.primary_party} ({_('Supplier')}) / {link.secondary_party} ({_('Customer')})"
	else:
		supplier_name = link.secondary_party
		customer_name = link.primary_party
		display_party = f"{link.secondary_party} ({_('Supplier')}) / {link.primary_party} ({_('Customer')})"

	if not from_date:
		# Default to start of the current fiscal year
		from_date = _get_fiscal_year_start(company, to_date)

	# ── Opening balance (before from_date) ──────────────────────────────

	opening_balance = _compute_opening_balance(
		supplier_name, customer_name, company, from_date
	)

	# ── Transaction rows (from_date to to_date) ─────────────────────────

	rows = _get_gl_entries(supplier_name, customer_name, company, from_date, to_date)

	# ── Build the result ────────────────────────────────────────────────

	data = []
	running_balance = opening_balance

	# Opening balance row
	data.append({
		"posting_date": from_date,
		"voucher_type": "",
		"voucher_no": "",
		"party": display_party,
		"role": "",
		"debit": 0,
		"credit": 0,
		"balance": opening_balance,
		"against_voucher": "",
		"remarks": _("Opening Balance"),
		"is_opening": 1,
	})

	for row in rows:
		running_balance += row["net_contribution"]
		data.append({
			"posting_date": row["posting_date"],
			"voucher_type": row["voucher_type"],
			"voucher_no": row["voucher_no"],
			"party": row["party"],
			"role": row["role"],
			"debit": row["debit"],
			"credit": row["credit"],
			"balance": running_balance,
			"against_voucher": row["against_voucher"] or "",
			"remarks": row["remarks"] or "",
		})

	# ── Summary / closing balance row ───────────────────────────────────

	total_debit = sum(r["debit"] for r in rows)
	total_credit = sum(r["credit"] for r in rows)
	closing_balance = running_balance

	data.append({
		"posting_date": "",
		"voucher_type": "",
		"voucher_no": "",
		"party": "",
		"role": "",
		"debit": total_debit,
		"credit": total_credit,
		"balance": closing_balance,
		"against_voucher": "",
		"remarks": _("Closing Balance"),
		"is_closing": 1,
		"indent": 0,
	})

	# ── Net position row (only when both roles exist) ───────────────────
	if supplier_name and customer_name:
		net_label = _get_net_label(closing_balance, supplier_name, customer_name)
		data.append({
			"posting_date": "",
			"voucher_type": "",
			"voucher_no": "",
			"party": "",
			"role": "",
			"debit": 0,
			"credit": 0,
			"balance": abs(closing_balance),
			"against_voucher": "",
			"remarks": f"**{net_label}**",
			"is_net_position": 1,
			"indent": 0,
		})

	return data


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _compute_opening_balance(supplier_name, customer_name, company, from_date):
	"""Compute the net position strictly before from_date.

	Uses ``get_balance_on`` from ERPNext which returns ``sum(debit) - sum(credit)``
	**up to and including** the given date. To avoid double-counting transactions
	on ``from_date`` (which are also fetched by ``_get_gl_entries``), we pass
	the day before ``from_date`` to get the balance strictly before the period.

	We convert to our sign convention where positive = we owe the party.
	"""
	from frappe.utils import add_days

	# Balance strictly before from_date (exclusive)
	cutoff_date = add_days(from_date, -1) if from_date else None

	opening = 0.0

	if supplier_name and cutoff_date:
		# get_balance_on for Payable returns negative (normal credit balance)
		supplier_gl = get_balance_on(
			party_type="Supplier",
			party=supplier_name,
			account_type="Payable",
			company=company,
			date=cutoff_date,
		)
		# Flip sign so positive = we owe supplier
		opening += -supplier_gl

	if customer_name and cutoff_date:
		# get_balance_on for Receivable returns positive (normal debit balance)
		customer_gl = get_balance_on(
			party_type="Customer",
			party=customer_name,
			account_type="Receivable",
			company=company,
			date=cutoff_date,
		)
		# Subtract because customer owing us is negative in our convention
		opening -= customer_gl

	return opening


def _get_gl_entries(supplier_name, customer_name, company, from_date, to_date):
	"""Fetch GL entries for both supplier and customer roles, sorted by date.

	Each entry's ``net_contribution`` is computed as ``credit - debit``,
	so positive values increase the "we owe the party" balance.

	Returns a list of dicts sorted by posting_date, voucher_no.
	"""
	entries = []

	if supplier_name:
		supplier_entries = frappe.db.sql(
			"""
			SELECT
				gle.posting_date,
				gle.voucher_type,
				gle.voucher_no,
				gle.party AS party,
				gle.debit,
				gle.credit,
				gle.against_voucher,
				gle.remarks
			FROM `tabGL Entry` gle
			WHERE gle.party_type = 'Supplier'
				AND gle.party = %s
				AND gle.company = %s
				AND gle.posting_date >= %s
				AND gle.posting_date <= %s
				AND gle.is_cancelled = 0
			ORDER BY gle.posting_date, gle.voucher_no
			""",
			(supplier_name, company, from_date, to_date),
			as_dict=True,
		)
		for e in supplier_entries:
			entries.append({
				"posting_date": e.posting_date,
				"voucher_type": e.voucher_type,
				"voucher_no": e.voucher_no,
				"party": e.party,
				"role": _("As Supplier"),
				"debit": flt(e.debit),
				"credit": flt(e.credit),
				"net_contribution": flt(e.credit) - flt(e.debit),
				"against_voucher": e.against_voucher,
				"remarks": e.remarks,
			})

	if customer_name:
		customer_entries = frappe.db.sql(
			"""
			SELECT
				gle.posting_date,
				gle.voucher_type,
				gle.voucher_no,
				gle.party AS party,
				gle.debit,
				gle.credit,
				gle.against_voucher,
				gle.remarks
			FROM `tabGL Entry` gle
			WHERE gle.party_type = 'Customer'
				AND gle.party = %s
				AND gle.company = %s
				AND gle.posting_date >= %s
				AND gle.posting_date <= %s
				AND gle.is_cancelled = 0
			ORDER BY gle.posting_date, gle.voucher_no
			""",
			(customer_name, company, from_date, to_date),
			as_dict=True,
		)
		for e in customer_entries:
			entries.append({
				"posting_date": e.posting_date,
				"voucher_type": e.voucher_type,
				"voucher_no": e.voucher_no,
				"party": e.party,
				"role": _("As Customer"),
				"debit": flt(e.debit),
				"credit": flt(e.credit),
				"net_contribution": flt(e.credit) - flt(e.debit),
				"against_voucher": e.against_voucher,
				"remarks": e.remarks,
			})

	# Sort chronologically
	entries.sort(key=lambda r: (r["posting_date"], r["voucher_no"] or ""))

	return entries


def _get_fiscal_year_start(company, for_date):
	"""Return the start date of the fiscal year containing for_date."""
	site_date = getdate(for_date)

	# Find the fiscal year that contains for_date
	fy_name = frappe.db.get_value(
		"Fiscal Year",
		[
			["year_start_date", "<=", site_date],
			["year_end_date", ">=", site_date],
		],
		"name",
		order_by="year_start_date DESC",
	)
	if fy_name:
		fy_start = frappe.db.get_value("Fiscal Year", fy_name, "year_start_date")
		if fy_start:
			return fy_start

	# Last resort: return January 1st of the for_date's year
	return site_date.replace(month=1, day=1)


def _get_net_label(net_balance, supplier_name, customer_name):
	"""Return a human-readable label for the net position."""
	if net_balance >= 0:
		return _("Net Position: Owed to Supplier ({0}) — €{1:,.2f}").format(
			supplier_name, abs(net_balance)
		)
	else:
		return _("Net Position: Owed by Customer ({0}) — €{1:,.2f}").format(
			customer_name, abs(net_balance)
		)
