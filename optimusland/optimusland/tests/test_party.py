# Copyright (c) 2026, KAINOTOMO PH LTD and Contributors
# See license.txt

"""Tests for party.py: get_party_net_position and create_netting_journal_entry.

Creates invoices via raw SQL to bypass ERPNext accounting validation
that requires a full chart of accounts.
"""

import frappe
from frappe.tests import IntegrationTestCase

from optimusland.optimusland.tests import (
    get_or_create_test_company,
    get_or_create_test_warehouse,
    get_or_create_test_supplier,
    get_or_create_test_customer,
)
from optimusland.utils.party import get_party_net_position, create_netting_journal_entry


class TestPartyNetPosition(IntegrationTestCase):
    """Tests for party net position utilities."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.company = get_or_create_test_company()
        cls.warehouse = get_or_create_test_warehouse(cls.company.name)
        cls.supplier = get_or_create_test_supplier(cls.company.name)
        cls.customer = get_or_create_test_customer(cls.company.name)
        cls.creditors_account = frappe.db.get_value(
            "Account", {"company": cls.company.name, "account_type": "Payable", "is_group": 0}
        )
        cls.debtors_account = frappe.db.get_value(
            "Account", {"company": cls.company.name, "account_type": "Receivable", "is_group": 0}
        )

        # Ensure the supplier and customer share the same name so they can be linked
        # (the factory creates "_Test Supplier Optimus" and "_Test Customer Optimus")
        # We need them to match for Party Link to make sense.
        cls.dual_party_name = "_Test Dual Party Optimus"

        # Create a dual-role supplier
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

        # Create a dual-role customer with the same name
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

        # Create the Party Link between them
        if not frappe.db.exists("Party Link", {"primary_party": cls.dual_party_name}):
            frappe.get_doc({
                "doctype": "Party Link",
                "primary_role": "Supplier",
                "primary_party": cls.dual_party_name,
                "secondary_role": "Customer",
                "secondary_party": cls.dual_party_name,
            }).insert(ignore_permissions=True)

    def setUp(self):
        super().setUp()
        self._created_pis = []
        self._created_sis = []
        self._cleanup_invoices()

    def tearDown(self):
        self._cleanup_invoices()
        super().tearDown()

    def _cleanup_invoices(self):
        """Remove test invoices and their GL entries."""
        for name in getattr(self, "_created_pis", []):
            frappe.db.delete("GL Entry", {"voucher_no": name})
            frappe.db.delete("Purchase Invoice Item", {"parent": name})
            frappe.db.delete("Purchase Invoice", {"name": name})
        for name in getattr(self, "_created_sis", []):
            frappe.db.delete("GL Entry", {"voucher_no": name})
            frappe.db.delete("Sales Invoice Item", {"parent": name})
            frappe.db.delete("Sales Invoice", {"name": name})

    def _create_pi(self, name, amount=1000.0, status="Unpaid"):
        """Create a Purchase Invoice via raw SQL."""
        frappe.db.sql(
            """
            INSERT INTO `tabPurchase Invoice`
            (name, owner, creation, modified, modified_by, docstatus,
             company, posting_date, due_date, supplier, status, outstanding_amount)
            VALUES (%s, 'Administrator', NOW(), NOW(), 'Administrator', 1,
             %s, %s, %s, %s, %s, %s)
            """,
            (name, self.company.name, frappe.utils.today(),
             frappe.utils.today(), self.dual_party_name, status, amount),
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
        # Set credit_to to the Payable account (needed for JE reference validation)
        frappe.db.set_value("Purchase Invoice", name, "credit_to", self.creditors_account)
        # Create GL entries that reflect a real Purchase Invoice (Credit Payable)
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
             'Purchase Invoice', %s, 0, %s, %s)
            """,
            (gl_name, frappe.utils.today(), account, self.dual_party_name,
             amount, name, self.company.name, name, name, self.dual_party_name),
        )
        self._created_pis.append(name)

    def _create_si(self, name, amount=1000.0, status="Unpaid"):
        """Create a Sales Invoice via raw SQL."""
        frappe.db.sql(
            """
            INSERT INTO `tabSales Invoice`
            (name, owner, creation, modified, modified_by, docstatus,
             company, posting_date, due_date, customer, status, outstanding_amount)
            VALUES (%s, 'Administrator', NOW(), NOW(), 'Administrator', 1,
             %s, %s, %s, %s, %s, %s)
            """,
            (name, self.company.name, frappe.utils.today(),
             frappe.utils.today(), self.dual_party_name, status, amount),
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
        # Set debit_to to the Receivable account (needed for JE reference validation)
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
             'Sales Invoice', %s, 0, %s, %s)
            """,
            (gl_name, frappe.utils.today(), account, self.dual_party_name,
             amount, name, self.company.name, name, name, self.dual_party_name),
        )
        self._created_sis.append(name)

    # ------------------------------------------------------------------
    # Tests for get_party_net_position
    # ------------------------------------------------------------------

    def test_no_party_link_returns_false(self):
        """Party without a Party Link returns has_party_link: False."""
        result = get_party_net_position("Supplier", self.supplier.name)
        self.assertFalse(result["has_party_link"])

    def test_returns_correct_outstanding_from_supplier(self):
        """Supplier perspective returns correct PI and SI GL balances."""
        uniq = frappe.generate_hash("", 6)
        self._create_pi(f"TST-PI-NET-{uniq}", amount=5000.0)
        self._create_si(f"TST-SI-NET-{uniq}", amount=2000.0)

        result = get_party_net_position("Supplier", self.dual_party_name)
        self.assertTrue(result["has_party_link"])
        self.assertEqual(result["pi_gl"], 5000.0)
        self.assertEqual(result["si_gl"], 2000.0)
        self.assertEqual(result["net_position"], 3000.0)
        self.assertIn("Owed to Supplier", result["net_label"])

    def test_returns_correct_outstanding_from_customer(self):
        """Customer perspective returns correct SI and PI GL balances."""
        uniq = frappe.generate_hash("", 6)
        self._create_pi(f"TST-PI-NET2-{uniq}", amount=3000.0)
        self._create_si(f"TST-SI-NET2-{uniq}", amount=1000.0)

        result = get_party_net_position("Customer", self.dual_party_name)
        self.assertTrue(result["has_party_link"])
        self.assertEqual(result["pi_gl"], 3000.0)
        self.assertEqual(result["si_gl"], 1000.0)
        self.assertEqual(result["net_position"], 2000.0)
        self.assertIn("Owed to Supplier", result["net_label"])

    def test_negative_net_position(self):
        """When SI GL > PI GL, label says 'Owed by Customer'."""
        uniq = frappe.generate_hash("", 6)
        self._create_pi(f"TST-PI-NET3-{uniq}", amount=1000.0)
        self._create_si(f"TST-SI-NET3-{uniq}", amount=3000.0)

        result = get_party_net_position("Supplier", self.dual_party_name)
        self.assertTrue(result["has_party_link"])
        self.assertEqual(result["pi_gl"], 1000.0)
        self.assertEqual(result["si_gl"], 3000.0)
        self.assertEqual(result["net_position"], 2000.0)
        self.assertIn("Owed by Customer", result["net_label"])

    def test_zero_outstanding_returns_zero(self):
        """When no GL entries exist, both balances are zero."""
        result = get_party_net_position("Supplier", self.dual_party_name)
        self.assertTrue(result["has_party_link"])
        self.assertEqual(result["pi_gl"], 0.0)
        self.assertEqual(result["si_gl"], 0.0)
        self.assertEqual(result["net_position"], 0.0)

    # ------------------------------------------------------------------
    # Tests for create_netting_journal_entry
    # ------------------------------------------------------------------

    def test_create_netting_je_no_link(self):
        """Creating a netting JE without a Party Link returns an error."""
        result = create_netting_journal_entry("Supplier", self.supplier.name)
        self.assertFalse(result["success"])
        self.assertIn("No Party Link", result.get("error", ""))

    def test_create_netting_je_success(self):
        """Creates a draft JE with the correct netting amount and invoice references."""
        uniq = frappe.generate_hash("", 6)
        pi_name = f"TST-PI-JE-{uniq}"
        si_name = f"TST-SI-JE-{uniq}"
        self._create_pi(pi_name, amount=8000.0)
        self._create_si(si_name, amount=3000.0)

        result = create_netting_journal_entry("Supplier", self.dual_party_name)
        self.assertTrue(result["success"])
        self.assertIn("journal_entry", result)

        je_name = result["journal_entry"]
        je = frappe.get_doc("Journal Entry", je_name)

        self.assertEqual(je.docstatus, 0)  # Draft
        self.assertEqual(len(je.accounts), 2)

        # Find the PI and SI rows
        pi_row = next(a for a in je.accounts if a.reference_type == "Purchase Invoice")
        si_row = next(a for a in je.accounts if a.reference_type == "Sales Invoice")

        # PI row: Debit Payable referencing the PI, amount = min(8000, 3000) = 3000
        self.assertEqual(pi_row.reference_name, pi_name)
        self.assertEqual(pi_row.debit_in_account_currency, 3000.0)
        self.assertEqual(pi_row.credit_in_account_currency, 0)

        # SI row: Credit Receivable referencing the SI
        self.assertEqual(si_row.reference_name, si_name)
        self.assertEqual(si_row.debit_in_account_currency, 0)
        self.assertEqual(si_row.credit_in_account_currency, 3000.0)

        # Clean up: delete the test JE
        frappe.delete_doc("Journal Entry", je_name, force=True)

    def test_create_netting_je_zero_outstanding(self):
        """Creating a netting JE when outstanding is zero returns an error."""
        result = create_netting_journal_entry("Supplier", self.dual_party_name)
        self.assertFalse(result["success"])
        self.assertIn("zero", result.get("error", "").lower())
