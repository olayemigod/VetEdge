# VFD-BILL-01 — Front Desk Navigation and Billing Center

## Goal

Separate front-desk appointment work from billing/accounting navigation, give Appointment Queue, Guest Booking Requests and Missed Appointments durable full-page URLs, and add a consolidated Veterinary Billing Center without replacing ERPNext accounting truth.

## Branch and composition safety

This slice is stacked on PR #60 Veterinary Home branch `feature/vetedge-smart-home-vhome01` at exact base `e9b1c63bc1ec44483a93f26e10bff485fab43913`.

PR #60 itself is not modified by this work. VFD-BILL-01 remains on `feature/vetedge-frontdesk-billing-center-vfd-bill-01` so VHOME QA evidence is not repointed or overwritten.

Do not merge divergent PR #47/#50/#51 histories to obtain this scope. The branch inherits the reconciled VetEdge composition through PR #60.

## Navigation contract

### Front Desk

Front Desk contains operational booking work:

1. Appointment Queue
2. Patients
3. Appointments
4. Pet Boarding Booking
5. Guest Booking Requests
6. Missed Appointments

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

The shared bundle publishes canonical `/desk/...` active routes for all three dedicated pages.

The old `/desk/vetedge-front-desk-action-center?tab=...` route is compatibility-only and redirects to the matching canonical page. `veterinary-appointment-queue` also redirects to the new Appointment Queue page.

Page roles preserve the access contract of the links they replace. In particular, Veterinary Nurse and Dispensary User retain Appointment Queue access where previously allowed, and Veterinary Nurse retains Missed Appointments access. The legacy Action Centre Page also retains those redirect-only personas so old bookmarks can reach the compatibility redirect instead of failing before its script executes.

### Billing Center menu group

Billing Center is inserted immediately after Front Desk and contains:

1. Customers
2. Sales Invoice
3. Payment Entry
4. Billing Session
5. Billing Center

The first four links open their existing authoritative DocType workflows. Billing Center opens `/desk/vetedge-billing-center`.

The sidebar transformation is idempotent and runs as part of the existing VetEdge Workspace Sidebar synchronization, so migrations cannot silently restore the old arrangement.

## Billing Center V1

Billing Center V1 is a read/management surface anchored on `Veterinary Billing Session`.

It provides:

- open Billing Session count;
- outstanding Billing Session count;
- outstanding amount;
- amount collected according to Billing Session truth;
- paginated Billing Session visibility;
- Company, Branch, Customer, Patient, status and creation-date filters;
- relevant, bounded Link searches;
- current draft and latest invoice visibility;
- drill-through to Billing Session and Sales Invoice;
- permission-aware shortcuts to Customers, Sales Invoices and Payment Entries.

### Deliberate V1 boundary

Billing Center does not guess unrelated ERPNext Sales Invoices into a Veterinary Branch. Veterinary Billing Session is the safe consolidated anchor because it already stores Customer, Patient, Company, Branch and billing totals.

General ERPNext accounting documents remain available from the Billing Center menu group and native ERPNext lists.

A later reporting/financial-management slice can extend cross-document reconciliation using the existing accounting-safe financial dataset/branch resolver after dedicated performance and permission QA.

## Accounting safety

Billing Center does not:

- submit or cancel Sales Invoices;
- mutate submitted Sales Invoices;
- create or allocate Payment Entries;
- amend submitted accounting documents;
- post GL entries;
- bypass Frappe permissions;
- use raw SQL;
- create a second billing ledger or billing-session model.

All accounting mutations remain in existing ERPNext/VetEdge workflows.

## Branch and permission safety

Billing Center requires an internal VetEdge user with an approved Front Desk, Branch Manager, Accounts/Cashier/Accounts User, VetEdge Administrator or System Manager role and read permission on Veterinary Billing Session.

Elevated VetEdge administrators retain global Branch visibility.

For non-global operational users:

- explicit Branch selection must be one of the user's active Branch assignments;
- no Branch selection scopes queries to all assigned Branches;
- zero assigned Branches fails closed to an empty Billing Center scope;
- Branch filter search never replaces or overwrites the server-authoritative Branch restriction;
- restricted Branch Link search returns only the caller's assigned Branch names.

All primary Billing Session reads use `frappe.get_list`, preserving Frappe permission-query conditions.

