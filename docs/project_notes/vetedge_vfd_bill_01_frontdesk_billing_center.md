# VFD-BILL-01 — Front Desk Navigation and Billing Center

## Goal

Separate first-class Patient access, appointment/front-desk work, and billing/accounting navigation while preserving existing VetEdge workflows, permissions, branch controls, and ERPNext accounting truth.

## Branch safety

This slice remains stacked on PR #60 branch `feature/vetedge-smart-home-vhome01` at exact base `e9b1c63bc1ec44483a93f26e10bff485fab43913`.

Do not retarget this PR to `main` or merge divergent PR #47/#50/#51 histories wholesale. PR #60's VHOME acceptance remains separate.

## Final navigation contract

### Direct primary items

The Veterinary sidebar starts with:

1. Veterinary Home
2. Patients
3. Dashboard
4. Clinical Operations
5. Appointments
6. Billing Center

Veterinary Home and Patients are direct one-click controls. They must have no chevron, expand/collapse behavior, hidden child, `aria-expanded` state, or second-click requirement.

Patients opens the existing Patient Resource Center at `/desk/vetedge-resource-center?resource=patients`. No new Patient page, DocType, permission model, or patient data model is introduced.

The persisted Workspace Sidebar stores Patients as its own one-item section so Product Menu also presents Patients separately. The EdgeSuite sidebar shell flattens that one-item section into a direct control immediately after Veterinary Home.

The existing Patients `display_depends_on` visibility expression is preserved. A customized Patients section containing additional administrator-added links is deliberately left unchanged rather than partially rewritten.

### Appointments / Front Desk

Front Desk now contains only appointment/booking work:

1. Appointment Queue
2. Appointments
3. Pet Boarding Booking
4. Guest Booking Requests
5. Missed Appointments

Patients is no longer under Front Desk/Appointments.

Customer, Sales Invoice and Payment Entry remain removed from Front Desk. Pet Boarding Booking remains moved from Hospital & Services to immediately after Appointments. Pet Grooming Appointment remains removed from product navigation only; its DocType/history/workflow are unchanged.

### Dedicated Front Desk pages

The existing shared EdgeSuite Front Desk implementation supplies three canonical pages:

- `/desk/vetedge-front-desk-queue`
- `/desk/vetedge-front-desk-guest-bookings`
- `/desk/vetedge-front-desk-missed-appointments`

The old action-center tab URLs and legacy Appointment Queue page remain compatibility redirects. Existing backend permissions, branch restrictions, workflow actions and timestamp-conflict protection remain authoritative.

### Billing Center

Billing Center contains:

1. Customers
2. Sales Invoice
3. Payment Entry
4. Billing Session
5. Billing Center

Billing Center V1 remains a read/management surface anchored on `Veterinary Billing Session`. It does not submit/cancel invoices, mutate submitted accounting documents, create/allocate payments, post GL entries, bypass Frappe permissions, use raw SQL, or create another billing ledger.

Branch-restricted users remain fail-closed; Branch Link search cannot reveal unassigned branches; Patient filter options are constrained by Company, Branch and selected Customer.

## Patient navigation implementation

The proven VFD-BILL-01 dashboard/sidebar transformation remains unchanged. `vetedge.install.patient_navigation.ensure_direct_patient_navigation` runs after normal sidebar synchronization during install/migrate.

For the standard VetEdge sidebar it:

- finds the existing Patients link;
- preserves its visibility expression;
- removes it from Front Desk;
- creates exactly one dedicated Patients one-item section before Dashboard;
- preserves Veterinary Home as the leading direct item;
- is idempotent.

`vetedge_postqa_navigation_hardening.js` then flattens the canonical Patients section to a direct EdgeSuite sidebar item, routes it in the same Desk tab, maintains active state, and places it immediately after Veterinary Home.

## Migration

No business-data or accounting-data migration is introduced. `bench --site vetedge.local migrate` must rebuild the normal VetEdge sidebar and then apply the direct Patients post-sync arrangement. Existing Patient, appointment, billing and accounting records remain unchanged.

## Final automated source validation

Final source candidate:

- workflow: `VFD-BILL-01 Validation`
- run: `34058059059`
- validated code head: `4e30239b5b41d8a3dc44b99aeabd8b9dfb9a8961`
- Python compile: PASS
- Ruff focused validation: PASS
- source-contract tests: PASS

Any commit after `4e30239b5b41d8a3dc44b99aeabd8b9dfb9a8961` must be documentation-only or source validation must be rerun.

## QA Center update

Keep the menu change inside the existing VFD-BILL-01 QA campaign. Do not create a separate divergent campaign. Add these Navigation cases:

- **VFDNAV-001 — Direct Patients placement:** Veterinary Home first; Patients immediately second; Dashboard, Clinical Operations and Appointments follow.
- **VFDNAV-002 — Direct Patients behavior:** no chevron/expand behavior; one click opens `/desk/vetedge-resource-center?resource=patients` in the same tab.
- **VFDNAV-003 — Product Menu separation:** Patients is its own Product Menu section/item and is absent from Appointments/Front Desk.
- **VFDNAV-004 — Access preservation:** existing entitled personas retain Patients visibility; no previously unauthorized persona gains access.
- **VFDNAV-005 — Active/navigation state:** Patients remains correctly active through Patient Resource Center/list/detail navigation; no duplicate active sidebar item; Back/Forward works.
- **VFDNAV-006 — Migration/idempotency:** repeated migrate/sidebar synchronization does not duplicate Patients or return it to Front Desk.

These supplement the existing VFD-BILL-01 Front Desk, Billing Center, role, branch-isolation and accounting-safety cases.

The repository defines the QA contract and case IDs. The authoritative QA Center is on local `vetedge.local`, so its campaign records must be updated there after this candidate is installed; GitHub cannot directly write records into that local site.

## Local acceptance

Run on `vetedge.local`:

```bash
bench --site vetedge.local migrate
bench build --app vetedge
bench --site vetedge.local run-tests \
  --app vetedge \
  --module vetedge.tests.test_vfd_bill_01_contract
bench --site vetedge.local clear-cache
```

Manual QA must confirm the six VFDNAV cases plus all existing VFD-BILL-01 checks, including Front Desk routes/actions, legacy redirects, role compatibility, Billing Center branch isolation, contextual filters, totals/drill-through, accounting immutability, responsive layout, light/dark mode and absence of unnecessary polling.

## Out of scope

- new Patient page/data model;
- Veterinary Patient permission changes;
- accounting workflow replacement;
- submitted accounting mutation;
- deleting Pet Grooming Appointment data/DocType;
- rebuilding Boarding/Grooming/Appointment workflows;
- broad reporting redesign.
