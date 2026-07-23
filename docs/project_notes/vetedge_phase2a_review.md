# VetEdge EdgeSuite UI Phase 2A Review

## Pull Request

- Draft PR: `#18 feat(vetedge): migrate clinical masters to full EdgeSuite UI`
- Implementation branch: `agent/vetedge-full-edgeui-masters-phase2a`
- Temporary CI base: `main`
- Intended review dependency: Phase 1 PR #17

The PR temporarily targets `main` because the repository workflow runs pull-request CI only for a `main` base. After Phase 1 merges, the Phase 2A diff should reduce to the clinical-master work and related review corrections.

## Review Result Before CI

The second-pass implementation review checked:

- Scope separation from consultations, lab, vaccination, hospitalisation, grooming and boarding.
- No Sales Invoice, Payment Entry or Stock Entry mutation.
- Permission-aware list and document APIs.
- Platform access enforcement on writes.
- Optimistic locking.
- Active dependent-master filtering and server validation.
- Direct list and named-record routes.
- Collision-safe EdgeSuite UI bundle loading.
- Veterinary Home restoration.
- Label-only persistent navigation.
- Short, action-focused descriptions in the searchable menu.
- Removal of visible `DocType`, `Page` and `Report` subtitles.
- Unsaved-change warnings and reliable confirmation-dialog closure.
- Static, frontend and clean-site Frappe test inclusion in CI.

## Pending

- GitHub CI result.
- Manual desktop and mobile browser QA.
- Role-by-role QA for Administrator, VetEdge Administrator, Doctor, Front Desk, Nurse and Branch Manager.
- Final grouped acceptance when Mathew confirms readiness for QA.

This phase must remain draft until the pending checks are completed.
