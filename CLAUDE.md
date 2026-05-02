# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

Optimusland is a Frappe custom app for KAINOTOMO PH LTD, extending ERPNext with field customizations, custom DocTypes, reports, and utility functions for the potatoes supply chain business.

## Commands

- **Run tests**: `bench run-tests --app optimusland`
- **Run a single test**: `bench run-tests --app optimusland --module optimusland.optimusland.doctype.delivery_note_billing_wizard.test_delivery_note_billing_wizard`
- **Install app on a site**: `bench --site [site-name] install-app optimusland`
- **Start dev server**: `bench start`
- **Build frontend assets**: `bench build` (or `bench build --app optimusland`)
- **Export fixtures** (after DocType changes): `bench --site [site-name] export-fixtures --app optimusland`

## Architecture

### Hooks-driven app

All configuration flows through `optimusland/hooks.py` (doc_events for server-side document lifecycle hooks, doctype_js/doctype_list_js for client-side JS injection, scheduler_events for background jobs). There is no custom app initialization beyond setting `__version__ = "16.0.1"` in `__init__.py`.

### DocType event hooks

- **Purchase Receipt**: `on_submit` triggers `create_production_plan` (auto-creates Production Plan → Work Orders → Stock Entries). `validate` triggers `set_batch_no` which auto-assigns or creates Batch documents for "Potatoes" item group items.
- **Sales Invoice**: `before_save` triggers `warn_unlinked_items` which warns when "Potatoes" items aren't linked to a Delivery Note.

### Utility modules (`optimusland/utils/`)

Server-side Python functions decorated with `@frappe.whitelist()` — callable from client-side JS via `frappe.call()`. Each module maps to a specific DocType domain:

| File | Purpose |
|------|---------|
| `purchase_receipt.py` | Production plan creation, batch auto-assignment, stock entry fixes |
| `batch.py` | Bulk create Purchase Receipt from selected Batches |
| `customer.py` | Match/reconcile Delivery Notes to Sales Invoices for a customer |
| `supplier.py` | Detect unlinked Journal Entries that cause false supplier balances |
| `delivery_note.py` | Add shipping cost and link Purchase Invoice to Delivery Note |
| `sales_invoice.py` | Mark invoice as Paid (direct SQL update) |
| `purchase_invoice.py` | Mark invoice as Paid, auto-fill Purchase Receipt references |
| `invoices_status.py` | Scheduled-task fixes for unpaid/overdue invoice status (GL-based reconciliation) |

### Client-side JS (`optimusland/public/js/`)

Injected into standard ERPNext DocType forms via `doctype_js` in hooks. Each JS file extends `frappe.ui.form.on("DocType", {...})` to add custom buttons, validation, field queries, and batch ID auto-generation.

### Custom DocTypes

- **WeightSlip** + **WeightSlipItem**: Real DocTypes with DB tables.
- **DeliveryNoteBillingWizard**: Virtual DocType — stores data as JSON in Long Text fields using `@property` getters/setters. No DB table.

### Custom Reports

- **Unbilled Delivery Notes**: Raw SQL with subquery-based aggregation to calculate billed vs unbilled amounts, with variance detection between system-tracked and computed values.
- **Purchase Receipt Gross Profit**: Profit analysis on purchase receipts.

### Custom fields (`optimusland/optimusland/custom/`)

JSON fixture files adding `custom_`-prefixed fields to 11 standard DocTypes (Batch, Delivery Note, Delivery Note Item, Packed Item, Purchase Receipt, Purchase Receipt Item, Sales Invoice, Sales Invoice Item, Sales Order, Sales Order Item, Sales Taxes and Charges).

## Key conventions

- Custom fields always use the `custom_` prefix
- Utility functions are `@frappe.whitelist()` so the client can call them via RPC
- Batch IDs follow the pattern: `{item_code} * {prefix} * {formatted_date} * {supplier}`
- The "Potatoes" item group gets special handling in multiple places (batch auto-creation, Delivery Note linking validation)
- Production flow: Purchase Receipt → [on_submit] → Production Plan → Work Orders → Stock Entries (Material Transfer + Manufacture)
- Raw SQL is preferred in reports for accuracy over ORM queries
- Git remote: `origin` = `phalouvas/optimusland` — push to origin, PR to main
