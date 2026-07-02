# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

Optimusland is a Frappe custom app for **KAINOTOMO PH LTD**, extending ERPNext with field customizations, custom DocTypes, reports, and utility functions for the potato supply chain business.

The company operates **Optimus Land** as an intermediary potato packager: it purchases bulk/unwashed potatoes from farmers (producers), washes/grades/bags them into packaged products, and sells to export customers (e.g., export customers).

## Business Context

### Process Flow

The complete operational flow:

```
Weight Slip → Batch → Purchase Receipt → [on_submit] → Production Plan → Work Orders → Stock Entries (Material Transfer + Manufacture) → Delivery Note → Sales Invoice → Purchase Invoice
```

A **Manufacturing Pipeline** workspace provides full-cycle visibility across all 8 stages (split into three tiers: Sourcing, Manufacturing, Fulfillment). Access it via the Optimus sidebar under **Settings → Manufacturing Pipeline** — restricted to System Manager role by default.

1. **Weight Slip**: Farmer weigh-in at the gate. Standalone record with free-text fields.
2. **Batch**: Created automatically by `set_batch_no()` during PR validate. Linked to Weight Slip via `custom_weight_slip` (auto-populated from PR).
3. **Purchase Receipt**: Potatoes received from farmers. `on_submit` triggers `create_production_plan` (`optimusland/utils/purchase_receipt.py`). Linked to its Production Plan via `custom_production_plan` (auto-populated).
4. **Production Plan**: Auto-created with items from the PR; each item's BOM fetched dynamically via `get_item_details()`.
5. **Work Orders**: Created from the Production Plan and submitted automatically.
6. **Stock Entries**: Two per Work Order — Material Transfer for Manufacture (raw materials consumed) then Manufacture (finished goods produced, with batch assignment and purchase rate).
7. **Delivery Note**: Packaged goods shipped to customers. Shipping cost can be added post-submit. SI→DN linking enforced natively via Selling Settings `dn_required=Yes`.
8. **Sales Invoice**: Billed to customer. No custom hooks — `dn_required=Yes` blocks save if items lack Delivery Note links.
9. **Purchase Invoice**: Farmer payment. Journal Entry `on_submit`/`on_cancel` hooks handle status (pipeline monitor covers unpaid/unlinked PIs).

1. **Purchase Receipt**: Potatoes received from farmers. `on_submit` triggers `create_production_plan` (`optimusland/utils/purchase_receipt.py`).
2. **Production Plan**: Auto-created with items from the PR; each item's BOM fetched dynamically via `get_item_details()`.
3. **Work Orders**: Created from the Production Plan and submitted automatically.
4. **Stock Entries**: Two per Work Order — Material Transfer for Manufacture (raw materials consumed) then Manufacture (finished goods produced, with batch assignment and purchase rate).
5. **Delivery Note**: Packaged goods shipped to customers. Shipping cost can be added post-submit.
6. **Sales Invoice**: Billed to customer. `before_save` warns if "Potatoes" items lack a Delivery Note link (soft warning, does not block save).

### Why Raw Potato is NOT in the BOM

The farmer's purchase price is negotiated **after** the final sale to the customer. If potato were in the Bill of Materials, its cost would lock at Work Order creation time — before the farmer has even been invoiced. This is intentional and correct.

BOMs contain only packaging and overhead:

| BOM | Cost | Contents |
|-----|------|----------|
| BOM-PB-005 | ~€0.0892/kg | Bags, electricity, salary, rent, fuel, pallets |
| BOM-PJ-003 | ~€0.0693/kg | Bags, cards, nets, threads, electricity, salary, rent, fuel, pallets |

No raw potato appears in any BOM.

### `supplier_rate` Formula

Calculated in the **Purchase Receipt Gross Profit** report (`purchase_receipt_gross_profit.py`, line 335):

$$ \text{supplier\_rate} = \text{selling\_rate} + \text{purchase\_rate} - \text{incoming\_rate} - \text{wished\_profit\_rate} $$

| Variable | Source |
|----------|--------|
| `selling_rate` | Sales Invoice Item `net_rate` |
| `purchase_rate` | Purchase Receipt Item `rate` |
| `incoming_rate` | Delivery Note `custom_shipping_rate` + Serial and Batch Entry `incoming_rate` |
| `wished_profit_rate` | `(wished_earning_percentage / 100) × selling_rate` (user filter parameter) |

This is a **negotiation tool**: the maximum payable to the farmer while achieving the wished profit. Not an accounting figure.

### Shipping Cost

Managed via the **"Add Shipping Cost"** button on submitted Delivery Notes:

1. Dialog opens — user enters cost or selects a Purchase Invoice (auto-fills from PI `grand_total`)
2. Calls `add_shipping_cost()` in `optimusland/utils/delivery_note.py`
3. Distributes cost per kg: `shipping_rate += shipping_cost / total_qty` (cumulative)
4. `custom_shipping_rate` feeds into `incoming_rate` in the profit report
5. **"Remove Shipping Cost"** button reverses it

**Known limitation**: Does NOT retroactively update already-created Sales Invoices.

### Batch Naming

