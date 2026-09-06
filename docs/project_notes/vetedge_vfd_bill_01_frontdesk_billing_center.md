# VFD-BILL-01 — Front Desk, Direct Patients & Billing Center

## Business goal

Separate patient access, appointments/front-desk work and billing/accounting navigation without changing ERPNext accounting truth or widening operational permissions.

## Primary navigation contract

The approved primary order is:

1. Veterinary Home — direct, non-collapsible
2. Patients — direct, non-collapsible
3. Appointments
4. Clinical Operations
5. Hospital & Services
6. Inventory / Pharmacy
7. Billing Center
8. Dashboard
9. Reports

All other existing navigation groups remain after Reports in their prior relative order.

## Appointments / Front Desk

Appointments contains Appointment Queue, Appointments, Pet Boarding Booking, Guest Booking Requests and Missed Appointments. Patients is not nested under Appointments. Customer, Sales Invoice and Payment Entry are not exposed under Appointments. Pet Grooming Appointment remains hidden from product navigation only; its DocType, workflow and history remain intact.

## Billing Center

Billing Center navigation contains Customers, Sales Invoice, Payment Entry, Billing Session and Billing Center.

- `/desk/vetedge-billing-center` — Billing Center
- `/desk/vetedge-billing-sessions` — Billing Sessions EdgeSuite worklist
- `/desk/vetedge-billing-sessions?name=VBS-...` — Billing Session EdgeSuite detail

The underlying `Veterinary Billing Session` DocType remains authoritative. Normal VetEdge drill-through no longer opens its native ERPNext form. Linked Sales Invoices remain authoritative ERPNext accounting documents and may open in native accounting UI.

Billing Center remains read/management only over existing Billing Session and ERPNext accounting truth. It does not submit, cancel, mutate or reconstruct submitted Sales Invoices, Payment Entries or GL entries.

## Billing Session EdgeSuite detail

The EdgeSuite detail mode shows Billing Session identity, Customer, friendly pet name plus patient ID, Branch and Company, Status, Payment Status and Payment Gate, Created From and Source Context, Charges/Invoiced/Paid/Outstanding totals, charge rows and invoice/status references, Open Latest Invoice when permitted, and Back to Billing Sessions.

`vetedge.services.billing_session_page.get_billing_session_detail` is read-only and branch-safe. It first resolves the caller's permitted Billing Session through permission-aware `frappe.get_list`, then loads child charge rows only for that authorized parent. Zero-Branch operational users fail closed.

## Billing Center presentation hardening

This slice also includes same-tab Billing Center/Billing Sessions routing, Product Menu item click handling, approved sidebar order and re-render drift correction, plain currency KPI formatting, removal of duplicate shortcut buttons, fuzzy Date Range presets, patient search by friendly name or ID, and friendly patient display with ID for disambiguation.

## Fuzzy date contract

Billing Center and Billing Sessions support Today, Yesterday, This Week, Last Week, This Month, Last Month, This Quarter, Last Quarter, This Year, Last Year, Full History and Custom Range. Selecting a preset fills From/To. Manual date edits switch to Custom. Reset returns to Full History.

## Friendly patient contract

`Veterinary Patient.name` remains the stored/filter value. `Veterinary Patient.patient_name` is the friendly display/search value. Patient search is bounded and intersected with Billing Sessions visible in the caller's branch/company/customer/activity scope. Results display for example `Bruno (VP-2026-00027)`.

## Billing Session activity lifecycle hardening

Billing Center defaults to `Actionable Billing` rather than treating every persisted Billing Session as an operationally open billing item.

Session Activity options are `Actionable Billing`, `All Sessions`, and `No Billing Activity`. Empty sessions remain inspectable and are not deleted, cancelled or auto-closed. `billing_core.get_or_create_billing_session()` remains unchanged pending installed-site Billing Core regression evidence.

## Branch and permission safety

- global/elevated users may use unrestricted scope unless an explicit Branch is selected;
- branch-restricted users can only query assigned Branches;
- zero assigned Branches fails closed;
- Branch search cannot reveal other branches;
- Patient options cascade through Company → Branch → Customer and Session Activity;
- Billing Session detail cannot load a session outside permitted Branch scope;
- no raw SQL or `ignore_permissions=True` is used in Billing Center/detail services.

## Automated validation

Validated code/test candidate: `a1f7e352e8d47df3bd99cdd318ccbb3272362594`

Workflow: `VFD-BILL-01 Validation`
Run: `34065453165`

Result:

- Python compile: PASS
- Ruff focused validation: PASS
- existing VFD-BILL-01 source contracts: PASS
- QA defect regression contracts: PASS
- EdgeSuite Billing Session detail routing/read-model contracts: PASS

The branch commits after `a1f7e352e8d47df3bd99cdd318ccbb3272362594` are documentation-only. Current QA checkout candidate: `26f28fec2b538332f9c80c172be4abfe41f08370`.

## QA Center cases

- `VFDNAV-001` through `VFDNAV-006` — primary order, direct Patients, Product Menu parity/clicks, access preservation, active state and migrate idempotency.
- `VFDBILL-UI-001` — Billing Center opens same-tab.
- `VFDBILL-UI-002` — Billing Sessions opens EdgeSuite worklist.
- `VFDBILL-UI-003` — currency KPIs contain no literal HTML.
- `VFDBILL-UI-004` — redundant shortcut row absent.
- `VFDBILL-DATE-001` — fuzzy date presets and Custom behavior.
- `VFDBILL-PAT-001` — search by pet friendly name and patient ID returns only visible/relevant patients.
- `VFDBILL-PAT-002` — list/detail show friendly pet name plus ID.
- `VFDBILL-ACT-001` through `VFDBILL-ACT-004` — Actionable/All/No Activity behavior and scope safety.
- `VFDBILL-DETAIL-001` — clicking a Billing Session opens `/desk/vetedge-billing-sessions?name=VBS-...`, never the native Veterinary Billing Session form.
- `VFDBILL-DETAIL-002` — detail uses the EdgeSuite Veterinary shell and shows authoritative totals/context/charges.
- `VFDBILL-DETAIL-003` — restricted Branch users cannot open a Billing Session outside permitted Branches.
- `VFDBILL-DETAIL-004` — linked Sales Invoice may open native ERPNext accounting UI; Billing Session itself remains EdgeSuite.

## Local acceptance

```bash
bench --site vetedge.local migrate
bench build --app vetedge
bench --site vetedge.local run-tests \
  --app vetedge \
  --module vetedge.tests.test_vfd_bill_01_contract
python -m pytest -q tests/test_vfd_bill_01_session_detail.py
bench --site vetedge.local clear-cache
```

Hard refresh or use a fresh Incognito window after the build.

For detail QA, open Billing Sessions, click a VBS row, confirm the URL becomes `/desk/vetedge-billing-sessions?name=...`, confirm the EdgeSuite Veterinary shell remains visible, validate totals and charge rows, use Back to Billing Sessions, then test Sales Invoice drill-through separately.

## Out of scope

- replacing ERPNext Sales Invoice or Payment Entry accounting UI;
- submitted accounting mutation;
- deleting/auto-closing existing Billing Sessions;
- changing Billing Core creation/continuity semantics before installed-site validation;
- broad navigation/report/workflow redesign.
