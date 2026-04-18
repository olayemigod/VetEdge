# Codex Usage Notes

## Why these files exist

Codex reads `AGENTS.md` before it starts work and benefits from repo-specific rules that define structure, commands, constraints, and what done means. Official Codex documentation describes `AGENTS.md` as the primary way to provide project instructions, and recommends including repository layout, conventions, build/test commands, and do-not rules. Use this repo pack as the authoritative instruction layer for VetEdge.

## Recommended workflow

1. Open the repo root.
2. Ask Codex to read:
   - `AGENTS.md`
   - `docs/vetedge_master_brief.md`
3. Give Codex one phase only.
4. Review the diff after each phase.
5. Use git checkpoints before and after major tasks.

## Recommended first prompt

Read `AGENTS.md` and `docs/vetedge_master_brief.md` first.

Then inspect the repository and implement only the requested current phase.

Constraints:
- Do not modify ERPNext core
- Do not modify Marley core
- Keep veterinary logic owned by VetEdge
- Use ERPNext standards for billing, payment, and stock
- Keep critical rules server-side
- Report created and modified files, assumptions, risks, and next step

## Good prompt style

Use:
- one phase at a time
- clear file boundaries
- explicit constraints
- clear done criteria

Avoid:
- "build the whole app"
- broad refactors
- speculative modules not requested in the current phase
