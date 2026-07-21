# VetEdge EdgeSuite Migration — Deferred QA Register

Status: **Deferred until the planned VetEdge EdgeSuite page/report migration is complete.**

This register exists so browser and real-data acceptance checks are not lost while CoreEdge service-layer testing and the wider VetEdge UI migration continue.

## Acceptance rule

Do not mark the VetEdge UI migration ready for merge or release until:

1. all planned page/report migration phases are complete;
2. automated validation is green against the required EdgeSuite UI branch or released `main`;
3. the checks below are completed on `vetedge.local` using existing clinic data;
4. submitted accounting documents remain unchanged;
5. branch, company, role and permission isolation are confirmed.

## A. Shared navigation and shell

- Veterinary Home is the first standalone product-menu item.
- Home is not duplicated under Dashboard.
- No visible menu description says Page, DocType, Report, Workspace or Link.
- Product pages open in the current tab.
- Intentionally native ERPNext documents open according to the approved navigation rule.
- The native Frappe sidebar is restored outside focused product shells.
- Waffle/product menu survives route changes and Desk rerenders.

## B. Veterinary Home and working branch

- `/app/vetedge-home` loads with the shared shell.
- Working Branch selection loads only permitted configured branches.
- Branch switch updates Company, Cost Center, Warehouse and Price List context.
- Patient, appointment, consultation, stock, billing and report operations follow the selected branch.
- Unconfigured-branch warning and administration action work.
- Home KPI counts reconcile with linked records for the selected branch.

## C. Veterinary Settings Center

- `/app/veterinary-settings-center` opens in the current tab.
- The whole operational page uses EdgeSuite UI.
- Metadata-driven tabs, sections and dependencies render correctly.
- Item searches show valid selling/service items rather than every Item.
- Price List searches show valid enabled selling Price Lists.
- File, password and child-table fields work.
- The Veterinary master switch remains protected.
- Timestamp-conflict protection prevents accidental overwrite.
- Saving still runs the native Veterinary Settings controller validations.
- Clinic name/logo changes update the permitted identity surfaces after cache/session refresh.

## D. Appointment and patient flow

- Patient-first appointment selection works.
- Dependent Owner, Patient, Branch and Practitioner values clear when the parent context changes.
- Pet Owner quick-create does not force Loyalty Program enrolment.
- Patient quick-create validates Branch-to-Company alignment.
- Date of Birth rejects future dates and updates Age.
- Existing-patient booking remains available.
- Medical History shows existing clinical records after Company-context migration.
- Multi-company and restricted-branch users cannot access unrelated records.

## E. Financial Dashboard and Revenue Summary

- Consultation Service Income receives values from the configured Consultation Item.
- Other consultation invoice items become Treatment Income unless explicitly classified under another service.
- Laboratory, Vaccination, Grooming, Boarding, Hospitalisation, Dispensary and Registration income remain separate.
- Consultation Service plus Treatment plus other allocated components reconciles to the submitted invoice total.
- Component paid and outstanding values reconcile to the submitted invoice.
- Revenue Composition cards remain visible.
- Only the duplicate composition donut/pie layout is absent.
- Revenue by Income Source remains available.
- Revenue Summary filters, columns, totals, links and exports work.
- No submitted Sales Invoice, Payment Entry, GL Entry or ledger value changes.

## F. Report migration — Phase 1

Reports:

- Branch Performance Report
- Consultation Register
- Planned Treatment

Checks:

- Shared header, KPI cards, filters, date presets, table, chart and empty state render.
- Default date range is This Month.
- Manual date edits switch the date preset to Custom Range.
- Full History uses the report backend’s available-data boundaries where supported.
- Branch Performance totals reconcile with operational and submitted-invoice data.
- Consultation Register document links, workflow status and billing values remain correct.
- Planned Treatment quantities, rates, amounts and consultation totals remain correct.
- Export and Print use the native report result.

## G. Report migration — Phase 2

Reports:

- Laboratory Report
- Vaccination Report
- Boarding Report
- Grooming Report

Checks:

- Existing filters still work and remain permission-aware.
- Laboratory pending, completed, cancelled, turnaround and unbilled indicators reconcile with source orders.
- Vaccination administered, due-soon and overdue indicators reconcile with source records.
- Boarding active/upcoming stays, duration, revenue and unbilled indicators reconcile with bookings.
- Grooming sessions, completion, revenue, unpaid and popular-service indicators reconcile with source records.
- Clicking linked documents opens the correct permitted record.
- Export, Print and Share work without replacing the native report table.

## H. Remaining migration phases

Add each remaining page/report group here before implementation. For every group record:

- routes and report names;
- shared components used;
- preserved backend/API source;
- permissions and branch/company rules;
- automated tests;
- browser and real-data acceptance checks.

## I. Console, network and performance review

- No JavaScript errors on migrated routes.
- No failed EdgeSuite or VetEdge asset requests.
- No stale private CoreEdge frontend imports.
- No unexpected new-tab navigation.
- No duplicate page shells, headers, KPI sections or charts.
- Large reports remain responsive and do not load unrestricted Link-field datasets.
- Socket.IO issues are recorded separately from page migration defects.

## J. Final acceptance evidence

Record:

- EdgeSuite UI commit tested;
- VetEdge commit tested;
- site and date tested;
- roles tested;
- branches/companies tested;
- reports/pages passed;
- known exceptions;
- screenshots or issue references where needed;
- merge recommendation.
