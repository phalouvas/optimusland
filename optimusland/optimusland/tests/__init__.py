# Copyright (c) 2026, KAINOTOMO PH LTD and Contributors
# See license.txt

"""Shared test fixtures and factory functions for optimusland tests.

All factories check frappe.db.exists() before creating to ensure idempotency.
Test data is created in the ephemeral test_ database only — never in production.
"""

import frappe

# Declare global dependencies so IntegrationTestCase can auto-load them
global_test_dependencies = ["User", "Company", "Item", "Warehouse", "Supplier", "Customer"]


# ---------------------------------------------------------------------------
# Company
# ---------------------------------------------------------------------------

def get_or_create_test_company():
	"""Return the site's default company, creating it if needed."""
	company = frappe.defaults.get_user_default("Company")
	if company and frappe.db.exists("Company", company):
		return frappe.get_doc("Company", company)

	# Look up the first company in the DB (created by bench new-site / setup wizard)
	company_name = frappe.db.get_value("Company", {}, "name")
	if company_name:
		return frappe.get_doc("Company", company_name)

	# Last resort: create a minimal company via db_insert (bypasses
	# on_update hooks like create_default_warehouses which need
	# Warehouse Types, Chart of Accounts, etc. that don't exist in
	# a bare test database).
	company_name = "_Test Company"
	abbr = "_TC"

	if not frappe.db.exists("Company", company_name):
		from datetime import date
		today = date.today()
		fy_start = date(today.year, 1, 1)
		fy_end = date(today.year, 12, 31)
		fy_name = f"{today.year}"

		if not frappe.db.exists("Fiscal Year", fy_name):
			fy = frappe.get_doc({
				"doctype": "Fiscal Year",
				"year": fy_name,
				"year_start_date": fy_start,
				"year_end_date": fy_end,
			})
			fy.db_insert()

		company = frappe.get_doc({
			"doctype": "Company",
			"company_name": company_name,
			"abbr": abbr,
			"default_currency": "EUR",
			"country": "Greece",
			"domain": "Services",
			"chart_of_accounts": "Standard",
			"enable_perpetual_inventory": 1,
		})
		company.db_insert()

	return frappe.get_doc("Company", company_name)


# ---------------------------------------------------------------------------
# Warehouse
# ---------------------------------------------------------------------------

def get_or_create_test_warehouse(company=None):
	"""Return a test warehouse, creating it if needed."""
	if not company:
		company = get_or_create_test_company().name

	warehouse_name = f"Stores - {frappe.db.get_value('Company', company, 'abbr')}"
	if frappe.db.exists("Warehouse", warehouse_name):
		return frappe.get_doc("Warehouse", warehouse_name)

	if not frappe.db.exists("Warehouse", "_Test Warehouse"):
		wh = frappe.get_doc({
			"doctype": "Warehouse",
			"warehouse_name": "_Test Warehouse",
			"company": company,
		})
		wh.insert(ignore_permissions=True)
		return wh

	return frappe.get_doc("Warehouse", "_Test Warehouse")


# ---------------------------------------------------------------------------
# Supplier
# ---------------------------------------------------------------------------

def get_or_create_test_supplier(company=None):
	"""Return a test supplier, creating if needed."""
	if not company:
		company = get_or_create_test_company().name

	# Ensure a non-group Supplier Group exists
	supplier_group_name = "_Test Supplier Group"
	if not frappe.db.exists("Supplier Group", supplier_group_name):
		frappe.get_doc({
			"doctype": "Supplier Group",
			"supplier_group_name": supplier_group_name,
			"parent_supplier_group": "All Supplier Groups",
		}).insert(ignore_permissions=True)

	if not frappe.db.exists("Supplier", "_Test Supplier Optimus"):
		supplier = frappe.get_doc({
			"doctype": "Supplier",
			"supplier_name": "_Test Supplier Optimus",
			"supplier_group": supplier_group_name,
			"supplier_type": "Company",
			"country": frappe.db.get_value("Company", company, "country") or "Greece",
		})
		supplier.insert(ignore_permissions=True)
		return supplier

	return frappe.get_doc("Supplier", "_Test Supplier Optimus")


# ---------------------------------------------------------------------------
# Customer
# ---------------------------------------------------------------------------

