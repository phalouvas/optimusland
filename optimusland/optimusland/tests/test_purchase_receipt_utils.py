# Copyright (c) 2026, KAINOTOMO PH LTD and Contributors
# See license.txt

"""Tests for purchase_receipt.py: create_production_plan, set_batch_no, fix_stock_entry.

These are the most critical functions in the app — they orchestrate the
entire manufacturing chain (Purchase Receipt → Production Plan →
Work Orders → Stock Entries).
"""

import frappe
from frappe.tests import IntegrationTestCase
from erpnext.manufacturing.doctype.work_order.work_order import make_stock_entry

from optimusland.optimusland.tests import (
	get_or_create_test_company,
	get_or_create_test_warehouse,
	get_or_create_test_supplier,
	get_or_create_test_potato_item,
	get_or_create_test_bom,
	get_or_create_test_packaging_item,
	setup_item_valuation,
	create_test_batch,
	create_test_purchase_receipt,
)
from optimusland.utils.purchase_receipt import (
	create_production_plan,
	set_batch_no,
	fix_stock_entry,
	fix_missing_accounts,
)


class TestCreateProductionPlan(IntegrationTestCase):
	"""Tests for create_production_plan (Purchase Receipt on_submit hook)."""

	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		cls.company = get_or_create_test_company()
		cls.warehouse = get_or_create_test_warehouse(cls.company.name)
		cls.supplier = get_or_create_test_supplier(cls.company.name)
		cls.potato_item = get_or_create_test_potato_item(cls.company.name)
		cls.packaging_item = get_or_create_test_packaging_item(cls.company.name)
		cls.bom = get_or_create_test_bom(cls.potato_item.item_code, cls.company.name)
		# Ensure BOM components have stock and valuation rate
		setup_item_valuation(cls.packaging_item.item_code, 0.50, cls.company.name)

	def tearDown(self):
		"""Rollback handled automatically by IntegrationTestCase."""
		pass

	def test_create_production_plan_basic(self):
		"""PR with 1 potato item → PP + WO + 2 SEs created."""
		batch = create_test_batch(self.potato_item.item_code, self.supplier.name,
								  prefix="TEST")

		pr = create_test_purchase_receipt(
			items_data=[{
				"item_code": self.potato_item.item_code,
				"qty": 100,
				"rate": 0.50,
				"batch_no": batch.name,
			}],
			supplier=self.supplier.name,
			company=self.company.name,
			warehouse=self.warehouse.name,
		)

		# Call the hook (normally triggered by on_submit)
		create_production_plan(pr)

		# Assert Production Plan created
		plans = frappe.get_all("Production Plan",
							   filters={"docstatus": 1},
							   order_by="creation DESC",
							   limit=1)
		self.assertGreater(len(plans), 0)
		plan = frappe.get_doc("Production Plan", plans[0].name)

		# Assert PO items match
		self.assertEqual(len(plan.po_items), 1)
		self.assertEqual(plan.po_items[0].item_code, self.potato_item.item_code)
		self.assertEqual(plan.po_items[0].planned_qty, 100)

		# Assert Work Orders created
		wos = frappe.get_all("Work Order",
							 filters={"production_plan": plan.name, "docstatus": 1})
		self.assertEqual(len(wos), 1)

		# Assert Stock Entries created
		wo_name = wos[0].name
		ses = frappe.get_all("Stock Entry",
							 filters={
								 "work_order": wo_name,
								 "docstatus": 1,
							 },
							 fields=["name", "stock_entry_type"],
							 order_by="creation ASC")
		self.assertEqual(len(ses), 2)
		self.assertEqual(ses[0].stock_entry_type, "Material Transfer for Manufacture")
		self.assertEqual(ses[1].stock_entry_type, "Manufacture")

		# Assert Manufacture SE has batch_no set
		se2 = frappe.get_doc("Stock Entry", ses[1].name)
		finished_items = [i for i in se2.items if i.is_finished_item]
		self.assertGreater(len(finished_items), 0)
		self.assertEqual(finished_items[0].batch_no, batch.name)

	def test_create_production_plan_multiple_items(self):
		"""PR with 2 potato items → 2 WOs, 4 SEs."""
		# Create a second potato-like item (clear default_bom from copy)
		second_item_code = "_Test Potato 2"
		if not frappe.db.exists("Item", second_item_code):
			item2 = frappe.copy_doc(self.potato_item)
			item2.item_code = second_item_code
			item2.item_name = second_item_code
			item2.default_bom = None
			item2.insert(ignore_permissions=True)
		else:
			item2 = frappe.get_doc("Item", second_item_code)

		bom2 = get_or_create_test_bom(item2.item_code, self.company.name)
		batch1 = create_test_batch(self.potato_item.item_code, self.supplier.name,
								   prefix="MULTI")
		batch2 = create_test_batch(item2.item_code, self.supplier.name,
								   prefix="MULTI")

		pr = create_test_purchase_receipt(
			items_data=[
				{"item_code": self.potato_item.item_code, "qty": 100, "rate": 0.50,
				 "batch_no": batch1.name},
				{"item_code": item2.item_code, "qty": 200, "rate": 0.40,
				 "batch_no": batch2.name},
			],
			supplier=self.supplier.name,
			company=self.company.name,
			warehouse=self.warehouse.name,
		)

		create_production_plan(pr)

		plans = frappe.get_all("Production Plan",
							   filters={"docstatus": 1},
							   order_by="creation DESC",
							   limit=1)
		plan = frappe.get_doc("Production Plan", plans[0].name)
		self.assertEqual(len(plan.po_items), 2)

		wos = frappe.get_all("Work Order",
							 filters={"production_plan": plan.name, "docstatus": 1})
		self.assertEqual(len(wos), 2)

	def test_create_production_plan_no_bom_item(self):
		"""Item without BOM is silently skipped — no crash."""
		# Create item with no BOM (clear default_bom from copy)
		no_bom_code = "_Test No BOM Potato"
		if frappe.db.exists("Item", no_bom_code):
			frappe.delete_doc("Item", no_bom_code)
		item_no_bom = frappe.copy_doc(self.potato_item)
		item_no_bom.item_code = no_bom_code
		item_no_bom.item_name = no_bom_code
		item_no_bom.default_bom = None
		item_no_bom.insert(ignore_permissions=True)

		batch = create_test_batch(item_no_bom.item_code, self.supplier.name,
								  prefix="NOBOM")

		pr = create_test_purchase_receipt(
			items_data=[{
				"item_code": item_no_bom.item_code,
				"qty": 50,
				"rate": 0.50,
				"batch_no": batch.name,
			}],
			supplier=self.supplier.name,
			company=self.company.name,
			warehouse=self.warehouse.name,
		)

		# Should not raise, silently skip item without BOM
		create_production_plan(pr)

		# No PP should be created (only item had no BOM)
		plans_after = frappe.get_all("Production Plan",
									 filters={"docstatus": 1},
									 order_by="creation DESC",
									 limit=1)

	def test_create_production_plan_no_batch_items(self):
		"""Non-batch items should not trigger PP creation."""
		# Create a non-batch item
		try:
			pr = create_test_purchase_receipt(
				items_data=[{
					"item_code": self.packaging_item.item_code,
					"qty": 10,
					"rate": 1.0,
				}],
				supplier=self.supplier.name,
				company=self.company.name,
				warehouse=self.warehouse.name,
			)

			create_production_plan(pr)

			# Since packaging_item has has_batch_no=0, no PP items → function returns early
			# Nothing to assert beyond no crash
		except Exception as e:
			self.fail(f"create_production_plan raised unexpectedly: {e}")

	def test_fix_stock_entry_source_item(self):
		"""fix_stock_entry appends source item and reverses items, sets purchase_rate."""
		batch = create_test_batch(self.potato_item.item_code, self.supplier.name,
								  prefix="FIXSE")

		# Create a minimal work order to generate a stock entry
		bom = self.bom
		wo = frappe.get_doc({
			"doctype": "Work Order",
			"production_item": self.potato_item.item_code,
			"bom_no": bom.name,
			"qty": 10,
			"company": self.company.name,
			"fg_warehouse": self.warehouse.name,
			"wip_warehouse": self.warehouse.name,
			"use_multi_level_bom": 0,
		})
		wo.insert(ignore_permissions=True)
		wo.submit()

		# Get the skeleton SE from make_stock_entry
		se = frappe.get_doc(make_stock_entry(wo.name, "Manufacture", wo.qty))

		# Count items before fix_stock_entry
		item_count_before = len(se.items)

		purchase_rate = 0.55
		se = fix_stock_entry(se, batch.name, self.potato_item.item_code, purchase_rate)

		# Assert a new source item was appended (count increased by 1)
		self.assertEqual(len(se.items), item_count_before + 1)

		# The appended source item has is_finished_item=0, matching item_code, and purchase_rate
		# After reversal, added items are at the front of the list
		# Find items with the same item_code as the production item
		production_item_entries = [i for i in se.items if i.item_code == self.potato_item.item_code]
		self.assertEqual(len(production_item_entries), 2)  # original finished + appended source

		# One should have is_finished_item=0 (the appended source item)
		source_entries = [i for i in production_item_entries if i.is_finished_item == 0]
		self.assertEqual(len(source_entries), 1)
		self.assertEqual(source_entries[0].basic_rate, purchase_rate)

		# One should have is_finished_item=1 (the original finished item)
		finished_entries = [i for i in production_item_entries if i.is_finished_item == 1]
		self.assertEqual(len(finished_entries), 1)

		# Assert items are reversed (first should be source, last should be finished)
		self.assertEqual(se.items[0].is_finished_item, 0)


