# VetEdge PR #36 Consolidation Recovery Audit

Date: 2026-08-11

Canonical QA branch: `integration/vetedge-current-qa-2026-08`

## Why this audit was required

Browser QA on PR #36 showed that the shared EdgeSuite theme controls worked and Dark appearance was corrected, but VetEdge navigation was not reliably reaching previously accepted EdgeSuite surfaces. Veterinary Home was not visible in the product navigation, many sidebar links opened native routes or routed incorrectly, and completed Medical History / clinical-vitals work appeared to be missing.

The purpose of this audit is to distinguish three cases:

1. accepted work that was actually deleted from the consolidation;
2. accepted work still present in source but no longer reachable because navigation regressed;
3. work that was explicitly deferred and therefore must not be misreported as a consolidation loss.

## Ancestry result

Accepted operational baseline PR #24 head: `1ef7ba68c25d307a3e4dc45196946ebbc22f4d5f`.

The PR #24 head is an ancestor of PR #36. A GitHub compare from the PR #24 head to the PR #36 recovery head reported the current branch ahead with zero commits behind and no accepted PR #24 files removed.

Therefore the main regression is not wholesale deletion of the accepted EdgeSuite implementation. It is navigation/discoverability drift layered on top of the preserved implementation.

## Accepted surface recovery matrix

| Surface | PR #24 accepted state | PR #36 audit result | Recovery action |
| --- | --- | --- | --- |
| Veterinary Home | `/app/vetedge` routes to current Resource Center | Page source exists, but Home was absent from sidebar/product menu and the controller used a hard browser redirect | Restore `Veterinary Home` as the first product-navigation group and keep Home → Resource Center routing inside Frappe Desk |
| Resource Center | EdgeSuite Resource Center for Patient, Appointment and supported operational resources | Source-controlled Page and bundle remain present | Native Patient/Appointment/Lab/Vaccination/Grooming/Boarding/Kennel menu targets now resolve directly to Resource Center routes |
| Veterinary Settings Center | Dedicated EdgeSuite Settings Center | Page source remains present | `Veterinary Settings` menu target resolves directly to `/app/veterinary-settings-center` |
| Veterinary Master Workspace | Dedicated EdgeSuite masters workspace | Page source remains present | Species, Breed, Symptom, Diagnosis Category, Diagnosis, Service Type and Consultation Type resolve directly to their workspace resource routes |
| Pricing & Service Master Workspace | Dedicated EdgeSuite pricing/service workspace | Page source remains present | Treatment Items/Types, Lab Tests, Vaccines and Grooming Services resolve directly to pricing workspace resource routes |
| Front Desk Action Centre | EdgeSuite Queue / Guest Requests / Missed Appointments | Page source remains present | Queue, Guest Request and Missed Appointment links resolve directly to Action Centre tabs |
| Clinical Workspace | EdgeSuite Consultation workspace | Current Vue source still contains consultation list/detail, treatment plan, Medical History, `New Vitals`, latest-vitals panel, billing context and workflow actions | `Veterinary Consultation` resolves directly to `/app/vetedge-clinical-workspace` |
| Medical History | Dedicated EdgeSuite Medical History page with patient/date filters, vital charts and longitudinal history | Still present and newer than PR #24. PR #30 lazy-loading work is present: summary + visible section + visible trend, cached section/trend loading and recent page reuse | Preserve direct `/app/veterinary-medical-history` route and include it in browser recovery QA |
| Vital Signs | Standalone Vital Signs remained native; same-tab access accepted. Clinical Workspace could create vitals; Medical History showed vital trends | This accepted state remains the intended release scope. A dedicated standalone EdgeSuite Vital Signs page was **not** completed in PR #24 | Keep `Veterinary Vital Signs` visible and same-tab. Validate `New Vitals` in Clinical Workspace and vital history/trends in Medical History. Dedicated standalone EdgeSuite Vital Signs remains a later migration unless separately approved |
| Hospital & Services | EdgeSuite service operations for Kennel Availability, Boarding Stay/Care and Grooming Session | Source work remains present | Accepted service routes resolve directly to `/app/vetedge-service-operations` resource routes |
| Executive Dashboard | Standalone EdgeSuite Executive Dashboard | Still present and newer than PR #24. Performance branch search/page reuse and Theme V1 compatibility are present | Keep direct dashboard route; Dark appearance browser defect fixed during theme QA |
| Stock Expiry Monitor | Canonical EdgeSuite report page | Still present and newer than PR #24 with low-data searchable filters/page reuse | Keep direct canonical Page route |
| Other dashboard-shell pages | PR #24 explicitly left the remaining legacy dashboard-shell family for later work | Pages may exist, but they were not part of the accepted full EdgeSuite migration | Do not label these as lost completed EdgeSuite work; handle them as a later dedicated migration phase |

