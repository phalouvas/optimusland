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

	company_abbr = frappe.db.get_value("Company", company, "abbr")
	warehouse_name = f"Stores - {company_abbr}"
	if frappe.db.exists("Warehouse", warehouse_name):
		return frappe.get_doc("Warehouse", warehouse_name)

	# Create a company-specific warehouse instead of falling back to _Test Warehouse
	wh = frappe.get_doc({
		"doctype": "Warehouse",
		"warehouse_name": "Stores",
		"company": company,
	})
	wh.insert(ignore_permissions=True)
	return wh


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
	Returns existing BOM if found.
	"""
	if not company:
		company = frappe.defaults.get_user_default("company")
	packaging_item = frappe.db.get_value("Item", {"item_group": "Packaging"}, "name")
	if not packaging_item:
		packaging_item = get_or_create_test_packaging_item(company)

	existing_bom = frappe.db.get_value("BOM", {"item": item_code, "is_active": 1, "docstatus": 1})
	if existing_bom:
		return frappe.get_doc("BOM", existing_bom)

	bom = frappe.get_doc({
		"doctype": "BOM",
		"item": item_code,
		"quantity": 1,
		"company": company,
		"items": [{
			"item_code": packaging_item.item_code,
			"qty": 1,
			"rate": 0,
		}],
	})
	bom.insert(ignore_permissions=True)
	bom.submit()

	# Set as default BOM on the item
	frappe.db.set_value("Item", item_code, "default_bom", bom.name, update_modified=False)

	return bom



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
# Weight Slip
# ---------------------------------------------------------------------------

def create_test_weight_slip(supplier, items_data=None, posting_date=None):
	"""Create a Weight Slip with the given items.

	Args:
		supplier: Supplier name
		items_data: List of dicts with keys: variety, size[, kilogram, quantity, jumbo_number]
		posting_date: Posting date (defaults to today)

	Returns the created Weight Slip document.
	"""
	if not posting_date:
		posting_date = frappe.utils.today()

	ws = frappe.get_doc({
		"doctype": "Weight Slip",
		"supplier": supplier,
		"posting_date": posting_date,
		"slip_number": f"TEST-{frappe.utils.now()}",
		"naming_series": "WS-.YYYY.-",
	})

	if items_data:
		for item_data in items_data:
			ws.append("items", {
				"variety": item_data.get("variety", ""),
				"size": item_data.get("size", ""),
				"kilogram": item_data.get("kilogram", "0"),
				"quantity": item_data.get("quantity", "0"),
				"jumbo_number": item_data.get("jumbo_number", ""),
			})

	ws.insert(ignore_permissions=True)
	return ws


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
