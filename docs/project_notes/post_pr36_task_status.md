# Post-PR #36 Task Status

| Phase | Status | Immediate outcome |
|---|---|---|
| EdgeSuite Reporting Standard V1 | In progress — reference adoption implemented | Shared EdgeSuite runtime remains in PR #19. Stock Expiry is the VetEdge `EdgeReportShell` reference consumer with query-level server pagination and bounded remote filters. Recognized VetEdge dashboards are adapted to `EdgeDashboardShell` with compatibility fallback. |
| Standard / Advanced report packaging | Implemented server-side — UI badge wiring pending | Report/dashboard tiering is centralized in `reporting_catalog.py`. Advanced access uses CoreEdge Feature entitlement `advanced_reports` in platform deployments and the existing Veterinary Settings flag for standalone sites. Data, Print and Export are server-enforced. VetEdge consumers still need to pass the returned tier metadata into the shared shell badge props for visible Standard / Advanced labels. |
| Export / Print / PDF Foundation | Implementation complete — QA pending | Report and dashboard shells expose opt-in Print/Export only when server-derived capabilities allow them. Stock Expiry has dedicated permission-rechecked export/print endpoints; Current Page export uses the paginated provider and All Filtered synchronous export has a 20,000-row safety ceiling. |
| Dashboard/report performance hardening | In progress | Consultation dashboard KPIs/charts now use database aggregates; Lab and Vaccination dashboard paths reuse aggregate/bounded providers. Financial aggregation remains on the canonical financial dataset until a dedicated branch/service-safe refactor is justified. |
| Remaining report migration/optimization | In progress | Planned Treatment, Consultation Register, Laboratory/Lab Order, Vaccination and Owner Register have optimized providers. Further reports should be classified by actual volume/value before adding dedicated providers. |
| VCN / NADIS reporting | New | Regulatory reports and export presets on shared reporting foundation. |
| Hospitalisation EdgeSuite completion | New | Complete only genuine operational gaps after implementation audit. |
| Training Centre / remaining legacy surfaces | New | Migrate verified remaining native resources. |
| Advanced reporting/intelligence | New | Saved views, drill-through, comparison, grouping, scheduled/exception reporting. |

PR #36 clinical and final consolidation QA remains ongoing and is not duplicated on this continuation branch.

## Stacked branch state

- PR #47 has been synchronized with the latest PR #36 head `fbb07d8833c1155f5646557ce2743f3eb72884ed` through merge commit `b84cc47c47b33c6f86e33d5481daa32243550c5e`.
- The continuation branch is now 125 commits ahead and 0 commits behind that PR #36 head; GitHub reports PR #47 as Draft and mergeable.
- The only true overlapping file during the sync was `vetedge/patches.txt`. The resolved file preserves both `add_vaccination_consultation_billing_edit_setting` from PR #36 and `add_reporting_action_settings` from PR #47.
- Temporary sync PR #49 is closed/merged into the continuation history. No force update was used.

## Reference consumer implementation

### Stock Expiry Monitor

- Uses the canonical `EdgeReportShell` for header, filters, insight cards, row table, result count, loading/error/empty states and pagination.
- Keeps query-level server pagination; changing page or page size does not materialize the complete dataset in the browser.
- Warehouse and Item Group use bounded permission-aware search with a 20-row window; Warehouse discovery and validation are constrained by normalized Branch context.
- Item uses Frappe permission-aware Link search with a 20-row search window.
- `Stock Expiry Status` is currently classified as Advanced and its data/search/Print/Export endpoints recheck entitlement server-side.
- Current Page Print/Export uses the interactive paginated provider rather than materializing the complete filtered dataset.
- All Filtered export is a separate server workflow and refuses synchronous materialization above 20,000 matching rows until a queued/chunked large-export path is introduced.
- Submitted ERPNext documents and stock/accounting records are not mutated by the reporting actions.

### VetEdge dashboards

- Recognized VetEdge dashboard routes use an `EdgeDashboardShell` compatibility adapter while retaining the existing product dashboard body/filter implementations.
- Dashboard Print/Export is opt-in, capability-driven and reauthorized server-side with dashboard scope.
- Executive, Financial, Inventory/Dispensary, Branch Performance and Practitioner Performance are currently classified as Advanced; Clinical, Lab, Vaccination, Hospitalisation, Boarding and Grooming are Standard.
- Consultation dashboard metrics use database aggregate queries instead of downloading consultation detail rows. Lab and Vaccination dashboard metrics reuse their aggregate providers.
- Dashboard export uses `artifact_kind = dashboard` semantics and a dedicated dashboard document model.
- If the shared dashboard shell is unavailable, the compatibility layer preserves the previous EdgePageLayout rendering path.

## Subscription architecture

- CoreEdge already models plan features as `CoreEdge Entitlement` records and supports `entitlement_type = Feature`; no new subscription DocType is required for report tiers.
- Canonical Advanced feature key: `advanced_reports`.
- Standard reports are included after normal product/role/scope permission checks.
- Advanced reports require normal permission checks plus the Advanced entitlement.
- Shell capability lookup returns locked metadata (`can_view = false`) without itself exposing report data, allowing a future upgrade/locked-state UI.
- Actual data, Print and Export endpoints fail closed when Advanced entitlement is absent.

## Current validation state

- VetEdge PR #47 remains Draft and mergeable after the PR #36 sync. No pull-request-triggered GitHub Actions workflow has been returned yet for merge head `b84cc47c47b33c6f86e33d5481daa32243550c5e`; source-contract checks must not be reported as CI acceptance.
- EdgeSuite UI PR #19 CI run #370 completed successfully on the reporting/tier-shell checkpoint.
- VetEdge source-contract coverage guards Standard/Advanced classification, CoreEdge Feature-entitlement use, standalone fallback, Stock Expiry branch-safe search/pagination/export limits, dashboard aggregate paths, server capability gating and no-mutation/no-permission-bypass rules.
- Visible tier badges are supported by EdgeSuite (`tier` + `subscriptionEntitled`) but are not yet passed by the current VetEdge Stock Expiry/dashboard consumers. This remains an explicit UI integration acceptance item, not a backend access gap.
- Browser QA remains required for Stock Expiry filter selection/clear, pagination/page-size changes, row navigation, summary semantics, branch-context refresh, locked Advanced state and notification coexistence.
- Browser/file QA remains required for Stock Expiry and representative dashboards across XLSX, CSV, PDF and Print, including Current Page vs All Filtered, selected columns, raw/presentation mode, chart inclusion and file integrity.
- Representative dashboard QA must include Executive, Financial and Branch Performance so direct/legacy rendering paths are confirmed to pass through the shared dashboard adapter without duplicated shell chrome.
- The reporting-action settings patch remains idempotent; the synchronized branch also preserves PR #36's vaccination consultation billing-edit settings patch.
