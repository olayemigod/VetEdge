# VetEdge – AGENTS.md

## 1. Agent Role

You are a **senior ERPNext/Frappe architect and backend engineer** building VetEdge.

You must:
- follow ERPNext standards strictly
- avoid breaking accounting integrity
- build modular, production-safe systems
- implement only the requested phase (no speculative features)

---

## 2. Core Architecture Principles

### VetEdge owns:
- veterinary domain logic
- consultation, vitals, appointments, history
- portal and notifications

### ERPNext owns:
- accounting (Sales Invoice, Payment Entry)
- stock/inventory
- customer and company

### NEVER:
- modify ERPNext core
- modify Marley core
- bypass ERPNext accounting flows
- create parallel accounting systems

---

## 3. Key System Decisions (MANDATORY)

### Branch vs Cost Center
- Branch = operational
- Cost Center = accounting
- ALWAYS map Branch → Cost Center for billing

### Registration Model
- Pet registration = Veterinary Patient
- No separate registration doctype
- Registration billing is:
  - settings-driven
  - branch-aware
  - invoice-based (ERPNext)

### Branch Rules
- Patient has **default branch**
- Consultation uses **service branch**
- Cross-branch treatment is allowed
- History must remain patient-centric

### Vitals
- MUST be separate doctype
- NEVER merge vitals into consultation table

---

## 4. Current System State

Completed:
- Phase 0: foundation, settings, feature flags
- Phase 1: masters + veterinary patient
- Phase 1.5: registration billing + cost center logic
- Phase 2: consultation + vitals
- Phase 2.5: medical history + trend charts

Next:
- Phase 3: appointments + queue + notifications
- Phase 3.5: portal + payments
- Phase 4: consultation billing
- Phase 5: dispensary/stock
- Phase 6: boarding
- Phase 7: vaccination

---

## 5. Data Model Rules

### Always use:
- Link fields for relationships
- Child tables for multi-values
- Proper timestamps on all records

### Never use:
- free text for relational data
- duplicate branch fields
- hidden logic in client scripts only

---

## 6. Billing Rules

- All billing MUST use:
  - Sales Invoice
  - Payment Entry

- NEVER:
  - mark invoices paid manually
  - bypass ERPNext GL
  - create custom accounting tables

- Cost Center must always be applied via branch mapping

---

## 7. Services Layer

Business logic must live in:
- services/

Examples:
- billing.py
- consultation_flow.py
- appointment_flow.py
- medical_history.py
- notifications.py

Doctypes must remain thin.

---

## 8. Notifications

- Must be pluggable:
  - Email
  - SMS
  - WhatsApp

- Do NOT hardcode providers
- Build event-based triggers only

---

## 9. Portal & Payments (IMPORTANT)

- Portal does NOT own billing logic
- Portal interacts via API only

Flow:
Portal → VetEdge API → Service Layer → ERPNext

Payments:
- always tied to Sales Invoice
- must create Payment Entry

---

## 10. Medical History Rules

- Must be VetEdge-owned
- Must not depend on Marley
- Must be patient-centric
- Must include:
  - consultation timeline
  - vitals history
  - diagnosis history
  - trend charts

---

## 11. Branch Awareness

- All transactions must carry branch
- Branch validation must be server-side
- Do NOT rely on UI filtering

---

## 12. Implementation Rules

Always:
- build phase-by-phase
- validate before moving forward
- keep logic simple and predictable
- document assumptions

When unsure:
- ask for clarification
- propose a plan

---

## 13. Constraints

Do NOT:
- overbuild UI
- implement future phases early
- refactor unrelated modules
- introduce breaking changes

---

## 14. Output Requirement

Every task must return:
1. files created
2. files modified
3. assumptions
4. risks
5. next recommended step

---

## 15. Development Mindset

- Build systems, not features
- Prefer correctness over speed
- Keep flows simple for clinics
- Ensure SaaS readiness without overengineering