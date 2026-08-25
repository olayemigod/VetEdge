# Continuation PR Scope

This PR contains **new post-PR #36 work only**. PR #36 remains responsible for its ongoing clinical and consolidation QA.

The continuation PR is intentionally stacked on PR #36 while PR #36 is open. It must be retargeted to `main` after PR #36 merges.

Implementation order:

1. Shared EdgeSuite reporting standard and provider contract.
2. Shared export/print/PDF foundation.
3. VetEdge report migration/optimization.
4. VCN/NADIS reporting.
5. Hospitalisation EdgeSuite operational completion.
6. Training Centre and verified remaining legacy surfaces.
7. Advanced reporting/intelligence.

Each slice must preserve low-data behaviour, server-authoritative permissions/business validation and ERPNext accounting integrity.
