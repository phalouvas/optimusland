# Copyright (c) 2026, KAINOTOMO PH LTD and contributors
# For license information, please see license.txt

import frappe
from frappe import _, scrub
from frappe.utils import flt, today, add_days


def execute(filters=None):
	if not filters:
		filters = frappe._dict()

	columns = get_columns()
	data = get_data(filters)
	return columns, data


def get_columns():
	return [
		{
			"label": _("Sales Invoice"),
			"fieldtype": "Link",
			"fieldname": "sales_invoice",
			"options": "Sales Invoice",
			"width": 140,
		},
		{
			"label": _("Date"),
			"fieldtype": "Date",
			"fieldname": "posting_date",
			"width": 90,
		},
		{
			"label": _("Customer"),
			"fieldtype": "Link",
			"fieldname": "customer",
			"options": "Customer",
			"width": 120,
		},
		{
			"label": _("Product"),
			"fieldtype": "Link",
			"fieldname": "item_code",
			"options": "Item",
			"width": 140,
		},
		{
			"label": _("Batch No"),
			"fieldtype": "Link",
			"fieldname": "batch_no",
			"options": "Batch",
			"width": 160,
		},
		{
			"label": _("Supplier"),
			"fieldtype": "Link",
			"fieldname": "supplier",
			"options": "Supplier",
			"width": 120,
		},
		{
			"label": _("Weight Slip"),
			"fieldtype": "Link",
			"fieldname": "weight_slip",
			"options": "Weight Slip",
			"width": 110,
		},
		{
			"label": _("Kilos"),
			"fieldtype": "Float",
			"fieldname": "qty",
			"precision": 1,
			"width": 80,
		},
		{
			"label": _("Sale Price (€/kg)"),
			"fieldtype": "Float",
			"fieldname": "selling_rate",
			"precision": 3,
			"width": 100,
		},
		{
			"label": _("Total Sale (€)"),
			"fieldtype": "Float",
			"fieldname": "selling_amount",
			"precision": 2,
			"width": 110,
		},
		{
			"label": _("Suggested Supplier Price (€/kg)"),
			"fieldtype": "Float",
			"fieldname": "formula_price",
			"precision": 4,
			"width": 120,
		},
		{
			"label": _("Paid to Supplier (€/kg)"),
			"fieldtype": "Float",
			"fieldname": "actual_price",
			"precision": 4,
			"width": 110,
		},
		{
			"label": _("Margin %"),
			"fieldtype": "Percent",
			"fieldname": "margin_achieved",
			"precision": 1,
			"width": 80,
		},
		{
			"label": _("Purchase Invoice"),
			"fieldtype": "Link",
			"fieldname": "purchase_invoice",
			"options": "Purchase Invoice",
			"width": 140,
		},
	]


