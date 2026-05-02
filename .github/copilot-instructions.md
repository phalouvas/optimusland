# Optimusland AI Agent Instructions

This file provides essential knowledge for AI agents working on the Optimusland Frappe/ERPNext custom app. Follow these guidelines to be immediately productive and avoid common pitfalls.

## Project Overview

Optimusland is a custom Frappe app for "Optimus Land" (KAINOTOMO PH LTD) that provides:
- **Field customizations** for 11 standard DocTypes (Delivery Note, Sales Invoice, Purchase Receipt, Batch, etc.)
- **Two custom DocTypes**: `DeliveryNoteBillingWizard` (virtual) and `WeightSlip` (real)
- **One custom Report**: `UnbilledDeliveryNotes` with advanced data integrity validation
- **Utilities** for batch workflows, invoice status fixes, customer/supplier enhancements
- **Frontend hooks** injecting custom JavaScript into 7 standard DocTypes

**Repository**: `phalouvas/optimusland`  
**Default branch**: `main`  
**Deployment target**: Frappe v15 (deploy configs reference v15; app reports version 16.0.1 — ensure compatibility when making changes)

## Development Environment

### Prerequisites
- **Frappe Bench** with Frappe v15/v16 installed
- **Python 3.10+** (specified in `pyproject.toml`)
- **Node.js** (for frontend assets)
- **Docker** (for deployment)

### Setup
1. Clone the repository into your bench apps directory: `cd ~/frappe-bench/apps && git clone <repo>`
2. Install the app: `bench --site [site-name] install-app optimusland`
3. For development mode: `bench setup requirements --dev`

**Note**: The workspace is currently at `/workspace/development/v16/apps/optimusland` which suggests v16 development, but deployment targets v15. Ensure compatibility when making changes.

## Build and Test

### Running Tests
- **Standard Frappe test command**: `bench run-tests --app optimusland`
- **Test files location**:
  - `optimusland/optimusland/doctype/delivery_note_billing_wizard/test_delivery_note_billing_wizard.py`
  - `optimusland/optimusland/doctype/weight_slip/test_weight_slip.py`
  - `optimusland/optimusland/report/unbilled_delivery_notes/test_report.py`

### Building Frontend Assets
- **Build app assets**: `bench build --app optimusland`
- JS changes in `optimusland/public/js/` require a build to take effect
- Custom DocType JS/JSON changes require `bench --site [site-name] export-fixtures --app optimusland`

### Docker Deployment (Production)
Refer to **[deploy/README.md](deploy/README.md)** for detailed setup:
- Multi-step process using `frappe_docker` fork
- Custom compose overrides (`compose.multi-bench-kainotomo.yaml`)
- Image build with version tagging (`phalouvas/optimusland-worker:15.24.1`)
- Deploy script: `deploy/deploy.sh`

## Architecture & Components

### Module Structure
Single module: `Optimusland` (see `optimusland/modules.txt`)

### Key Components
1. **Virtual DocType Pattern** (`DeliveryNoteBillingWizard`)
   - Stores all data as JSON in Long Text fields
   - Uses `@property` getters/setters with `json.loads()`/`json.dumps()`
   - No database tables
   - Reference: **[WIZARD_IMPLEMENTATION.md](optimusland/optimusland/doctype/delivery_note_billing_wizard/WIZARD_IMPLEMENTATION.md)**

2. **Custom Report with SQL Queries** (`UnbilledDeliveryNotes`)
   - Uses raw SQL JOINs for accuracy rather than ORM
   - Subquery-based calculation with customer validation
   - Data integrity validation with variance detection
   - Reference: **[IMPLEMENTATION_SUMMARY.md](optimusland/optimusland/report/unbilled_delivery_notes/IMPLEMENTATION_SUMMARY.md)** and **[README.md](optimusland/optimusland/report/unbilled_delivery_notes/README.md)**

3. **Field Customizations**
   - JSON files in `optimusland/optimusland/custom/`
   - Prefixed with `custom_` (e.g., `custom_supplier_optimus`)
   - Applied to 11 standard DocTypes

4. **Utilities** (`optimusland/utils/`)
   - 8 Python modules with `@frappe.whitelist()` decorators
   - Callable via Frappe RPC from client-side
   - Examples: batch workflows, invoice status fixes

5. **Frontend Hooks** (`hooks.py`)
   - Custom JavaScript injected into 7 standard DocTypes
   - Located in `optimusland/public/js/`
   - Bound via `doctype_js` and `doctype_list_js` in hooks

## Project-Specific Conventions

### 1. Virtual DocType Pattern
- Use `@property` + JSON serialization for field state
- Example: `delivery_note_billing_wizard.py`
- Tab-based workflow (`wizard_tab` field) – changing tabs mid-process could lose unsaved data

