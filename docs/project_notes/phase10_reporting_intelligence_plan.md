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
- comparison-period presentation primitives;
- common grouping/subtotal presentation primitives where safe;
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
- premium Advanced Reporting feature entitlement;
- report drill-through targets;
- saved-view validation and product integration;
- scheduled-report recipient permissions;
- exception definitions based on Veterinary business rules;
- XLSX/CSV/PDF extraction and ERPNext-safe source data.

## Phase 10A — Advanced Report View State V1

Status: **implemented; browser/network QA pending**.

EdgeSuite UI PR #19 supplies an opt-in `EdgeReportShell` column chooser. VetEdge Report Center consumes it through URL-only `columns=` state. Column changes are presentation-only and do not reload report providers or call backend APIs. Screen-visible columns and Export-dialog defaults use the same shared shell state.

Source contract: `vetedge/tests/test_report_center_view_state_contract.py`.

## Phase 10B — Private Named Saved Views

Status: **implementation complete; automated/browser QA pending**.

### Storage and ownership

Private views use Frappe v16 per-user `__UserSettings` through `frappe.model.utils.user_settings`; no VetEdge DocType or migration was added.

- scope: `VetEdge Report Center`;
- key: `vetedge_report_views_v1`;
- maximum 25 private views per user;
- current authenticated user only;
- no team/public sharing model yet.

Frappe synchronizes the user-settings cache to the database through its standard hourly-maintenance `sync_user_settings` job.

### Security/privacy contract

- report View authorization is revalidated on list/save/rename/apply;
- Advanced report entitlement therefore remains enforced;
- list returns view metadata only, not stored Patient/Owner/filter values;
- stored state is returned only through explicit Apply after current scope revalidation;
- stale/inaccessible Branch is removed and current server Branch normalization reapplied;
- supported smart-filter values are rechecked through the existing bounded permission-aware report-filter search;
- invalid stale filter values are removed without disclosing their old values to the client;
- report result rows/charts/summary datasets are never stored.

### Report Center UX

Report Center now supplies Saved Views, Save View, Rename and Delete controls. Applying a view performs one state-validation request and exactly one ordinary provider refresh, resets pagination and updates the shareable URL. Manual filter/column edits clear the selected-view marker.

Default auto-apply is intentionally deferred because it must be designed as a single-load startup path rather than adding a second initial report request.

Detailed record: `docs/project_notes/phase10b_saved_views_implementation.md`.

Source contracts:

- `vetedge/tests/test_report_saved_views_contract.py`;
- `vetedge/tests/test_report_center_saved_views_ui_contract.py`.

## Phase 10C — Previous-Period Comparison

Status: **shared presentation + first aggregate backend implemented; Report Center UI adoption pending**.

### Subscription rule

Comparison is an **Advanced Reporting feature**, even when the underlying operational report is Standard. Report shell capabilities therefore expose a separate `advanced_features_entitled` result backed by the existing `advanced_reports` feature entitlement.

This distinction allows, for example:

- Consultation Register: Standard report and normally viewable;
- Previous-period Consultation comparison: available only when `advanced_reports` is entitled.

### Shared EdgeSuite presentation

EdgeSuite UI PR #19 now provides `EdgeReportComparisonPanel`:

- product-neutral current/comparison metric presentation;
- period labels;
- delta and percentage-delta presentation;
- optional positive/negative/warning delta tones;
- responsive 4/2/1-column layout;
- no Frappe API/database/product/permission logic.

### First VetEdge reference — Consultation Register

`vetedge.services.report_comparison.get_report_comparison()` initially supports Consultation Register only.

Comparison model:

- current selected period vs immediately preceding equal-length period;
- if no date range is supplied, current period defaults to the latest 30 days;
- server calculates metrics using the existing Consultation aggregate/query helpers;
- no current-period detail rows are materialized for comparison;
- no previous-period detail rows are materialized;
- interactive report pagination remains independent.

Initial metrics:

- Total Consultations;
- Completed;
- Completion Rate;
- Average Planned Value;
- Follow-up Required;
- Cancelled.

Metadata explicitly reports `aggregate_only=true` and `detail_rows_materialized=false`.

Vaccination Due Soon/Overdue was deliberately not used as the first comparison reference because those are present-state due snapshots; mechanically comparing them to a previous date period would be semantically misleading.

Source contract: `vetedge/tests/test_report_comparison_contract.py`.

### Phase 10C UI next

Report Center should expose Compare Previous Period only when:

- the current report has a supported comparison provider; and
- `advanced_features_entitled` is true.

Toggling comparison must load only the aggregate comparison endpoint. It must not fetch a second detail-row dataset or disturb report pagination. If report filters change while comparison is visible, refresh the aggregate comparison once using the new filters.

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

Each exception requires an explicit business definition, role/Branch visibility, bounded query, clickable source record and an explanation of why the record is exceptional.

## Phase 10F — Scheduled Reports

Schedule only after saved-view/filter state is stable.

Requirements include execution-time permission revalidation, recipient governance, Branch/company/tenant revalidation, attachment-size/row limits, retry/failure audit and automatic disabling when report/view access is lost.

## Performance rules

- server filtering/query-level pagination for detail datasets;
- bounded permission-aware remote Link search;
- no large hidden master preloads;
- comparison/grouping KPIs use aggregates rather than duplicated detail datasets;
- full export remains separate from interactive pagination;
- no polling;
- column-only presentation changes do not reload providers.

## Things not to change

- Do not mutate submitted ERPNext accounting documents.
- Do not move report-role/Branch/tenant enforcement into JavaScript.
- Do not introduce browser-side full-dataset materialization for grouping/comparison.
- Do not use private user settings as the future team/public sharing model.
- Do not build VetEdge-only reusable report presentation components where EdgeSuite owns the generic capability.
- Do not claim Phase 10 accepted until EdgeSuite UI PR #19 and VetEdge consumer automated/browser/network QA pass.
