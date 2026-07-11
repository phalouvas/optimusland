import frappe

from erpnext.manufacturing.doctype.work_order.work_order import get_item_details, make_stock_entry


@frappe.whitelist()
def create_production_plan(purchase_receipt, method=None):
    """Create Production Plan from Purchase Receipt items (dual-run gate).

    During the dual-run transition:
    - Old item codes (PJ-, PB-, P- prefixed) → Production Plan created (legacy)
    - New single-code items → skipped (use Repack workflow instead)

    After all old WOs complete, this function is removed entirely.
    See Issue #78 for the full transition plan.
    """
    purchase_receipt = frappe.get_doc("Purchase Receipt", purchase_receipt.name)

    # Dual-run gate: skip Production Plan for new single-code items
    old_prefixes = ("PJ-", "PB-", "P-")
    has_old_items = any(
        item.item_code.startswith(old_prefixes) for item in purchase_receipt.items
    )
    if not has_old_items:
        purchase_receipt.add_comment(
            "Comment",
            "All items use the new single-code scheme. "
            "Production Plan creation skipped — use Repack Stock Entry instead. "
            "This is expected behaviour per the new blended rate workflow.",
        )
        return

    batch_nos = []
    for item in purchase_receipt.items:
        batch_no = None
        if item.batch_no == None and item.serial_and_batch_bundle:
                batch_no = frappe.db.sql(f"SELECT batch_no FROM `tabSerial and Batch Entry` WHERE parent = '{item.serial_and_batch_bundle}'", as_dict=True)[0].batch_no
        else:
            batch_no = item.batch_no
        if batch_no:
            batch_nos.append({"item_code": item.item_code, "batch_no": batch_no, "purchase_rate": item.rate})

    pln = frappe.get_doc(
        {
            "doctype": "Production Plan",
            "posting_date": purchase_receipt.posting_date,
        }
    )

    skipped_items = []
    for purchase_receipt_item in purchase_receipt.items:
        has_batch_no = frappe.db.get_value("Item", purchase_receipt_item.item_code, "has_batch_no")
        if has_batch_no:
            try:
                item_details = get_item_details(purchase_receipt_item.item_code)
            except Exception as e:
                purchase_receipt.add_comment(
                    "Comment",
                    f"Failed to create Production Plan for item {purchase_receipt_item.item_code}: {str(e)}"
                )
                skipped_items.append(purchase_receipt_item.item_code)
                continue
            purchase_receipt_item.bom_no = item_details.bom_no
            pln.append(
                "po_items",
                {
                    "item_code": purchase_receipt_item.item_code,
                    "bom_no": purchase_receipt_item.bom_no,
                    "planned_qty": purchase_receipt_item.qty,
                    "planned_start_date": purchase_receipt.posting_date,
                    "stock_uom": purchase_receipt_item.uom,
                    "warehouse": purchase_receipt_item.warehouse,
                },
            )

    if not pln.po_items:
        if skipped_items:
            purchase_receipt.add_comment(
                "Comment",
                f"Failed to create Production Plan: all {len(skipped_items)} item(s) lack BOMs. Skipped items: {', '.join(skipped_items)}"
            )
        return

    pln.insert()
    pln.submit()

    # Link the Production Plan back to the Purchase Receipt for traceability
    purchase_receipt.db_set("custom_production_plan", pln.name)

    # If some items were skipped, add a summary comment
    if skipped_items:
        purchase_receipt.add_comment(
            "Comment",
            f"Production Plan {pln.name} created with {len(pln.po_items)} item(s). Skipped {len(skipped_items)} item(s) without BOM: {', '.join(skipped_items)}"
        )

    pln.make_work_order()
    work_orders = frappe.get_all(
        "Work Order", fields=["name"], filters={"production_plan": pln.name}, as_list=1
    )

    # Find WIP warehouse for the company (required by ERPNext v16 before submit)
    company_abbr = frappe.db.get_value("Company", pln.company, "abbr")
    wip_warehouse = frappe.db.get_value(
        "Warehouse",
        {"warehouse_name": "Work In Progress", "company": pln.company},
        "name",
    )

    for work_order in work_orders:
        wo = frappe.get_doc("Work Order", work_order[0])
        if not wo.wip_warehouse and wip_warehouse:
            wo.wip_warehouse = wip_warehouse
        wo.submit()

        batch_no = None
        for batch in batch_nos:
            if batch["item_code"] == wo.production_item:
                batch_no = batch["batch_no"]
                purchase_rate = batch["purchase_rate"]
                break

        se1 = frappe.get_doc(make_stock_entry(wo.name, "Material Transfer for Manufacture", wo.qty))
        se1.set_posting_time = 1
        se1.posting_date = purchase_receipt.posting_date
        se1.posting_time = purchase_receipt.posting_time
        se1.insert()
        se1.submit()

        se2 = frappe.get_doc(make_stock_entry(wo.name, "Manufacture", wo.qty))
        se2 = fix_stock_entry(se2, batch_no, wo.production_item, purchase_rate)
        se2.set_posting_time = 1
        se2.posting_date = purchase_receipt.posting_date
        se2.posting_time = purchase_receipt.posting_time

        fix_missing_accounts(se2)

        se2.insert()
        se2.submit()

    pass


