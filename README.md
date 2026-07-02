## Optimusland

Optimus Land customizations for ERPNext v16 — potato supply chain management.

### Features

- **Automated manufacturing flow**: Purchase Receipt submit auto-creates Production Plan → Work Orders → Stock Entries (Material Transfer + Manufacture)
- **Manufacturing Pipeline Dashboard**: Three-tier visibility (Sourcing → Manufacturing → Fulfillment) in a dedicated workspace, restricted to System Managers. Access via Optimus sidebar → Settings → Manufacturing Pipeline.
- **Daily pipeline health digest**: Automated email summary of critical and warning-level alerts
- **Payment reminders**: Configurable 4-level escalation (Email + SMS) for overdue Sales Invoices
- **Shipping cost management**: Add/remove shipping costs on submitted Delivery Notes
- **Batch-to-PR bulk creation**: Create Purchase Receipts from selected Batches
- **Supplier unlinked JV detection**: Warns when Journal Entries could affect supplier balance accuracy
- **Invoice status reconciliation**: GL-based auto-fix for unpaid/overdue invoice statuses (JE hooks + daily cron)
- **Batch traceability**: Full chain from Weight Slip → Batch → PR → PP → WO → SE → DN → SI via custom link fields

### Testing

```bash
# Run all tests
bench run-tests --app optimusland

# Run a specific module
bench run-tests --app optimusland --module optimusland.optimusland.tests.test_purchase_receipt_utils

# Run tests for a specific doctype
bench run-tests --app optimusland --doctype "Delivery Note"

# Run a single test class
bench run-tests --app optimusland --module optimusland.optimusland.tests.test_delivery_note_utils.TestValidateBatchManufacture
```

Tests use `IntegrationTestCase` and run in an isolated `test_` database — never touching production data. Each test is transactionally rolled back after completion.

#### License

mit