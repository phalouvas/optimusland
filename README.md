## Optimusland

Optimus Land customizations

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