def fix_missing_accounts(se):
    """Ensure all items and additional costs have expense_account and cost_center set."""
    company_default_expense = frappe.get_cached_value(
        "Company", se.company, "stock_adjustment_account"
    )
    company_default_cost_center = frappe.get_cached_value(
        "Company", se.company, "cost_center"
    )

    for item in se.items:
        if not item.expense_account:
            item.expense_account = frappe.db.get_value(
                "Item Default", {"parent": item.item_code, "company": se.company}, "expense_account"
            ) or company_default_expense
        if not item.cost_center:
            item.cost_center = frappe.db.get_value(
                "Item Default", {"parent": item.item_code, "company": se.company}, "buying_cost_center"
            ) or company_default_cost_center

    for cost in se.get("additional_costs", []):
        if not cost.expense_account:
            cost.expense_account = company_default_expense


def fix_stock_entry(se, batch_no, item_code, purchase_rate):
    """Inject the farmer's purchase_rate into a Manufacture Stock Entry.

    Business context
    ----------------
    Raw potato is deliberately NOT in the Bill of Materials because the
    farmer's purchase price is negotiated AFTER the sale to the customer
    (BOM costs lock at Work Order creation time).  This means
    ``make_stock_entry("Manufacture")`` produces items for BOM components
    (bags, electricity, salary, etc.) but has NO consumption row for the
    potato itself.

    What this function does
    -----------------------
    1. Assigns ``batch_no`` and ``use_serial_batch_fields`` to every item
       matching ``item_code`` in the Stock Entry.
    2. Builds a source (consumed) item row with ``is_finished_item=0`` and
       ``basic_rate=purchase_rate`` — this represents the raw potato being
       consumed during manufacturing.
    3. If no source item for the production item already exists, injects
       one into the consumed-items group.
    4. Re-orders items so consumed rows (``is_finished_item=0``) precede
       finished rows (``is_finished_item=1``) — the standard Manufacture
       Stock Entry structure.

    Downstream consumer
    -------------------
    The Serial and Batch Entry records created from this Stock Entry
    derive their ``incoming_rate`` from consumed items' ``basic_rate``.
    The **Purchase Receipt Gross Profit** report reads ``sbe.incoming_rate``
    to compute the ``supplier_rate`` formula:

        supplier_rate = selling_rate + purchase_rate
                       - incoming_rate
                       - wished_profit_rate

    If ``incoming_rate`` is understated (missing potato cost), the
    ``supplier_rate`` is overstated and the farmer negotiation tool
    suggests overpaying the farmer.

    Returns
    -------
    frappe.model.document.Document
        The same Stock Entry document with modified items, returned for
        chaining convenience.
    """
    expense_account = frappe.db.get_value(
        "Item Default", {"parent": item_code, "company": se.company}, "expense_account"
    )
    if not expense_account:
        expense_account = frappe.get_cached_value(
            "Company", se.company, "stock_adjustment_account"
        )

    cost_center = frappe.db.get_value(
        "Item Default", {"parent": item_code, "company": se.company}, "buying_cost_center"
    )
    if not cost_center:
        cost_center = frappe.get_cached_value("Company", se.company, "cost_center")

    # ----------------------------------------------------------------
    # Phase 1: assign batch_no and detect whether a source item exists
    # ----------------------------------------------------------------
    source_item_exists = False
    source_item_template = None

    for item in se.items:
        if item.item_code == item_code:
            item.batch_no = batch_no
            item.use_serial_batch_fields = 1

            # Capture the first matching item as a template for the
            # source (consumed) row we may need to inject
            if source_item_template is None:
                source_item_template = {
                    "item_code": item.item_code,
                    "s_warehouse": item.t_warehouse,
                    "bom_no": item.bom_no,
                    "qty": item.qty,
                    "batch_no": item.batch_no,
                    "use_serial_batch_fields": 1,
                    "is_finished_item": 0,
                    "basic_rate": purchase_rate,
                    "expense_account": expense_account,
                    "cost_center": cost_center,
                }

            if item.is_finished_item == 0:
                source_item_exists = True

    # Edge case: no item matched the production item code — nothing to do
    if source_item_template is None:
        frappe.log_error(
            message=(
                f"fix_stock_entry: no item matching '{item_code}' found "
                f"in Stock Entry {se.name}"
            ),
            title="fix_stock_entry — No matching item",
        )
        return se

    # ----------------------------------------------------------------
    # Phase 2: inject source item if needed, then order by item type
    # ----------------------------------------------------------------
    if not source_item_exists:
        se.append("items", source_item_template)

    # Stable sort: consumed (0) before finished (1).
    # This replaces the previous fragile `append + reverse` pattern and
    # works regardless of the order `make_stock_entry()` returns items.
    se.items.sort(key=lambda i: i.is_finished_item)

    # ----------------------------------------------------------------
    # Phase 3: validate post-modification structural integrity
    # ----------------------------------------------------------------
    if not any(i.is_finished_item == 1 for i in se.items):
        frappe.throw(
            _(
                "fix_stock_entry: no finished item (is_finished_item=1) "
                "after modification. The Manufacture Stock Entry "
                "structure is invalid."
            )
        )

    production_source_items = [
        i
        for i in se.items
        if i.item_code == item_code and i.is_finished_item == 0
    ]
    if not production_source_items:
        frappe.throw(
            _(
                "fix_stock_entry: no source item for '{0}' with "
                "is_finished_item=0 after modification. The "
                "purchase_rate injection failed."
            ).format(item_code)
        )

    return se