Full traceability via batch IDs, generated in `set_batch_no()` (`optimusland/utils/purchase_receipt.py`, lines 177–180):

```
{item_code} * {prefix} * {formatted_date} * {supplier}
```

Fallback when no prefix:

```
{item_code} * {formatted_date} * {supplier}
```

## Commands

### Testing

Tests use Frappe's `IntegrationTestCase` (not the deprecated `FrappeTestCase`). They run in an isolated `test_` database — never touching production data. Each test is transactionally isolated (auto-rollback after completion). Tests run automatically via GitHub Actions on every PR to `version-16` (see `.github/workflows/ci.yml`), and **locally via a pre-push git hook** at `.githooks/pre-push`.

- **Run all tests**: `bench run-tests --app optimusland`
- **Run a single module**: `bench run-tests --app optimusland --module optimusland.optimusland.tests.test_purchase_receipt_utils`
- **Run by doctype**: `bench run-tests --app optimusland --doctype "Purchase Receipt"`
- **Run pipeline tests**: `bench run-tests --app optimusland --module optimusland.optimusland.tests.test_pipeline`

Test fixtures live in `optimusland/optimusland/tests/__init__.py` (factory functions). The `before_tests` hook seeds minimum data (Company, Item, BOM, Supplier, Customer) in the test DB only.

### Other commands

