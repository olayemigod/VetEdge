#!/usr/bin/env python3
"""Generate VetEdge migration go/no-go gate documents.

This is documentation/reporting only. It does not generate a clone, import data,
mutate data, create redirects, rename roles, or create executable scripts.
"""

from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path
from typing import Any


WRITE_DISABLED_MESSAGE = "write mode intentionally disabled for migration go/no-go gate"
STAGING_NOTICE = "STAGING REVIEW ONLY — NOT AN IMPORT PACKAGE"

SIGNOFF_ROLES = [
	"Product owner",
	"Technical lead",
	"CoreEdge/platform owner",
	"Data owner/client representative",
	"Finance/accounting reviewer",
	"Operations/support reviewer",
]

REQUIRED_DECISIONS = [
	"Will migration use business-data import or site-conversion?",
	"Are VetEdge roles renamed to Veterinary roles?",
	"Are portal routes changed, redirected, or preserved?",
	"Are email templates rebranded to Veterinary or client-specific tokens?",
	"How will CoreEdge activation be mapped?",
	"How will historical submitted invoices/stock records be treated?",
	"What data is excluded from import?",
	"What is the rollback plan?",
	"What is the downtime window?",
	"Who signs off?",
]

RISK_ROWS = [
	("RISK-001", "roles/permissions", "role rename mistakes", "users lose or gain unintended access", "medium", "use reviewed role mapping and permission diff", "", "open"),
	("RISK-002", "portal routes", "portal route breakage", "owners cannot access portal/booking", "medium", "decide redirect/preserve strategy before cutover", "", "open"),
	("RISK-003", "email branding", "email branding leakage", "client receives VetEdge-branded messages", "medium", "tokenize/review all templates", "", "open"),
	("RISK-004", "CoreEdge", "CoreEdge activation mismatch", "wrong product activation or tenant context", "high", "platform owner approves distribution mapping", "", "open"),
	("RISK-005", "dashboards/routes", "dashboard route mismatch", "launcher/sidebar dashboards break", "medium", "route validation gate", "", "open"),
	("RISK-006", "accounting/stock", "submitted financial/stock link damage", "accounting or inventory history corrupted", "high", "never rewrite submitted internals", "", "open"),
	("RISK-007", "files", "attachment/file mapping gaps", "clinical/business evidence unavailable", "medium", "file reference reconciliation", "", "open"),
	("RISK-008", "hospitalisation", "hospitalisation child/table metadata misunderstanding", "operational records sampled/imported incorrectly", "medium", "metadata review and sampler validation", "", "open"),
	("RISK-009", "patch lineage", "patch lineage confusion", "migration replays unsafe app history", "high", "exclude patch lineage from import", "", "open"),
	("RISK-010", "cutover", "client downtime/rollback failure", "failed migration causes extended outage", "high", "approved downtime and rollback rehearsal", "", "open"),
]


def parse_args() -> argparse.Namespace:
	parser = argparse.ArgumentParser(description="Generate migration go/no-go gate package.")
	parser.add_argument("--resolution-dir", required=True)
	parser.add_argument("--output-dir", required=True)
	parser.add_argument("--verbose", action="store_true")
	parser.add_argument("--write", action="store_true")
	args = parser.parse_args()
	if args.write:
		parser.error(WRITE_DISABLED_MESSAGE)
	return args


def load_json(path: Path) -> Any:
	if not path.exists():
		raise FileNotFoundError(f"Required resolution artifact missing: {path}")
	return json.loads(path.read_text(encoding="utf-8"))


def read_text(path: Path) -> str:
	if not path.exists():
		raise FileNotFoundError(f"Required resolution artifact missing: {path}")
	return path.read_text(encoding="utf-8")


def read_csv(path: Path) -> list[dict[str, str]]:
	if not path.exists():
		raise FileNotFoundError(f"Required resolution artifact missing: {path}")
	with path.open(newline="", encoding="utf-8") as handle:
		return list(csv.DictReader(handle))


def blockers_from_resolution(summary: dict[str, Any], blockers_text: str) -> list[dict[str, str]]:
	blocked_items = list(summary.get("blocked_items") or [])
	rows = []
	if "CoreEdge/product references" in blocked_items or "CoreEdge/product references" in blockers_text:
		rows.append(
			{
				"blocker_id": "BLK-001",
				"area": "CoreEdge/product references",
				"description": "CoreEdge/product references need platform decision.",
				"source_file": "coreedge_mapping.md / unresolved_blockers.md",
				"severity": "high",
				"required_decision": "Approve product_family/distribution/activation mapping.",
				"owner": "CoreEdge/platform owner",
				"status": "open",
				"target_resolution": "",
				"notes": "",
			}
		)
	if "DocType JSON identity fields" in blocked_items or "DocType JSON identity" in blockers_text:
		rows.append(
			{
				"blocker_id": "BLK-002",
				"area": "DocType JSON identity fields",
				"description": "DocType JSON identity fields remain blocked from automatic migration.",
				"source_file": "future_import_contract_draft.md / unresolved_blockers.md",
				"severity": "high",
				"required_decision": "Confirm no automatic DocType/table identity migration.",
				"owner": "Technical lead",
				"status": "open",
				"target_resolution": "",
				"notes": "",
			}
		)
	return rows


