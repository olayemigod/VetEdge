# VFD-BILL-01 — Front Desk Navigation and Billing Center

## Goal

Separate first-class Patient access, front-desk appointment work, and billing/accounting navigation; give Appointment Queue, Guest Booking Requests and Missed Appointments durable full-page URLs; and add a consolidated Veterinary Billing Center without replacing ERPNext accounting truth.

## Branch and composition safety

This slice is stacked on PR #60 Veterinary Home branch `feature/vetedge-smart-home-vhome01` at exact base `e9b1c63bc1ec44483a93f26e10bff485fab43913`.

PR #60 itself is not modified by this work. VFD-BILL-01 remains on `feature/vetedge-frontdesk-billing-center-vfd-bill-01` so VHOME QA evidence is not repointed or overwritten.

Do not merge divergent PR #47/#50/#51 histories to obtain this scope. The branch inherits the reconciled VetEdge composition through PR #60.

## Navigation contract

### Primary direct navigation

The top of the Veterinary sidebar is:

1. Veterinary Home
2. Patients
3. Dashboard
4. Clinical Operations
5. Appointments
6. Billing Center

`Veterinary Home` and `Patients` are direct one-click sidebar items. They are not collapsible categories and must have no expand icon, `aria-expanded` state, hidden child, or second-click behavior.

`Patients` routes to the existing Patient Resource Center at `/desk/vetedge-resource-center?resource=patients`. No new Patient page, DocType or patient data model is introduced.

The persisted Workspace Sidebar keeps Patients as a dedicated one-item section so the Product Menu also presents Patients separately from appointment/front-desk work. The EdgeSuite sidebar shell flattens that one-item section into the direct Patients control immediately after Veterinary Home.

The Patients link preserves the existing `Veterinary Patient` visibility expression. Moving it does not broaden role access.

### Appointments / Front Desk

The underlying Front Desk section contains appointment and booking work only:

1. Appointment Queue
2. Appointments
3. Pet Boarding Booking
4. Guest Booking Requests
5. Missed Appointments

Patients is no longer under Front Desk/Appointments.

`Customer`, `Sales Invoice` and `Payment Entry` are removed from Front Desk.

`Pet Boarding Booking` is moved out of Hospital & Services because booking is a front-desk activity. Boarding Stay and Boarding Care Record remain under Hospital & Services.

`Pet Grooming Appointment` is removed from product navigation only. Its DocType, historical records and workflow integration are not deleted or renamed.

Existing role-visibility expressions are preserved when established links move sections. The new Billing Session and Billing Center links use their own bounded visibility contract rather than inheriting unrelated Front Desk access.

### Dedicated Front Desk pages

The three workflow views reuse one EdgeSuite Front Desk component in fixed-page mode:

- `/desk/vetedge-front-desk-queue`
- `/desk/vetedge-front-desk-guest-bookings`
- `/desk/vetedge-front-desk-missed-appointments`

The dedicated pages do not show the old queue/guest/missed tab switcher. They keep the same permission-aware backend services, branch filtering, optimistic timestamp checks and authoritative appointment/guest/missed actions.

The old `/desk/vetedge-front-desk-action-center?tab=...` route is compatibility-only and redirects to the matching canonical page. `veterinary-appointment-queue` also redirects to the new Appointment Queue page.

Page roles preserve the access contract of the links they replace. Veterinary Nurse and Dispensary User retain Appointment Queue access where previously allowed, and Veterinary Nurse retains Missed Appointments access.

### Billing Center menu group

Billing Center contains:

1. Customers
2. Sales Invoice
3. Payment Entry
4. Billing Session
5. Billing Center

The first four links open their existing authoritative DocType workflows. Billing Center opens `/desk/vetedge-billing-center`.

## Patient navigation implementation safety

The existing VFD-BILL-01 dashboard/sidebar transformation remains unchanged. A bounded post-sync helper, `vetedge.install.patient_navigation.ensure_direct_patient_navigation`, runs immediately after the normal VetEdge sidebar synchronization on install/migrate.

It:

- finds the existing Patients link;
- preserves its `display_depends_on` visibility rule;
- removes the old Patients occurrence from Front Desk;
- creates exactly one dedicated Patients one-item section before Dashboard;
- preserves leading direct Veterinary Home navigation;
- is idempotent;
- leaves a customized Patients section intact if it contains additional administrator-added links.

The EdgeSuite post-QA navigation hardening then flattens that canonical one-item Patients section into a direct sidebar item and positions it immediately after Veterinary Home.

## Billing Center V1

Billing Center V1 is a read/management surface anchored on `Veterinary Billing Session`.

It provides open/outstanding Billing Session counts, outstanding and collected amounts, paginated Billing Session visibility, Company/Branch/Customer/Patient/status/date filters, bounded Link searches, current draft/latest invoice visibility, drill-through to Billing Session and Sales Invoice, and permission-aware shortcuts to Customers, Sales Invoices and Payment Entries.

