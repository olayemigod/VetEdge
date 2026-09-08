# VetEdge post-PR36 reconciliation validation

Date: 2026-08-26

## Decision

**NOT READY**

The isolated migration is successful and idempotent, current-main clinical safeguards remain protected, recovered reporting/Hospitalisation/configuration suites pass, and one genuine CoreEdge adapter-boundary regression was fixed. Release readiness is blocked because the packaged official NADIS disease-outbreak template is corrupt/incomplete: runtime reconstruction cannot satisfy strict base64 decoding or the recorded authoritative SHA-256, so an outbreak workbook cannot be generated.

## Scope and immutable references

- Branch: `reconcile/vetedge-post-pr36-programme`
- Starting main: `e08a9278c2c975a5e5d4221481a760a90e21a8ea`
- Reconciliation before validation fixes: `c5d6787b9abfdb5b646e510539c40f75100e08b5`
- Reconciliation worktree: `/home/olayemigod/frappe-bench/worktrees/vetedge-post-pr36-reconcile`
- Pinned-main worktree: `/home/olayemigod/frappe-bench/worktrees/vetedge-main-e08a927`
- Shared source site `vetedge.local` was not migrated or mutated.

## Isolated QA sites and backups

- Reconciliation: `vetedge-reconcile.local`
- Starting-main baseline: `vetedge-main-baseline.local`
- Both were restored from the same `vetedge.local` database/public/private-file backup.
- Installed apps recorded: Frappe 16.27.0, ERPNext 16.28.0, VetEdge 0.0.1, Payments, CoreEdge, EdgeSuite UI.
- Relevant integration mode: standalone; tests/developer mode enabled only on the clones.
- Source backup: `/home/olayemigod/frappe-bench/qa_artifacts/vetedge_reconciliation_20260826/source_backup`
- Pre-migration backup: `/home/olayemigod/frappe-bench/qa_artifacts/vetedge_reconciliation_20260826/reconcile_pre_migration`
- Each backup contains database, site config, public files, and private files. No secrets are recorded here.

## Migration and smoke result

- Migration pass 1/pass 2: PASS/PASS (idempotent).
- Cache clear and production VetEdge asset build: PASS.
- Patch Log remained 786. `vetedge.patches.add_reporting_action_settings` already existed in the cloned DB; no new patch row ran.
- DocType, fixture, dashboard, customization, language, portal-menu, app, and after-migrate sync completed without schema errors.
- Regulatory DocTypes verified: Veterinary Disease Outbreak; Veterinary Outbreak Animal Group; Veterinary Outbreak Diagnosis Basis; Veterinary Outbreak Control Measure; Veterinary Outbreak Location; Veterinary Regulatory Report Run.
- Pages verified: Regulatory Reporting; Report Center; Hospitalisation Operations; Training Centre; Administration; Branch Access/User Access; Care Locations; Settings Center.
- Reporting fields verified: `enable_reporting_print`, `enable_reporting_export`.
- Reports verified: Consultation Register, Planned Treatment, VetEdge Scheduled Report Bridge.
- Retired `veterinary-hospitalisation-dashboard`: absent as required.

## Differential full-suite result

- Starting main: 1,324 tests; 15 failures + 4 errors = 19.
- Reconciliation at `c5d6787`: 1,336 tests; 27 failures + 4 errors = 31.
- Reconciliation final: 1,336 tests; 26 failures + 4 errors = 30.
- Original 31 classifications: A = 1, B = 4, C = 26, D = 0, E = 0.
- JUnit: `/home/olayemigod/frappe-bench/qa_artifacts/vetedge_reconciliation_20260826/test_results`.

### Differential failure matrix

