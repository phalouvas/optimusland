# Unbilled Delivery Notes Report

## Overview
This enhanced report shows all delivery note items that have unbilled amounts, with advanced data integrity validation and comprehensive billing tracking. The report matches delivery note items directly with sales invoice items for maximum accuracy.

## 🆕 Enhanced Features (Latest Version)

### 1. **Complete Coverage**
- **Includes ALL delivery note items**, even those with zero linked sales invoices
- **No items missed** due to lack of sales invoice linkages
- **Handles edge cases** where delivery notes have no billing activity

### 2. **Advanced Aggregation**
- **Proper partial billing support** across multiple sales invoices
- **Subquery-based calculation** for accurate aggregation
- **Credit note handling** (returns are subtracted correctly)

### 3. **Customer Validation**
- **Prevents data corruption** from incorrectly linked invoices
- **Customer matching** ensures delivery notes only count invoices for the same customer
- **Data integrity protection** against manual linking errors

### 4. **Data Integrity Validation**
- **System vs. Calculated comparison** to identify discrepancies
- **Variance detection** highlights where ERPNext's tracking is wrong
- **Audit trail support** for financial reconciliation

## Features
- Shows delivery note items with unbilled amounts
- Calculates billed vs unbilled amounts using actual invoice data
- Displays billing percentage for each item
- Optional filters for company, date range, and customer
- Summary row with totals
- Color-coded display for easy identification
- **Enhanced**: Includes closed delivery notes to catch billing errors
- **Enhanced**: Data integrity validation with variance analysis

## Filters
- **Company**: Filter by specific company (optional)
- **From Date**: Start date for delivery notes (default: 1 month ago)
- **To Date**: End date for delivery notes (default: today)
- **Customer**: Filter by specific customer (optional)

## Columns
- **Delivery Note**: Link to the delivery note document
- **Date**: Posting date of the delivery note
- **Customer**: Customer name
- **Item Code**: Item code from delivery note
- **Item Name**: Item description
- **Qty**: Quantity delivered
- **Rate**: Rate per unit
- **Amount**: Total amount for the item
- **Billed Amount**: Amount that has been billed in sales invoices (calculated from actual data)
- **Unbilled Amount**: Remaining amount to be billed (highlighted in red)
- **% Billed**: Percentage of the amount that has been billed
- **Status**: Current status of the delivery note (including closed)
- **🆕 System Billed Amt**: ERPNext's stored billed_amt value for comparison
- **🆕 Variance**: Difference between calculated and system billed amounts
- **Company**: Company name

## Color Coding
- **Red**: Unbilled amounts, 0% billed items, and closed delivery notes with unbilled amounts
- **Orange**: Partially billed items (1-50% billed) and "To Bill" status
- **Dark Orange**: Moderately billed items (51-99% billed)
- **Green**: Fully billed items (100% billed) and "Completed" status
- **🆕 Blue**: Positive variance (calculated > system billed amount)
- **🆕 Purple**: Negative variance (calculated < system billed amount)
- **Bold**: Summary row totals and significant discrepancies

## Usage
1. Navigate to Reports > Optimusland > Unbilled Delivery Notes
2. Apply desired filters
3. Click "Refresh" to generate the report
4. Review unbilled items and take action as needed
5. **🆕 Check variance column** for data integrity issues

## Technical Details
- Report Type: Script Report
- Reference Doctype: Delivery Note
- Module: Optimusland
- **Enhanced Query**: Uses subquery with customer validation for accurate billing calculation
- **Includes**: ALL delivery note statuses (including closed) for complete visibility
- **Excludes**: Only draft and cancelled sales invoices
- **Validation**: Customer matching prevents incorrect invoice linkages

## Data Integrity Features
- **Variance Detection**: Identifies where system tracking differs from actual calculations
- **Zero-Invoice Coverage**: Catches delivery notes with no linked sales invoices
- **Customer Validation**: Prevents billing calculations from wrong customer invoices
- **Audit Support**: Provides evidence for financial reconciliation and compliance

## Permissions
Available to users with the following roles:
- Stock User
- Stock Manager
- Sales User
- Accounts User
- Delivery User
- Delivery Manager

## 🚨 Important Notes
- **Variance Column**: Non-zero values indicate data integrity issues requiring investigation
- **Closed Status**: Closed delivery notes with unbilled amounts may indicate process errors
- **Customer Validation**: The report only counts sales invoices for the matching customer
- **Real-time Accuracy**: All calculations based on actual sales invoice data, not stored fields