def set_batch_no(purchase_receipt, method=None):

    # Get items with empty batch_no
    items_without_batch = []
    for item in purchase_receipt.items:
        if not item.batch_no:
            items_without_batch.append(item)

    # Filter for items that should have batch numbers (has_batch_no=1) and belong to "Potatoes" item group
    batch_required_items = []
    for item in items_without_batch:
        has_batch_no = frappe.db.get_value("Item", item.item_code, "has_batch_no")
        item_group = frappe.db.get_value("Item", item.item_code, "item_group")
        if has_batch_no == 1 and item_group == "Potatoes":
            batch_required_items.append(item)

    # Loop through items that require batch numbers
    for item in batch_required_items:

        # Search for existing batches that match our criteria
        batches = frappe.get_all(
            "Batch",
            filters={
                "item": item.item_code,
                "custom_supplier_optimus": purchase_receipt.supplier,
                "manufacturing_date": purchase_receipt.posting_date,
                "custom_prefix": item.custom_batch_prefix,
            },
            fields=["name", "batch_id"]
        )

        date_format = frappe.utils.get_user_date_format()
        manufactured_date = frappe.utils.formatdate(purchase_receipt.posting_date, date_format)

        if batches:
            # Use the first matching batch
            batch_no = batches[0].name
            # Assign the batch number to the item
            item.batch_no = batch_no
            # Link the Weight Slip to the Batch for traceability
            if purchase_receipt.get("custom_weight_slip"):
                frappe.db.set_value("Batch", batch_no, "custom_weight_slip", purchase_receipt.custom_weight_slip)
        else:
            # Create a new batch if none exists
            new_batch = frappe.new_doc("Batch")
            if item.custom_batch_prefix:
                new_batch.batch_id = item.item_code + " * " + item.custom_batch_prefix + " * " + manufactured_date + " * " + purchase_receipt.supplier
            else:
                new_batch.batch_id = item.item_code + " * " + manufactured_date + " * " + purchase_receipt.supplier
            new_batch.item = item.item_code
            new_batch.manufacturing_date = purchase_receipt.posting_date
            new_batch.custom_supplier_optimus = purchase_receipt.supplier
            new_batch.custom_prefix = item.custom_batch_prefix
            new_batch.custom_weight_slip = purchase_receipt.get("custom_weight_slip")
            new_batch.insert()

            # Assign the new batch to the item
            item.batch_no = new_batch.name
