# Optimusland — Copilot Instructions

## Project Overview

Optimusland is a Frappe v16 custom app for **KAINOTOMO PH LTD**, extending ERPNext with customizations for the potato supply chain business.

**Optimus Land** operates as intermediary potato packager:
- Buys bulk/unwashed potatoes from farmers (suppliers)
- Washes/grades/bags into packaged products
- Sells to export customers

**Always use "Supplier" not "Grower"** in labels, field names, and code.

## Business Flow (post-Issue #78)

Old BOM/Manufacturing (Production Plan → Work Orders → Stock Entries) replaced with:

```
Weight Slip → Batch → Purchase Receipt → Delivery Note → Sales Invoice → Purchase Invoice
```

No BOMs, no Work Orders, no Manufacture Stock Entries.

### Price Calculation

**Base Rate** (€/kg) — from real P&L data (`blended_rate.py`):
- **Operating Rate**: Exponential weighted average of P&L operating accounts ÷ kg sold (90-day lookback)
- **Capital Rate**: Depreciation accounts ÷ annual kg sold (365-day lookback)

**Supplier Price Formula:**

$$ \text{price} = \text{selling\_rate} \times (1 - \text{margin\%}) - \text{operating\_rate} - \text{capital\_rate} - \text{addl\_costs\_per\_kg} $$

Set on PI via **"Calculate Grower Price"** button. Previewed on SI via **"Preview Grower Price"** button.

### Reports

| Report | Type | Purpose |
|--------|------|---------|
| **Base Rate** | Script | Per-batch: SI, kilos, sale, suggested, paid, margin %, profit € |
| **Supplier Profitability** | Script | Grouped by supplier |
| **Customer Profitability** | Script | Grouped by customer |

### Settings (Optimus General Settings)

- Operating/depreciation P&L accounts
- Lookback days, half-life days
- Item group + UOM (default Potatoes/Kg)
- Default target margin %
- Sanity check thresholds

## Key Files

### Python (`optimusland/utils/`)

| File | Purpose |
|------|---------|
| `blended_rate.py` | Base rate calculator. `@frappe.whitelist()` |
| `grower_calculator.py` | Supplier price + PI creation + WS batch lookup. `@frappe.whitelist()` |
| `purchase_receipt.py` | `set_batch_no()` on validate |
| `batch.py` | Bulk-create PR from batches |
| `party.py` | Net Position + Netting JE |
| `delivery_note.py` | Add/remove shipping cost (legacy) |
| `payment_reminder.py` | Daily — overdue SI reminders |
| `setup.py` | `after_migrate` — seed templates |

### JS (`optimusland/public/js/`)

| File | Purpose |
|------|---------|
| `sales_invoice.js` | Add Cost, Remove Cost, Preview Grower Price |
| `purchase_invoice.js` | Calculate Grower Price dialog |
| `purchase_receipt.js` | Sort items, filter WS |
| `batch.js` / `batch_list.js` | Batch auto-id, Create PR |
| `supplier.js` / `customer.js` | Net Position + Netting JE |

### DocType Hooks (`hooks.py`)

```python
doc_events = {
    "Purchase Receipt": {
        "validate": "optimusland.utils.purchase_receipt.set_batch_no",
        "on_submit": "optimusland.utils.purchase_receipt.update_weight_slip_status",
        "on_cancel": "optimusland.utils.purchase_receipt.update_weight_slip_status",
    },
}
```

### Custom DocTypes

- **Weight Slip** + **Weight Slip Item**: Farmer weigh-in
- **Blended Rate Snapshot**: Audit trail (auto-created)
- **Sales Invoice Additional Cost**: Child table for Draft SI costs

### Reports (`optimusland/optimusland/report/`)

| Report | Type |
|--------|------|
| `base_rate/base_rate.py` | Script — per-batch detail |
| `supplier_profitability/supplier_profitability.py` | Script — grouped by supplier |
| `customer_profitability/customer_profitability.py` | Script — grouped by customer |
| `unbilled_delivery_notes/` | Script — unbilled DNs |

### Report Name Convention

Frappe derives module path from JSON `name`. "Customer Profitability" → module `customer_profitability` → file `customer_profitability.py` in `customer_profitability/`.

### Custom Fields — Key Ones

| DocType | Fields |
|---------|--------|
| Batch | `custom_prefix`, `custom_supplier_optimus` (→Supplier), `custom_weight_slip` (→WS) |
| Customer | `custom_national_id` |
| PR | `custom_weight_slip` |
| PR Item | `custom_batch_prefix` |
| SI | `additional_costs` (table → Sales Invoice Additional Cost) |
| DN | `custom_shipping_cost`, `custom_shipping_rate` (hidden — legacy) |

### Frappe RPC Gotchas

- Lists arrive as JSON strings — call `frappe.parse_json()` at function entry
- PI→PR link is `pr_detail`, not `purchase_receipt_item`
- Batch→SI trace goes through Serial and Batch Entry bundles

## Commands

- **Run all tests**: `bench run-tests --app optimusland`
- **Run module**: `bench run-tests --app optimusland --module optimusland.optimusland.tests.test_batch_utils`
- **Dev**: JS/Python auto-reload — no `bench build` needed
- **Migrate**: `bench --site [site] migrate`
- **Start server**: `bench start`
