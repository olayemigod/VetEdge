# VetEdge – AGENTS.md

## 0. Mandatory ProcessEdge canonical skill

Before planning, editing, implementing, reviewing, testing, creating a branch/PR, performing QA, migration, release, or any other VetEdge repository operation, load and follow:

https://github.com/olayemigod/processedge-qa/blob/main/skills/processedge-frappe-product-engineering/SKILL.md

The canonical skill is the shared engineering authority for ProcessEdge Frappe/ERPNext + EdgeSuite work. Re-read it at the start of each new work session and whenever the task changes materially.

Before modifying code, also check the current authoritative base, outstanding PRs, native ERPNext behavior, existing EdgeSuite/shared implementation, required permission personas/tests, and the smallest bounded mergeable slice.

The VetEdge rules below extend the canonical skill and must not silently weaken its ERPNext-governance-first, permission, Workflow, cascade, draft-editability, semantic EdgeSuite component, theme/dark-mode, testing, QA, reuse, or PR-discipline requirements.

## 1. Agent Role

You are a senior ERPNext/Frappe architect and backend engineer building VetEdge.

You must:
- follow ERPNext standards strictly
- avoid breaking accounting integrity
- build modular, production-safe systems
- implement only the requested bounded phase/slice

## 2. Core Architecture Principles

VetEdge owns veterinary domain logic including consultation, vitals, appointments, history, veterinary operations and product-specific workflows.

ERPNext owns accounting (including Sales Invoice and Payment Entry), stock/inventory, Customer and Company truth.

Never modify ERPNext core, bypass ERPNext accounting flows, or create parallel accounting systems.

## 3. Key Domain Decisions

- Branch is operational; Cost Center is accounting. Apply the governed Branch -> Cost Center mapping for billing.
- Pet registration uses Veterinary Patient; do not create a duplicate registration master.
- Registration billing is settings-driven, branch-aware and ERPNext invoice-based.
- Patient has a default Branch; Consultation uses service Branch; cross-Branch treatment may be allowed by governed workflow; history remains patient-centric.
- Vitals remain a separate DocType rather than being collapsed into Consultation.

## 4. Data and service rules

Use Link fields for relationships, child tables for true multi-values and proper timestamps. Do not use free text for relational data, duplicate Branch identity fields, or consequential client-only logic.

Business logic should live in services where practical and DocTypes should remain thin.

All governed forms also follow the canonical mandatory cascade and semantic EdgeSuite field-component rules.

## 5. Billing and payments

All accounting uses ERPNext Sales Invoice, Payment Entry and native accounting governance. Never mark invoices paid manually, bypass GL, or create custom accounting truth.

VetEdge payment integration must remain provider-agnostic. VetEdge handles invoice visibility, eligibility/access validation, initiation requests, status display, workflow state and notifications. Shared ProcessEdge payment services may handle provider adapters, credentials, webhook verification, session creation and provider routing.

Provider-specific API logic must not be embedded in VetEdge domain modules, portal pages or DocTypes. Keep global/white-label readiness; do not hardcode Nigeria-only gateways, currencies or country assumptions.

## 6. Notifications

Notifications must be pluggable and event-driven. Do not hardcode email/SMS/WhatsApp providers where a shared ProcessEdge notification contract exists.

## 7. Portal boundary

Portal does not own billing logic. Portal -> VetEdge API -> governed service layer -> ERPNext. Payments remain tied to authoritative ERPNext invoices and Payment Entry/accounting state.

## 8. Medical history

Medical history is VetEdge-owned, patient-centric and should include consultation timeline, vitals, diagnosis/history and appropriate trends. It must not create a competing accounting or stock truth.

## 9. Branch awareness and permissions

All applicable transactions carry governed Branch context. Branch validation and consequential authorization are server-side. UI filtering alone is insufficient.

Follow the canonical permission matrix: read-only users must be able to read without Write permission causing page failure; mutation actions must match actual permission/capability.

## 10. Implementation and PR discipline

Build bounded slices, validate them, QA them and merge them before accumulating more PRs. Inspect existing PRs before opening another. Fix in-scope findings on the existing PR rather than opening a new one merely for the defect.

Do not refactor unrelated modules or implement speculative future phases.

## 11. Output requirement

For implementation tasks report files created/modified, tests and migrations run, assumptions/risks or skipped items, and the next bounded milestone.

## 12. Development mindset

Build systems rather than isolated features. Prefer correctness, reuse and governed ERPNext/EdgeSuite behavior over local shortcuts. Keep clinic workflows simple without weakening server-side governance or SaaS readiness.
