# VHOME-01 — Role-Aware Veterinary Home

## Goal

Replace the `/desk/vetedge` redirect with a real Veterinary Home that acts as a role-aware operational action centre and compact mini dashboard.

Veterinary Home must answer four questions for the logged-in user:

1. What needs my attention?
2. What should I do next?
3. What is the current operational snapshot within my access scope?
4. Where can I go quickly to complete the work?

## Base and integration rule

This slice is based on the authoritative VetEdge QA branch `qa/vetedge-full-implementation-2026-08-29` at PR #57 head `75e392e9c6faa873fadfd8af3a86db5abf0d9ebe`.

Do not retarget this slice to `main` or merge divergent PR #47/#50/#51 histories into it. VHOME-01 is a stacked orchestration slice over the reconciled QA composition.

## Implemented scope

- `/desk/vetedge` mounts a dedicated EdgeSuite Veterinary Home instead of redirecting to Resource Center.
- Server-authoritative `vetedge.services.home.get_home_payload`.
- Internal-staff-only access.
- Role/persona detection for:
  - Administrator
  - Branch Manager
  - Veterinary Doctor
  - Front Desk
  - Accounts / Cashier
  - Laboratory
  - Veterinary Nurse
  - Dispensary
  - Grooming
- Multi-role users receive a primary persona plus additional authorised action groups.
- Current branch context is validated with existing VetEdge access helpers.
- Metrics use permission-aware `frappe.get_list` queries and explicit branch filters where the source DocType exposes a recognised branch field.
- Attention cards are derived from access-scoped operational counts.
- Quick actions are filtered by DocType existence and current Frappe permissions.
- Existing EdgeSuite workspaces are reused for drill-through.
- Warm page reuse refreshes stale Home data without remounting the Vue app.
- Responsive light/dark compatible presentation using shared EdgeSuite tokens.

## Current first-slice metrics

Depending on role and permission availability, the Home can show:

- Today's Appointments
- Waiting / Checked In
- My Active Consultations / Active Consultations
- Completed Today
- Lab Results to Review
- Missed Follow-up
- Pending Dispensary
- Outstanding Invoices

Metrics that cannot be read by the logged-in user are omitted rather than elevated with permission bypass.

## Existing workflows reused

VHOME-01 deep-links to existing authoritative surfaces including:

- Clinical Workspace
- Front Desk Action Centre
- Veterinary Resource Center
- Hospitalisation Operations
- Service Operations
- Executive Dashboard
- Veterinary Administration
- Veterinary Settings
- Stock Expiry Monitor
- native ERPNext Sales Invoice / Payment Entry where appropriate for authorised accounts users

The Home does not reproduce workflow transitions, billing creation, stock posting, payment allocation or consultation state mutation.

## Safety rules

- No submitted ERPNext accounting document mutation.
- No Sales Invoice, Payment Entry or Stock Entry construction from Veterinary Home.
- No `ignore_permissions=True`.
- No raw SQL.
- No generic DocType browser.
- No CoreEdge frontend dependency.
- Existing branch, company, Frappe permission and VetEdge permission helpers remain authoritative.
- Resource Center remains available and continues to own record browsing/editing where already accepted.
- Executive Dashboard remains the full management dashboard; Veterinary Home is an operational snapshot.

## Automated contracts

Focused source-contract coverage verifies:

- Veterinary Home no longer redirects to Resource Center.
- EdgeSuite Home loader/bundle/mount contract.
- action-centre, mini-dashboard and access-context UI presence.
- role, branch and permission-aware backend contract.
- reuse of accepted operational routes.
- absence of business-document writes, permission bypass and raw SQL.

## Required installed-site QA before acceptance

1. Build VetEdge assets successfully.
2. Run focused VHOME-01 tests and existing professional UI regression tests.
3. Open `/desk/vetedge` directly and by VetEdge launcher/sidebar navigation.
4. Verify no automatic redirect to Resource Center.
5. Verify Doctor persona and doctor-specific consultation filtering.
6. Verify Front Desk persona and queue/missed/guest actions.
7. Verify Nurse, Lab, Groomer and Dispensary actions according to actual role permissions.
8. Verify Accounts/Cashier sees only authorised accounting actions and data.
9. Verify Branch Manager and Administrator multi-area actions.
10. Verify multi-role user shows additional access without losing primary role work.
11. Verify explicit branch context and restricted-branch behaviour with at least two branches.
12. Verify a user cannot obtain metrics/quick actions for a DocType they cannot read.
13. Verify mobile/narrow layout.
14. Verify EdgeSuite light and dark appearance.
15. Verify warm navigation away/back refreshes after the stale threshold without duplicate mounts.
16. Verify Resource Center, Clinical Workspace, Front Desk Action Centre, Hospitalisation Operations and Executive Dashboard regressions.

## Out of scope for VHOME-01

- AI-generated clinical or business recommendations.
- configurable/personalised widget layout.
- charts and long-term trend analytics.
- replacement of Executive Dashboard.
- replacement of existing action centres/workspaces.
- new accounting, stock, billing or payment workflows.
- new CoreEdge entitlements.

## Follow-up candidates

VHOME-02 can add richer exception rules, notification integration, overdue hospitalisation-care intelligence, vaccination-due intelligence, workload ageing, and role-specific financial summaries after VHOME-01 browser and permission QA is accepted.
