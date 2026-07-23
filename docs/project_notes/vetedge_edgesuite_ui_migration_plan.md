# VetEdge EdgeSuite UI Migration Plan

## Purpose

This note controls the phased migration of VetEdge pages and DocTypes from native Frappe Desk presentation into full EdgeSuite UI experiences.

A migration is complete only when the page uses EdgeSuite components for its operational list, filters, form, workflow controls, dialogs, child rows and responsive states. CSS styling of a native Frappe form is not a completed migration.

## Mandatory Phase Review Gate

Before a phase completion report is issued, the implementation must be reviewed again for loopholes. The review must cover:

1. Business workflow preservation.
2. Permission, tenant, company and branch safety.
3. Frontend filtering plus server-side validation for dependent fields.
4. Submitted accounting and stock-document safety.
5. Optimistic locking and unsaved-change protection.
6. Loading, empty, error and mobile states.
7. Navigation, direct routes and notification links.
8. Asset loading, collision-safe bundle names and stale-cache protection.
9. Unit, integration, migration and manual QA coverage.
10. Behaviour intentionally left on native or dedicated pages.

Manual browser QA will be grouped and performed when Mathew confirms that he is ready for QA. Until then, phases remain implemented and automated-review complete, but not manually accepted.

## Navigation Standard

VetEdge uses a dense operational menu because the product has many workflows.

- Persistent shell navigation shows icon plus clear label only.
- It does not show a subtitle beneath every link.
- Searchable waffle/product menus may show concise, action-focused descriptions.
- Internal types such as `DocType`, `Page`, `Report`, package names or module names must never appear as user-facing menu descriptions.
- Veterinary Home must remain available at `/app/vetedge` from every migrated shell page.
- Product routes open in the same tab unless an external or deliberately separate ERPNext destination is required.

## Phase 1 — Core Documents and Settings

### Scope

- Veterinary Patient
- Veterinary Appointment
- Veterinary Settings

### Implementation

- Full EdgeSuite document workspace.
- Permission-aware lists and forms.
- Dynamic Link queries and backend validation.
- Appointment actions delegated to existing VetEdge services.
- Veterinary Settings grouped through EdgeSuite settings navigation.
- Owner Portal Logo remains portal-scoped.
- Operational product logo remains separate and follows deployment identity rules.

### Review Findings and Corrections

- Replaced unsafe reliance on `Meta.workflow_state_field` for Frappe v16 compatibility.
- Prevented `Workflow not found` messages for status-based VetEdge documents without active Frappe Workflow records.
- Separated the standalone `edgesuite_ui.bundle.js` from CoreEdge's historical generic bundle name.
- Made optional branding assets unable to freeze page mounting.
- Corrected owner-logo upload model propagation and persistence.
- Added shared unsaved-change and confirmation-dialog safety.
- Restored Veterinary Home navigation.
- Removed technical link-type subtitles from dense navigation.

### Status

Implemented on the Phase 1 branch. Automated CI and clean-site integration are complete; grouped manual QA and acceptance remain pending.

## Phase 2A — Clinical Reference Masters

### Scope

- Veterinary Species
- Veterinary Breed
- Veterinary Symptom
- Veterinary Diagnosis Category
- Veterinary Diagnosis
- Veterinary Service Type
- Consultation Type

### Business Goal

Provide a clean, consistent setup experience for clinical reference records used by registration, consultation and service workflows.

### Implementation

- Dedicated EdgeSuite master workspace.
- Permission-aware list, search, filters, create, edit and delete.
- Normal `doc.insert()` and `doc.save()` controller execution.
- VetEdge platform-access checks on mutations.
- Optimistic timestamp protection.
- Active Species filtering and server validation for Breed.
- Active Diagnosis Category filtering and server validation for Diagnosis.
- Enabled sales-item filtering and server validation for Service Type default items.
- Non-negative Service Type rates and Consultation Type sort order.
- No mutation of Sales Invoice, Payment Entry, Stock Entry or submitted accounting documents.

### Review Findings and Corrections

- Added unsaved-change protection and reliable confirmation-dialog closure.
- Added direct-route migration for lists and named records.
- Ensured the professional UI loads the collision-safe standalone EdgeSuite UI bundle.
- Made the persistent sidebar label-only while keeping short descriptions in search/product menus.
- Added static contracts and clean-site Frappe integration tests to CI.

