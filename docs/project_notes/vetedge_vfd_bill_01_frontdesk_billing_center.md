# VFD-BILL-01 — Front Desk Navigation and Billing Center

## Goal

Separate first-class Patient access, appointment/front-desk work, and billing/accounting navigation while preserving existing VetEdge workflows, permissions, branch controls, and ERPNext accounting truth.

## Branch safety

This slice remains stacked on PR #60 branch `feature/vetedge-smart-home-vhome01` at exact base `e9b1c63bc1ec44483a93f26e10bff485fab43913`.

Do not retarget this PR to `main` or merge divergent PR #47/#50/#51 histories wholesale. PR #60's VHOME acceptance remains separate.

## Final navigation contract

The Veterinary top-level menu order is now:

1. Veterinary Home
2. Patients
3. Appointments
4. Clinical Operations
5. Hospital & Services
6. Inventory / Pharmacy
7. Billing Center
8. Dashboard
9. Reports

All other existing menu groups remain after Reports in their existing relative order. This is an ordering change only: no group contents, routes, permissions, business logic, or accounting behavior are changed by this order update.

Veterinary Home and Patients remain direct one-click controls. They have no chevron, expand/collapse behavior, hidden child, `aria-expanded` state, or second-click requirement. Patients opens the existing Patient Resource Center at `/desk/vetedge-resource-center?resource=patients`.

The persisted Workspace Sidebar uses `Front Desk` as the underlying section identity, while the EdgeSuite UI continues presenting that section as `Appointments`. `Clinical` similarly continues presenting as `Clinical Operations`. This preserves stable internal configuration while giving users the approved labels.

The persisted order is also used by Product Menu, so Product Menu and sidebar must show the same primary sequence. A customized Patients section containing additional administrator-added links remains protected from destructive rewriting.

### Appointments / Front Desk

Appointments contains only appointment/booking work:

1. Appointment Queue
2. Appointments
3. Pet Boarding Booking
4. Guest Booking Requests
5. Missed Appointments

Patients is no longer under Appointments. Customer, Sales Invoice and Payment Entry remain removed. Pet Grooming Appointment remains hidden from product navigation only; its DocType/history/workflow are unchanged.

### Dedicated Front Desk pages

The shared EdgeSuite Front Desk implementation supplies:

- `/desk/vetedge-front-desk-queue`
- `/desk/vetedge-front-desk-guest-bookings`
- `/desk/vetedge-front-desk-missed-appointments`

Old action-center tab URLs and the legacy Appointment Queue page remain compatibility redirects. Existing backend permissions, branch restrictions, actions and timestamp-conflict protection remain authoritative.

### Billing Center

Billing Center contains Customers, Sales Invoice, Payment Entry, Billing Session and Billing Center.

Billing Center V1 remains read/management only over `Veterinary Billing Session`. It does not submit/cancel invoices, mutate submitted accounting documents, create/allocate payments, post GL entries, bypass Frappe permissions, use raw SQL, or create another billing ledger.

## Navigation implementation

`vetedge.install.patient_navigation.ensure_direct_patient_navigation` runs after normal sidebar synchronization during install/migrate. It now performs two bounded steps:

1. preserve the direct Patients contract; and
2. reorder only the approved named primary groups.

The order helper recognizes stable/visible aliases (`Front Desk`/`Appointments`, `Clinical`/`Clinical Operations`, and `Inventory / Pharmacy`/`Inventory / Dispensary`). Unlisted groups are appended after Reports without changing their relative order.

`vetedge_postqa_navigation_hardening.js` mirrors the approved order in the rendered EdgeSuite shell after Veterinary Home and Patients are flattened into direct controls.

## Migration

No business-data or accounting-data migration is introduced. `bench --site vetedge.local migrate` rebuilds the normal VetEdge sidebar, applies the direct Patients arrangement, and applies the approved top-level order. Existing records and workflows remain unchanged.

## Frozen automated validation

Latest code/test candidate:

- workflow: `VFD-BILL-01 Validation`
- run: `34058750193`
- validated code/test head: `bfeb04488c528e50c5ddf30442f51c55db0d7d99`
- Python compile: PASS
- Ruff focused validation: PASS
- source-contract tests: PASS

The source contract locks the rendered order as Appointments → Clinical Operations → Hospital & Services → Inventory / Pharmacy → Billing Center → Dashboard → Reports after direct Veterinary Home and Patients. The installed-site test contract also validates the persisted Workspace Sidebar/Product Menu order.

Any later source/test change requires a fresh green validation run.

## QA Center update

Keep this inside the existing VFD-BILL-01 QA campaign. The Navigation cases are now:

- **VFDNAV-001 — Primary menu order:** exactly Veterinary Home → Patients → Appointments → Clinical Operations → Hospital & Services → Inventory / Pharmacy → Billing Center → Dashboard → Reports. Any remaining groups follow Reports in their previous relative order.
- **VFDNAV-002 — Direct Patients behavior:** no chevron/expand behavior; one click opens `/desk/vetedge-resource-center?resource=patients` in the same tab.
- **VFDNAV-003 — Product Menu parity:** Product Menu presents the same approved primary order; Patients remains separate from Appointments; no group contents change.
- **VFDNAV-004 — Access preservation:** existing visibility/permissions are unchanged; no unauthorized persona gains access from reordering.
- **VFDNAV-005 — Active/navigation state:** active menu state, Patient navigation and browser Back/Forward remain correct.
- **VFDNAV-006 — Migration/idempotency:** repeated migrate/sidebar sync preserves the exact approved order without duplicates, lost groups or moved-back Patients.

These supplement all existing Front Desk, Billing Center, branch-isolation, role, accounting-safety, responsive, light/dark and performance checks.

The authoritative QA Center remains on local `vetedge.local`; GitHub defines these case contracts but cannot write the corresponding local QA records directly.

## Local acceptance

```bash
bench --site vetedge.local migrate
bench build --app vetedge
bench --site vetedge.local run-tests \
  --app vetedge \
  --module vetedge.tests.test_vfd_bill_01_contract
bench --site vetedge.local clear-cache
```

Manual QA must verify both sidebar and Product Menu order exactly, then confirm all remaining groups stay after Reports in their existing relative order.

## Out of scope

- changing any group contents other than the already-approved VFD-BILL-01 membership changes;
- new Patient page/data model;
- Veterinary Patient permission changes;
- accounting workflow replacement;
- submitted accounting mutation;
- deleting Pet Grooming Appointment data/DocType;
- rebuilding Boarding/Grooming/Appointment workflows;
- broad reporting redesign.
