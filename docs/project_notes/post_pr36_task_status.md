# Post-PR #36 Task Status

| Phase | Status | Immediate outcome |
|---|---|---|
| EdgeSuite Reporting Standard V1 | In progress — reference adoption implemented | Shared EdgeSuite runtime remains in PR #19. Stock Expiry is now the VetEdge `EdgeReportShell` reference consumer with server pagination and bounded remote filters. Recognized VetEdge dashboards are adapted to `EdgeDashboardShell` with compatibility fallback. |
| Export / Print / PDF Foundation | Implementation complete — QA pending | Report and dashboard shells expose opt-in Print/Export only when server-derived capabilities allow them. Stock Expiry has dedicated permission-rechecked export/print endpoints; dashboard export remains dashboard-aware rather than flattening actions through a report permission scope. |
| Remaining report migration/optimization | In progress | Planned Treatment, Consultation Register, Laboratory/Lab Order, Vaccination and Owner Register have optimized providers. Further reports should be classified by actual volume/value before adding dedicated providers. |
| VCN / NADIS reporting | New | Regulatory reports and export presets on shared reporting foundation. |
| Hospitalisation EdgeSuite completion | New | Complete only genuine operational gaps after implementation audit. |
| Training Centre / remaining legacy surfaces | New | Migrate verified remaining native resources. |
| Advanced reporting/intelligence | New | Saved views, drill-through, comparison, grouping, scheduled/exception reporting. |

PR #36 clinical and final consolidation QA remains ongoing and is not duplicated on this continuation branch.

## Reference consumer implementation

### Stock Expiry Monitor

- Uses the canonical `EdgeReportShell` for header, filters, insight cards, row table, result count, loading/error/empty states and pagination.
- Keeps query-level server pagination; changing page or page size does not materialize the complete dataset in the browser.
- Warehouse and Item Group no longer preload up to 500 records. They use the existing bounded permission-aware Stock Expiry search endpoint with a 20-row search window.
- Item uses Frappe permission-aware Link search with a 20-row search window.
- Print/Export buttons are driven by `Stock Expiry Status` reporting capabilities and revalidated server-side on every action.
- Dedicated Stock Expiry export/print service uses the established full Stock Expiry dataset only for the explicit server-side document-generation workflow; the browser does not iterate report pages to create a full export.
- Submitted ERPNext documents and stock/accounting records are not mutated by the reporting actions.

### VetEdge dashboards

- Recognized VetEdge dashboard routes use an `EdgeDashboardShell` compatibility adapter while retaining the existing product dashboard body/filter implementations.
- Dashboard Print/Export is opt-in, capability-driven and reauthorized server-side with dashboard scope.
- Dashboard export uses `artifact_kind = dashboard` semantics and a dedicated dashboard document model.
- If the shared dashboard shell is unavailable, the compatibility layer preserves the previous EdgePageLayout rendering path.

## Current validation state

- VetEdge PR #47 remains Draft and mergeable. GitHub has not returned a pull-request workflow run for the current stacked VetEdge head, so source-contract checks are implementation guards only and must not be reported as CI acceptance.
- VetEdge source-contract coverage now guards Stock Expiry `EdgeReportShell` adoption, bounded filter search, server pagination, dedicated read-only Stock Expiry actions, dashboard `EdgeDashboardShell` adoption, server capability gating and no-mutation/no-permission-bypass rules.
- EdgeSuite UI PR #19 frontend validation and theme/navigation browser smoke passed on the previous checkpoint. Its Fast Validation was blocked only by Ruff formatting in `test_shell_permission_contract.py`; that lint defect has been corrected and a new CI run is in progress.
- Browser QA remains required for Stock Expiry filter selection/clear, pagination/page-size changes, row navigation, summary semantics, branch-context refresh, and notification coexistence.
- Browser/file QA remains required for Stock Expiry and representative dashboards across XLSX, CSV, PDF and Print, including Current Page vs All Filtered, selected columns, raw/presentation mode, chart inclusion and file integrity.
- Representative dashboard QA must include Executive, Financial and Branch Performance so direct/legacy rendering paths are confirmed to pass through the shared dashboard adapter without duplicated shell chrome.
- No migrations were added by the Stock Expiry/dashboard shell adoption itself. The previously registered idempotent reporting-action settings patch remains the only relevant migration in this programme slice.
