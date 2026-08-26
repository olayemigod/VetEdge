# VetEdge post-PR36 reconciliation log

Date: 2026-08-26
Branch: reconcile/vetedge-post-pr36-programme
Starting main SHA: e08a9278c2c975a5e5d4221481a760a90e21a8ea
PR47: 6e273352fdaacd2bbf478aa4caa5ce975a481a31
PR50: fa11960760fd85def526f5d0582a3bc15ff5b1a7
PR50 branch point: 92d6256c375afb3d757537718182dd7d864850dc

## Policy

Created directly from current origin/main. PR47 and PR50 were not merged or rebased wholesale. Precedence: current-main safety, then PR47 bounded completeness, then PR50 regulatory-only additions. The original dirty checkout was not modified.

## Recovered

PR47:
- Structured consultation, lab, vaccination, owner, patient, treatment-plan, and stock-expiry providers.
- Report Center filters, sorting, saved views, comparison, grouping, exceptions, export/print, capabilities, scheduling, and Scheduled Report bridge.
- Dashboard aggregates and Stock Expiry workbench.
- Hospitalisation Operations with server-side branch, practitioner, patient, and permission guards.
- EdgeSuite administration, branch access, care locations, role bundles, notifications, practitioner coverage, license, and training pages.

PR50 regulatory-only:
- VCN/NADIS workbench, Disease Outbreak, Regulatory Report Run, child tables, permissions, state, export, and installer navigation.
- Species, diagnosis, and vaccine NADIS mappings.
- Vaccination reason editor integration while preserving linked_appointment uniqueness and main clinical/payment guards.
- Official workbook hashes: vaccination 458e7af8b47c491f5245f5fc6cc8bbe754bbc23ab63829e88bb2083b813c05ba; outbreak 8ea90b4b5c30a66029186905e9aab846bf897f40121d5ec7d7d69acf2964db94.

Exact paths are listed in vetedge_post_pr36_reconciliation_inventory.txt.

## Not restored

- PR47 deletions/reversions of accepted clinical context, payment gates, appointment actions, boarding safety, lab billing/cancellation, medical-history integrity, and vaccination payment behavior.
- PR50 configuration/navigation rollbacks, wholesale hooks/sidebar/UI identity, practitioner regression, weaker role delegation, or wholesale vaccination schema.
- Retired Hospitalisation Dashboard.
- Provider-specific payments, accounting bypasses, or ERPNext/Marley core changes.

## Conflict decisions

- hooks.py: added only Hospitalisation and Disease Outbreak permission entries.
- Sidebar: retained PR47/current navigation, replaced retired dashboard with Operations, and kept regulatory insertion installer-managed.
- Vaccination: added vaccination_reason only; preserved linked_appointment uniqueness, permissions, search fields, and workflow metadata.
- Clinical editor/mutation security: extended config with NADIS while retaining Lab cancellation, consultation-link, and protected-field safeguards.
- Practitioner and role bundles: retained stronger current/PR47 guards; rejected PR50 regressions.
- NADIS assets: replaced truncated vaccination payload with the official checksum-matching workbook; used the verified multipart-capable loader.
- Reporting tests: aligned stale source-string expectations to the final PR47 EdgeReportShell/provider/scheduling architecture.

## Commits

- 5b12cee reporting
- 8e92175 Hospitalisation Operations
- f154086 EdgeSuite configuration/training
- ddfc8df VCN/NADIS regulatory delta

## Verification

- Reporting: 112 passed.
- Hospitalisation/report integration: 24 passed.
- Configuration/training/role security: all 26 pass.
- VCN/NADIS: 47 passed.
- Current-main safety subset: 79 passed.
- Site-aware Billing Core: 139/140; the one unchanged pre-existing payment-gate expectation failed.
- Full site-aware run: 1,308 tests with 25 failures and 4 errors, then 21 recovered-workspace/stock-expiry tests with 2 failures. Observed failures are unchanged legacy drift or deliberately retired contracts, including tests demanding the removed Hospitalisation Dashboard.
- Production asset build: passed and explicitly linked VetEdge assets from this worktree.
- git diff --check: passed.

Migration was not run: the safety reviewer rejected mutating shared site vetedge.local without explicit approval for that named site.

Browser QA was not run: the in-app browser could not verify its admin security policy for http://vetedge.local:8000 and denied access. No workaround was used.

## Assumptions and risks

- origin/main at e08a927 is the operational baseline.
- PR47 is authoritative only for reporting/operations/configuration; PR50 only for VCN/NADIS.
- Local official workbooks are authoritative because their SHA-256 values match expected hashes.
- New schema/navigation is not applied to vetedge.local until migration is explicitly approved.
- Visual QA remains blocked; automated navigation contracts and build output are the current UI evidence.
- Existing full-suite drift should be triaged separately against main, not expanded into this reconciliation.

## Recommended PR

Title: Reconcile post-PR36 reporting, operations, EdgeSuite, and VCN/NADIS work

Body:
- starts from current main at e08a927 without wholesale PR merges/rebases
- recovers bounded PR47 reporting, Hospitalisation Operations, configuration, and training
- recovers only PR50 VCN/NADIS regulatory work
- preserves current-main clinical, appointment, payment, permission, and accounting safeguards
- preserves vaccination appointment uniqueness and rejects navigation/role/practitioner regressions
- packages checksum-verified official NADIS workbooks
- includes four reviewable implementation commits and focused regression coverage
- production build passes; migration and browser QA remain blocked as documented
