# VetEdge Performance & Data Efficiency Programme

## Goal

Make VetEdge fast on ordinary clinic hardware and economical on ordinary mobile or shared internet connections without weakening permissions, veterinary workflow correctness, tenant/branch isolation, or ERPNext accounting integrity.

This programme treats performance and data usage as product requirements, not cosmetic optimisation.

## Baseline principle

Do not optimise by guesswork.

Every performance change should be tied to one of these measurable outcomes:

- faster cold page load;
- faster warm/repeat navigation;
- fewer transferred bytes;
- fewer browser requests;
- smaller API payloads;
- lower API/server duration;
- fewer or cheaper database queries;
- less unnecessary background traffic;
- preserved correctness and freshness.

## Current baseline scope

The first audit starts from the consolidated post-PR #24 `main` state and includes the later follow-up commits already on `main`.

Priority workflows:

1. Login / initial Desk boot
2. Veterinary Resource Center
3. Appointment create/edit flow
4. Veterinary Settings Center
5. Veterinary Master Workspace
6. Pricing & Service Master Workspace
7. Front Desk Action Centre
8. Clinical Workspace
9. Medical History
10. Hospital & Services Operations
11. Stock Expiry Monitor
12. Executive Dashboard
13. Legacy Vital Signs route
14. Billing helper interactions
15. Lab and Vaccination routes as they migrate to EdgeSuite UI

## P0 — Static repository audit

`tools/vetedge_performance_audit.py` is a read-only repository scanner. It does not connect to Frappe, mutate data, edit source files, or change accounting documents.

It records:

- files and source bytes scanned;
- public bundle/source size warnings;
- frontend `frappe.call` occurrences;
- EdgeSuite loader count;
- continuous `setInterval` polling signals;
- Desk page unmount/remount-on-show signals;
- `frappe.get_all()` calls without explicit limits;
- unusually large client or server page-size requests.

Static findings are review signals. They are not proof that a code path is slow in production.

### Run locally

```bash
python tools/vetedge_performance_audit.py \
  --root . \
  --json-out /tmp/vetedge-performance-audit.json \
  --markdown-out /tmp/vetedge-performance-audit.md
```

### GitHub baseline

The `VetEdge Performance Audit` workflow runs the harness on relevant pull requests and can also be started manually with `workflow_dispatch`.

Artifacts retained for 30 days:

- `performance-audit.json`
- `performance-audit.md`

This allows later optimisation PRs to compare their static baseline with earlier results.

## P0.1 — Browser/network baseline

Static analysis must be followed by browser measurements against a realistic VetEdge site.

For each priority workflow capture three conditions:

### Cold load

Browser cache cleared or disabled for the first visit.

Record:

- transferred bytes;
- resource bytes;
- request count;
- JS/CSS/font/image transfer;
- API transfer;
- largest resources;
- DOM/content-ready timing where useful;
- time until the workflow is usable.

### Warm load

Repeat with normal browser cache enabled.

Record the same metrics and confirm hashed/versioned static assets are reused instead of transferred again.

### Repeat workflow navigation

Navigate away and return to the same VetEdge page during one Desk session.

Record:

- whether product bundles transfer again;
- whether the Vue page remounts;
- which APIs run again;
- bytes transferred on return;
- whether repeated calls are needed for correctness or only caused by lifecycle behaviour.

## P0.2 — API payload baseline

Capture request and response size for the main APIs used by each priority page.

Review for:

- entire documents returned where a small field projection would be enough;
- duplicated data in one response;
- child rows loaded before the user opens the relevant section;
- lists larger than the visible page;
- repeated identical reference-data calls;
- multiple calls that can safely share one summary response;
- data that can be derived client-side from an already returned result without weakening server-side validation.

Do not move security, permission, tenant, branch, workflow, stock, payment, or accounting validation to the client merely to save bytes.

## P0.3 — Server/query baseline

