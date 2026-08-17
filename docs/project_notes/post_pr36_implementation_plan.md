# VetEdge Post-PR #36 Implementation Track

## Purpose

This branch is the continuation track for new VetEdge work after the current PR #36 QA baseline. It starts from PR #36 head `bce4faf51ecd036ecec3fe04466f9c3c5de365b7` so completed/recovered EdgeSuite work is preserved rather than restarted.

While PR #36 remains open, this PR should target the PR #36 integration branch. After PR #36 is merged to `main`, this continuation PR should be retargeted to `main` and reconciled before merge.

## Status rule

- Ongoing work remains in PR #36: clinical QA for Vital Signs, Laboratory Order and Vaccination Record, plus final combined navigation/theme/mobile/performance QA.
- New work belongs here unless it is strictly required to repair a PR #36 QA blocker.

## New implementation phases

### Phase 4 — EdgeSuite Reporting Standard V1
Status: New

Build on the already implemented Stock Expiry Monitor, Planned Treatment Report and VetEdge Report Center. Do not replace them. Establish a reusable report-provider contract that supports ordinary Frappe Query Reports and optimized paginated providers for large/high-use reports.

Shared requirements: summary cards where meaningful, server-side filtering/pagination for large datasets, bounded permission-aware Link search, lazy/aggregate data retrieval, drill/open actions, no large hidden master preloads, and separate interactive vs full-export execution paths.

Reusable reporting capability belongs in EdgeSuite UI where possible; VetEdge should contain product-specific providers and business rules.

### Phase 5 — Export / Print / PDF Foundation
Status: New

Extend the existing EdgeSuite download capability into a shared Export Builder.

Required formats: XLSX, CSV and PDF.

Required options: current page or all filtered records; include/exclude summary, filters, charts, letterhead, report title, generated metadata and totals; column selection/order; PDF orientation and repeated table headings.

If all presentation options are disabled, export only the raw table (column headings + rows).

Print and PDF must share a robust paginated rendering model rather than depend on the currently visible browser page. Generated files must use correct MIME types/extensions and pass integrity/open tests. Do not suppress browser security warnings; generate valid files so warnings are not triggered by corrupt/mismatched output.

### Phase 6 — Remaining VetEdge Report Migration / Optimization
Status: New

Inventory each remaining native/legacy report against the live branch. Use the shared Report Center for suitable small/simple reports and optimized paginated providers for large/high-use reports.

Prioritize Consultation Register, Laboratory Report, Vaccination Report, Owner Register, Patient Report, Revenue Summary, Service Revenue, Unpaid Invoice, Practitioner/Branch Performance, Stock Usage/Dispensary, treatment reports, Boarding/Grooming/Hospitalisation reporting and remaining administrative reports.

Do not resurrect historical PR #13/#14 architecture wholesale; recover only useful business/KPI/filter ideas that remain valid.

### Phase 7 — VCN / NADIS Regulatory Reporting
Status: New

Implement VCN/NADIS reports using the same shared report/export foundation. Support regulatory-specific export presets/templates without creating a separate reporting architecture.

### Phase 8 — Hospitalisation EdgeSuite Operational Completion
Status: New

Assess the actual current Hospitalisation implementation before coding, then complete only genuine gaps across admission, occupancy/care location, clinical activities, medication/feeding/vitals, stock, charges, billing/payment and discharge. Preserve submitted accounting-document integrity and existing hospitalisation business services.

### Phase 9 — Training Centre and Remaining Legacy Surfaces
Status: New

Re-audit the live branch after preceding phases and migrate only resources that remain genuinely native/legacy. Do not restart already implemented or QA-accepted work.

### Phase 10 — Advanced Reporting and Intelligence
Status: New

Add saved views, column chooser, drill-through, comparison periods, conditional highlighting, grouping/subtotals, shareable report state, export presets, scheduled reports and exception reporting after the reporting/export foundation is stable.

## Performance and data-usage acceptance rules

All new report/page work must be evaluated for client-side data usage and operational speed. Use browser/network/server evidence: request count, transferred bytes, payload size, duplicate requests, cold/warm/repeat navigation and slowest APIs.

Do not load full datasets merely to populate an interactive table, filter, KPI card or chart. Summary aggregates should be server-calculated where appropriate. Full export must be a separate server-side workflow from interactive pagination.

## Safety rules

- Do not mutate submitted Sales Invoices or other submitted accounting documents.
- Keep payment, stock, clinical, tenant/company/branch and permission validation server-authoritative.
- Do not add `ignore_permissions` to bypass business access rules.
- Do not introduce hard CoreEdge frontend dependencies.
- Preserve white-label/generic Veterinary operational wording.
- Keep changes backward compatible unless a migration is explicitly required.

## Merge strategy

1. Continue PR #36 QA independently.
2. Implement new phases on this continuation branch.
3. While PR #36 is open, base this PR on `integration/vetedge-current-qa-2026-08` so review shows only continuation work.
4. After PR #36 merges to `main`, retarget this PR to `main`, update/rebase as needed, rerun full validation and resolve any integration drift.
5. Merge this PR to `main` only after PR #36 and after its own QA gates pass.
