## Optimusland

Optimus Land customizations for ERPNext v16 — potato supply chain management.

### Features

- **Simplified workflow**: Purchase Receipt → Delivery Note → Sales Invoice → Purchase Invoice (no BOMs/Manufacturing)
- **Blended Rate Calculator**: Real P&L-based rate per kg — Operating Rate (90-day weighted avg) + Capital Rate (365-day depreciation) → **Base Rate**
- **Grower Price Formula**: `selling_rate × (1 − margin%) − base_rate − additional_costs_per_kg` — automatically computes recommended supplier price per batch
- **SI Additional Costs**: Add shipping/cold storage/storage costs on Draft Sales Invoices before the grower price preview
- **PI Price Calculator**: "Calculate Grower Price" button traces batch → SI → selling price, applies formula, lets user override before creating the Purchase Invoice
- **Base Rate Report**: Per-batch profitability — sale price, suggested price, paid, margin %, profit €
- **Supplier Profitability**: Grouped by supplier — kilos, avg sale, avg paid, margin %, profit
- **Customer Profitability**: Grouped by customer — same metrics
- **Blended Rate Snapshot**: Audit trail of every rate calculation, stored as DocType
- **Configurable Settings**: Operating/depreciation accounts, lookback periods, item group/UOM filters, margin %, sanity check thresholds
- **Payment reminders**: Configurable 4-level escalation (Email + SMS) for overdue Sales Invoices
- **Batch traceability**: Full chain from Weight Slip → Batch → PR → DN → SI via custom link fields
- **Invoice status reconciliation**: GL-based auto-fix for unpaid/overdue invoice statuses

### Testing

```bash
# Run all tests
bench run-tests --app optimusland

# Run a specific module
bench run-tests --app optimusland --module optimusland.optimusland.tests.test_batch_utils
```

Tests use `IntegrationTestCase` and run in an isolated `test_` database.

#### License

mit