Profile the slowest APIs before adding database indexes.

Measure:

- total request duration;
- number of SQL queries;
- repeated/N+1 queries;
- expensive counts;
- repeated permission/context lookups;
- slow report queries;
- cacheable configuration/reference lookups.

Indexes should be added only where query evidence shows value. Avoid speculative indexes that increase write cost without improving common VetEdge reads.

## P1 — Quick wins

After measurements, prioritise low-risk changes:

1. remove unnecessary repeated API calls;
2. stop unnecessary page remount/reload behaviour while keeping explicit freshness rules;
3. paginate routine lists and history sections;
4. return only fields required by the active screen;
5. reduce background polling and pause it when the page is inactive;
6. reduce oversized bundles or defer secondary page code;
7. cache/version static assets correctly;
8. reduce unnecessary font/image transfers;
9. cache safe reference/configuration data with clear invalidation;
10. avoid repeated remote CoreEdge calls during normal button interactions when a safe session access context already exists.

## P2 — EdgeSuite UI performance standard

Remaining VetEdge migrations should comply with a shared EdgeSuite performance contract.

Recommended rules:

- page-specific bundles should contain only required product code;
- shared EdgeSuite runtime should be loaded once and browser-cacheable;
- no page should fetch an entire master dataset merely to populate a Link field;
- Link searches must be server-side, permission-aware and paginated;
- operational pages should not depend on large hidden preloads;
- returning to a page should not automatically redownload unchanged static assets;
- automatic refresh must have a documented freshness reason;
- large history/report data should load on demand or in pages;
- full export is a separate workflow from interactive table loading.

## P3 — Backend optimisation

Only after profiling:

- remove N+1 query paths;
- combine repeated reads where safe;
- add evidence-backed indexes;
- cache safe settings/reference data;
- optimise expensive count/report queries;
- keep permission-aware ORM/query behaviour;
- keep submitted accounting documents immutable.

## P4 — Low Data Mode

Low Data Mode is a later product feature, not a substitute for efficient defaults.

Possible settings:

- Standard
- Low Data

Low Data Mode may reduce optional refresh frequency, image loading, prefetching, animation and nonessential dashboard activity. Core clinical, billing, stock, permission and accounting correctness must remain identical.

## Performance acceptance targets

Initial targets are provisional until the first live baseline exists.

Track at minimum:

| Metric | Target direction |
|---|---|
| Cold transferred bytes | Down |
| Warm transferred bytes | Strongly down |
| Repeat-page transferred bytes | Minimal where data is still fresh |
| API request count | Down where calls are redundant |
| Interactive list page size | Paginated / bounded |
| Background requests while idle | Near zero unless operationally required |
| Slow API/server duration | Down |
| N+1/repeated SQL | Removed |
| Static assets reused from cache | Up |

Do not adopt arbitrary hard budgets as release gates until the first representative clinic baseline has been recorded.

## Safety rules

Do not:

- mutate submitted Sales Invoices, Payment Entries or Stock Entries for performance reasons;
- bypass ERPNext permissions;
- weaken branch/doctor/owner validation;
- cache payment or stock state beyond a safe freshness window without explicit invalidation;
- move correctness rules to frontend-only validation;
- load all records and filter in the browser;
- add broad indexes without query evidence;
- complete a large unrelated refactor inside a performance PR.

## Delivery sequence

1. Static audit harness and GitHub artifact
2. Browser/network baseline
3. API payload baseline
4. Server/query baseline
5. P1 quick-win PRs, one focused area at a time
6. EdgeSuite shared performance contract
7. Backend/index optimisation based on evidence
8. Low Data Mode only after efficient defaults are established

## PR reporting requirement

Every performance PR should report:

- workflow measured;
- before measurement;
- after measurement;
- files changed;
- tests run;
- migrations/patches if any;
- data usage effect;
- speed effect;
- freshness/correctness trade-off if any;
- risks and follow-up work.