def go_no_go_summary(resolution_summary: dict[str, Any], blockers: list[dict[str, str]]) -> dict[str, Any]:
	open_blockers = [row for row in blockers if row["status"] != "resolved"]
	migration_allowed = not open_blockers
	return {
		"notice": STAGING_NOTICE,
		"source_readiness_status": resolution_summary.get("source_readiness_status"),
		"source_readiness_score": resolution_summary.get("source_readiness_score"),
		"open_blockers": open_blockers,
		"accepted_risks": [],
		"required_decisions": REQUIRED_DECISIONS,
		"migration_allowed": migration_allowed,
		"reason": "No open blockers." if migration_allowed else "Migration rehearsal is not allowed while blockers remain open.",
		"clone_generated": False,
		"import_behavior_created": False,
		"business_data_mutated": False,
	}


def migration_gate_md(summary: dict[str, Any]) -> str:
	blockers = "\n".join(f"- {row['blocker_id']}: {row['description']}" for row in summary["open_blockers"]) or "- None"
	decisions = "\n".join(f"- [ ] {item}" for item in summary["required_decisions"])
	return f"""# Migration Go/No-Go Gate

{STAGING_NOTICE}

## Current Status

- Source readiness: `{summary['source_readiness_status']}`
- Readiness score: `{summary['source_readiness_score']}`
- Migration allowed: `{str(summary['migration_allowed']).lower()}`
- Reason: {summary['reason']}

## What Is Allowed

- Human review of generated artifacts.
- Completion of mapping templates and sign-off forms.
- Non-mutating validation design.

## What Is Not Allowed

- Clone generation.
- Import behavior.
- Runtime data mutation.
- Role renames or route redirects.
- CoreEdge changes.
- SQL/shell/import/restore/migrate scripts.

## Open Blockers

{blockers}

## Required Approvals

{decisions}

## Required Test Evidence

- Audit tool tests pass.
- Package/rehearsal/review/resolution generator tests pass.
- No forbidden script outputs exist.

## Required Staging Evidence

- Rehearsal summaries reviewed.
- Redaction report reviewed.
- Dangerous exclusions reviewed.
- Sample limits verified.

## Required Rollback Evidence

- Site-level rollback plan documented.
- Downtime window approved.
- Rehearsal rollback owner assigned.

## Conditions For Moving To Future Import Rehearsal

- All blockers resolved.
- Required decisions signed off.
- Future test app exists.
- Import contract validator remains non-mutating.

## Conditions That Force No-Go

- Any unresolved high-severity blocker.
- Missing CoreEdge mapping decision.
- Attempt to rewrite submitted accounting/stock internals.
- Missing rollback owner or downtime approval.
"""


def signoff_template_md() -> str:
	lines = ["# Migration Sign-Off Template", "", STAGING_NOTICE, ""]
	for role in SIGNOFF_ROLES:
		lines.extend(
			[
				f"## {role}",
				"",
				"- Name:",
				"- Role:",
				"- Date:",
				"- Decision: approve / reject / approve with conditions",
				"- Comments:",
				"",
			]
		)
	return "\n".join(lines)


def required_decisions_md() -> str:
	return "# Required Decisions\n\n" + STAGING_NOTICE + "\n\n" + "\n".join(f"- [ ] {item}" for item in REQUIRED_DECISIONS) + "\n"


def checklist_md(title: str, items: list[str]) -> str:
	return f"# {title}\n\n{STAGING_NOTICE}\n\n" + "\n".join(f"- [ ] {item}" for item in items) + "\n"


def future_scope_md() -> str:
	return f"""# Future Rehearsal Scope

{STAGING_NOTICE}

Phase 2I does not create a clone, import validator, import tool, or migration runner.

Recommended Phase 2J:

Non-mutating import contract validator against a clean Veterinary test app once the clone exists.

Phase 2J may validate:

- Required mappings are complete.
- Target DocTypes exist.
- Target routes/assets exist.
- Dangerous DocTypes remain excluded.
- Submitted accounting/stock internals are not in scope.

Phase 2J must still not import or mutate data unless separately approved in a later phase.
"""


