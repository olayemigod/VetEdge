# Post-PR #36 Task Status

| Phase | Status | Immediate outcome |
|---|---|---|
| EdgeSuite Reporting Standard V1 | In progress | Shared EdgeSuite runtime in PR #19; VetEdge Report Center is provider-aware; Stock Expiry registered as query-level paginated reference; Planned Treatment marked paged-response/optimization-pending |
| Export / Print / PDF Foundation | In progress | Shared Export Builder now supports XLSX/CSV/PDF options, raw/presentation modes, column selection and file-integrity validation; VetEdge Report Center uses it with a permission-aware server export service; legacy PDF download now validates PDF bytes before save |
| Remaining report migration/optimization | New | Classify and migrate reports using generic or optimized paginated providers; Planned Treatment query-level pagination is an identified optimization item |
| VCN / NADIS reporting | New | Regulatory reports and export presets on shared reporting foundation |
| Hospitalisation EdgeSuite completion | New | Complete only genuine operational gaps after implementation audit |
| Training Centre / remaining legacy surfaces | New | Migrate verified remaining native resources |
| Advanced reporting/intelligence | New | Saved views, drill-through, comparison, grouping, scheduled/exception reporting |

PR #36 clinical and final consolidation QA remains ongoing and is not duplicated on this continuation branch.

## Current validation state

- EdgeSuite UI PR #19 provider-runtime CI passed at the Phase 4 checkpoint; new Export Builder commits require the next CI checkpoint.
- VetEdge PR #47 source-contract tests cover provider selection, pagination classification, raw export, MIME/generator contract and verified download handling.
- Browser QA remains required for Query Report fallback, Stock Expiry provider mode, Planned Treatment provider mode, filters, summary cards, chart rendering, pagination, same-Desk return navigation, Export Builder options and generated XLSX/CSV/PDF files.
- Presentation chart inclusion and fully shared paginated Print/PDF parity are still incomplete and must not be reported as accepted yet.
