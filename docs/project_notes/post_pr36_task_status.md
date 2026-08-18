# Post-PR #36 Task Status

| Phase | Status | Immediate outcome |
|---|---|---|
| EdgeSuite Reporting Standard V1 | In progress — reference adoption implemented | Shared EdgeSuite runtime remains in PR #19. Stock Expiry and the generic VetEdge Report Center now use the canonical `EdgeReportShell`. Recognized VetEdge dashboards are adapted to `EdgeDashboardShell` with compatibility fallback. |
| Standard / Advanced report packaging | Implemented — browser QA pending | Report/dashboard tiering is centralized in `reporting_catalog.py`. Advanced access uses CoreEdge Feature entitlement `advanced_reports` in platform deployments and the existing Veterinary Settings flag for standalone sites. Stock Expiry, Report Center and shared dashboards now pass server tier/entitlement metadata into the EdgeSuite shell for visible Standard / Advanced / Advanced · Locked state. |
| Export / Print / PDF Foundation | Implementation complete — QA pending | Report and dashboard shells expose opt-in Print/Export only when server-derived capabilities allow them. Stock Expiry has dedicated permission-rechecked export/print endpoints; Current Page export uses the paginated provider and All Filtered synchronous export has a 20,000-row safety ceiling. Report Center now uses the shell-owned Export/Print controls instead of permanently rendering manual actions. |
| Dashboard/report performance hardening | In progress | Consultation dashboard KPIs/charts now use database aggregates; Lab and Vaccination dashboard paths reuse aggregate/bounded providers. Shared branch-scoped reporting now fails closed when a branch-scoped user has no assigned Veterinary Branch. Financial aggregation remains on the canonical financial dataset until a dedicated branch/service-safe refactor is justified. |
| Remaining report migration/optimization | In progress | Planned Treatment, Consultation Register, Laboratory/Lab Order, Vaccination and Owner Register have optimized providers. Further reports should be classified by actual volume/value before adding dedicated providers. |
| VCN / NADIS reporting | New | Regulatory reports and export presets on shared reporting foundation. |
| Hospitalisation EdgeSuite completion | New | Complete only genuine operational gaps after implementation audit. |
| Training Centre / remaining legacy surfaces | New | Migrate verified remaining native resources. |
| Advanced reporting/intelligence | New | Saved views, drill-through, comparison, grouping, scheduled/exception reporting. |

PR #36 clinical and final consolidation QA remains ongoing and is not duplicated on this continuation branch.

## Stacked branch state

- PR #47 has been synchronized with the latest PR #36 head `fbb07d8833c1155f5646557ce2743f3eb72884ed` through merge commit `b84cc47c47b33c6f86e33d5481daa32243550c5e`.
- The continuation branch is based directly on that PR #36 head and GitHub currently reports PR #47 as Draft and mergeable.
- The only true overlapping file during the sync was `vetedge/patches.txt`. The resolved file preserves both `add_vaccination_consultation_billing_edit_setting` from PR #36 and `add_reporting_action_settings` from PR #47.
- Temporary sync PR #49 is closed/merged into the continuation history. No force update was used.

## Reference consumer implementation

### Stock Expiry Monitor

- Uses the canonical `EdgeReportShell` for header, filters, insight cards, row table, result count, loading/error/empty states and pagination.
- Keeps query-level server pagination; changing page or page size does not materialize the complete dataset in the browser.
- Warehouse and Item Group use bounded permission-aware search with a 20-row window; Warehouse discovery and validation are constrained by normalized Branch context.
- Item uses Frappe permission-aware Link search with a 20-row search window.
- `Stock Expiry Status` is classified as Advanced and its data/search/Print/Export endpoints recheck entitlement server-side.
- The shell receives `report_tier` and `subscription_entitled` from the server capability context and therefore displays Advanced / Advanced · Locked consistently with actual entitlement.
- Current Page Print/Export uses the interactive paginated provider rather than materializing the complete filtered dataset.
- All Filtered export is a separate server workflow and refuses synchronous materialization above 20,000 matching rows until a queued/chunked large-export path is introduced.
- Submitted ERPNext documents and stock/accounting records are not mutated by the reporting actions.

### VetEdge Report Center