## Navigation root cause

Three navigation layers were competing:

1. Workspace Sidebar items still carried native Frappe `Page`, `DocType` and `Report` targets.
2. `vetedge_professional_ui.js` converted those targets into shell routes.
3. `vetedge_ui_bridge.js` / accepted-route alignment attempted to redirect selected native routes into EdgeSuite workspaces after navigation had already started.

That architecture made the completed EdgeSuite pages depend on redirect timing and asset order. A page could therefore appear missing even though its implementation was present.

## Recovery implemented on PR #36

A late canonical navigation adapter now loads after the existing VetEdge UI bridge:

`vetedge/public/js/vetedge_navigation_recovery.js`

It:

- injects `Veterinary Home` as a first-class product navigation item;
- rewrites already-migrated native targets directly to their accepted EdgeSuite destinations;
- wraps the shared `EdgeAppShell` so sidebar navigation uses the canonical routes;
- rewrites VetEdge product-menu sections so the waffle uses the same accepted routes;
- preserves Frappe `route_options` for query-string workspace context;
- uses `frappe.set_route(...)` for same-Desk navigation and full navigation only as fallback;
- does not change permissions, clinical logic, accounting, stock posting or submitted documents.

The `/app/vetedge` controller was also changed to use Frappe Desk routing to the Resource Center rather than `window.location.replace(...)`.

## Direct canonical mappings restored

Examples include:

- Patient → `/app/vetedge-resource-center?resource=patients`
- Appointment → `/app/vetedge-resource-center?resource=appointments`
- Appointment Queue → `/app/vetedge-front-desk-action-center?tab=queue`
- Guest Booking Request → `/app/vetedge-front-desk-action-center?tab=guest`
- Missed Appointment → `/app/vetedge-front-desk-action-center?tab=missed`
- Consultation → `/app/vetedge-clinical-workspace`
- Settings → `/app/veterinary-settings-center`
- Species and other clinical masters → `/app/vetedge-master-workspace?...`
- Treatment/Lab/Vaccine/Grooming masters → `/app/vetedge-pricing-master-workspace?...`
- Boarding Stay/Care and Grooming Session → `/app/vetedge-service-operations?...`

## Regression protection

The existing professional EdgeSuite contract suite now asserts:

- the recovery asset loads after `vetedge_ui_bridge.js`;
- Veterinary Home is present;
- the accepted migrated resources have direct canonical EdgeSuite routes;
- the final shared `EdgeAppShell` is replaced by the canonical navigation wrapper;
- navigation uses Frappe Desk routing;
- `/app/vetedge` retains its accepted Resource Center target without `window.location.replace`.

The existing clean-site sidebar integrity test continues to reject published links whose underlying Page, Report or DocType does not exist.

## QA restart gate

Do not resume the wider Forms / Dialogs / Tables / Notifications / Mobile theme matrix until this recovery head passes automated validation and browser navigation confirms:

1. Veterinary Home is visible and opens the Resource Center.
2. Patient and Appointment open the Resource Center in the same tab.
3. Queue / Guest / Missed open the Front Desk Action Centre.
4. Consultation opens the Clinical Workspace.
5. Medical History opens its current lazy-loaded EdgeSuite page.
6. Clinical Workspace `New Vitals` works and latest vitals render.
7. Vital Signs remains visible and opens same-tab native Vital Signs as the accepted PR #24 scope.
8. Settings / Masters / Pricing links open their EdgeSuite workspaces.
9. Service-operation links open the EdgeSuite service workspace.
10. Executive Dashboard and Stock Expiry continue to open directly.
11. Browser Back/Forward and repeated navigation do not strand the user on a stale native route.

## Separate retained work

PR #11 and PR #12 remain outside PR #36 by design because they are the CoreEdge remote-service authority/cutover track. This audit does not fold them into product UI QA.
