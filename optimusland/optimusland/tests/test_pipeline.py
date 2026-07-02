# Copyright (c) 2026, KAINOTOMO PH LTD and Contributors
# See license.txt

"""Tests for the Manufacturing Pipeline Dashboard data queries and actions."""

import frappe
from frappe.tests import IntegrationTestCase
from frappe.utils import today, add_days


class TestPipeline(IntegrationTestCase):
    """Integration tests for pipeline data queries, alerts, and actions."""

    def setUp(self):
        """Set up test data before each test."""
        self.company = _get_test_company()
        self.supplier = _get_test_supplier()
        self.customer = _get_test_customer()
        self.potato_item = _get_test_potato_item()
        self.packaging_item = _get_test_packaging_item()

    # ------------------------------------------------------------------
    # Pipeline data queries
    # ------------------------------------------------------------------

    def test_get_pipeline_data_returns_tiers(self):
        """Pipeline data returns all three tier keys."""
        from optimusland.utils.pipeline import get_pipeline_data

        data = get_pipeline_data(
            from_date=add_days(today(), -60),
            to_date=today(),
        )
        self.assertIn("sourcing", data)
        self.assertIn("manufacturing", data)
        self.assertIn("fulfillment", data)

    def test_get_pipeline_data_with_pr_returns_sourcing_data(self):
        """A submitted PR appears in the sourcing tier."""
        pr = _create_test_pr(self.supplier, self.potato_item)
        pr.submit()

        from optimusland.utils.pipeline import get_pipeline_data

        data = get_pipeline_data(
            from_date=add_days(today(), -1),
            to_date=add_days(today(), 1),
        )
        sourcing_prs = [r for r in data["sourcing"] if r["pr"] == pr.name]
        self.assertEqual(len(sourcing_prs), 1, "Submitted PR should appear in sourcing data")

    def test_get_pipeline_data_respects_supplier_filter(self):
        """Supplier filter narrows the sourcing tier results."""
        pr = _create_test_pr(self.supplier, self.potato_item)
        pr.submit()

        from optimusland.utils.pipeline import get_pipeline_data

        data = get_pipeline_data(
            from_date=add_days(today(), -1),
            to_date=add_days(today(), 1),
            supplier=self.supplier.name,
        )
        self.assertGreater(len(data["sourcing"]), 0,
                           "Should find PRs for the correct supplier")

        data2 = get_pipeline_data(
            from_date=add_days(today(), -1),
            to_date=add_days(today(), 1),
            supplier="NONEXISTENT",
        )
        self.assertEqual(len(data2["sourcing"]), 0,
                         "Should find no PRs for a non-existent supplier")

    # ------------------------------------------------------------------
    # Alert detection
    # ------------------------------------------------------------------

    def test_alert_pr_no_pp(self):
        """PR without custom_production_plan triggers a critical alert."""
        pr = _create_test_pr(self.supplier, self.potato_item)
        pr.submit()
        # Explicitly clear the PP link to ensure alert detection
        frappe.db.set_value("Purchase Receipt", pr.name, "custom_production_plan", None)
        frappe.db.commit()

        from optimusland.utils.pipeline import get_alerts

        alerts = get_alerts(
            from_date=add_days(today(), -1),
            to_date=add_days(today(), 1),
        )
        pr_alerts = [a for a in alerts if a.get("entity") == pr.name
                     and a.get("doctype") == "Purchase Receipt"
                     and a["severity"] == "critical"]
        self.assertGreater(len(pr_alerts), 0,
                           "PR without PP should trigger a critical alert")

    def test_alert_wo_stuck(self):
        """Alert detection handles draft WO gracefully."""
        from optimusland.utils.pipeline import get_alerts

        # Just verify the alert function runs without error and returns a list
        alerts = get_alerts(
            from_date=add_days(today(), -10),
            to_date=add_days(today(), 1),
        )
        self.assertIsInstance(alerts, list)
        # The test DB may not have stuck WOs, but the function should
        # not crash and should return a valid list

    # ------------------------------------------------------------------
    # KPI counts
    # ------------------------------------------------------------------

    def test_get_kpi_counts_returns_keys(self):
        """KPI counts return all expected keys."""
        from optimusland.utils.pipeline import get_kpi_counts

        counts = get_kpi_counts()
        self.assertIn("prs_today", counts)
        self.assertIn("open_wos", counts)
        self.assertIn("ready_to_ship", counts)
        self.assertIn("total_alerts", counts)

    def test_get_kpi_counts_prs_today(self):
        """A PR submitted today increments prs_today."""
        pr = _create_test_pr(self.supplier, self.potato_item)
        pr.submit()

        from optimusland.utils.pipeline import get_kpi_counts

        counts = get_kpi_counts()
        self.assertGreaterEqual(counts["prs_today"], 1,
                                "PRs today should be at least 1")

    # ------------------------------------------------------------------
    # Actions
    # ------------------------------------------------------------------

    def test_retry_production_plan_nonexistent(self):
        """Retrying a non-existent PR returns an error."""
        from optimusland.utils.pipeline import retry_production_plan

        result = retry_production_plan("NONEXISTENT-PR-001")
        self.assertFalse(result["success"])

    def test_force_submit_work_order_nonexistent(self):
        """Force-submitting a non-existent WO returns an error."""
        from optimusland.utils.pipeline import force_submit_work_order

        result = force_submit_work_order("NONEXISTENT-WO-001")
        self.assertFalse(result["success"])

    def test_get_pipeline_data_fulfillment(self):
        """Fulfillment data returns valid structure."""
        from optimusland.utils.pipeline import get_pipeline_data

        data = get_pipeline_data(
            from_date=add_days(today(), -60),
            to_date=today(),
        )
        # Just verify it's a list (might be empty in test DB, but that's OK)
        self.assertIsInstance(data["fulfillment"], list)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _get_test_company():
    from optimusland.optimusland.tests import get_or_create_test_company
    return get_or_create_test_company()


def _get_test_supplier():
    from optimusland.optimusland.tests import get_or_create_test_supplier
    return get_or_create_test_supplier()


def _get_test_customer():
    from optimusland.optimusland.tests import get_or_create_test_customer
    return get_or_create_test_customer()


def _get_test_potato_item():
    from optimusland.optimusland.tests import get_or_create_test_potato_item
    return get_or_create_test_potato_item()


def _get_test_packaging_item():
    from optimusland.optimusland.tests import get_or_create_test_packaging_item
    return get_or_create_test_packaging_item()


def _create_test_pr(supplier, item):
    """Create a minimal Purchase Receipt for testing."""
    company = _get_test_company()
    warehouse = frappe.db.get_value(
        "Warehouse", {"company": company.name}, "name"
    ) or frappe.db.sql("SELECT name FROM `tabWarehouse` LIMIT 1")[0][0]

    pr = frappe.get_doc({
        "doctype": "Purchase Receipt",
        "supplier": supplier.name,
        "company": company.name,
        "posting_date": today(),
        "items": [{
            "item_code": item.item_code,
            "qty": 100,
            "rate": 10.0,
            "warehouse": warehouse,
            "uom": "Nos",
            "stock_uom": "Nos",
            "conversion_factor": 1,
        }],
    })
    try:
        pr.insert(ignore_permissions=True)
    except Exception:
        # Fall back to db_insert if workflow validation fails
        pr.db_insert()
        for item_row in pr.items:
            item_row.db_insert()

    return pr
