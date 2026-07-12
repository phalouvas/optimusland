# Copyright (c) 2026, KAINOTOMO PH LTD and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.utils import flt


def execute(filters=None):
	if not filters:
		filters = frappe._dict()

	columns = get_columns()
	data = get_data(filters)
	return columns, data


def get_columns():
	return [
		{
			"label": _("Customer"),
			"fieldtype": "Link",
			"fieldname": "customer",
			"options": "Customer",
			"width": 200,
		},
		{
			"label": _("Kilos"),
			"fieldtype": "Float",
			"fieldname": "qty",
			"precision": 1,
			"width": 90,
		},
		{
			"label": _("Avg Sale (€/kg)"),
			"fieldtype": "Float",
			"fieldname": "selling_rate",
			"precision": 3,
			"width": 100,
		},
		{
			"label": _("Revenue (€)"),
			"fieldtype": "Currency",
			"fieldname": "selling_amount",
			"options": "currency",
			"width": 120,
		},
		{
			"label": _("Avg Suggested (€/kg)"),
			"fieldtype": "Float",
			"fieldname": "formula_price",
			"precision": 4,
			"width": 110,
		},
		{
			"label": _("Avg Paid (€/kg)"),
			"fieldtype": "Float",
			"fieldname": "actual_price",
			"precision": 4,
			"width": 100,
		},
		{
			"label": _("Margin %"),
			"fieldtype": "Percent",
			"fieldname": "margin_achieved",
			"precision": 1,
			"width": 80,
		},
		{
			"label": _("Profit (€)"),
			"fieldtype": "Currency",
			"fieldname": "profit_amount",
			"options": "currency",
			"width": 110,
		},
	]


def get_data(filters):
	"""Get detail rows from Base Rate, group by customer."""
	from optimusland.optimusland.report.base_rate.base_rate import get_data as base_get_data

	detail = base_get_data(filters)

	# Remove the auto totals row if present
	detail = [r for r in detail if r.get("sales_invoice") != "Total"]

	if not detail:
		return []

	# Count occurrences per SI item to deduplicate batch join inflation
	si_counts = {}
	for r in detail:
		si = r.get("si_item_name") or r["sales_invoice"]
		si_counts[si] = si_counts.get(si, 0) + 1

	# Group by customer
	groups = {}
	for r in detail:
		key = r.get("customer") or "_unknown"
		divider = si_counts.get(r.get("si_item_name") or r["sales_invoice"], 1)
		adj_qty = r["qty"] / divider
		adj_amount = r["selling_amount"] / divider

		if key not in groups:
			groups[key] = {"qty": 0, "revenue": 0, "formula_w": 0, "actual_w": 0, "margin_w": 0, "paid_qty": 0, "profit": 0}
		g = groups[key]
		g["qty"] += adj_qty
		g["revenue"] += adj_amount
		g["formula_w"] += r["formula_price"] * adj_qty
		if r["actual_price"] > 0 and r["profit_amount"] is not None:
			g["actual_w"] += r["actual_price"] * adj_qty
			g["paid_qty"] += adj_qty
			g["margin_w"] += r["margin_achieved"] * adj_qty
			g["profit"] += r["profit_amount"]

	results = []
	for customer, g in sorted(groups.items()):
		avg_sale = round(g["revenue"] / g["qty"], 3) if g["qty"] else 0
		avg_formula = round(g["formula_w"] / g["qty"], 4) if g["qty"] else 0
		if g["paid_qty"] > 0:
			avg_actual = round(g["actual_w"] / g["paid_qty"], 4)
			avg_margin = round(g["margin_w"] / g["paid_qty"], 1)
		else:
			avg_actual = 0
			avg_margin = None

		results.append({
			"customer": customer,
			"qty": round(g["qty"], 1),
			"selling_rate": avg_sale,
			"selling_amount": round(g["revenue"], 2),
			"formula_price": avg_formula,
			"actual_price": avg_actual,
			"margin_achieved": avg_margin,
			"profit_amount": round(g["profit"], 2) if g["paid_qty"] > 0 else None,
		})

	# Add totals row
	_add_totals(results)

	return results


def _add_totals(results):
	"""Append a grand total row."""
	if not results:
		return

	total_qty = sum(r["qty"] for r in results)
	total_revenue = sum(r["selling_amount"] for r in results)
	avg_sale = round(total_revenue / total_qty, 3) if total_qty else 0
	avg_formula = round(sum(r["formula_price"] * r["qty"] for r in results) / total_qty, 4) if total_qty else 0

	paid = [r for r in results if r["profit_amount"] is not None]
	if paid:
		paid_qty = sum(r["qty"] for r in paid)
		avg_actual = round(sum(r["actual_price"] * r["qty"] for r in paid) / paid_qty, 4)
		avg_margin = round(sum(r["margin_achieved"] * r["qty"] for r in paid) / paid_qty, 1)
		total_profit = round(sum(r["profit_amount"] for r in paid), 2)
	else:
		avg_actual = 0
		avg_margin = None
		total_profit = None

	results.append({
		"customer": "Total",
		"qty": round(total_qty, 1),
		"selling_rate": avg_sale,
		"selling_amount": round(total_revenue, 2),
		"formula_price": avg_formula,
		"actual_price": avg_actual,
		"margin_achieved": avg_margin,
		"profit_amount": total_profit,
	})
