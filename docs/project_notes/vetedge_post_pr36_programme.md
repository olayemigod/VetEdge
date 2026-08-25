# VetEdge Post-PR36 Programme

This branch contains new work that must follow PR #36. It is intentionally stacked on `integration/vetedge-current-qa-2026-08` and must be retargeted/reconciled against `main` only after PR #36 merges.

## Scope ownership

PR #36 continues to own QA/fixes for Vital Signs, Veterinary Lab Order operational workflow, Veterinary Vaccination Record operational workflow, and the final EdgeSuite consolidation gate. This branch must not duplicate or redesign those accepted clinical workflows.

## Phase 4 — EdgeSuite Reporting Standard V1 — In progress

- Shared reporting runtime is implemented in linked EdgeSuite UI PR #19.
- VetEdge Report Center resolves product providers first and falls back to Frappe Query Reports.
- Stock Expiry remains the query-level paginated reference provider.
- Planned Treatment performs query-level detail pagination while preserving the existing scoped-consultation access resolver.
- Lab Order Report uses a dedicated query-level paginated, read-only provider with report-role, branch and DocType read checks. Summary/status cards use aggregate queries; result-entry timestamps are resolved only for the current page's child rows.
- Vaccination Report uses a dedicated query-level paginated, read-only provider. Due Soon/Overdue filtering is pushed into the database query and summary cards are aggregate-backed.
- Lab/Vaccination optimized providers accept the Report Center's `customer` filter alias as owner context while retaining `owner` for native report compatibility.

## Phase 5 — Export / Print / PDF Foundation — Implementation complete; QA pending

Implemented: XLSX/CSV/PDF, current-page/all-filtered scope, raw table mode, optional title/filters/cards/charts/letterhead/generated metadata/totals, selected column order, PDF orientation/repeated headings, shared Print/PDF document rendering, verified downloads, and bounded chart presentation.

Acceptance still requires real browser/file QA, real letterhead combinations and representative chart/export testing.

## Phase 6 — Remaining report migration / optimisation — In progress

Optimized providers completed structurally:
1. Planned Treatment.
2. Laboratory / Lab Order Report.
3. Vaccination Report.

Lab/Vaccination provider acceptance still needs browser/network QA to confirm filter parity, pagination, display names, cards, chart and row navigation against real data. Structural implementation is complete; do not rework their clinical DocType workflows from this reporting branch.

Consultation Register is the next high-use candidate for detailed audit because its invoice/treatment/vaccination enrichments must remain semantically correct if paginated. Small/bounded reports may remain on the generic Report Center provider where measurement does not justify a dedicated provider.

## Performance contract

Server filtering/query-level pagination for large/high-use data sets; bounded permission-aware Link search; no hidden large master preloads or unnecessary polling; cards/charts independent of complete interactive rows; separate server export; measure request count, transferred bytes, payload size, repeat navigation and slow APIs.

## Safety contract

Report endpoints are read-only. Never mutate submitted ERPNext accounting documents. Keep report roles, DocType permissions, branch/company/tenant context and clinical access server-authoritative. No permission bypass or hard CoreEdge frontend dependency. Generate valid files rather than suppressing browser security warnings.

## Current checkpoint

Phase 5 code is implementation-complete but QA-pending. Phase 6 has three optimized providers structurally implemented. Source-contract tests cover registration, pagination, report/branch normalization, DocType read permission, owner/customer compatibility, aggregate cards and no-mutation rules. PR #47 remains Draft until its own automated/browser/network/file acceptance gates pass and PR #36 merges first.
