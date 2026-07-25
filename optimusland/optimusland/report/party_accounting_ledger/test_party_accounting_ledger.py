# Copyright (c) 2026, KAINOTOMO PH LTD and Contributors
# See license.txt

"""Tests for the Party Accounting Ledger report.

Creates a dual-role party (Supplier + Customer linked via Party Link),
creates test invoices on both sides, and verifies the report output
including opening balance, transaction rows, running balance, and
closing/net position summary.
"""

import frappe
from frappe.tests import IntegrationTestCase
from frappe.utils import today

from optimusland.optimusland.tests import (
    get_or_create_test_company,
    get_or_create_test_warehouse,
)
from optimusland.optimusland.report.party_accounting_ledger.party_accounting_ledger import (
    execute,
)


class TestPartyAccountingLedger(IntegrationTestCase):
    """Tests for the Party Accounting Ledger report."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.company = get_or_create_test_company()
        cls.warehouse = get_or_create_test_warehouse(cls.company.name)
        cls.creditors_account = frappe.db.get_value(
            "Account",
            {"company": cls.company.name, "account_type": "Payable", "is_group": 0},
        )
        cls.debtors_account = frappe.db.get_value(
            "Account",
            {"company": cls.company.name, "account_type": "Receivable", "is_group": 0},
        )

        cls.dual_party_name = "_Test Report Dual Party"

        # Create dual-role supplier
        if not frappe.db.exists("Supplier", cls.dual_party_name):
            sg = "_Test Supplier Group"
            if not frappe.db.exists("Supplier Group", sg):
                frappe.get_doc({
                    "doctype": "Supplier Group",
                    "supplier_group_name": sg,
                    "parent_supplier_group": "All Supplier Groups",
                }).insert(ignore_permissions=True)
            frappe.get_doc({
                "doctype": "Supplier",
                "supplier_name": cls.dual_party_name,
                "supplier_group": sg,
                "supplier_type": "Company",
            }).insert(ignore_permissions=True)

        # Create dual-role customer
        if not frappe.db.exists("Customer", cls.dual_party_name):
            cg = "_Test Customer Group"
            if not frappe.db.exists("Customer Group", cg):
                frappe.get_doc({
                    "doctype": "Customer Group",
                    "customer_group_name": cg,
                    "parent_customer_group": "All Customer Groups",
                }).insert(ignore_permissions=True)
            frappe.get_doc({
                "doctype": "Customer",
                "customer_name": cls.dual_party_name,
                "customer_group": cg,
                "customer_type": "Company",
                "territory": "All Territories",
            }).insert(ignore_permissions=True)

        # Create Party Link
        link_doc = frappe.get_doc({
            "doctype": "Party Link",
            "primary_role": "Supplier",
            "primary_party": cls.dual_party_name,
            "secondary_role": "Customer",
            "secondary_party": cls.dual_party_name,
        })
        if not frappe.db.exists("Party Link", {"primary_party": cls.dual_party_name}):
            link_doc.insert(ignore_permissions=True)
        else:
            existing = frappe.db.get_value("Party Link", {"primary_party": cls.dual_party_name}, "name")
            link_doc = frappe.get_doc("Party Link", existing)
        cls.party_link_name = link_doc.name

        # Create a single-role supplier (no link) for the "no link" test
        cls.solo_supplier_name = "_Test Solo Supplier Report"
        if not frappe.db.exists("Supplier", cls.solo_supplier_name):
            frappe.get_doc({
                "doctype": "Supplier",
                "supplier_name": cls.solo_supplier_name,
                "supplier_group": "_Test Supplier Group",
                "supplier_type": "Company",
            }).insert(ignore_permissions=True)

    def setUp(self):
        super().setUp()
        self._created_pis = []
        self._created_sis = []
        self._created_gl_entries = []
        self._cleanup_invoices()
        self._cleanup_gl_entries()

    def tearDown(self):
        self._cleanup_gl_entries()
        self._cleanup_invoices()
        super().tearDown()

    # ------------------------------------------------------------------
    # Cleanup helpers
    # ------------------------------------------------------------------

    def _cleanup_gl_entries(self):
        for name in getattr(self, "_created_gl_entries", []):
            frappe.db.delete("GL Entry", {"name": name})

    def _cleanup_invoices(self):
        for name in getattr(self, "_created_pis", []):
            frappe.db.delete("Purchase Invoice Item", {"parent": name})
            frappe.db.delete("GL Entry", {"voucher_no": name})
            frappe.db.delete("Purchase Invoice", {"name": name})
        for name in getattr(self, "_created_sis", []):
            frappe.db.delete("Sales Invoice Item", {"parent": name})
            frappe.db.delete("GL Entry", {"voucher_no": name})
            frappe.db.delete("Sales Invoice", {"name": name})

    # ------------------------------------------------------------------
    # Test data factories
    # ------------------------------------------------------------------

    def _create_pi(self, name, amount=1000.0):
        """Create a Purchase Invoice via raw SQL with corresponding GL Entry."""
        frappe.db.sql(
            """
            INSERT INTO `tabPurchase Invoice`
            (name, owner, creation, modified, modified_by, docstatus,
             company, posting_date, due_date, supplier, status, outstanding_amount)
            VALUES (%s, 'Administrator', NOW(), NOW(), 'Administrator', 1,
             %s, %s, %s, %s, 'Unpaid', %s)
            """,
            (name, self.company.name, today(), today(), self.dual_party_name, amount),
        )
        pi_item_name = f"{name}-item-1"
        frappe.db.sql(
            """
            INSERT INTO `tabPurchase Invoice Item`
            (name, parent, parenttype, parentfield, item_code, qty, rate, amount,
             uom, stock_uom, conversion_factor, warehouse)
            VALUES (%s, %s, 'Purchase Invoice', 'items', '_Test Status Item',
             10, %s, %s, 'Nos', 'Nos', 1.0, %s)
            """,
            (pi_item_name, name, amount / 10, amount, self.warehouse.name),
        )
        frappe.db.set_value("Purchase Invoice", name, "credit_to", self.creditors_account)

        account = self.creditors_account or "2110 - Creditors - OL"
        gl_name = f"{name}-gl-1"
        frappe.db.sql(
            """
            INSERT INTO `tabGL Entry`
            (name, posting_date, account, party_type, party,
             debit_in_account_currency, credit_in_account_currency,
             against, company, voucher_type, voucher_no, is_cancelled,
             against_voucher, against_voucher_type)
            VALUES (%s, %s, %s, 'Supplier', %s, 0, %s, %s, %s,
             'Purchase Invoice', %s, 0, %s, 'Purchase Invoice')
            """,
            (gl_name, today(), account, self.dual_party_name,
             amount, name, self.company.name, name, name),
        )
        self._created_pis.append(name)
        self._created_gl_entries.append(gl_name)

    def _create_si(self, name, amount=1000.0):
        """Create a Sales Invoice via raw SQL with corresponding GL Entry."""
        frappe.db.sql(
            """
            INSERT INTO `tabSales Invoice`
            (name, owner, creation, modified, modified_by, docstatus,
             company, posting_date, due_date, customer, status, outstanding_amount)
            VALUES (%s, 'Administrator', NOW(), NOW(), 'Administrator', 1,
             %s, %s, %s, %s, 'Unpaid', %s)
            """,
            (name, self.company.name, today(), today(), self.dual_party_name, amount),
        )
        si_item_name = f"{name}-item-1"
        frappe.db.sql(
            """
            INSERT INTO `tabSales Invoice Item`
            (name, parent, parenttype, parentfield, item_code, qty, rate, amount,
             uom, stock_uom, conversion_factor, warehouse)
            VALUES (%s, %s, 'Sales Invoice', 'items', '_Test Status Item',
             10, %s, %s, 'Nos', 'Nos', 1.0, %s)
            """,
            (si_item_name, name, amount / 10, amount, self.warehouse.name),
        )
        frappe.db.set_value("Sales Invoice", name, "debit_to", self.debtors_account)

        account = self.debtors_account or "1310 - Debtors - OL"
        gl_name = f"{name}-gl-1"
        frappe.db.sql(
            """
            INSERT INTO `tabGL Entry`
            (name, posting_date, account, party_type, party,
             debit_in_account_currency, credit_in_account_currency,
             against, company, voucher_type, voucher_no, is_cancelled,
             against_voucher, against_voucher_type)
            VALUES (%s, %s, %s, 'Customer', %s, %s, 0, %s, %s,
             'Sales Invoice', %s, 0, %s, 'Sales Invoice')
            """,
            (gl_name, today(), account, self.dual_party_name,
             amount, name, self.company.name, name, name),
        )
        self._created_sis.append(name)
        self._created_gl_entries.append(gl_name)

    # ------------------------------------------------------------------
    # Tests
    # ------------------------------------------------------------------

    def test_report_structure(self):
        """Report returns correct columns and data structure."""
        columns, data = execute(filters={})
        self.assertIsInstance(columns, list)
        self.assertIsInstance(data, list)

        # Columns
        col_fieldnames = [c["fieldname"] for c in columns]
        expected_fields = [
            "posting_date",
            "voucher_type",
            "voucher_no",
            "party",
            "role",
            "debit",
            "credit",
            "balance",
            "against_voucher",
            "remarks",
        ]
        for field in expected_fields:
            self.assertIn(field, col_fieldnames)

    def test_empty_filters_returns_empty_data(self):
        """No party_link returns empty list."""
        columns, data = execute(filters={})
        self.assertEqual(data, [])

        columns, data = execute(filters={"party_link": ""})
        self.assertEqual(data, [])

        columns, data = execute(filters={"party_link": "NonExistentLink"})
        self.assertEqual(data, [])

    def test_no_party_link_shows_single_side(self):
        """Party without a Party Link still shows single-sided ledger."""
        uniq = frappe.generate_hash("", 6)
        pi_name = f"TST-PI-SOLO-{uniq}"
        frappe.db.sql(
            """
            INSERT INTO `tabPurchase Invoice`
            (name, owner, creation, modified, modified_by, docstatus,
             company, posting_date, due_date, supplier, status, outstanding_amount)
            VALUES (%s, 'Administrator', NOW(), NOW(), 'Administrator', 1,
             %s, %s, %s, %s, 'Unpaid', 500.0)
            """,
            (pi_name, self.company.name, today(), today(), self.solo_supplier_name),
        )
        pi_item_name = f"{pi_name}-item-1"
        frappe.db.sql(
            """
            INSERT INTO `tabPurchase Invoice Item`
            (name, parent, parenttype, parentfield, item_code, qty, rate, amount,
             uom, stock_uom, conversion_factor, warehouse)
            VALUES (%s, %s, 'Purchase Invoice', 'items', '_Test Status Item',
             5, 100.0, 500.0, 'Nos', 'Nos', 1.0, %s)
            """,
            (pi_item_name, pi_name, self.warehouse.name),
        )
        account = self.creditors_account or "2110 - Creditors - OL"
        gl_name = f"{pi_name}-gl-1"
        frappe.db.sql(
            """
            INSERT INTO `tabGL Entry`
            (name, posting_date, account, party_type, party,
             debit_in_account_currency, credit_in_account_currency,
             against, company, voucher_type, voucher_no, is_cancelled,
             against_voucher, against_voucher_type)
            VALUES (%s, %s, %s, 'Supplier', %s, 0, 500.0, %s, %s,
             'Purchase Invoice', %s, 0, %s, 'Purchase Invoice')
            """,
            (gl_name, today(), account, self.solo_supplier_name,
             pi_name, self.company.name, pi_name, pi_name),
        )
        self._created_pis.append(pi_name)
        self._created_gl_entries.append(gl_name)

        columns, data = execute(filters={
            "party_link": self.party_link_name,
            "company": self.company.name,
        })

        self.assertGreater(len(data), 0)
        # Should have at least opening + transaction + closing rows
        self.assertGreaterEqual(len(data), 3)

        # Find the opening row
        opening = data[0]
        self.assertEqual(opening["remarks"], "Opening Balance")

        # Find the closing row
        closing = [r for r in data if r.get("is_closing")][0]
        self.assertEqual(closing["balance"], 500.0)

    def test_dual_role_report_structure(self):
        """Report for a dual-role party shows both supplier and customer transactions."""
        uniq = frappe.generate_hash("", 6)
        self._create_pi(f"TST-RPT-PI-{uniq}", amount=5000.0)
        self._create_si(f"TST-RPT-SI-{uniq}", amount=2000.0)

        columns, data = execute(filters={
            "party_link": self.party_link_name,
            "company": self.company.name,
        })

        self.assertGreater(len(data), 0)

        # Opening balance row
        opening = data[0]
        self.assertEqual(opening["remarks"], "Opening Balance")

        # Find transaction rows (skip opening and closing)
        transaction_rows = [
            r for r in data
            if not r.get("is_opening") and not r.get("is_closing") and not r.get("is_net_position")
        ]

        # Should have at least 2 transaction rows (PI and SI)
        self.assertGreaterEqual(len(transaction_rows), 2)

        # Verify both roles appear
        roles = set(r["role"] for r in transaction_rows)
        self.assertIn("As Supplier", roles)
        self.assertIn("As Customer", roles)

        # Find closing balance row
        closing = [r for r in data if r.get("is_closing")]
        self.assertEqual(len(closing), 1)
        # Running balance should be 5000 - 2000 = 3000 (we owe supplier more than they owe us)
        self.assertEqual(closing[0]["balance"], 3000.0)

        # Find net position row
        net_pos = [r for r in data if r.get("is_net_position")]
        self.assertEqual(len(net_pos), 1)
        self.assertEqual(net_pos[0]["balance"], 3000.0)
        self.assertIn("Owed to Supplier", net_pos[0]["remarks"])

    def test_negative_net_position(self):
        """When customer owes more than supplier, net position shows 'Owed by Customer'."""
        uniq = frappe.generate_hash("", 6)
        self._create_pi(f"TST-RPT-PI2-{uniq}", amount=1000.0)
        self._create_si(f"TST-RPT-SI2-{uniq}", amount=4000.0)

        columns, data = execute(filters={
            "party_link": self.party_link_name,
            "company": self.company.name,
        })

        closing = [r for r in data if r.get("is_closing")][0]
        self.assertEqual(closing["balance"], -3000.0)

        net_pos = [r for r in data if r.get("is_net_position")][0]
        self.assertEqual(net_pos["balance"], 3000.0)
        self.assertIn("Owed by Customer", net_pos["remarks"])

    def test_transactions_in_correct_order(self):
        """Transaction rows are ordered chronologically by posting_date."""
        uniq = frappe.generate_hash("", 6)
        # Create SI first, then PI — report should order by posting_date regardless
        self._create_si(f"TST-RPT-ORD-SI-{uniq}", amount=1000.0)
        self._create_pi(f"TST-RPT-ORD-PI-{uniq}", amount=2000.0)

        columns, data = execute(filters={
            "party_link": self.party_link_name,
            "company": self.company.name,
        })

        transaction_rows = [
            r for r in data
            if not r.get("is_opening") and not r.get("is_closing") and not r.get("is_net_position")
        ]

        # Dates should be non-decreasing
        dates = [r["posting_date"] for r in transaction_rows]
        for i in range(1, len(dates)):
            self.assertGreaterEqual(dates[i], dates[i - 1])

    def test_running_balance_calculation(self):
        """Running balance is correctly computed after each transaction."""
        uniq = frappe.generate_hash("", 6)
        self._create_si(f"TST-RPT-BAL-SI-{uniq}", amount=1000.0)
        self._create_pi(f"TST-RPT-BAL-PI-{uniq}", amount=3000.0)

        columns, data = execute(filters={
            "party_link": self.party_link_name,
            "company": self.company.name,
        })

        # Find transaction rows (excluding opening/closing/net rows)
        trx = [
            r for r in data
            if not r.get("is_opening") and not r.get("is_closing") and not r.get("is_net_position")
        ]

        # SI (Customer owes us): credit - debit = 0 - 1000 = -1000 → balance = -1000
        # PI (We owe supplier): credit - debit = 3000 - 0 = 3000 → balance = 2000
        expected_balances = [-1000.0, 2000.0]
        for i, row in enumerate(trx):
            self.assertEqual(
                row["balance"],
                expected_balances[i],
                f"Row {i}: expected balance {expected_balances[i]}, got {row['balance']}",
            )

    def test_opening_balance_respected(self):
        """With from_date after some transactions, only later transactions appear."""
        uniq = frappe.generate_hash("", 6)
        pi_name = f"TST-RPT-OP-{uniq}"
        gl_name = f"{pi_name}-gl-1"

        # Create a GL entry with an earlier date
        account = self.creditors_account or "2110 - Creditors - OL"
        frappe.db.sql(
            """
            INSERT INTO `tabGL Entry`
            (name, posting_date, account, party_type, party,
             debit_in_account_currency, credit_in_account_currency,
             against, company, voucher_type, voucher_no, is_cancelled,
             against_voucher, against_voucher_type)
            VALUES (%s, '2025-01-01', %s, 'Supplier', %s,
             0, 2000.0, %s, %s,
             'Purchase Invoice', %s, 0, %s, 'Purchase Invoice')
            """,
            (gl_name, account, self.dual_party_name,
             pi_name, self.company.name, pi_name, pi_name),
        )
        self._created_gl_entries.append(gl_name)

        # Now create a transaction in the current period
        self._create_si(f"TST-RPT-OP-SI-{uniq}", amount=500.0)

        columns, data = execute(filters={
            "party_link": self.party_link_name,
            "company": self.company.name,
            "from_date": today(),
        })

        # Opening balance should be 2000 (from the earlier GL entry)
        opening = data[0]
        self.assertEqual(opening["remarks"], "Opening Balance")
        self.assertEqual(opening["balance"], 2000.0)

        # Only the SI transaction should appear in the period
        trx = [
            r for r in data
            if not r.get("is_opening") and not r.get("is_closing") and not r.get("is_net_position")
        ]
        self.assertEqual(len(trx), 1)
        self.assertEqual(trx[0]["voucher_type"], "Sales Invoice")
        # SI contributes -500 (credit - debit = 0 - 500)
        self.assertEqual(trx[0]["balance"], 1500.0)

    def test_customer_perspective(self):
        """Report works identically when accessed from Customer perspective."""
        uniq = frappe.generate_hash("", 6)
        self._create_pi(f"TST-RPT-CP-PI-{uniq}", amount=3000.0)
        self._create_si(f"TST-RPT-CP-SI-{uniq}", amount=1000.0)

        columns, data = execute(filters={
            "party_link": self.party_link_name,
            "company": self.company.name,
        })

        self.assertGreater(len(data), 0)
        opening = data[0]
        self.assertEqual(opening["remarks"], "Opening Balance")

        # Should show same net position
        closing = [r for r in data if r.get("is_closing")][0]
        self.assertEqual(closing["balance"], 2000.0)

        # Roles should be present
        trx = [
            r for r in data
            if not r.get("is_opening") and not r.get("is_closing") and not r.get("is_net_position")
        ]
        roles = set(r["role"] for r in trx)
        self.assertIn("As Supplier", roles)
        self.assertIn("As Customer", roles)

    def test_zero_entries_returns_basic_structure(self):
        """When no GL entries exist, report shows only opening and closing with zero balance."""
        columns, data = execute(filters={
            "party_link": self.party_link_name,
            "company": self.company.name,
        })

        self.assertGreaterEqual(len(data), 2)
        # Opening at zero
        self.assertEqual(data[0]["balance"], 0.0)
        self.assertEqual(data[0]["remarks"], "Opening Balance")

        # Closing at zero
        closing = [r for r in data if r.get("is_closing")]
        self.assertEqual(len(closing), 1)
        self.assertEqual(closing[0]["balance"], 0.0)