def write_csv(path: Path, columns: list[str], rows: list[dict[str, str]]) -> None:
	path.parent.mkdir(parents=True, exist_ok=True)
	with path.open("w", newline="", encoding="utf-8") as handle:
		writer = csv.DictWriter(handle, fieldnames=columns)
		writer.writeheader()
		for row in rows:
			writer.writerow({column: row.get(column, "") for column in columns})


def write_json(path: Path, payload: Any) -> None:
	path.parent.mkdir(parents=True, exist_ok=True)
	path.write_text(json.dumps(payload, indent=2, sort_keys=True, default=str), encoding="utf-8")


def generate_go_no_go(resolution_dir: Path, output_dir: Path) -> dict[str, Any]:
	resolution_summary = load_json(resolution_dir / "resolution_summary.json")
	_unresolved = read_text(resolution_dir / "unresolved_blockers.md")
	_manual = read_csv(resolution_dir / "manual_review_resolution.csv")
	_future_contract = read_text(resolution_dir / "future_import_contract_draft.md")
	blockers = blockers_from_resolution(resolution_summary, _unresolved)
	summary = go_no_go_summary(resolution_summary, blockers)

	output_dir.mkdir(parents=True, exist_ok=True)
	write_json(output_dir / "go_no_go_summary.json", summary)
	(output_dir / "migration_gate.md").write_text(migration_gate_md(summary), encoding="utf-8")
	(output_dir / "signoff_template.md").write_text(signoff_template_md(), encoding="utf-8")
	write_csv(
		output_dir / "blockers_register.csv",
		["blocker_id", "area", "description", "source_file", "severity", "required_decision", "owner", "status", "target_resolution", "notes"],
		blockers,
	)
	write_csv(
		output_dir / "risk_register.csv",
		["risk_id", "area", "risk", "impact", "likelihood", "mitigation", "owner", "status"],
		[
			{
				"risk_id": risk_id,
				"area": area,
				"risk": risk,
				"impact": impact,
				"likelihood": likelihood,
				"mitigation": mitigation,
				"owner": owner,
				"status": status,
			}
			for risk_id, area, risk, impact, likelihood, mitigation, owner, status in RISK_ROWS
		],
	)
	(output_dir / "required_decisions.md").write_text(required_decisions_md(), encoding="utf-8")
	(output_dir / "cutover_readiness_checklist.md").write_text(
		checklist_md(
			"Cutover Readiness Checklist",
			[
				"All blockers resolved.",
				"Mappings reviewed and signed off.",
				"Staging rehearsal evidence reviewed.",
				"Role/route/email/CoreEdge decisions approved.",
				"No submitted accounting/stock internals in import scope.",
			],
		),
		encoding="utf-8",
	)
	(output_dir / "rollback_readiness_checklist.md").write_text(
		checklist_md(
			"Rollback Readiness Checklist",
			[
				"Site-level backup validated.",
				"Rollback owner assigned.",
				"Rollback timing tested.",
				"Downtime communication approved.",
				"Go/no-go meeting scheduled.",
			],
		),
		encoding="utf-8",
	)
	(output_dir / "future_rehearsal_scope.md").write_text(future_scope_md(), encoding="utf-8")
	return summary


def validate_no_forbidden_outputs(output_dir: Path) -> list[str]:
	if not output_dir.exists():
		return []
	forbidden = []
	for path in output_dir.rglob("*"):
		if path.is_file() and (path.suffix in {".sql", ".sh"} or path.name in {"import.py", "restore.py", "migrate.py"}):
			forbidden.append(str(path))
	return forbidden


def print_summary(summary: dict[str, Any], output_dir: Path, verbose: bool) -> None:
	print("VetEdge migration go/no-go package")
	print(f"Output directory: {output_dir}")
	print(f"Migration allowed: {summary['migration_allowed']}")
	print(f"Reason: {summary['reason']}")
	print(f"Open blockers: {len(summary['open_blockers'])}")
	if verbose:
		for blocker in summary["open_blockers"]:
			print(f"  - {blocker['blocker_id']}: {blocker['description']}")


def main() -> int:
	args = parse_args()
	output_dir = Path(args.output_dir)
	summary = generate_go_no_go(Path(args.resolution_dir), output_dir)
	forbidden = validate_no_forbidden_outputs(output_dir)
	if forbidden:
		raise RuntimeError(f"Forbidden output files generated: {forbidden}")
	print_summary(summary, output_dir, args.verbose)
	return 0


if __name__ == "__main__":
	raise SystemExit(main())