def get_or_create_test_customer(company=None):
	"""Return a test customer, creating if needed."""
	if not company:
		company = get_or_create_test_company().name

	# Ensure a non-group Customer Group exists
	customer_group_name = "_Test Customer Group"
	if not frappe.db.exists("Customer Group", customer_group_name):
		frappe.get_doc({
			"doctype": "Customer Group",
			"customer_group_name": customer_group_name,
			"parent_customer_group": "All Customer Groups",
		}).insert(ignore_permissions=True)

	if not frappe.db.exists("Customer", "_Test Customer Optimus"):
		customer = frappe.get_doc({
			"doctype": "Customer",
			"customer_name": "_Test Customer Optimus",
			"customer_group": customer_group_name,
			"customer_type": "Company",
			"territory": "All Territories",
			"country": frappe.db.get_value("Company", company, "country") or "Greece",
		})
		customer.insert(ignore_permissions=True)
		return customer

	return frappe.get_doc("Customer", "_Test Customer Optimus")


# ---------------------------------------------------------------------------
# Items
# ---------------------------------------------------------------------------

def get_or_create_test_potato_item(company=None):
	"""Create a Potato item with has_batch_no=1, in 'Potatoes' item group."""
	if not company:
		company = get_or_create_test_company().name

	if frappe.db.exists("Item", "_Test Potato"):
		return frappe.get_doc("Item", "_Test Potato")

	# Ensure "Potatoes" item group exists
	if not frappe.db.exists("Item Group", "Potatoes"):
		frappe.get_doc({
			"doctype": "Item Group",
			"item_group_name": "Potatoes",
			"parent_item_group": "All Item Groups",
		}).insert(ignore_permissions=True)

	item = frappe.get_doc({
		"doctype": "Item",
		"item_code": "_Test Potato",
		"item_name": "_Test Potato",
		"item_group": "Potatoes",
		"is_stock_item": 1,
		"has_batch_no": 1,
		"create_new_batch": 1,
		"stock_uom": "Nos",
		"opening_stock": 0,
		"include_item_in_manufacturing": 1,
		"company": company,
	})
	item.insert(ignore_permissions=True)
	return item


def get_or_create_test_packaging_item(company=None):
	"""Create a non-potato packaging item (for BOM components)."""
	if not company:
		company = get_or_create_test_company().name

	if frappe.db.exists("Item", "_Test Packaging"):
		return frappe.get_doc("Item", "_Test Packaging")

	item = frappe.get_doc({
		"doctype": "Item",
		"item_code": "_Test Packaging",
		"item_name": "_Test Packaging",
		"item_group": "All Item Groups",
		"is_stock_item": 1,
		"has_batch_no": 0,
		"stock_uom": "Nos",
		"opening_stock": 0,
		"company": company,
	})
	item.insert(ignore_permissions=True)
	return item


# ---------------------------------------------------------------------------
# Bill of Materials
# ---------------------------------------------------------------------------

def get_or_create_test_bom(item_code, company=None):
	"""Create a BOM for the given item with packaging as a component.

	Only creates if no BOM exists for this item.
	"""
	if not company:
		company = get_or_create_test_company().name

	existing_bom = frappe.db.get_value("BOM", {"item": item_code, "is_active": 1, "docstatus": 1})
	if existing_bom:
		return frappe.get_doc("BOM", existing_bom)

	packaging_item = get_or_create_test_packaging_item(company)
	company_abbr = frappe.db.get_value("Company", company, "abbr")

	bom = frappe.get_doc({
		"doctype": "BOM",
		"item": item_code,
		"quantity": 1.0,
		"company": company,
		"is_active": 1,
		"is_default": 1,
		"currency": frappe.db.get_value("Company", company, "default_currency") or "EUR",
		"items": [
			{
				"item_code": packaging_item.item_code,
				"qty": 0.1,
				"rate": 0.50,
				"amount": 0.05,
				"stock_uom": packaging_item.stock_uom,
				"uom": packaging_item.stock_uom,
				"conversion_factor": 1.0,
				"company": company,
				"warehouse": f"Stores - {company_abbr}",
			}
		],
	})
	bom.insert(ignore_permissions=True)
	bom.submit()

	# Set as default BOM on the item
	frappe.db.set_value("Item", item_code, "default_bom", bom.name, update_modified=False)

	return bom


# ---------------------------------------------------------------------------
# Batch
# ---------------------------------------------------------------------------

def create_test_batch(item_code, supplier, prefix=None, manufacturing_date=None):
	"""Create a Batch with custom_supplier_optimus set.

	Returns the created or existing Batch document.
	"""
	if not manufacturing_date:
		manufacturing_date = frappe.utils.today()

	# Build a unique batch ID to avoid duplicates
	batch_id = f"{item_code} * {prefix or ''} * {manufacturing_date} * {supplier}"

	if frappe.db.exists("Batch", {"batch_id": batch_id}):
		return frappe.get_doc("Batch", {"batch_id": batch_id})

	batch = frappe.get_doc({
		"doctype": "Batch",
		"batch_id": batch_id,
		"item": item_code,
		"manufacturing_date": manufacturing_date,
		"custom_supplier_optimus": supplier,
		"custom_prefix": prefix or "",
	})
	batch.insert(ignore_permissions=True)
	return batch


