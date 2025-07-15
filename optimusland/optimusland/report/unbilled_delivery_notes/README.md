# Unbilled Delivery Notes Report

## Overview
This report shows all delivery note items that have unbilled amounts, helping identify which items from delivery notes haven't been fully invoiced yet.

## Features
- Shows delivery note items with unbilled amounts
- Calculates billed vs unbilled amounts
- Displays billing percentage for each item
- Optional filters for company, date range, and customer
- Summary row with totals
- Color-coded display for easy identification

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
- **Billed Amount**: Amount that has been billed in sales invoices
- **Unbilled Amount**: Remaining amount to be billed (highlighted in red)
- **% Billed**: Percentage of the amount that has been billed
- **Status**: Current status of the delivery note
- **Company**: Company name

## Color Coding
- **Red**: Unbilled amounts and 0% billed items
- **Orange**: Partially billed items (1-50% billed)
- **Dark Orange**: Moderately billed items (51-99% billed)
- **Green**: Fully billed items (100% billed)
- **Bold**: Summary row totals

## Usage
1. Navigate to Reports > Optimusland > Unbilled Delivery Notes
2. Apply desired filters
3. Click "Refresh" to generate the report
4. Review unbilled items and take action as needed

## Technical Details
- Report Type: Script Report
- Reference Doctype: Delivery Note
- Module: Optimusland
- Query: Joins Delivery Note and Delivery Note Item tables
- Excludes: Closed delivery notes and fully billed items

## Permissions
Available to users with the following roles:
- Stock User
- Stock Manager
- Sales User
- Accounts User
- Delivery User
- Delivery Manager