Billing Center Page roles are aligned with actual Billing Session data access. Accounts Manager is intentionally not advertised as a standalone Billing Center Page role unless the underlying Billing Session permission contract is later expanded deliberately.

## Smart filtering

Billing Center filters cascade:

- changing Company clears Branch, Customer and Patient;
- changing Branch clears Customer and Patient;
- changing Customer clears Patient;
- Patient Link search is server-filtered by the selected Customer as well as Company/Branch context;
- Branch Link search cannot leak unassigned Branch names.

Link option APIs return values from permitted Billing Session context and are capped at 20 options. Billing Session rows are capped at 100 per request and default to 25.

## Migration and backward compatibility

No business-data migration or accounting data rewrite is required.

`bench --site vetedge.local migrate` must:

1. import the four new Page definitions;
2. rebuild the live VetEdge Workspace Sidebar using the idempotent navigation transform;
3. retain existing DocTypes and historical data;
4. retain old Front Desk URLs as compatibility redirects.

Rollback of the UI slice does not require reversing business data because no new accounting or clinical data model is introduced.

## Automated validation

A stacked-PR-specific source gate exists at `.github/workflows/vfd-bill-01-validation.yml` because the repository's general CI listens only to PRs targeting `main`.

Latest green source validation evidence:

- workflow: `VFD-BILL-01 Validation`
- run: `34055850616`
- head: `81e263afdc4f660aae385e9d259599845d432ab7`
- Python compile: PASS
- Ruff focused validation: PASS
- pure source-contract tests: PASS

The source gate does not replace installed-site QA.

Run on the authoritative local site before merge:

```bash
bench --site vetedge.local run-tests \
  --app vetedge \
  --module vetedge.tests.test_vfd_bill_01_contract

bench --site vetedge.local migrate
bench build --app vetedge
```

## Manual browser QA

Test on `vetedge.local` after migration and asset build.

### Navigation

- Front Desk displays the six intended links in the intended order.
- Customer/Sales Invoice/Payment Entry are absent from Front Desk.
- Billing Center appears immediately after Front Desk with five requested links.
- Pet Boarding Booking appears once, under Front Desk, directly after Appointments.
- Pet Grooming Appointment does not appear in product navigation.
- Boarding Stay, Boarding Care Record and Grooming Session remain under Hospital & Services.
- Queue/Missed visibility remains correct for Veterinary Nurse; Queue visibility remains correct for Dispensary User.

### Front Desk pages

For Appointment Queue, Guest Booking Requests and Missed Appointments:

- each sidebar item opens its own `/desk/...` URL in the same Desk tab;
- the EdgeSuite Front Desk shell remains visible;
- no queue/guest/missed tab strip is shown;
- Company/Branch and permission behavior remains correct;
- existing actions work and timestamp-conflict protection still prevents overwrites;
- browser Back/Forward behavior is sane;
- old Action Center tab URLs redirect to the correct new page;
- old Appointment Queue bookmarks still work, including previously entitled Nurse/Dispensary personas.

### Billing Center

Test Administrator, VetEdge Administrator, Front Desk, Branch Manager, Accounts/Cashier and Accounts User personas as applicable:

- permitted sessions load;
- zero-branch operational user sees no cross-branch data;
- Branch A user cannot select or retrieve Branch B billing sessions;
- Branch A user cannot discover Branch B through Branch Link search;
- Company → Branch → Customer → Patient filtering cascades correctly;
- selected Customer restricts Patient Link options server-side;
- paging does not exceed configured limits;
- session totals reconcile to the source Billing Sessions;
- Open Session opens the authoritative Veterinary Billing Session;
- Open Latest Invoice opens the authoritative Sales Invoice;
- Customer/Sales Invoice/Payment Entry shortcuts respect native ERPNext permissions;
- no action on the page directly submits, cancels or mutates an accounting document.

### Presentation / performance

Verify desktop and narrower widths in light and dark mode. Confirm no unnecessary polling or repeated background requests.

## Out of scope

- replacing ERPNext Sales Invoice or Payment Entry forms;
- direct payment allocation from Billing Center;
- credit notes, write-offs or invoice cancellation UI;
- changing Billing Core pricing or payment gates;
- changing submitted accounting documents;
- deleting Pet Grooming Appointment records or DocType;
- rebuilding Boarding, Grooming or Appointment workflows;
- broad reporting/financial dashboard redesign.