Billing Center does not guess unrelated ERPNext Sales Invoices into a Veterinary Branch. Veterinary Billing Session remains the safe consolidated anchor.

## Accounting and branch safety

Billing Center does not submit/cancel Sales Invoices, mutate submitted accounting documents, create/allocate Payment Entries, post GL entries, bypass Frappe permissions, use raw SQL, or create another billing ledger.

For non-global operational users, explicit Branch must be assigned; blank Branch means all assigned Branches; zero assigned Branches fails closed; Branch Link search cannot reveal unassigned branches; and Patient Link options are server-filtered by selected Customer as well as Company/Branch context.

## Migration and backward compatibility

No business-data migration or accounting data rewrite is required.

`bench --site vetedge.local migrate` must:

1. import the VFD-BILL-01 Page definitions;
2. rebuild the normal VetEdge Workspace Sidebar;
3. apply the idempotent direct Patients post-sync arrangement;
4. retain existing Patient, appointment, billing and accounting DocTypes/history;
5. retain old Front Desk URLs as compatibility redirects.

## Automated validation

A stacked-PR-specific source gate exists at `.github/workflows/vfd-bill-01-validation.yml`.

Latest green source validation evidence for the direct Patients implementation:

- workflow: `VFD-BILL-01 Validation`
- run: `34057713347`
- validated code head: `51c3b2e62471a4388eafc402a7a317d5946373ac`
- Python compile: PASS
- Ruff focused validation: PASS
- pure source-contract tests: PASS

The source gate explicitly covers direct Patients post-sync wiring, direct/non-collapsible shell behavior, placement after Veterinary Home, preservation of patient visibility, Front Desk removal, and the existing VFD-BILL-01 billing/front-desk contracts.

The source gate does not replace installed-site QA.

## QA Center delta

Keep this in the existing VFD-BILL-01 QA campaign. Do not create a divergent campaign just for the menu rearrangement. Add the following cases to the Navigation section and execute them on the same exact candidate used for the rest of VFD-BILL-01 acceptance:

- **VFDNAV-001 — Direct Patients placement:** Veterinary Home is first, Patients is immediately second, then Dashboard, Clinical Operations and Appointments.
- **VFDNAV-002 — Direct Patients behavior:** Patients has no chevron/expand state and opens `/desk/vetedge-resource-center?resource=patients` in the same tab with one click.
- **VFDNAV-003 — Product Menu separation:** Patients appears as its own Product Menu section/item and does not appear under Appointments/Front Desk.
- **VFDNAV-004 — Patient access preservation:** existing entitled personas still see Patients; moving it does not grant access to a persona that previously lacked Veterinary Patient visibility.
- **VFDNAV-005 — Patient active/navigation state:** Patients is active on Patient Resource Center/list/detail navigation without leaving duplicate sidebar items active; browser Back/Forward remains sane.
- **VFDNAV-006 — Migration/idempotency:** running the sidebar synchronization/migrate again does not duplicate Patients or move it back under Front Desk.

These cases supplement, rather than replace, the existing VFD-BILL-01 Navigation, Front Desk, Billing Center, branch-isolation, role and accounting-safety cases.

## Local runtime acceptance

Run on the authoritative local site before merge:

```bash
bench --site vetedge.local migrate
bench build --app vetedge
bench --site vetedge.local run-tests \
  --app vetedge \
  --module vetedge.tests.test_vfd_bill_01_contract
bench --site vetedge.local clear-cache
```

### Manual navigation QA

Confirm:

- Veterinary Home and Patients are direct controls with no expand icon/functionality;
- Patients sits immediately after Veterinary Home;
- Dashboard, Clinical Operations, Appointments and Billing Center follow in the intended order;
- Patients is absent from Front Desk/Appointments;
- Product Menu presents Patients separately;
- Patients opens the existing Patient Resource Center in the same tab;
- patient list/detail/new-record navigation still resolves through the accepted Veterinary Patient Resource Center behavior;
- existing Patients role visibility remains correct for Administrator/System Manager, VetEdge Administrator, Front Desk, Doctor, Veterinary Nurse, Branch Manager, Dispensary User and Lab Technician as permitted by the pre-existing visibility contract;
- no unauthorized role gains Patients access;
- Front Desk contains Queue, Appointments, Pet Boarding Booking, Guest Booking Requests and Missed Appointments in that order;
- Customer/Sales Invoice/Payment Entry remain absent from Front Desk;
- Billing Center and its existing branch/accounting QA remain green.

## Out of scope

- a new Patient page or data model;
- changing Veterinary Patient permission logic;
- replacing ERPNext Sales Invoice or Payment Entry forms;
- direct payment allocation from Billing Center;
- changing submitted accounting documents;
- deleting Pet Grooming Appointment records/DocType;
- rebuilding Boarding, Grooming or Appointment workflows;
- broad reporting/financial dashboard redesign.
