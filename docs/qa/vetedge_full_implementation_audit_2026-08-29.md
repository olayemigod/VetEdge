# VetEdge Full Implementation QA Consolidation Audit — 2026-08-29

## Purpose

This document records the source lines and file-level evidence used to establish the consolidated VetEdge browser-QA candidate. It exists because the post-PR36 implementation branches have rewritten/divergent Git ancestry, so ahead/behind commit counts alone are not a reliable indicator of feature presence.

## Authoritative QA Branch

- Branch: `qa/vetedge-full-implementation-2026-08-29`
- Starting reconciled candidate: `84de39058f4f2b69370f4bc269260f7ff985df64`
- Main accepted baseline: `e08a9278c2c975a5e5d4221481a760a90e21a8ea` (merged PR #36)
- QA campaign: `VE-QA-2026-08-28-001`

This branch is a QA integration candidate. It is not merge-ready merely because implementation is consolidated. Installed-site migration, build, automated validation and browser QA remain release gates.

## Source Lines Audited

### PR #47 — Post-PR36 reporting and operations

- Branch: `agent/vetedge-post-pr36-reporting-and-operations`
- Audited head: `6e273352fdaacd2bbf478aa4caa5ce975a481a31`
- Includes reporting foundation, export/print/PDF, Hospitalisation Operations, Training Centre migration, saved views, previous-period comparison, grouping/subtotals, exception reporting, scheduled reports and related operational/configuration work.

### PR #50 — VCN / NADIS regulatory reporting

- Branch: `agent/vetedge-vcn-nadis-reports`
- Audited head: `fa11960760fd85def526f5d0582a3bc15ff5b1a7`
- Includes official-template-backed NADIS vaccination/outbreak reporting, regulatory mappings, report-run persistence, frozen attachment sending and regulatory workbench.
- The PR #50 branch is **not** safe to merge wholesale into the consolidated QA candidate because it was cut from an earlier PR #47 checkpoint and its branch history also removes/reverts unrelated post-PR36 workspaces. Regulatory work is therefore verified by file-level comparison against the reconciled candidate rather than by whole-branch merge.

### PR #51 — Hospitalisation Episode workspace

- Branch: `feature/vetedge-hospitalisation-episode`
- Audited head: `ffd054023297f29074e6945837a267b17ec150d5`
- Includes the EdgeSuite Hospitalisation Episode workspace and authoritative service facade.

### Reconciliation / Training Centre

- Branch: `reconcile/vetedge-post-pr36-programme`
- Audited head: `324114962b7f2225f169163173758f1298219035`
- Includes accepted Training Centre shell work and other post-PR36 reconciliation fixes.

## File-Level Verification Samples

The following important files on the reconciled QA candidate were compared by Git blob SHA to their source lines:

| Capability | File | Source | SHA result |
| --- | --- | --- | --- |
| Previous-period comparison | `vetedge/services/report_comparison.py` | PR #47 | Identical: `9097382442b924cb948199765f453c01881b5578` |
| Grouping/subtotals | `vetedge/services/report_grouping.py` | PR #47 | Identical: `03b791087f76bf9f2d87bb5cdc531a1bcf9c9a65` |
| Named saved views | `vetedge/services/report_saved_views.py` | PR #47 | Identical: `3e3156327b85effe69459d9ccec14f685977bffb` |
| Scheduled reports | `vetedge/services/report_scheduling.py` | PR #47 | Identical: `7dca2d37388f2d055c57318687831fa8efc303f8` |
| Report export | `vetedge/services/report_export.py` | PR #47 | Identical: `817badfaea866db439ee922d7dbbf6b8f842cad2` |
| Print/PDF model | `vetedge/services/report_print.py` | PR #47 | Identical: `64990c8e7c50cd1fca99eb9cbff67a72fdaa0ee1` |
| NADIS vaccination export | `vetedge/services/nadis_vaccination_export.py` | PR #50 | Identical: `c1779a4c86c34ef4c7cd45f38eb1fc773ccdcf67` |
| Regulatory report runs | `vetedge/services/regulatory_report_runs.py` | PR #50 | Identical: `2e6595b7edde6d3224e4cf2d82cfc038b50f6438` |
| Hospitalisation Episode service | `vetedge/services/hospitalisation_episode.py` | PR #51 | Identical: `18159a92b72967da0a29d1d43e2f0f7eba601d67` |
| Hospitalisation Episode UI | `vetedge/public/js/vetedge_hospitalisation_episode/VetEdgeHospitalisationEpisode.vue` | PR #51 | Identical: `3a5d9b8e796386da198dbbfc931342bac382f6bd` |
| Training Centre UI | `vetedge/public/js/vetedge_training_centre/VetEdgeTrainingCentre.vue` | Reconciliation | Identical: `786801bf216d31686535f47bc3e91418dd444e15` |

## Reconciled Files That Intentionally Differ

A differing blob SHA is not automatically a missing feature. Where the reconciliation line contains a later safety/integration change, the reconciled version is authoritative.

Example:

- `vetedge/services/report_exceptions.py`
  - PR #47 blob: `d5b27d50d903b7e491344e118ce42192df0b2f42`
  - reconciled QA blob: `0cde5a8ad28641e6585b04ae04693e0ee5fb877a`
  - reason retained: the reconciled version suppresses pending-stock exceptions when Hospitalisation Dispensary Flow is disabled, preventing users from being shown stock actions they cannot and should not execute.

Similarly, regulatory/reporting catalogue and outbreak-export files may intentionally differ where the reconciliation branch combines PR #47 operational work, PR #50 regulatory work and later safety fixes. Such files must be assessed by behavior and tests, not replaced simply to match an older source branch SHA.

## Safety Rules for Further Consolidation

1. Do not merge PR #47, PR #50 or PR #51 wholesale into this branch solely to satisfy Git ancestry.
2. Do not delete later reconciliation fixes merely because source PR blobs differ.
3. Preserve ERPNext accounting and stock truth; never mutate submitted accounting documents.
4. Preserve branch/company/permission checks and fail-closed behavior.
5. Add only genuine missing implementation discovered through file-level or runtime validation.
6. Keep source PRs intact; integration changes belong on this QA branch until QA acceptance determines the final merge path.

## Required Validation Before Release

- clean `bench --site <site> migrate`
- `bench build --app vetedge`
- focused and full VetEdge automated tests appropriate to the candidate
- browser QA through ProcessEdge QA Control Centre
- permission/branch/company isolation
- accounting/stock/payment-gate safety
- export/PDF/XLSX file opening
- VCN/NADIS template fidelity and saved-report workflow
- Hospitalisation Operations/Episode workflow
- Training Centre regression
- responsive, dark/light, performance and data-usage checks

## Local QA Pull Target

Once this branch head has passed exact-head source/CI checks, local QA should use only:

`qa/vetedge-full-implementation-2026-08-29`

Do not mix PR #47, #50 or #51 into the local checkout independently during the same QA campaign.
