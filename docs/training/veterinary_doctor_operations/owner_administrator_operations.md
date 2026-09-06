# Owner and Administrator Operations

## Module Purpose

Configure and govern the complete VetEdge and ERPNext operating model without weakening clinical, stock, branch, access or accounting controls. “Owner” is a business responsibility, not a single software role; exercises require the approved VetEdge Administrator or System Manager access plus the necessary ERPNext manager roles.

## 1. Foundation Setup

1. Confirm Company, currency, country, Chart of Accounts and fiscal year.
2. Create or review each Veterinary Branch as an operational location.
3. Map every Branch to the approved Cost Center used for billing.
4. Create Warehouses for physical custody, including main, pharmacy/dispensary, laboratory, boarding and quarantine locations where required.
5. Confirm default selling Price List, branch Item Prices, Mode of Payment and account defaults.
6. Create named users, apply the narrowest Veterinary Role Bundle and assign branches.
7. Test each role with a separate user before production use.

## 2. Veterinary Settings Governance

Open `/app/veterinary-settings-center`. Review and approve every applicable area:

| Area | Owner decision |
|---|---|
| Setup | Enable VetEdge, clinic defaults, Cost Center enforcement, default Price List |
| Registration Billing | Registration Item, fee, invoice policy and branch rules |
| Clinical | Consultation, structured vitals, lab result entry/review, vaccination and consultation billing |
| Appointments | Appointment enablement, reminder hours and reminder lead time |
| Billing & Payment | Billing Sessions, payment gate mode, invoice-before-service, partial-payment policy |
| Pharmacy / Dispensary | Treatment billing, dispensary flow, strict expiry, FEFO and override controls |
| Stock Expiry Alerts | Monitor enablement, reminder-day windows and approved channels |
| Hospitalisation | Enablement, consultation requirement, direct admission, payment gate and billing defaults |
| Grooming & Boarding | Service enablement, booking, capacity, care and billing rules |
| Owner Portal | Guest booking, cancellation/reschedule and summary visibility |
| Portal Branding | Brand name, logo, colours, headings, cards and controlled CSS |
| Communication | Backend, channels, notification events and reminder windows |
| Advanced | Advanced Reports, branch restriction and non-production demo controls |

Record old value, new value, reason, approver, effective date and test evidence for every production change. Never expose API keys in training screenshots.

## 3. Masters, Service Items and Pricing

1. Search before creating Species, Breed, Symptom, Diagnosis, Consultation Type, Service Type, Treatment Type, Treatment Item, Lab Test or Vaccine.
2. Link each billable Veterinary service to an active ERPNext Item.
3. Keep `Maintain Stock` off for pure services and on for physical goods.
4. Set approved selling rates through Item Price and branch Price Lists.
5. Test pricing from the source workflow and investigate zero-rate items before production use.

## 4. ERPNext Stock and Procurement Essentials

1. Create stock Items with Stock UOM, Item Group, valuation and warehouse defaults.
2. Enable `Has Batch No` and `Has Expiry Date` for medicines, vaccines and other controlled stock.
3. Run Purchase Order → Purchase Receipt → Purchase Invoice → Payment Entry.
4. At receipt, confirm accepted warehouse, actual quantity, Batch and expiry before submission.
5. Use Stock Entry with Purpose `Material Transfer` for warehouse transfers.
6. Use Stock Reconciliation only after a controlled physical count and variance investigation.
7. Monitor Stock Balance, Stock Ledger, Batch-Wise Balance, Stock Ageing and Stock Expiry Monitor.
8. Quarantine expired or doubtful stock; complete the approved return, transfer, disposal or write-off process.

## 5. Sales, Billing Center and Payment Control

1. Use Sales Order for a controlled customer commitment when required.
2. Use VetEdge Billing / Payment or the authorised ERPNext flow to create a Sales Invoice.
3. Submit only after customer, company, branch/Cost Center, Items, rates, taxes and totals are correct.
4. Create and submit Payment Entry, allocate it to the correct invoice and verify the outstanding amount.
5. Open Billing Center at `/desk/vetedge-billing-center` for consolidated visibility.
6. Review open Billing Sessions, outstanding sessions, outstanding amount and amount collected.
7. Filter Company → Branch → Customer → Patient; changing Company clears downstream scope and changing Customer clears Patient.
8. Drill through to the authoritative Billing Session or latest invoice. Billing Center does not submit invoices or allocate payments.

## 6. Veterinary Home, Dashboards and Reports

1. Start at `/desk/vetedge` and reconcile role-aware attention cards to source rows.
2. Use Executive, Financial, Branch Performance, Clinical, Lab, Vaccination, Hospitalisation, Inventory/Dispensary, Boarding, Grooming and Practitioner Performance dashboards according to permission.
3. Use the same branch, date range, status and posting basis when reconciling dashboard totals with reports.
4. Review essential VetEdge reports for consultations, patients, owners, lab, vaccination, planned treatment, hospitalisation, revenue, unpaid invoices and stock expiry.
5. Review ERPNext Stock Balance, Stock Ledger, Purchase Register, Sales Register, Accounts Receivable, Accounts Payable, General Ledger, Trial Balance, Profit and Loss, Balance Sheet and Cash Flow.

## 7. VCN / NADIS Regulatory Setup and Reporting

1. Confirm the reporting Company has Country and every reporting Branch has NADIS State/Admin Level 1 and NADIS LGA/Admin Level 2.
2. Map Veterinary Species to NADIS Species.
3. Map Veterinary Vaccine to the approved NADIS disease, vaccine type and source; complete applicable PANVAC evidence.
4. Map Veterinary Diagnosis to NADIS Disease and maintain Disease Outbreak Register records for reportable outbreaks.
5. Open `/desk/vetedge-regulatory-reporting`, select Company, Branch, period and report type.
6. Validate and resolve every blocked mapping or source-data issue.
7. Generate the report and retain the frozen workbook attachment on the Regulatory Report Run.
8. Mark Sent only after confirmed external submission evidence exists.
9. Record Accepted or Rejected regulator outcome. Accepted is final; correct a rejected submission through a new run and mark the old run Superseded where appropriate.

## 8. Daily, Weekly and Month-End Control

- Daily: review clinical, lab, vaccination, inpatient, revenue, collection, stock and service exceptions.
- Weekly: review expiry windows, regulatory readiness, purchase commitments, receivables, access changes and unresolved assignments.
- Month-end: confirm cut-off, stock counts, reconciliations, registers, ledger, bank reconciliation, Trial Balance, Profit and Loss, Balance Sheet and Cash Flow.

## Practice Exercise

Using synthetic data, configure one safe stock Item with Batch and expiry, trace a purchase-to-pay cycle, inspect Billing Center, reconcile one Veterinary Home card, validate a regulatory report run and document the evidence required before production approval.

## Related Screenshots

![Veterinary Settings Center](training_assets/screenshots/veterinary-settings-center.png)
![Billing Center consolidated visibility](training_assets/screenshots/billing-center.png)
![VCN NADIS Regulatory Reporting](training_assets/screenshots/regulatory-reporting.png)