def get_data(filters):
	"""Get all SIs with Potato items within the date range,
	calculate formula price, and show actual paid price from PI."""

	# Read item_group and uom from settings (with defaults)
	settings = frappe.get_single("Optimus General Settings")
	item_group = settings.item_group or "Potatoes"
	uom = settings.uom or "Kg"

	conditions = _build_conditions(filters)

	# Get SIs with filtered items
	sis = frappe.db.sql(
		f"""
		SELECT
			si.name AS sales_invoice,
			si.posting_date,
			si.customer,
			sii.name AS si_item_name,
			sii.item_code,
			sii.qty,
			sii.net_rate AS selling_rate,
			sii.amount AS selling_amount,
			sbe.batch_no
		FROM `tabSales Invoice` si
		INNER JOIN `tabSales Invoice Item` sii ON sii.parent = si.name
		INNER JOIN `tabItem` item ON item.name = sii.item_code
		LEFT JOIN `tabDelivery Note Item` dni ON dni.name = sii.dn_detail
		LEFT JOIN `tabSerial and Batch Entry` sbe ON sbe.parent = dni.serial_and_batch_bundle
		WHERE si.docstatus = 1
			AND si.company = %(company)s
			AND si.posting_date BETWEEN %(from_date)s AND %(to_date)s
			AND item.item_group = %(item_group)s
			AND sii.uom = %(uom)s
			{conditions}
		ORDER BY si.posting_date DESC, si.name
		""",
		{**filters, "item_group": item_group, "uom": uom},
		as_dict=True,
	)

	if not sis:
		return []

	# Collect unique batch numbers
	batch_nos = list({s.batch_no for s in sis if s.batch_no})

	# Get grower info from batches
	grower_map = {}
	ws_map = {}
	if batch_nos:
		batches = frappe.db.get_all(
			"Batch",
			filters={"name": ["in", batch_nos]},
			fields=["name", "custom_supplier_optimus", "custom_weight_slip"],
		)
		for b in batches:
			grower_map[b.name] = b.custom_supplier_optimus
			ws_map[b.name] = b.custom_weight_slip

	# Get actual paid prices from PIs for these batches
	actual_map = {}
	if batch_nos:
		pi_prices = frappe.db.sql(
			"""
			SELECT
				sbe.batch_no,
				pii.rate AS paid_rate,
				pi.name AS pi_name
			FROM `tabPurchase Invoice Item` pii
			INNER JOIN `tabPurchase Invoice` pi ON pi.name = pii.parent AND pi.docstatus = 1
			INNER JOIN `tabPurchase Receipt Item` pri ON pri.name = pii.pr_detail
			LEFT JOIN `tabSerial and Batch Entry` sbe ON sbe.parent = pri.serial_and_batch_bundle
			WHERE sbe.batch_no IN %(batch_nos)s
			ORDER BY pi.posting_date DESC
			""",
			{"batch_nos": tuple(batch_nos)},
			as_dict=True,
		)
		for p in pi_prices:
			if p.batch_no and p.batch_no not in actual_map:
				actual_map[p.batch_no] = {
					"rate": p.paid_rate,
					"pi": p.pi_name,
				}

	# Get current base rate for formula calculation
	from optimusland.utils.blended_rate import get_base_rate

	base = get_base_rate(filters.get("company"))
	op_rate = flt(base.get("operating_rate", 0))
	cap_rate = flt(base.get("capital_rate", 0))
	base_rate = op_rate + cap_rate

	# Default margin
	margin_pct = flt(frappe.db.get_single_value("Optimus General Settings", "default_target_margin_pct")) or 6

	results = []
	for s in sis:
		batch = s.batch_no
		grower = grower_map.get(batch) if batch else None
		ws = ws_map.get(batch) if batch else None

		# Formula price = selling × (1 - margin%) - base_rate
		selling = flt(s.selling_rate)
		margin_amt = selling * (margin_pct / 100)
		formula = round(max(selling - margin_amt - base_rate, 0), 4)

		actual_info = actual_map.get(batch, {})
		actual = flt(actual_info.get("rate"))
		pi_name = actual_info.get("pi")

		# Calculate actual margin % when PI exists (colored via JS formatter)
		if actual > 0:
			margin_achieved = round((selling - actual - base_rate) / selling * 100, 1) if selling > 0 else None
		else:
			margin_achieved = None

		results.append({
			"sales_invoice": s.sales_invoice,
			"posting_date": s.posting_date,
			"customer": s.customer,
			"item_code": s.item_code,
			"batch_no": batch,
			"supplier": grower,
			"weight_slip": ws,
			"qty": flt(s.qty),
			"selling_rate": selling,
			"selling_amount": flt(s.selling_amount),
			"formula_price": formula,
			"actual_price": actual,
			"margin_achieved": margin_achieved,
			"purchase_invoice": pi_name,
		})

	return results


def _build_conditions(filters):
	conditions = ""
	if filters.get("supplier"):
		conditions += f"""
			AND sbe.batch_no IN (
				SELECT name FROM tabBatch
				WHERE custom_supplier_optimus = %(supplier)s
			)
		"""
	if filters.get("customer"):
		conditions += " AND si.customer = %(customer)s"
	if filters.get("batch_no"):
		conditions += " AND sbe.batch_no LIKE %(batch_no)s"
		filters.batch_no = f"%{filters.batch_no}%"
	if filters.get("sales_invoice"):
		conditions += " AND si.name = %(sales_invoice)s"
	return conditions
