# VetEdge EdgeSuite UI Document Migration

## Goal

Move VetEdge operational DocTypes from the legacy-looking Frappe presentation into the EdgeSuite UI experience without replacing Frappe's proven document engine or changing VetEdge business rules.

## Architecture Decision

VetEdge will use two complementary UI patterns:

1. **Native Desk EdgeSuite layer** for standard DocType list views, add/edit forms, workflow actions, child tables, timelines, dialogs, and Settings.
2. **Dedicated EdgeSuite pages** for dashboards, queues, action centres, guided workflows, and other screens that need a purpose-built experience.

This avoids rebuilding ERPNext/Frappe form behaviour, permissions, workflow, comments, attachments, child tables, audit history, and document lifecycle logic in parallel Vue applications.

## Phase 1 — Native Document Foundation

Implemented on branch `agent/vetedge-edgeui-docs-phase1`.

### Coverage

The adapter applies automatically when:

- the active route is a Frappe `List` or `Form` route; and
- the DocType module is `Veterinary`.

This covers operational documents, service documents, masters, and single settings DocTypes without maintaining a fragile manual list.

### Surfaces migrated

- List page header, filters, rows, status indicators, empty state, sidebar, and pagination
- Add New and standard primary actions
- Document form header, dashboard, sections, tabs, fields, child tables, timeline, and status
- Workflow and action menu presentation
- Frappe dialogs and modal primary actions opened from Veterinary screens
- Veterinary Settings, including a settings-specific introduction and warning context
- Same-tab navigation to native VetEdge DocType routes instead of redirecting operational records into the Resource Center

### Safety boundaries

The Phase 1 adapter is presentation-only.

It does not:

- call server APIs;
- insert, update, delete, submit, cancel, or amend documents;
- replace existing DocType JavaScript controllers;
- bypass permissions, branch filters, workflow rules, or backend validation;
- mutate submitted Sales Invoices or other accounting documents;
- change billing, payment gates, stock, laboratory, vaccination, hospitalisation, grooming, or boarding logic.

## Phase 2 — Operational Screen Review

Review the most-used workflows individually and add DocType-specific EdgeSuite refinements only where the generic foundation is insufficient.

Recommended order:

1. Veterinary Patient
2. Veterinary Appointment and Missed Appointment
3. Veterinary Consultation
4. Veterinary Lab Order
5. Veterinary Vaccination Record
6. Veterinary Hospitalisation
7. Pet Grooming Appointment and Session
8. Pet Boarding Booking, Stay, and Care Record
9. Kennel and Veterinary Care Location
10. Veterinary masters and setup documents

Each review should check:

- list columns and default ordering;
- branch, company, patient, owner, practitioner, and status filters;
- Add New defaults and dependent field queries;
- workflow action prominence and permitted transitions;
- dialogs, billing modal, result-entry modal, and service-specific actions;
- child-table readability and mobile behaviour;
- submitted-document read-only behaviour;
- useful links to related documents and reports.

## Phase 3 — Settings Information Architecture

Veterinary Settings should be reviewed after Phase 1 browser QA and reorganised into clear operational sections where necessary:

- General and company context
- Consultation and registration billing
- Payment gates and invoice behaviour
- Laboratory controls
- Vaccination controls
- Hospitalisation and care locations
- Grooming and boarding
- Inventory and dispensary
- Notifications and reminders
- Integrations and platform access

Any field movement must preserve fieldnames, defaults, patches, and backward compatibility.

## Required Verification

### Automated

- JavaScript syntax check for `vetedge_desk_ui.js`
- Python compilation for `hooks.py` and the contract test
- `test_vetedge_desk_edgeui_contract.py`
- Existing EdgeSuite UI dependency and professional UI contract tests
- Existing affected DocType tests when a later phase changes a DocType controller

### Local site

Run on `vetedge.local`:

```bash
bench build --app vetedge
bench --site vetedge.local clear-cache
bench --site vetedge.local migrate
```

### Manual QA

For at least one user in each relevant role:

- Open a Veterinary list from the product menu and confirm it remains in the same tab.
- Search, filter, paginate, select rows, and open a record.
- Create a permitted draft record and verify all existing defaults and dynamic filters.
- Open and edit a draft record.
- Confirm submitted records remain protected.
- Run available workflow actions and confirm only permitted actions appear.
- Open standard and VetEdge custom dialogs and confirm they remain functional.
- Add and edit child-table rows.
- Open Veterinary Settings, save a harmless test change, restore it, and confirm no layout regression.
- Check desktop, tablet, and mobile widths.
- Navigate to a non-Veterinary ERPNext DocType and confirm the VetEdge document styling is not applied.

## Rollback

The foundation can be rolled back safely by removing the two `vetedge_desk_ui` asset entries from `hooks.py`. No database migration or data reversal is required.
