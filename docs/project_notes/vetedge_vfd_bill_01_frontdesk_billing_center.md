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

Appointments contains:

1. Appointment Queue
2. Appointments
3. Pet Boarding Booking
4. Guest Booking Requests
5. Missed Appointments

Patients is not nested under Appointments. Customer, Sales Invoice and Payment Entry are not exposed under Appointments. Pet Grooming Appointment remains hidden from product navigation only; its DocType, workflow and history remain intact.

## Dedicated Front Desk Pages

The dedicated routes are:

- `/desk/vetedge-front-desk-queue`
- `/desk/vetedge-front-desk-guest-bookings`
- `/desk/vetedge-front-desk-missed-appointments`

They share the same Front Desk EdgeSuite component in fixed-workflow mode. Legacy Front Desk Action Center and appointment queue URLs remain compatibility redirects.

## Billing Center

Billing Center navigation contains:

1. Customers
2. Sales Invoice
3. Payment Entry
4. Billing Session
5. Billing Center

`Billing Session` targets the EdgeSuite Page `/desk/vetedge-billing-sessions`. Billing Center targets `/desk/vetedge-billing-center`. Both remain in the current Desk window.

Billing Center is read/management only over existing `Veterinary Billing Session` and ERPNext accounting truth. It does not submit, cancel, mutate or reconstruct submitted Sales Invoices, Payment Entries or GL entries.

## Billing Center presentation hardening

The local browser QA defects closed in this slice include:

- Billing Center and Billing Sessions same-tab routing.
- Product Menu item click handling.
- requested sidebar ordering and re-render drift detection.
- plain currency KPI formatting instead of literal HTML produced by `frappe.format()`.
- removal of redundant Customers / Sales Invoices / Payment Entries / Billing Sessions shortcut buttons above KPI cards.
- real EdgeSuite Billing Sessions worklist Page.
- fuzzy Date Range presets using the shared `frappe.EdgeSuite.DateRanges` helper.
- patient search by friendly pet name or Veterinary Patient ID.
- patient list display as friendly name with patient ID for disambiguation.

## Fuzzy date contract

Billing Center and Billing Sessions support:

- Today
- Yesterday
- This Week
- Last Week
- This Month
- Last Month
- This Quarter
- Last Quarter
- This Year
- Last Year
- Full History
- Custom Range

Selecting a preset fills From/To. Manual date edits switch to Custom. Reset returns to Full History. Existing backend date validation remains authoritative.

## Friendly patient contract

`Veterinary Patient.name` remains the stored/filter value. `Veterinary Patient.patient_name` is the friendly display/search value.

Patient search is bounded and then intersected with Billing Sessions visible in the caller's branch/company/customer/activity scope. Results display for example `Bruno (VP-2026-00027)`.

The Billing Center list uses the same friendly display while retaining the authoritative patient ID for disambiguation.

## Billing Session activity lifecycle hardening

### Why zero-value sessions exist

Current billing-core continuity can create an Active Billing Session before a source ultimately produces a billable payload. A consultation may therefore leave an empty session when billing is disabled/not applicable, no payload is produced, or previously pending charges are later retired. The parent Billing Session is intentionally not deleted by the totals refresh.

### Operational correction in this PR

Billing Center now defaults to `Actionable Billing` rather than treating every persisted Billing Session as an operationally open billing item.

Session Activity options are:

- `Actionable Billing` — any financial movement or draft/latest invoice link.
- `All Sessions` — full visible Billing Session history.
- `No Billing Activity` — zero charges, zero invoiced, zero paid, zero outstanding and no draft/latest invoice link.

Empty sessions remain inspectable and are not deleted, cancelled or auto-closed. This protects historical/source continuity while preventing placeholders from inflating the default work queue and Open Sessions KPI.

When Actionable Billing is selected, Billing Center reports how many no-activity sessions are hidden and directs the user to All Sessions or No Billing Activity for review.

Patient/customer link searches follow the selected Session Activity scope so dependent filters remain relevant.

### Deferred core-lifecycle change

This slice deliberately does not change `billing_core.get_or_create_billing_session()` or delete existing sessions. Preventing creation of a new session before charge payload materiality is proven changes billing continuity semantics and must be validated with installed-site Billing Core tests first. The current operational hardening is reversible/read-only and does not alter accounting documents.

## Branch and permission safety

Billing Center remains permission-aware and branch-safe:

- global/elevated users may use unrestricted scope unless an explicit Branch is selected;
- branch-restricted users can only query assigned Branches;
- zero assigned Branches fails closed;
- Branch search cannot reveal other branches;
- Patient options cascade through Company → Branch → Customer and Session Activity;
- APIs use permission-aware Billing Session queries and bounded result sizes;
- no raw SQL or `ignore_permissions=True` is used in Billing Center.

## Migration and backward compatibility

- Existing DocTypes and submitted accounting documents are unchanged.
- Existing Front Desk legacy routes redirect to the new dedicated Pages.
- Existing patient IDs and Billing Session links remain authoritative.
- Sidebar synchronization remains idempotent.
- Custom Patients sections with additional administrator-added links are preserved.

## Automated validation

Latest source/test candidate: `f7cf50d2538c9d645106a2d27080d25eb3a00715`

Workflow: `VFD-BILL-01 Validation`
Run: `34064531074`

Result:

- Python compile: PASS
- Ruff focused validation: PASS
- original VFD-BILL-01 source contracts: PASS
- QA defect regression contracts: PASS
- fuzzy date contract: PASS
- friendly patient search/list contract: PASS
- actionable/empty Billing Session activity contract: PASS

## Local acceptance

On `vetedge.local` run:

```bash
bench --site vetedge.local migrate
bench build --app vetedge
bench --site vetedge.local run-tests \
  --app vetedge \
  --module vetedge.tests.test_vfd_bill_01_contract
bench --site vetedge.local clear-cache
```

Then hard-refresh or use a fresh Incognito window.

### QA cases

- `VFDNAV-001` exact primary navigation order.
- `VFDNAV-002` Patients direct/non-collapsible/same-tab.
- `VFDNAV-003` Product Menu items navigate and mirror approved order.
- `VFDNAV-004` role visibility unchanged.
- `VFDNAV-005` active state and Back/Forward behavior.
- `VFDNAV-006` migrate/sidebar synchronization idempotency.
- `VFDBILL-UI-001` Billing Center opens same-tab.
- `VFDBILL-UI-002` Billing Sessions opens EdgeSuite worklist.
- `VFDBILL-UI-003` currency KPIs contain no HTML markup.
- `VFDBILL-UI-004` redundant shortcut row absent.
- `VFDBILL-DATE-001` fuzzy date presets populate valid From/To dates and Custom works.
- `VFDBILL-PAT-001` search by pet friendly name and patient ID returns only visible/relevant patients.
- `VFDBILL-PAT-002` list shows friendly pet name plus ID.
- `VFDBILL-ACT-001` default Actionable Billing excludes zero/no-invoice placeholders from rows, totals and Open Sessions.
- `VFDBILL-ACT-002` All Sessions restores full visible history.
- `VFDBILL-ACT-003` No Billing Activity shows only zero/no-invoice sessions.
- `VFDBILL-ACT-004` no activity filter widens Branch/company/customer permissions.

## Out of scope

- deleting legacy empty Billing Sessions;
- automatically cancelling/closing empty sessions;
- changing submitted Sales Invoices or Payment Entries;
- changing Billing Core continuity semantics before installed-site validation;
- broad navigation rewrites outside the bounded VFD-BILL-01 contract.