- **Install app on a site**: `bench --site [site-name] install-app optimusland``
- **Start dev server**: `bench start`
- **Build frontend assets**: `bench build` (or `bench build --app optimusland`)
- **Export fixtures** (after DocType changes): `bench --site [site-name] export-fixtures --app optimusland`

## Architecture

### Hooks-driven app

All configuration flows through `optimusland/hooks.py`:
- **`doc_events`**: Server-side document lifecycle hooks (Purchase Receipt, Sales Invoice)
- **`doctype_js`** / **`doctype_list_js`**: Client-side JS injection into DocType forms and list views
- **`scheduler_events`**: Daily background jobs — fix unpaid/overdue invoice status, send payment reminders
- **`after_migrate`**: Seeds default payment reminder templates (`optimusland.utils.setup.after_migrate`)

There is no custom app initialization beyond setting `__version__ = "16.0.1"` in `__init__.py`.

### DocType event hooks

- **Purchase Receipt**: `on_submit` triggers `create_production_plan` (auto-creates Production Plan → Work Orders → Stock Entries). `validate` triggers `set_batch_no` which auto-assigns or creates Batch documents for "Potatoes" item group items. `create_production_plan` now sets `custom_production_plan` on PR for traceability and logs BOM failures as PR comments (not silent skips).
- **Delivery Note**: `before_submit` triggers `validate_batch_manufacture` — blocks DN submission if batches haven't been manufactured.
- **Journal Entry**: `on_submit` and `on_cancel` hooks in `invoices_status.py` — auto-mark invoices as Paid when GL balance ≈ 0, and revert on cancellation.
- **Sales Invoice**: No custom hooks — SI→DN linking is enforced natively via Selling Settings `dn_required=Yes`.

### Python Utility Modules (`optimusland/utils/`)

Server-side Python functions decorated with `@frappe.whitelist()` — callable from client-side JS via `frappe.call()`. Each module maps to a specific DocType domain:

| File | Purpose |
|------|---------|
| `purchase_receipt.py` | Production plan auto-creation (`on_submit`), batch auto-assignment (`validate`), Stock Entry account fixing |
| `batch.py` | Bulk create Purchase Receipt from selected Batches |
| `supplier.py` | Detect unlinked Journal Entries on Supplier forms |
| `delivery_note.py` | Add/remove shipping cost, link Purchase Invoice to Delivery Note |
| `sales_invoice.py` | Mark invoice as Paid (direct SQL — legacy, see `invoices_status.py` for current approach) |
| `purchase_invoice.py` | Mark invoice as Paid (direct SQL — legacy), auto-fill Purchase Receipt references |
| `invoices_status.py` | GL-based invoice status reconciliation (JE `on_submit`/`on_cancel` hooks + daily cron). Replaced `mark_paid` SQL functions. |
| `payment_reminder.py` | Daily scheduled task — send Email/SMS payment reminders for overdue Sales Invoices (levels 1–4) |
| `pipeline.py` | Manufacturing Pipeline Dashboard data queries, alert detection, retry/submit actions — called from the workspace Custom HTML Block |
| `pipeline_monitor.py` | Daily pipeline health digest email — sends critical/warning alerts to configured recipients |
| `setup.py` | `after_migrate` — seeds 8 default payment reminder templates into Optimus General Settings + creates the Pipeline Dashboard Custom HTML Block |

### Client-side JS (`optimusland/public/js/`)

Injected into standard ERPNext DocType forms via **`doctype_js`** in hooks (form views) and **`doctype_list_js`** (list views). Each file extends `frappe.ui.form.on(...)` for form scripts or `frappe.listview_settings[...]` for list scripts.

| File | Injected Into | Purpose |
|------|---------------|---------|
| `purchase_receipt.js` | Purchase Receipt form | Sorts items by qty descending before save; filters `custom_weight_slip` by supplier |
| `batch.js` | Batch form | Auto-generates `batch_id` on new Batch records |
| `batch_list.js` | Batch list view | "Create Purchase Receipt" action from selected Batches (validates same supplier) |
| `supplier.js` | Supplier form | On load: checks for unlinked Journal Entries, shows warning alert |
| `delivery_note.js` | Delivery Note form | "Add Shipping Cost" dialog + "Remove Shipping Cost" button (submitted DNs only) |
| `sales_invoice.js` | Sales Invoice form | "Mark as Paid" button (submitted+overdue); Incoterm reminder on new invoices |
| `purchase_invoice.js` | Purchase Invoice form | "Mark as Paid" button (submitted+overdue); naming series reminder on new invoices |

### Custom DocTypes

- **WeightSlip** + **WeightSlipItem**: Real DocTypes with DB tables.
- **DeliveryNoteBillingWizard**: Virtual DocType — stores data as JSON in Long Text fields using `@property` getters/setters. No DB table.

### Manufacturing Pipeline Dashboard

A **separate workspace** (restricted to System Manager role) for full-cycle pipeline visibility:

| Tier | Stages | Backend function |
|------|--------|-----------------|
| **Sourcing** | Weight Slip → Batch → PR | `pipeline.py:_get_sourcing_data()` |
| **Manufacturing** | PR → PP → WO → SE | `pipeline.py:_get_manufacturing_data()` |
| **Fulfillment** | DN → SI → PI | `pipeline.py:_get_fulfillment_data()` |

The workspace shows:
- **Shortcuts** with `stats_filter` for live alert counts (Failed PRs, Stuck WOs, Unbilled DNs)
- **Custom HTML Block**: Interactive pipeline table with color-coded status, click-to-navigate entity links, Retry/Submit action buttons. All three tiers and alerts start collapsed by default.
- **Alerts panel**: Cross-cutting issues — orphaned PRs, missing BOMs, stuck WOs, unbilled DNs, manufactured batches ready to ship, unlinked PIs, unlinked supplier JVs

Access it from the Optimus sidebar under **Settings → Manufacturing Pipeline**. Configured via `optimusland/optimusland/workspace/manufacturing_pipeline/manufacturing_pipeline.json`. The Custom HTML Block is created automatically by `after_migrate` (`setup.py`) and served from `optimusland/public/html/pipeline_table.html`. Python backend at `utils/pipeline.py` with `@frappe.whitelist()` methods. Daily digest email via `utils/pipeline_monitor.py`.

### Custom Reports

- **Unbilled Delivery Notes**: Raw SQL with subquery-based aggregation to calculate billed vs unbilled amounts, with variance detection between system-tracked and computed values.
- **Purchase Receipt Gross Profit**: Profit analysis on purchase receipts.

### Custom Fields (`optimusland/optimusland/custom/`)

JSON fixture files adding fields to standard DocTypes. Fields use the `custom_` prefix convention of ERPNext.

| DocType | Custom Fields Added |
|---------|-------------------|
| Batch | `custom_prefix` (Data), `custom_supplier_optimus` (Link → Supplier), `custom_weight_slip` (Link → Weight Slip, read-only, auto-set from PR) |
| Customer | `custom_national_id` (Data) |
| Delivery Note | `custom_shipping_purchase_invoice` (Link → PI), `custom_shipping_cost` (Currency), `custom_shipping_rate` (Float, read-only), `custom_is_shipping_cost_added` (Check, read-only) |
| Purchase Receipt | `custom_weight_slip` (Link → Weight Slip), `custom_production_plan` (Link → Production Plan, read-only, auto-set on PP creation) |
| Purchase Receipt Item | `custom_batch_prefix` (Data, fetch from `batch_no.custom_prefix`) |
| Sales Invoice | `custom_shipping_cost` (Currency, hidden in print), `shipping_details` (Markdown Editor) |
| Sales Order Item | `supplier_code` (Link → Supplier), `supplier_name` (Data, fetch from `supplier_code`) |

Other fixture files exist (Delivery Note Item, Packed Item, Sales Invoice Item, Sales Order, Sales Taxes and Charges) but contain only property setters (layout/visibility changes), not custom fields.

## Key conventions

- Custom fields always use the `custom_` prefix
- Utility functions are `@frappe.whitelist()` so the client can call them via RPC
- Batch IDs follow the pattern: `{item_code} * {prefix} * {formatted_date} * {supplier}` for full traceability
- The "Potatoes" item group gets special handling in multiple places (batch auto-creation, Delivery Note linking validation)
- `warn_unlinked_items` uses `frappe.msgprint` (soft warning) — does NOT block save (intentional)
- Raw SQL is preferred in reports for accuracy over ORM queries
- Git remote: `origin` = `phalouvas/optimusland` — push to origin, PR to main
- Error logging uses `frappe.add_comment("Comment", ...)` on the affected document rather than silent exceptions (applied in `create_production_plan` for BOM-fetch failures)
- SI→DN linking is enforced at ERPNext core level via Selling Settings `dn_required=Yes`, no custom validation needed
