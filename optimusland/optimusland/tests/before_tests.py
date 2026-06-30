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
	get_or_create_test_bom,
)


def before_tests():
	"""Seed minimum test data shared across all test modules."""
	# Enable Serial and Batch Bundle support (ERPNext v16 requirement)
	frappe.db.set_single_value("Stock Settings", "enable_serial_and_batch_no_for_item", 1)

	company = get_or_create_test_company()
	get_or_create_test_warehouse(company.name)
	get_or_create_test_supplier(company.name)
	get_or_create_test_customer(company.name)
	potato_item = get_or_create_test_potato_item(company.name)
	get_or_create_test_bom(potato_item.item_code, company.name)