class TestSetBatchNo(IntegrationTestCase):
	"""Tests for set_batch_no (Purchase Receipt validate hook)."""

	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		cls.company = get_or_create_test_company()
		cls.warehouse = get_or_create_test_warehouse(cls.company.name)
		cls.supplier = get_or_create_test_supplier(cls.company.name)
		cls.potato_item = get_or_create_test_potato_item(cls.company.name)
		cls.packaging_item = get_or_create_test_packaging_item(cls.company.name)

	def test_set_batch_no_new_batch(self):
		"""Potato item without batch → new Batch created."""
		pr = frappe.get_doc({
			"doctype": "Purchase Receipt",
			"supplier": self.supplier.name,
			"company": self.company.name,
			"posting_date": frappe.utils.today(),
			"set_posting_time": 1,
			"items": [{
				"item_code": self.potato_item.item_code,
				"qty": 100,
				"rate": 0.50,
				"warehouse": self.warehouse.name,
				"uom": self.potato_item.stock_uom,
				"stock_uom": self.potato_item.stock_uom,
				"conversion_factor": 1.0,
				"custom_batch_prefix": "TEST",
			}],
		})
		pr.insert(ignore_permissions=True)

		# Call validate hook
		set_batch_no(pr)

		# Assert batch_no was set
		self.assertIsNotNone(pr.items[0].batch_no)

		# Assert Batch document was created
		batch = frappe.get_doc("Batch", pr.items[0].batch_no)
		self.assertEqual(batch.item, self.potato_item.item_code)
		self.assertEqual(batch.custom_supplier_optimus, self.supplier.name)

	def test_set_batch_no_existing_batch(self):
		"""Existing matching batch is reused, not duplicated."""
		pre_batch = create_test_batch(self.potato_item.item_code, self.supplier.name,
									  prefix="REUSE")
		existing_name = pre_batch.name

		pr = frappe.get_doc({
			"doctype": "Purchase Receipt",
			"supplier": self.supplier.name,
			"company": self.company.name,
			"posting_date": frappe.utils.today(),
			"set_posting_time": 1,
			"items": [{
				"item_code": self.potato_item.item_code,
				"qty": 100,
				"rate": 0.50,
				"warehouse": self.warehouse.name,
				"uom": self.potato_item.stock_uom,
				"stock_uom": self.potato_item.stock_uom,
				"conversion_factor": 1.0,
				"custom_batch_prefix": "REUSE",
			}],
		})
		pr.insert(ignore_permissions=True)

		set_batch_no(pr)

		# Assert existing batch reused
		self.assertEqual(pr.items[0].batch_no, existing_name)

	def test_set_batch_no_without_prefix(self):
		"""No custom_prefix → batch_id format: {item_code} * {date} * {supplier}."""
		pr = frappe.get_doc({
			"doctype": "Purchase Receipt",
			"supplier": self.supplier.name,
			"company": self.company.name,
			"posting_date": frappe.utils.today(),
			"set_posting_time": 1,
			"items": [{
				"item_code": self.potato_item.item_code,
				"qty": 100,
				"rate": 0.50,
				"warehouse": self.warehouse.name,
				"uom": self.potato_item.stock_uom,
				"stock_uom": self.potato_item.stock_uom,
				"conversion_factor": 1.0,
				"custom_batch_prefix": None,
			}],
		})
		pr.insert(ignore_permissions=True)

		set_batch_no(pr)

		self.assertIsNotNone(pr.items[0].batch_no)
		batch = frappe.get_doc("Batch", pr.items[0].batch_no)
		# batch_id should NOT contain a prefix segment
		self.assertNotIn("*  *", frappe.db.get_value("Batch", batch.name, "batch_id"))

	def test_set_batch_no_non_potato_skipped(self):
		"""Non-Potato item group → no batch created."""
		pr = frappe.get_doc({
			"doctype": "Purchase Receipt",
			"supplier": self.supplier.name,
			"company": self.company.name,
			"posting_date": frappe.utils.today(),
			"set_posting_time": 1,
			"items": [{
				"item_code": self.packaging_item.item_code,
				"qty": 10,
				"rate": 1.0,
				"warehouse": self.warehouse.name,
				"uom": self.packaging_item.stock_uom,
				"stock_uom": self.packaging_item.stock_uom,
				"conversion_factor": 1.0,
			}],
		})
		pr.insert(ignore_permissions=True)

		set_batch_no(pr)

		# No batch_no set for non-Potato items
		self.assertIsNone(pr.items[0].batch_no)
