# VetEdge Phase 10 — Advanced Reporting & Intelligence Plan

## Goal

Extend the accepted EdgeSuite Reporting Standard into an actionable advanced reporting experience without moving product permissions, accounting truth, clinical rules or tenant/Branch logic into the shared UI layer.

Phase 10 must build on EdgeSuite UI PR #19 and VetEdge PR #47. It must not create parallel report shells or product-specific versions of capabilities that are reusable across ProcessEdge products.

## Architecture boundary

### EdgeSuite UI owns

Product-neutral presentation/runtime capability:

- report/dashboard shell composition;
- column visibility controls;
- serializable presentation view state;
- common grouping/subtotal presentation primitives where safe;
- comparison-period presentation primitives;
- conditional-highlight presentation primitives;
- export/print UI contracts;
- empty/loading/error/pagination behavior.

The shared layer must not call VetEdge APIs, query databases directly, determine Branch/role permissions, save product data or infer accounting/clinical truth.

### VetEdge owns

Product/data authority:

- report provider selection;
- report filters and smart Link searches;
- Branch/company/role/plan visibility;
- query-level pagination and aggregates;
- report-specific comparison calculations;
- report drill-through targets;
- saved-view ownership/persistence if introduced;
- scheduled-report recipient permissions;
- exception definitions based on Veterinary business rules;
- XLSX/CSV/PDF extraction and ERPNext-safe source data.

## Phase 10A — Advanced Report View State V1

Status: **shared EdgeSuite implementation in PR #19; VetEdge adoption pending shared CI/browser validation**.

### Shared capability

EdgeSuite UI PR #19 adds an opt-in `EdgeReportShell` column chooser:

- `columnChooserEnabled=false` by default;
- `viewState.visible_columns` initializes visible columns;
- `view-state-change` emits `{ visible_columns: [...] }`;
- at least one report column remains visible;
- `Show all` restores the full provider column set;
- current visible columns are supplied to Export dialog initialization;
- no localStorage/sessionStorage/database/API persistence in shared runtime;
- responsive chooser presentation is shared.

### VetEdge first adoption

Report Center should be the first consumer after EdgeSuite CI/browser acceptance.

Implementation contract:

1. Add `columns` to Report Center URL state only; do not send it to report providers.
2. Parse a compact comma-separated `columns=` value into `viewState.visible_columns`.
3. Enable `columnChooserEnabled` on `EdgeReportShell`.
4. Handle `view-state-change` by updating only presentation state and `history.replaceState`.
5. Do **not** reload the provider when columns change.
6. Ignore stale/unknown column keys; EdgeSuite shell reconciles them against current provider columns.
7. A copied URL must reproduce report, filters and visible-column selection.
8. Clearing custom column state should remove the `columns=` parameter rather than storing the complete default list.
9. Export dialog should begin with the current visible column set, while the server still validates requested export columns.

Example conceptual URL:

`/desk/vetedge-report-center?report=Consultation+Register&branch=Lagos&columns=consultation,patient,practitioner,status`

No new DocType is required for Phase 10A.

## Phase 10B — Named Saved Views

Do not implement until Phase 10A is accepted.

Required design decisions before a DocType exists:

- owner: user-only, role, Branch, tenant/company, or shared;
- who may create shared views;
- who may edit/delete another user's/shared view;
- whether a view can be marked default;
- report-key/version compatibility when columns or filters change;
- private vs shared naming collisions;
- safe migration/deactivation of views referring to retired reports;
- whether CoreEdge should eventually govern cross-product shared-view entitlement/usage.

Proposed minimum record if approved later:

- product app;
- report name/key;
- view name;
- owner user;
- visibility (`Private`, `Shared`);
- Branch/company scope if applicable;
- normalized filters JSON;
- presentation state JSON;
- default flag;
- enabled flag;
- last used timestamp.

All filter and permission validation must be reapplied when a saved view is loaded; stored state must never become a permission bypass.

## Phase 10C — Comparison Periods

Prefer report-provider support rather than browser-side materialization.

Examples:

- Current period vs previous period;
- Current month vs prior month;
- Branch vs Branch where user has access;
- practitioner/service performance comparison.

Rules:

- server calculates comparison aggregates;
- interactive row pagination remains independent;
- do not fetch two full row datasets merely to calculate KPI deltas;
- financial comparison must retain the canonical accounting/Branch resolver.

## Phase 10D — Grouping, Subtotals and Conditional Highlighting

Implement shared presentation only after provider contracts can supply safe grouping metadata.

Examples:

- group Consultation Register by Branch, Practitioner, Type or Status;
- group Vaccination by Vaccine/Branch/due status;
- highlight overdue vaccination, missing price, unpaid invoice, pending stock posting or operational exceptions;
- subtotal numeric columns from server-authoritative aggregates where required.

Do not let browser-side grouping replace server pagination for large datasets.

## Phase 10E — Exception Reporting

Exception reports should surface action, not merely another dashboard.

Potential Veterinary exceptions:

- overdue vaccinations;
- pending Lab results/review;
- Hospitalisation missing prices/pending stock/pending discharge actions;
- unpaid/partly-paid service invoices;
- expired/soon-expiring stock;
- repeated missed appointments;
- stale treatment plans/follow-ups where business rules define them.

Each exception requires:

- explicit business definition;
- role/Branch visibility;
- bounded query;
- clickable source record;
- state that explains why the record is exceptional;
- no hidden mutations from the report itself unless a permission-aware existing action is deliberately exposed.

## Phase 10F — Scheduled Reports

Schedule only after saved-view/filter state is stable.

Requirements:

- permission-aware report/view resolution at execution time, not only schedule creation time;
- recipient governance;
- Branch/company/tenant scope revalidation;
- safe attachment size/row limits;
- failure/retry audit;
- no queued export of unlimited datasets;
- disable schedules automatically when the underlying report/view is retired or access is lost;
- use CoreEdge messaging/email services where appropriate in platform deployments without making EdgeSuite UI depend on CoreEdge.

## Tests required

### Shared EdgeSuite UI

- column chooser default-off backward compatibility;
- serialization/reconciliation of visible columns;
- last-column protection;
- responsive/mobile panel;
- export-dialog alignment;
- no product/API/persistence logic in shared shell.

### VetEdge Phase 10A

- URL parsing/serialization;
- stale column keys ignored safely;
- no provider reload when only columns change;
- filters remain provider-owned and unchanged;
- Back/Forward/shareable URL behavior;
- export receives only validated requested columns;
- locked Advanced report cannot leak columns/data through URL state.

### Later persisted/scheduled phases

- owner/shared permissions;
- Branch/company fail-closed behavior;
- migration/version compatibility;
- schedule execution reauthorization;
- recipient and attachment safety;
- manual browser/network QA.

## Things not to change

- Do not mutate submitted ERPNext accounting documents.
- Do not move report-role/Branch/tenant enforcement into JavaScript.
- Do not introduce browser-side full-dataset materialization for grouping/comparison.
- Do not add polling for report state.
- Do not add a saved-view DocType merely because a column chooser now exists.
- Do not build a VetEdge-only column chooser; consume the shared EdgeSuite contract.
- Do not claim Phase 10A accepted until EdgeSuite UI PR #19 and VetEdge consumer browser/network QA pass.