- Migrated from manual `EdgePageLayout` + manual table/pagination/action composition to canonical `EdgeReportShell`.
- Provider loading remains product-owned and resolves optimized providers first with Query Report fallback.
- Summary cards, chart slot, result table, result count, loading/error/empty states and pagination are now shell-owned.
- Print/Export visibility is derived from `get_shell_capabilities`; locked Advanced reports stop before provider loading and show plan-access state without exposing report data.
- Standard / Advanced / Advanced · Locked tier display is driven by the same server capability response.
- Existing URL filter retention, dashboard return navigation, provider badge and chart rendering are preserved.

### VetEdge dashboards

- Recognized VetEdge dashboard routes use an `EdgeDashboardShell` compatibility adapter while retaining the existing product dashboard body/filter implementations.
- Dashboard Print/Export is opt-in, capability-driven and reauthorized server-side with dashboard scope.
- Executive, Financial, Inventory/Dispensary, Branch Performance and Practitioner Performance are classified as Advanced; Clinical, Lab, Vaccination, Hospitalisation, Boarding and Grooming are Standard.
- The shared adapter passes `report_tier` and `subscription_entitled` into `EdgeDashboardShell`, so the same server-authoritative tier state is visible across dashboard routes.
- Consultation dashboard metrics use database aggregate queries instead of downloading consultation detail rows. Lab and Vaccination dashboard metrics reuse their aggregate providers.
- Dashboard export uses `artifact_kind = dashboard` semantics and a dedicated dashboard document model.
- If the shared dashboard shell is unavailable, the compatibility layer preserves the previous EdgePageLayout rendering path.

## Subscription architecture

- CoreEdge already models plan features as `CoreEdge Entitlement` records and supports `entitlement_type = Feature`; no new subscription DocType is required for report tiers.
- Canonical Advanced feature key: `advanced_reports`.
- Standard reports are included after normal product/role/scope permission checks.
- Advanced reports require normal permission checks plus the Advanced entitlement.
- Shell capability lookup returns locked metadata (`can_view = false`) without exposing report data, enabling locked/upgrade presentation.
- Actual data, Print and Export endpoints fail closed when Advanced entitlement is absent.

## Branch/report isolation hardening

- Branch-scoped reporting now fails closed if the user has a branch-scoped VetEdge role but no assigned Veterinary Branch. The shared `report_visibility.py` raises `PermissionError` instead of returning unfiltered data.
- Existing selected-branch validation remains unchanged: an explicitly requested branch outside the user's assigned set is denied.
- One assigned branch remains the automatic default; multiple assigned branches continue to prefer a valid user default and otherwise use the deterministic first assigned branch.
- Users with explicit global branch access remain outside the branch-scoped fail-closed gate.
- Stock Expiry adds an additional warehouse-scope fail-closed layer so an unmapped Branch or Branch/Warehouse mismatch cannot broaden inventory results.

## Current validation state

- VetEdge PR #47 remains Draft and mergeable. No pull-request-triggered GitHub Actions workflow or commit status has been returned yet for the current continuation head; source-contract checks must not be reported as CI acceptance.
- EdgeSuite UI PR #19 CI run #370 completed successfully on the reporting/tier-shell checkpoint.
- VetEdge source-contract coverage guards Standard/Advanced classification, CoreEdge Feature-entitlement use, standalone fallback, shared branch fail-closed behavior, Stock Expiry branch-safe search/pagination/export limits, Report Center `EdgeReportShell` adoption, dashboard tier-aware `EdgeDashboardShell` adoption, dashboard aggregate paths, server capability gating and no-mutation/no-permission-bypass rules.
- Browser QA remains required for Stock Expiry filter selection/clear, pagination/page-size changes, row navigation, summary semantics, branch-context refresh, locked Advanced state and notification coexistence.
- Report Center browser QA must verify provider fallback/optimized providers, filters, summary cards, charts, result pagination, Standard/Advanced/Locked badges, Print/Export visibility and Back-to-Dashboard navigation.
- Browser/file QA remains required for Stock Expiry, Report Center and representative dashboards across XLSX, CSV, PDF and Print, including Current Page vs All Filtered, selected columns, raw/presentation mode, chart inclusion and file integrity.
- Representative dashboard QA must include Executive, Financial and Branch Performance so direct/legacy rendering paths are confirmed to pass through the shared dashboard adapter without duplicated shell chrome.
- The reporting-action settings patch remains idempotent; the synchronized branch also preserves PR #36's vaccination consultation billing-edit settings patch.
