# VetEdge Phase 4A — Manual QA Round 1

## QA Date

24 July 2026

## Tester

Mathew Alao / ProcessEdge Solutions Limited

## Environment

- Site: `vetedge.local`
- VetEdge branch: `agent/vetedge-full-edgeui-clinical-workspace-phase4a`
- EdgeSuite UI branch: `agent/edgeui-document-foundation`

## Passed

- Veterinary Clinical Workspace route opens.
- Page resets to the top.
- Workspace title and subtitle render.
- New Consultation action renders and opens Patient and Visit.
- Branch, Practitioner, Status and Search filters render.

## Failed in Round 1

1. Summary-card icon names rendered as text instead of SVG icons.
2. Consultation rows loaded but displayed em dashes because the table expected `fieldname` while the product supplied `key`.
3. Row click could not be tested because displayed row data was unusable.
4. `/app/vetedge` returned `Page vetedge not found`.

## Root Causes

- `EdgeStatCard` treated its `icon` prop as literal fallback text.
- `EdgeDataTable` accepted only `fieldname`, while existing product consumers use both `key` and `fieldname` column contracts.
- The Veterinary Home Page JSON was not sufficient to guarantee an existing Page record on an already-running site.
- The first VetEdge-local compatibility wrapper was ineffective at runtime and belonged in the shared EdgeSuite UI layer.

## Corrections

### EdgeSuite UI

- Added shared stat-icon normalization and SVG rendering.
- Added shared `key` to `fieldname` table-column normalization.
- Preserved row-click, selection and action events through the compatibility wrapper.
- Preserved explicit component-family registry boundaries.
- Added frontend assertions for icon aliases and table-column normalization.

### VetEdge

- Removed the ineffective product-local display wrappers.
- Added an idempotent post-migration patch to create or repair the stable `vetedge` Desk Page.
- Added a live Frappe test requiring the Page record to exist after migration.
- Tightened static contracts so the failed local wrapper cannot return unnoticed.

## Round 2 Browser Retest

### Passed

- Summary cards render graphical icons instead of icon-name text.
- Consultation rows display actual values.
- Status and Payment render as badges where applicable.
- Clicking a populated row opens the selected consultation.
- New Consultation still opens the Patient and Visit screen.

### Pending Explicit Confirmation

- `/app/vetedge` opens Veterinary Home and redirects to the Executive Dashboard without `Page vetedge not found`.

## Status

Clinical Workspace Stage 0 checks passed after correction. Veterinary Home route confirmation remains pending before Stage 1 workflow QA begins.