### 2. Direct SQL Queries
- Reports use raw SQL for accuracy
- JOIN pattern: link via `delivery_note`/`dn_detail` fields in sales invoice items
- Always include customer validation to prevent incorrect invoice linkages

### 3. Custom Field Naming
- Prefix with `custom_` (e.g., `custom_supplier_optimus`)
- Defined in JSON files under `optimusland/optimusland/custom/`

### 4. Client-Side APIs
- Utilities exposed via `@frappe.whitelist()` decorator
- Call from JavaScript using `frappe.call()`

### 5. Server-Side HTML Rendering
- Wizard renders interactive HTML tables in Python
- JavaScript binds to these tables at client-side
- Pattern: `window.global_function` in JS for table interaction

## Potential Pitfalls

### 1. Version Mismatch
- Workspace is `v16` but deployment targets Frappe v15
- Ensure changes are compatible with both versions
- Test on appropriate bench environment

### 2. Virtual DocType Limitations
- No automatic DB persistence
- Must manually manage JSON serialization in properties
- Tab state management crucial

### 3. Scheduled Tasks
- `tasks.py` has daily background jobs commented out
- Re-enable carefully as they modify invoice status globally

### 4. No Linting/Type Checking
- No mypy, flake8, or linting in pipeline
- Code quality relies on manual review
- Consider adding type hints for new code

### 5. Docker Deployment Complexity
- Multi-step process with custom overrides
- Ensure environment files are updated before deployment
- Image build must be done on local machine, not production server

## Key Files as Reference Patterns

| File | Purpose | Pattern |
|------|---------|---------|
| `optimusland/optimusland/doctype/delivery_note_billing_wizard/delivery_note_billing_wizard.py` | Virtual DocType with JSON persistence | `@property` + `json.loads()`/`json.dumps()` for field state |
| `optimusland/optimusland/report/unbilled_delivery_notes/unbilled_delivery_notes.py` | SQL report with subqueries | JOIN pattern linking via `delivery_note`/`dn_detail` fields |
| `optimusland/optimusland/utils/batch.py` | Utility callable from UI | `@frappe.whitelist()` + `frappe.new_doc()` for bulk operations |
| `optimusland/optimusland/doctype/delivery_note_billing_wizard/delivery_note_billing_wizard.js` | Client-side form logic | `window.global_function` for HTML table interaction binding |
| `optimusland/optimusland/custom/delivery_note.json` | Field customization | JSON structure with `custom_fields` array, `dt` = DocType name |

## Common Tasks for AI Agents

### Adding a New Custom Field
1. Create/edit JSON file in `optimusland/optimusland/custom/`
2. Follow existing pattern: `{"dt": "DocType", "custom_fields": [...]}`
3. Prefix field name with `custom_`
4. Test field appears in DocType form

### Creating a New Utility Function
1. Add to existing module in `optimusland/utils/` or create new one
2. Use `@frappe.whitelist()` decorator
3. Document with docstring
4. Add client-side call in appropriate JS file if needed

### Writing a Test
1. Extend `FrappeTestCase`
2. Place tests in the relevant `doctype/` or `report/` directory
3. Run with `bench run-tests --app optimusland --module <module-path>`

### Modifying the Wizard
1. Understand tab-based workflow (`wizard_tab` field)
2. Maintain JSON serialization in properties
3. Update both Python and JavaScript files
4. Test tab transitions don't lose data

### Updating the Report
1. Use SQL queries with customer validation
2. Include data integrity validation (variance detection)
3. Follow color-coding scheme documented in README
4. Test with edge cases (zero invoices, closed delivery notes)

## Documentation Links

- **[deploy/README.md](deploy/README.md)** – Docker setup, image build, deployment
- **[WIZARD_IMPLEMENTATION.md](optimusland/optimusland/doctype/delivery_note_billing_wizard/WIZARD_IMPLEMENTATION.md)** – Virtual DocType architecture
- **[IMPLEMENTATION_SUMMARY.md](optimusland/optimusland/report/unbilled_delivery_notes/IMPLEMENTATION_SUMMARY.md)** – Report enhancements
- **[unbilled_delivery_notes/README.md](optimusland/optimusland/report/unbilled_delivery_notes/README.md)** – User-facing report guide
- **[hooks.py](optimusland/hooks.py)** – Frontend JavaScript injections
- **[pyproject.toml](pyproject.toml)** – Python dependencies

## Notes for AI Agents

- **Always check version compatibility** (v15 vs v16)
- **Preserve existing patterns** – this codebase has established conventions
- **Link to existing documentation** rather than duplicating information
- **Test changes** using Frappe's test framework before deployment
- **Consider Docker implications** for production deployment

---

*Last updated: May 2, 2026*  
*For questions, refer to the repository owner: KAINOTOMO PH LTD (info@kainotomo.com)*