# ---------------------------------------------------------------------------
# Purchase Receipt
# ---------------------------------------------------------------------------

def create_test_purchase_receipt(items_data, supplier=None, company=None, warehouse=None,
								 do_not_submit=False, posting_date=None):
	"""Create a Purchase Receipt with the given items.

	Args:
		items_data: List of dicts with keys: item_code, qty, rate[, batch_no, uom]
		supplier: Supplier name (defaults to _Test Supplier Optimus)
		company: Company name (defaults to site default)
		warehouse: Warehouse name (defaults to Stores)
		do_not_submit: If True, leave in Draft state
		posting_date: Posting date (defaults to today)
	"""
	if not supplier:
		supplier = get_or_create_test_supplier().name
	if not company:
		company = get_or_create_test_company().name
	if not warehouse:
		warehouse = get_or_create_test_warehouse(company).name
	if not posting_date:
		posting_date = frappe.utils.today()

	pr = frappe.get_doc({
		"doctype": "Purchase Receipt",
		"supplier": supplier,
		"company": company,
		"posting_date": posting_date,
		"set_posting_time": 1,
	})

	for item_data in items_data:
		item_doc = frappe.get_doc("Item", item_data["item_code"])
		pr.append("items", {
			"item_code": item_data["item_code"],
			"qty": item_data["qty"],
			"rate": item_data.get("rate", 0),
			"uom": item_data.get("uom", item_doc.stock_uom),
			"stock_uom": item_doc.stock_uom,
			"conversion_factor": 1.0,
			"warehouse": item_data.get("warehouse", warehouse),
			"batch_no": item_data.get("batch_no"),
		})

	pr.insert(ignore_permissions=True)

	if not do_not_submit:
		pr.submit()

	return pr


# ---------------------------------------------------------------------------
# Delivery Note
# ---------------------------------------------------------------------------

def create_test_delivery_note(items_data, customer=None, company=None, warehouse=None,
							  do_not_submit=False, posting_date=None):
	"""Create a Delivery Note with the given items."""
	if not customer:
		customer = get_or_create_test_customer().name
	if not company:
		company = get_or_create_test_company().name
	if not warehouse:
		warehouse = get_or_create_test_warehouse(company).name
	if not posting_date:
		posting_date = frappe.utils.today()

	dn = frappe.get_doc({
		"doctype": "Delivery Note",
		"customer": customer,
		"company": company,
		"posting_date": posting_date,
		"set_posting_time": 1,
	})

	total_amount = 0.0
	for item_data in items_data:
		item_doc = frappe.get_doc("Item", item_data["item_code"])
		amount = item_data.get("rate", 0) * item_data["qty"]
		total_amount += amount
		dn.append("items", {
			"item_code": item_data["item_code"],
			"qty": item_data["qty"],
			"rate": item_data.get("rate", 0),
			"amount": amount,
			"uom": item_data.get("uom", item_doc.stock_uom),
			"stock_uom": item_doc.stock_uom,
			"conversion_factor": 1.0,
			"warehouse": item_data.get("warehouse", warehouse),
			"batch_no": item_data.get("batch_no"),
		})

	dn.total = total_amount
	dn.insert(ignore_permissions=True)

	if not do_not_submit:
		dn.submit()

	return dn


# ---------------------------------------------------------------------------
# Sales Invoice
# ---------------------------------------------------------------------------

def create_test_sales_invoice(items_data, customer=None, company=None, warehouse=None,
							  do_not_submit=False, posting_date=None):
	"""Create a Sales Invoice with the given items."""
	if not customer:
		customer = get_or_create_test_customer().name
	if not company:
		company = get_or_create_test_company().name
	if not warehouse:
		warehouse = get_or_create_test_warehouse(company).name
	if not posting_date:
		posting_date = frappe.utils.today()

	si = frappe.get_doc({
		"doctype": "Sales Invoice",
		"customer": customer,
		"company": company,
		"posting_date": posting_date,
		"set_posting_time": 1,
		"due_date": posting_date,
	})

	total_amount = 0.0
	for item_data in items_data:
		item_doc = frappe.get_doc("Item", item_data["item_code"])
		amount = item_data.get("rate", 0) * item_data["qty"]
		total_amount += amount
		si.append("items", {
			"item_code": item_data["item_code"],
			"qty": item_data["qty"],

			"rate": item_data.get("rate", 0),
			"amount": amount,
			"uom": item_data.get("uom", item_doc.stock_uom),
			"stock_uom": item_doc.stock_uom,
			"conversion_factor": 1.0,
			"warehouse": item_data.get("warehouse", warehouse),
			"delivery_note": item_data.get("delivery_note"),
			"dn_detail": item_data.get("dn_detail"),
		})

	si.total = total_amount
	si.insert(ignore_permissions=True)

	if not do_not_submit:
		si.submit()

	return si


