# VetEdge Phase 10 — Advanced Reporting & Intelligence Plan

## Goal

Extend the accepted EdgeSuite Reporting Standard into an actionable advanced reporting experience without moving product permissions, accounting truth, clinical rules or tenant/Branch logic into the shared UI layer.

Phase 10 builds on EdgeSuite UI PR #19 and VetEdge PR #47. It must not create parallel report shells or product-specific versions of reusable presentation capabilities.

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
- saved-view validation and product integration;
- scheduled-report recipient permissions;
- exception definitions based on Veterinary business rules;
- XLSX/CSV/PDF extraction and ERPNext-safe source data.

## Phase 10A — Advanced Report View State V1

Status: **implemented; browser/network QA pending**.

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

### VetEdge adoption

Report Center is the first consumer.

Implemented contract:

1. `columns` is Report Center URL state only; it is never sent to report providers.
2. A compact comma-separated `columns=` value initializes `viewState.visible_columns`.
3. `columnChooserEnabled` is enabled on Report Center `EdgeReportShell`.
4. `view-state-change` updates presentation state and `history.replaceState` only.
5. Column changes do **not** reload the provider or call a backend API.
6. Stale/unknown column keys are reconciled by the shared shell against current provider columns.
7. A copied URL reproduces report, filters and visible-column selection.
8. Export dialog starts from the current visible-column set while server export validation remains authoritative.

Example:

`/desk/vetedge-report-center?report=Consultation+Register&branch=Lagos&columns=consultation,patient,practitioner,status`

Source contract: `vetedge/tests/test_report_center_view_state_contract.py`.

## Phase 10B — Private Named Saved Views

Status: **backend persistence implemented; Report Center UI adoption next**.

### Storage decision

Do **not** add a new saved-view DocType for private views.

Frappe v16 already provides per-user `__UserSettings` storage through `frappe.model.utils.user_settings`. VetEdge therefore stores private named report views under the `VetEdge Report Center` user-settings scope. This gives user ownership without another schema migration and preserves standalone deployment.

The shared EdgeSuite shell remains persistence-free.

### Implemented backend

`vetedge.services.report_saved_views` provides:

- `get_saved_report_views(report_name)`;
- `save_report_view(...)`;
- `delete_saved_report_view(view_id)`.

Safety and data limits:

- current authenticated Frappe user only;
- Guest is rejected;
- report entitlement is rechecked on list/save;
- maximum 25 private views per user;
- 80-character view names;
- report/filter/column values are bounded;
- only Report Center-supported filter keys are stored;
- at most 100 visible-column keys;
- duplicate view names within one report are rejected;
- one optional default view per report;
- only filter/presentation metadata is stored — never report result rows;
- no `ignore_permissions`, arbitrary SQL or new DocType/table;
- no team/public sharing fields yet.

Source contract: `vetedge/tests/test_report_saved_views_contract.py`.

### Phase 10B UI slice — next

Report Center should use existing EdgeSuite primitives rather than native custom HTML:

- `EdgeDropdown` for the current report's saved views;
- `EdgeModal` + `EdgeInput` for Save/Rename View;
- explicit Save Current View / Update View / Delete View actions;
- apply a saved view by replacing Report Center filters + `viewState`, updating URL, then performing the ordinary report refresh once;
- column-only edits remain presentation-only until the user explicitly saves/updates the named view;
- load only saved views for the current report;
- no polling;
- no hidden preload of views for every report;
- delete/update must operate only on IDs returned for the current user.

### Shared/team views remain deferred

Private user settings are intentionally not the storage model for team/public views. Before shared views exist, define:

- tenant/company/Branch ownership scope;
- who may publish or withdraw a shared view;
- read/edit/delete roles;
- naming collisions between private/shared views;
- whether Branch-limited views may be shared outside that Branch;
- CoreEdge governance in shared-hosted/white-label environments;
- audit trail requirements.

Stored state must never become a permission bypass. Filters, report entitlement, Branch/company and role access are always revalidated at execution time.

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

### VetEdge Phase 10B

- private-user isolation through Frappe user settings;
- Guest rejection;
- report entitlement revalidation;
- filter allowlist and payload bounds;
- duplicate name behavior;
- default-view behavior;
- maximum-view limit;
- apply/load/delete UI behavior;
- one ordinary provider refresh when a saved filter view is applied;
- no provider refresh for unsaved column-only presentation changes;
- no result-row persistence.

### Later shared/scheduled phases

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
- Do not add a private saved-view DocType when Frappe user settings already provide the required user-owned storage.
- Do not use private user settings as the future team/public sharing model.
- Do not build a VetEdge-only column chooser; consume the shared EdgeSuite contract.
- Do not claim Phase 10A/10B accepted until EdgeSuite UI PR #19 and VetEdge consumer browser/network QA pass.
