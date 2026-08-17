# VetEdge Post-PR36 Programme

This branch contains new work that must follow PR #36. It is intentionally stacked on `integration/vetedge-current-qa-2026-08` and must be retargeted/reconciled against `main` only after PR #36 merges.

## Scope ownership

PR #36 continues to own QA/fixes for Vital Signs, Veterinary Lab Order operational workflow, Veterinary Vaccination Record operational workflow, and the final EdgeSuite consolidation gate. This branch must not duplicate or redesign those accepted clinical workflows.

## Phase 4 — EdgeSuite Reporting Standard V1 — In progress

- Shared reporting runtime is implemented in linked EdgeSuite UI PR #19.
- VetEdge Report Center resolves product providers first and falls back to Frappe Query Reports.
- Stock Expiry remains the query-level paginated reference provider.
- Planned Treatment now performs query-level detail pagination while preserving the existing scoped-consultation access resolver.
- Lab Order Report now uses a dedicated query-level paginated, read-only provider with report-role, branch and DocType read checks. Summary/status cards use aggregate queries; result-entry timestamps are resolved only for the current page's child rows.
- Vaccination Report now uses a dedicated query-level paginated, read-only provider. Due Soon/Overdue filtering is pushed into the database query and summary cards are aggregate-backed.

## Phase 5 — Export / Print / PDF Foundation — Implementation complete; QA pending

Implemented:
- XLSX, CSV and PDF export.
- Current Page and All Filtered scopes.
- raw table mode when all presentation options are off.
- optional report title, filters, summary cards, charts, letterhead, generated metadata and totals.
- user-selected column order.
- PDF orientation and repeated headings.
- server-generated Print/PDF document model.
- verified downloads that reject empty responses, HTML errors, invalid PDF/XLSX signatures and MIME mismatches.
- chart presentation in PDF/Print and structured chart data in XLSX/CSV.

Acceptance still requires real browser/file QA, real letterhead combinations and representative chart/export testing.

## Phase 6 — Remaining report migration / optimisation — In progress

Optimized providers completed structurally:
1. Planned Treatment.
2. Laboratory / Lab Order Report.
3. Vaccination Report.

Next reports must be audited individually. Small/bounded reports may stay on the generic Report Center Query Report provider. Large/high-use reports should receive server-paginated providers only where actual data volume/network/server measurements justify it.

## Performance contract

- Server filtering and query-level pagination for large/high-use data sets.
- Bounded permission-aware Link search.
- No large hidden master preloads.
- No unnecessary polling.
- Summary cards/charts must not depend on downloading all interactive rows.
- Full export remains a separate server workflow from interactive pagination.
- Measure request count, transferred bytes, response payload size, repeat navigation and slow APIs during QA.

## Safety contract

- Never mutate submitted ERPNext accounting documents.
- Report endpoints are read-only.
- Keep report roles, DocType permissions, branch/company/tenant context and clinical access server-authoritative.
- No permission bypass.
- No hard CoreEdge frontend dependency.
- Do not suppress browser security warnings; generate valid files and reject invalid responses.
