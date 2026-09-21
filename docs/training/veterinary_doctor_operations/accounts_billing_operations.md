# Accounts, Cashier and Billing Operations

## Module Purpose

Complete invoice, payment and financial correction work through ERPNext while using VetEdge Billing Sessions and Billing Center as operational context.

## Invoice and Collection Procedure

1. Open Billing / Payment from the patient or source service, or open Billing Center at `/desk/vetedge-billing-center`.
2. Confirm Company, Branch, Cost Center, Customer/Pet Owner, Patient and source document.
3. Review the Billing Session and invoice history before creating another invoice.
4. Confirm Items, quantities, rates, taxes, discounts, due date and totals while the Sales Invoice is Draft.
5. Submit the Sales Invoice only when the source service and accounting dimensions are correct.
6. Create a Payment Entry for the actual amount and Mode of Payment received.
7. Allocate the Payment Entry to the correct submitted invoice and submit it.
8. Reopen Billing Center or the source workflow and verify outstanding and payment-gate results.

## Billing Center Boundary

Billing Center consolidates read and management visibility around Veterinary Billing Session. It does not submit invoices, allocate payments, post General Ledger entries or replace ERPNext financial reports.

## Submitted-Document Corrections

1. Stop when a submitted Sales Invoice or Payment Entry is wrong.
2. Preserve the document IDs, source record, message and financial evidence.
3. Select the accountant-approved cancellation, return, credit note, amendment, refund or reconciliation process.
4. Do not edit submitted amounts, mark an invoice paid manually or create an unlinked payment.
5. Verify the General Ledger, invoice outstanding amount and VetEdge gate after correction.

## Essential Reports

- Sales Register and Sales Order Analysis
- Accounts Receivable and Payment Ledger
- General Ledger and Trial Balance
- Bank Reconciliation
- Profit and Loss, Balance Sheet and Cash Flow
- VetEdge Revenue Summary, Unpaid Invoice and Branch Performance reports

## Practice Exercise

Using synthetic records, trace a Billing Session to its Sales Invoice and submitted Payment Entry, verify allocation, and document the correct response to one submitted-invoice error.

## Related Screenshots

![Billing Session and invoice history](training_assets/screenshots/billing-session-invoice-history.png)