### Status

Implemented on `agent/vetedge-full-edgeui-masters-phase2a`. Automated CI and clean-site integration are complete; grouped manual QA and acceptance remain pending.

## Phase 2B — Pricing and Service Masters

### Scope

- Veterinary Treatment Item
- Veterinary Treatment Type
- Veterinary Lab Test
- Veterinary Vaccine
- Pet Grooming Service

### Business Goal

Provide a dedicated pricing-aware setup experience that preserves ERPNext Item rules, existing Item Price and shelf-life controller behaviour, and safe stock versus non-stock selection.

### Implementation

- Dedicated `/app/vetedge-pricing-master-workspace` EdgeSuite page.
- Permission-aware list, search, filters, pagination, create, edit and delete.
- Full Frappe section and conditional-field metadata in the EdgeSuite forms.
- Normal `doc.insert()` and `doc.save()` execution so existing controllers remain authoritative.
- VetEdge platform-access checks for mutations and optimistic timestamp protection.
- Immutable autoname identity fields after creation.
- Enabled sales Item filtering for Treatment Items and Treatment Types.
- Enabled non-stock sales Item filtering for Lab Tests and Grooming Services.
- Enabled stock or non-stock sales Item support for Vaccines.
- Active Species, Service Type and Treatment Type filtering and backend validation.
- Enabled selling Price List filtering and backend validation.
- Clear save-behaviour notices for Item Price and Item shelf-life side effects.
- One clear Active/Inactive filter even where the underlying DocType stores `disabled`.
- Native list and form routes redirected into the EdgeSuite workspace.

### Pricing and Stock Boundaries

- Treatment Item saves may update ERPNext Item Price and Item shelf life through existing controller hooks.
- Lab Test and Vaccine saves may update ERPNext Item Price through existing controller hooks.
- Grooming Service Default Rate remains a VetEdge service default and does not silently update Item Price.
- The workspace does not create, submit, cancel or mutate Sales Invoice, Payment Entry or Stock Entry records.
- Submitted accounting and stock documents are not changed.

### Status

Implemented on `agent/vetedge-full-edgeui-pricing-masters-phase2b` under draft PR #19. Focused Phase 2B CI, full VetEdge regression CI, clean-site builds, migration and live pricing-side-effect tests are complete; grouped manual QA and acceptance remain pending.

## Deferred Phases

### Phase 3 — Front Desk Action Workflows

Expected candidates:

- Veterinary Guest Booking Request
- Veterinary Missed Appointment action centre
- Appointment Queue

Missed Appointment must preserve its dedicated reschedule, cancel and resolve actions and fix the existing modified-after-open conflict.

### Phase 4 — Clinical Documents

Expected candidates:

- Veterinary Consultation
- Veterinary Vital Signs
- Veterinary Medical History

Consultation requires a dedicated provider for clinical state, planned treatment rows, lab and vaccination creation, billing sessions, payment gates and cancellation resolution. It must not use the generic document provider.

### Phase 5 — Laboratory and Vaccination

- Veterinary Lab Order
- Veterinary Vaccination Record
- Related dashboards and reports

Dedicated providers must preserve result entry, uploads, review, stock, pricing, billing and payment boundaries.

### Phase 6 — Hospitalisation, Boarding and Grooming

- Veterinary Hospitalisation
- Veterinary Care Location
- Kennel
- Pet Boarding Booking, Stay and Care Record
- Pet Grooming Appointment and Session

These require dedicated admission, occupancy, care, service-completion, charge-sync, discharge and billing providers.

### Phase 7 — Reports and Regulatory Work

- Operational reports migrated to EdgeSuite report experiences where useful.
- VCN/NADIS vaccination and disease-outbreak reports.
- Regulatory export, review and submission workflow.

Reports must remain permission-aware, branch/company filtered, clickable and export-safe.

## Things Not to Change

- Do not mutate submitted Sales Invoices, Payment Entries or submitted Stock Entries.
- Do not bypass existing VetEdge service-layer workflow validation.
- Do not expose CoreEdge administration to normal Veterinary users.
- Do not merge complex clinical or billing workflows into the generic master/document provider.
- Do not rename internal apps, modules or packages as part of visible branding work.
- Do not report a phase as manually accepted until Mathew starts the grouped QA session.
