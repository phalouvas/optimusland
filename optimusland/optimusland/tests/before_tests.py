# Copyright (c) 2026, KAINOTOMO PH LTD and Contributors
# See license.txt

"""Runs once before all tests in the test_ database.

This function is invoked by the `before_tests` hook in hooks.py.
It ensures minimum test data exists so individual tests don't each
need to create their own Company, Item, BOM, etc.

This runs ONLY in the ephemeral test database — never in production.
"""

import frappe
from optimusland.optimusland.tests import (
	get_or_create_test_company,
	get_or_create_test_warehouse,
	get_or_create_test_supplier,
	get_or_create_test_customer,
	get_or_create_test_potato_item,
)


def _seed_stock(item_code, warehouse, qty, company):
	"""Create a stock entry to add initial stock for a test item."""
	if frappe.db.exists("Stock Entry", {"stock_entry_type": "Material Receipt", "docstatus": 1}):
		return  # already seeded

	se = frappe.get_doc({
		"doctype": "Stock Entry",
		"stock_entry_type": "Material Receipt",
		"company": company,
		"set_posting_time": 1,
		"posting_date": frappe.utils.today(),
		"items": [{
			"item_code": item_code,
			"qty": qty,
			"basic_rate": 1.0,
			"basic_amount": qty * 1.0,
			"t_warehouse": warehouse,
			"uom": frappe.db.get_value("Item", item_code, "stock_uom"),
			"conversion_factor": 1.0,
		}],
	})
	se.insert(ignore_permissions=True)
	se.submit()


def before_tests():
	"""Seed minimum test data shared across all test modules."""
	# Enable Serial and Batch Bundle support (ERPNext v16 requirement)
	frappe.db.set_single_value("Stock Settings", "enable_serial_and_batch_no_for_item", 1)

	# Ensure custom_production_plan field exists on Purchase Receipt
	if not frappe.db.exists("Custom Field",
		{"dt": "Purchase Receipt", "fieldname": "custom_production_plan"}):
		frappe.get_doc({
			"doctype": "Custom Field",
			"dt": "Purchase Receipt",
			"fieldname": "custom_production_plan",
			"fieldtype": "Link",
			"label": "Production Plan",
			"options": "Production Plan",
			"read_only": 1,
			"insert_after": "custom_weight_slip",
			"module": "Optimusland",
		}).insert(ignore_permissions=True)
		frappe.db.commit()

	# Ensure custom_weight_slip field exists on Batch
	if not frappe.db.exists("Custom Field",
		{"dt": "Batch", "fieldname": "custom_weight_slip"}):
		frappe.get_doc({
			"doctype": "Custom Field",
			"dt": "Batch",
			"fieldname": "custom_weight_slip",
			"fieldtype": "Link",
			"label": "Weight Slip",
			"options": "Weight Slip",
			"read_only": 1,
			"insert_after": "custom_supplier_optimus",
			"module": "Optimusland",
		}).insert(ignore_permissions=True)
		frappe.db.commit()

	company = get_or_create_test_company()
	warehouse = get_or_create_test_warehouse(company.name)
	get_or_create_test_supplier(company.name)
	get_or_create_test_customer(company.name)
	potato_item = get_or_create_test_potato_item(company.name)

	# Seed stock for BOM components so Production Plan → Work Order →
	# Material Transfer stock entries don't fail with NegativeStockError
	from optimusland.optimusland.tests import get_or_create_test_packaging_item
	packaging = get_or_create_test_packaging_item(company.name)
	company_abbr = frappe.db.get_value("Company", company.name, "abbr")
	stores_warehouse = f"Stores - {company_abbr}"
	_seed_stock(packaging.item_code, stores_warehouse, 10000, company.name)