| # | Test | Main | Reconciliation | Class | Action/evidence |
|---:|---|---|---|---|---|
| 1 | Notification item fallback route | FAIL | FAIL | C | Legacy `/app` expectation; current Frappe v16 route is `/desk`. |
| 2 | Vaccination batch expiry derivation | ERROR | ERROR | C | Test stub lacks current `frappe.db.exists`. |
| 3 | Vaccination default validity date | FAIL | FAIL | C | Stale date-only serialization expectation. |
| 4 | Vaccination default next-due date | FAIL | FAIL | C | Same stale serialization contract. |
| 5 | Vaccination next-due appointment event | ERROR | ERROR | C | Test patches retired `emit_appointment_event`. |
| 6 | Registration: unrelated old invoice | FAIL | FAIL | B | Equivalent main behavior; payment logic unchanged. |
| 7 | Registration: billing-group source status | FAIL | FAIL | B | Equivalent main behavior; no gate weakening. |
| 8 | Launcher route identity | FAIL | FAIL | C | Legacy `/app/vetedge` expectation. |
| 9 | Financial dashboard shell asset | FAIL | FAIL | C | Retired `dashboard_shell.js` source check; bundle host is current. |
| 10 | Training Centre API in page loader | PASS | FAIL | C | API moved intentionally into recovered EdgeSuite Vue bundle; replacement contracts pass. |
| 11 | Hospitalisation Dashboard page | ERROR | ERROR | C | Dashboard deliberately retired. |
| 12 | Planned Treatment visibility helper | FAIL | FAIL | C | Superseded by accepted EdgeSuite report provider/route. |
| 13 | Hospitalisation Dashboard roles | ERROR | ERROR | C | Same deliberate retirement as #11. |
| 14 | Product-menu `visibleNavbar()` string | FAIL | FAIL | C | Superseded by shared EdgeSuite menu runtime. |
| 15 | Medical History dialog row strings | FAIL | FAIL | C | Stale UI source contract. |
| 16 | Medical History treatment-plan strings | FAIL | FAIL | C | Stale UI source contract. |
| 17 | Appointment final-status metadata/UI | FAIL | FAIL | C | Stale source contract; frozen appointment suites pass 16/16. |
| 18 | No direct CoreEdge imports in services | PASS | FAIL | A | Fixed: entitlement call moved behind `coreedge_adapter.py`; platform tests pass 8/8. |
| 19 | Executive optimized adapter marker (1) | PASS | FAIL | C | Old branch string superseded by aggregate-first adapters. |
| 20 | Executive optimized adapter marker (2) | PASS | FAIL | C | Duplicate collection of #19. |
| 21 | Stock Expiry cold metadata string | PASS | FAIL | C | Superseded by bounded server-side report shell. |
| 22 | Stock Expiry aggregate SQL string | PASS | FAIL | C | Superseded implementation detail; replacement contracts pass. |
| 23 | Report Insights private CoreEdge frontend import | FAIL | FAIL | B | Equivalent starting-main failure. |
| 24 | Reference loader component list | PASS | FAIL | C | Recovered shell uses current component contract. |
| 25 | Billing Core closed partial-paid session | FAIL | FAIL | B | Exact pre-existing 139/140 result. |
| 26 | Phase-5 clinical-route source contract | FAIL | FAIL | B | Equivalent starting-main failure. |
| 27 | Executive fluid-layout strings | PASS | FAIL | C | Superseded by shared EdgeSuite report shell. |
| 28 | Executive KPI-grid strings | PASS | FAIL | C | Same as #27. |
| 29 | Executive notification-shell strings | PASS | FAIL | C | Same as #27. |
| 30 | Stock Expiry old component list | PASS | FAIL | C | `EdgePageLayout` replaced by `EdgeAppShell` + `EdgeReportShell`. |
| 31 | Stock Expiry compact-shell strings | PASS | FAIL | C | Same superseded contract as #30. |

No main behavior was changed to make B/C cases green.

## Genuine reconciliation fixes

1. CoreEdge boundary: added `check_vetedge_feature_entitlement(...)` to the canonical adapter; the reporting service now uses it; the recovered test enforces no direct service import. Behavior and fail-open/fail-closed decisions are preserved.
2. NADIS global readiness: removed the redundant Nigeria fallback. Validation already requires Country, so valid exports are unchanged and missing Country remains fail-closed.

## Automated validation

| Suite/check | Result |
|---|---|
| Recovered reporting | 125/125 PASS |
| Hospitalisation Operations/integrity | 11/11 PASS |
| VCN/NADIS contracts | 47/47 PASS |
| Config/navigation/training/role security | 26/26 PASS; 58 subtests |
| Smart Appointment + Resource Center | 16/16 PASS |
| Payment/vaccination/lab/accounting/clinical safeguards | 52/52 PASS |
| Focused changed contracts | 18/18 PASS |
| Platform boundary | 8/8 PASS |
| Billing Core site-aware | 139/140; one B failure |
| Full reconciliation final | 1,336; 26 failures + 4 errors |
| Starting-main full | 1,324; 15 failures + 4 errors |
| Old-Frappe workspace/Stock Expiry category | 21; 2 C failures |
| Production asset build | PASS |