# ---------------------------------------------------------------------------
# Stock Entry (Manufacture)
# ---------------------------------------------------------------------------

def create_test_manufacture_stock_entry(item_code, batch_no, qty, company=None, warehouse=None):
	"""Create a submitted Manufacture Stock Entry for a given batch.

	Creates both a raw material item (consumed from warehouse) and a
	finished item (produced into warehouse) to satisfy ERPNext validation.

	Looks up accounts dynamically from the company defaults to avoid
	hardcoded account name assumptions.
	"""
	if not company:
		company = get_or_create_test_company().name
	if not warehouse:
		warehouse = get_or_create_test_warehouse(company).name

	company_doc = frappe.get_cached_doc("Company", company)
	expense_account = company_doc.stock_adjustment_account
	cost_center = company_doc.cost_center
	abbr = company_doc.abbr

	if not expense_account:
		expense_account = frappe.db.get_value(
			"Account",
			{"company": company, "account_type": "Stock Adjustment", "is_group": 0},
		)
	if not expense_account:
		if not frappe.db.exists("Account", f"Stock Adjustment - {abbr}"):
			parent = frappe.db.get_value("Account", {"company": company, "is_group": 1},
										 order_by="lft")
			exp = frappe.get_doc({
				"doctype": "Account",
				"account_name": "Stock Adjustment",
				"company": company,
				"parent_account": parent,
				"account_type": "Stock Adjustment",
			})
			exp.insert(ignore_permissions=True)
		expense_account = f"Stock Adjustment - {abbr}"

	if not cost_center:
		cost_center = frappe.db.get_value("Cost Center",
										  {"company": company, "is_group": 0}, "name")

	se = frappe.get_doc({
		"doctype": "Stock Entry",
		"stock_entry_type": "Manufacture",
		"company": company,
		"set_posting_time": 1,
		"posting_date": frappe.utils.today(),
		"items": [
			{
				"item_code": item_code,
				"qty": qty,
				"s_warehouse": warehouse,
				"batch_no": batch_no,
				"use_serial_batch_fields": 1,
				"is_finished_item": 0,
				"basic_rate": 0,
				"expense_account": expense_account,
				"cost_center": cost_center,
			},
			{
				"item_code": item_code,
				"qty": qty,
				"t_warehouse": warehouse,
				"batch_no": batch_no,
				"use_serial_batch_fields": 1,
				"is_finished_item": 1,
				"basic_rate": 0,
				"expense_account": expense_account,
				"cost_center": cost_center,
			},
		],
	})
	se.insert(ignore_permissions=True)
	se.submit()
	return se


# ---------------------------------------------------------------------------
# Stock Setup Helpers
# ---------------------------------------------------------------------------

def setup_item_valuation(item_code, valuation_rate, company=None):
	"""Set valuation rate on an item and create an opening stock entry if needed.

	Ensures the item has both a valuation rate and available stock in the
	default warehouse so stock entries (Material Transfer, Manufacture) can
	process without errors.
	"""
	if not company:
		company = get_or_create_test_company().name

	# Set valuation rate on the item master
	frappe.db.set_value("Item", item_code, "valuation_rate", valuation_rate,
						update_modified=False)

	# Check if item already has stock in the warehouse
	warehouse = get_or_create_test_warehouse(company).name
	actual_qty = frappe.db.get_value("Bin",
									 {"item_code": item_code, "warehouse": warehouse},
									 "actual_qty") or 0

	if actual_qty <= 0:
		stock_uom = frappe.db.get_value("Item", item_code, "stock_uom") or "Nos"
		default_supplier = get_or_create_test_supplier(company).name

		pr = frappe.get_doc({
			"doctype": "Purchase Receipt",
			"supplier": default_supplier,
			"company": company,
			"posting_date": frappe.utils.today(),
			"set_posting_time": 1,
			"items": [{
				"item_code": item_code,
				"qty": 100,
				"rate": valuation_rate,
				"uom": stock_uom,
				"stock_uom": stock_uom,
				"conversion_factor": 1.0,
				"warehouse": warehouse,
			}],
		})
		pr.insert(ignore_permissions=True)
		pr.submit()
