# VetEdge Phase 9 — Legacy Surface Audit

## Goal

Finish the EdgeSuite migration by replacing genuinely legacy custom product surfaces while **not** rewriting native Frappe/ERPNext forms that remain the correct authoritative workflow surface.

A native DocType form is not automatically a migration defect. It becomes a migration candidate only when VetEdge already has, or needs, a product-owned simplified operational experience that provides clear business value without duplicating server-side workflow rules.

## Classification rules

### Migrate

Migrate a surface when it is a custom VetEdge Page with large page-local HTML/CSS/JavaScript, duplicated layout/navigation behavior, manual tables/cards/loading states, or a product workflow that should visibly live in the shared EdgeSuite shell.

### Keep native / wrap with EdgeSuite navigation

Keep a native DocType form when it remains the authoritative place for complex Frappe workflow, child tables, permissions, accounting/stock integration, submit/cancel semantics or specialist clinical operations. Prefer an EdgeSuite list/workbench that links into the form rather than rebuilding the entire form.

### Already migrated / adapted

Do not restart surfaces already running through EdgeSuite components, shared report/dashboard shells, Resource Center, Master Workspace, Pricing Master Workspace, Clinical Workspace, Front Desk Action Center or other current product pages.

## Phase 9A — Training Centre

Status: **implemented, browser QA pending**.

Before migration:

- `veterinary_training_centre.js` was approximately 23 KB and owned its own page HTML, cards, tabs, search, Markdown renderer, Mermaid loading/rendering, video panel, screenshot panel, practice panel and page-local CSS.
- Backend services were already appropriately separated in `services/training_centre.py`.
- Training modules were already role-filtered server-side and module content was already lazy-loaded.
- YouTube URLs were already validated and converted to `youtube-nocookie.com` embeds.
- Markdown paths were restricted to the approved repository training directory.

Implemented:

- Added `public/js/vetedge_training_centre/VetEdgeTrainingCentre.vue`.
- Added `public/js/vetedge_training_centre.bundle.js` using shared workspace safety.
- Replaced the large Frappe Page implementation with a thin EdgeSuite runtime/mount loader.
- Preserved the existing `get_training_modules` and `get_training_module_content` APIs; no training content model or role rule was rewritten.
- Module list remains a single small role-filtered request.
- Guide content remains lazy: content is requested only when a module is opened.
- Client search remains local over the already-bounded visible module manifest; no repeated search API traffic is introduced.
- Safe Markdown rendering remains escaped by default, with bounded handling for headings, tables, code, checklists, links and images.
- Cross-training-module links continue to open modules inside Training Centre.
- External links use `noopener noreferrer`.
- Video iframes consume only server-validated embed URLs.
- Mermaid remains a local asset and is loaded only if the visible guide/practice content actually contains Mermaid blocks.
- Module deep links using `?module=` remain supported.

### Training Centre browser QA

1. Open Training Centre from Veterinary sidebar.
2. Confirm there is one EdgeSuite shell and no competing native custom header/sidebar chrome.
3. Confirm only modules permitted for the logged-in role are shown.
4. Search by title, description and role group.
5. Open modules and verify guide content loads only on selection.
6. Confirm direct `?module=<id>` navigation works for permitted modules and rejects unavailable modules.
7. Verify Read Guide / Watch Video / Screenshots / Practice Exercise tabs.
8. Verify internal training-module links change module without a full-page reload.
9. Verify external links open safely in a new tab.
10. Verify local Mermaid diagrams render when present and code remains visible if Mermaid cannot load.
11. Verify valid training video embed, video-coming-soon and invalid/unavailable-video states.
12. Test mobile widths and long tables/code blocks.
13. Network QA: record initial module-list bytes, one guide-content request per opened module, Mermaid request only when required and no polling.

## Current legacy-surface classification

### Already EdgeSuite / shared-shell based — do not restart

- VetEdge home/product shell.
- Front Desk Action Center.
- Clinical Workspace.
- Resource Center and its migrated resource families.
- Master Workspace.
- Pricing Master Workspace.
- Veterinary Settings Center.
- Medical History.
- Stock Expiry Monitor.
- Generic Report Center.
- EdgeSuite-adapted dashboards.
- Hospitalisation Operations workbench.
- Training Centre after Phase 9A.

### Native DocType form remains authoritative by design

These should not be converted wholesale merely to eliminate native Frappe forms:

- Veterinary Consultation — complex clinical workflow, planned treatment, billing/payment and downstream orders.
- Veterinary Hospitalisation — child Activities/Charge Sheet, admission, stock, billing and discharge workflow.
- Veterinary Lab Order — result workflow/billing remains specialist operational logic.
- Veterinary Vaccination Record — stock/billing/administration workflow remains specialist operational logic.
- ERPNext Sales Invoice, Payment Entry, Item, Warehouse, Batch and accounting/stock documents — ERPNext remains accounting/inventory truth.

Use EdgeSuite queues/workbenches/editors around these records where simplification is valuable, but keep server rules and submitted-document integrity authoritative.

### Candidates for further audit

Do not implement these until repository and browser audit confirms the current route is genuinely legacy or creates user friction:

- Kennel Availability / Kennel Availability Board overlap: determine whether both routes are still needed or one is obsolete.
- Remaining standalone custom Pages not already represented by shared EdgeSuite bundles.
- Sidebar DocType links that duplicate a current Resource Center or operational workbench route.
- Setup/master DocTypes that still force normal users into technical native forms even though Master Workspace can safely own their common create/edit flow.
- Boarding and Grooming native operational details: keep core workflow but check whether queue/detail navigation can be consolidated further.

## Safety rules for remaining Phase 9

- Do not rewrite submitted ERPNext accounting or stock records.
- Do not migrate a complex form only for visual consistency.
- Do not duplicate mutation rules into Vue components; call existing permission-aware services.
- Keep bounded Link searches and server validation for dependent fields.
- Preserve Branch/company/tenant and role visibility on every new workbench/list endpoint.
- Prefer lazy loading and page-level pagination over large hidden payloads.
- Preserve white-label/generic Veterinary wording on operational UI.

## Phase 9A acceptance state

Implementation and source contracts are complete. Browser/build/CI acceptance is still pending. PR #47 remains Draft until its stacked-base and QA gates are resolved.