The broader 89-test critical source selection produced 82 passes and seven failures. Five fail identically on main; two are superseded Planned Treatment provider/sidebar strings. The narrower frozen behavior suites above are green.

## NADIS workbook validation

Vaccination:

- Generated from verified official template: PASS.
- File: `/home/olayemigod/frappe-bench/qa_artifacts/vetedge_reconciliation_20260826/workbooks/qa_nadis_vaccination.xlsx`.
- Source SHA-256 verified: `458e7af8b47c491f5245f5fc6cc8bbe754bbc23ab63829e88bb2083b813c05ba`.
- Reopen: PASS; `Vaccinations` sheet, 851 x 88, QA row at row 5.
- ZIP integrity PASS; openpyxl warnings 0.
- Evidence: `vaccination_workbook_verification.json` beside the workbook.

Disease outbreak:

- Generation: BLOCKED, correctly failing closed.
- Concatenated base64 is 43,735 bytes (not divisible by four).
- Adding one padding byte produces SHA-256 `bcd90428923a289aeb46d8a52565c2ddf07ea734f71afb2df5dcc32079e4335f`, not authoritative `8ea90b4b5c30a66029186905e9aab846bf897f40121d5ec7d7d69acf2964db94`.
- No exact alternative exists in the bench, attachments, Git objects, or current refs.
- Do not guess/rebuild/substitute it. Supply the exact official XLSX and rerun `scripts/package_nadis_templates.py`.

The 47 contracts cover fail-closed mappings, no consultation-to-outbreak inference, branch/role restrictions, private generated files, frozen-file send behavior, and Generated/Sent/Accepted/Rejected/Superseded states. Installed-site report-run/browser lifecycle is pending because the outbreak file cannot generate.

## Browser QA status

**BLOCKED**

The in-app browser refused `http://vetedge-reconcile.local:8000/desk/vetedge` because its admin-enforced security policy could not be verified. This is an environment condition, not a VetEdge failure. No bypass was attempted.

When the template and browser access are restored, run in order:

1. Smart Appointment APPT-ROW/APPT-01 through APPT-07, duplicate prevention, practitioner filters, boarding split, Front Desk parity, Resource Center actions.
2. Vaccination create/open, correct billing evidence, mappings, next-due behavior.
3. Lab create/open and consultation billing evidence.
4. Payment gates: Administrator non-bypass, Draft rejection, submitted-unpaid configuration, immutable submitted invoices.
5. Hospitalisation Operations: branch/practitioner scope, discharge/payment gates, idempotent stock, reports, no retired Dashboard.
6. Administration/configuration: Administration, Branch Access/User Access, Care Locations, Settings aliases, cross-branch denial.
7. Training Centre list/module navigation and one EdgeSuite shell.
8. Report Center smart Links, bounded pagination, branch fail-closed, export scope.
9. Standard reports including Planned Treatment.
10. Advanced Saved Views; ensure permissions cannot be bypassed.
11. Previous Period Comparison entitlement and identical scope.
12. Grouping/Subtotals entitlement and complete filtered dataset.
13. Exceptions/highlighting safety.
14. Scheduled-report bridge/UI and recipient permissions.
15. Regulatory workbench Company/Branch/role isolation and explicit outbreak truth.
16. NADIS generation/history: reopen both in Excel/LibreOffice without repair; private Generate & Save; frozen single Send; Accepted/Rejected/Superseded.

Do not begin advanced reporting browser QA until steps 1-4 pass.

## Assumptions, risks, next step

- Equivalent data state comes from one source backup; baseline intentionally did not apply reconciliation schema.
- C classification requires direct repository diff plus replacement-contract evidence.
- The official outbreak workbook cannot be synthesized from metadata.
- Release blocker: corrupt/incomplete outbreak package.
- Browser behavior remains unexecuted due enforced local-URL denial.
- Full suite remains non-green from four B and 26 C cases; none are unexplained.
- QA sites/artifacts remain; shared `vetedge.local` is untouched.

Next step: provide the official outbreak XLSX matching SHA-256 `8ea90b4b5c30a66029186905e9aab846bf897f40121d5ec7d7d69acf2964db94`, repackage it, rerun generation/reopen, then execute browser QA.
