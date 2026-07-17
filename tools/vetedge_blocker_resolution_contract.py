#!/usr/bin/env python3
"""Generate Phase 2J clone/migration blocker resolution contracts.

This is policy/reporting only. It does not generate a clone, import data,
mutate business data, rename roles, create redirects, modify CoreEdge, or write
executable SQL/shell/import/restore/migrate scripts.
"""

from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path
from typing import Any


WRITE_DISABLED_MESSAGE = "write mode intentionally disabled for blocker resolution contract"
NOTICE = "POLICY CONTRACT ONLY - NOT A CLONE, NOT AN IMPORT PACKAGE"

ROLE_ROUTE_MAPPINGS = [
	("role", "VetEdge Administrator", "Veterinary Administrator", "future mapping only; no rename in this phase"),
	("role", "VetEdge Doctor", "Veterinary Doctor", "future mapping only; no rename in this phase"),
	("role", "VetEdge Receptionist", "Veterinary Receptionist", "future mapping only; no rename in this phase"),
	("role", "VetEdge Billing User", "Veterinary Billing User", "future mapping only; no rename in this phase"),
	("route", "/vetedge_portal", "/veterinary_portal", "future mapping only; no redirect in this phase"),
	("route", "/vetedge_guest_booking", "/veterinary_guest_booking", "future mapping only; no redirect in this phase"),
	("route", "/desk/vetedge-executive-dashboard", "/desk/veterinary-executive-dashboard", "future clone landing route only"),
]

SYSTEM_IDENTITY_RECORDS = [
	"DocType",
	"DocField",
	"DocPerm",
	"Module Def",
	"Role",
	"Has Role",
	"Workspace",
	"Page",
	"Report identity records",
	"Installed Applications",
	"Patch Log",
]

FORBIDDEN_OUTPUT_NAMES = {"import.py", "restore.py", "migrate.py"}
FORBIDDEN_OUTPUT_SUFFIXES = {".sql", ".sh"}


def parse_args() -> argparse.Namespace:
	parser = argparse.ArgumentParser(description="Generate VetEdge Phase 2J blocker resolution contracts.")
	parser.add_argument("--go-no-go-dir", required=True)
	parser.add_argument("--resolution-dir", required=True)
	parser.add_argument("--clone-audit-json")
	parser.add_argument("--output-dir", required=True)
	parser.add_argument("--verbose", action="store_true")
	parser.add_argument("--write", action="store_true")
	args = parser.parse_args()
	if args.write:
		parser.error(WRITE_DISABLED_MESSAGE)
	return args


def load_json(path: Path, *, required: bool = True) -> Any:
	if not path.exists():
		if required:
			raise FileNotFoundError(f"Required artifact missing: {path}")
		return None
	return json.loads(path.read_text(encoding="utf-8"))


def read_text(path: Path, *, required: bool = True) -> str:
	if not path.exists():
		if required:
			raise FileNotFoundError(f"Required artifact missing: {path}")
		return ""
	return path.read_text(encoding="utf-8")


def read_csv(path: Path, *, required: bool = True) -> list[dict[str, str]]:
	if not path.exists():
		if required:
			raise FileNotFoundError(f"Required artifact missing: {path}")
		return []
	with path.open(newline="", encoding="utf-8") as handle:
		return list(csv.DictReader(handle))


def write_json(path: Path, payload: Any) -> None:
	path.parent.mkdir(parents=True, exist_ok=True)
	path.write_text(json.dumps(payload, indent=2, sort_keys=True, default=str), encoding="utf-8")


def write_csv(path: Path, columns: list[str], rows: list[dict[str, Any]]) -> None:
	path.parent.mkdir(parents=True, exist_ok=True)
	with path.open("w", newline="", encoding="utf-8") as handle:
		writer = csv.DictWriter(handle, fieldnames=columns)
		writer.writeheader()
		for row in rows:
			writer.writerow({column: row.get(column, "") for column in columns})


def load_registry(script_path: Path) -> dict[str, Any]:
	registry_path = script_path.parent / "veterinary_clone_audit_registry.json"
	registry = load_json(registry_path, required=False)
	return registry or {}


def count_value(value: Any) -> int | None:
	if value is None:
		return None
	if isinstance(value, dict):
		return sum(int(item or 0) for item in value.values())
	if isinstance(value, list):
		return len(value)
	try:
		return int(value)
	except (TypeError, ValueError):
		return None


def clone_audit_status(clone_audit_json: Path | None, registry: dict[str, Any] | None = None) -> dict[str, Any]:
	if not clone_audit_json:
		return {"provided": False, "unknown_count": None, "unknown_threshold": None, "status": "not_provided"}
	payload = load_json(clone_audit_json, required=False)
	if payload is None:
		return {"provided": True, "path": str(clone_audit_json), "unknown_count": None, "unknown_threshold": None, "status": "missing"}
	counts = payload.get("category_counts") or payload.get("reference_category_counts") or payload.get("counts") or {}
	unknown_count = count_value(counts.get("unknown", 0))
	threshold = payload.get("unknown_threshold")
	if threshold is None:
		threshold = (registry or {}).get("unknown_threshold")
	if threshold is None:
		threshold = (payload.get("registry") or {}).get("unknown_threshold")
	return {
		"provided": True,
		"path": str(clone_audit_json),
		"unknown_count": unknown_count,
		"unknown_threshold": threshold,
		"status": "reviewed" if unknown_count == 0 else "review_required",
	}


def remaining_no_go_rows(blockers: list[dict[str, str]]) -> list[dict[str, str]]:
	areas = {row.get("area", "") for row in blockers}
	rows: list[dict[str, str]] = []
	if "CoreEdge/product references" in areas or not blockers:
		rows.append(
			{
				"item_id": "NO-GO-001",
				"area": "CoreEdge/product references",
				"source_blocker": "CoreEdge/product references need platform decision.",
				"policy_decision": "Resolved at contract level: product_family and distribution model are defined; CoreEdge code implementation is deferred.",
				"status": "policy_resolved_code_deferred",
				"still_blocks_migration_rehearsal": "yes",
				"notes": "Do not reuse VetEdge activation blindly for Veterinary.",
			}
		)
	if "DocType JSON identity fields" in areas or not blockers:
		rows.append(
			{
				"item_id": "NO-GO-002",
				"area": "DocType JSON identity fields",
				"source_blocker": "DocType JSON identity fields remain blocked from automatic migration.",
				"policy_decision": "Resolved as blocked from automatic business-data migration; source clone transforms require reviewed clone-generation process.",
				"status": "policy_resolved_auto_migration_blocked",
				"still_blocks_migration_rehearsal": "yes",
				"notes": "Do not migrate DocType/DocField/DocPerm/Module Def/Role/Workspace/Page/Patch Log as business data.",
			}
		)
	for row in blockers:
		area = row.get("area", "")
		if area in {"CoreEdge/product references", "DocType JSON identity fields"}:
			continue
		rows.append(
			{
				"item_id": f"NO-GO-{len(rows) + 1:03d}",
				"area": area,
				"source_blocker": row.get("description", ""),
				"policy_decision": "No Phase 2J policy decision recorded.",
				"status": row.get("status", "open"),
				"still_blocks_migration_rehearsal": "yes",
				"notes": row.get("notes", ""),
			}
		)
	return rows


def build_summary(
	go_no_go_summary: dict[str, Any],
	remaining_rows: list[dict[str, str]],
	clone_audit: dict[str, Any],
	registry: dict[str, Any],
) -> dict[str, Any]:
	still_no_go = [row for row in remaining_rows if row.get("still_blocks_migration_rehearsal") == "yes"]
	return {
		"notice": NOTICE,
		"coreedge_contract_defined": True,
		"doctype_identity_policy_defined": True,
		"clone_policy_defined": True,
		"migration_policy_defined": True,
		"role_route_branding_policy_defined": True,
		"app_lineage_policy_defined": True,
		"remaining_no_go_count": len(still_no_go),
		"remaining_no_go_items": still_no_go,
		"migration_rehearsal_allowed": False,
		"clone_generation_write_allowed": False,
		"import_behavior_created": False,
		"clone_generated": False,
		"business_data_mutated": False,
		"source_migration_allowed_before_phase_2j": go_no_go_summary.get("migration_allowed"),
		"clone_audit_status": clone_audit,
		"clone_registry_loaded": bool(registry),
	}


def coreedge_distribution_contract_md() -> str:
	return f"""# CoreEdge Distribution Contract

{NOTICE}

No CoreEdge runtime behavior is modified by this document.

## Frozen Distribution Model

| Concept | Decision |
| --- | --- |
| Product family | `product_family = veterinary_practice` |
| VetEdge distribution | `distribution = vetedge` |
| Future Veterinary distribution | `distribution = veterinary` |
| VetEdge activation | Separate VetEdge SaaS activation record/path. |
| Veterinary activation | Separate Veterinary white-label activation record/path. |
| Activation reuse | Do not reuse VetEdge activation blindly for Veterinary. |

## Feature Gates

CoreEdge feature gates must be distribution-aware and support both `vetedge` and `veterinary` where licensed:

- Stock Expiry
- Veterinary Financial Dashboard
- Veterinary Hospitalisation Dashboard
- SMS
- Email
- WhatsApp
- EdgeFinder
- Wallet/service usage

## Contract Decision

CoreEdge/product references are resolved at policy level. CoreEdge implementation is deferred and remains outside Phase 2J.
"""


def doctype_identity_policy_md() -> str:
	records = "\n".join(f"- {record}" for record in SYSTEM_IDENTITY_RECORDS)
	return f"""# DocType Identity Policy

{NOTICE}

## Frozen Rule

DocType JSON identity fields must not be treated as client data migration payload.

## Source-Code Clone Generation

DocType JSON may be transformed only as part of a reviewed source-tree clone generation process. It must not be transformed by live-site database conversion or broad blind replacement.

## Business Data Migration Exclusions

The following records must not be auto-migrated as business data:

{records}

Submitted business documents must be migrated by an approved business-data strategy or preserved in ERPNext-native historical context. Do not rewrite system identity tables or submitted accounting/stock internals.

## Contract Decision

Automatic migration of DocType JSON identity fields remains blocked.
"""


def clone_generation_policy_md(summary: dict[str, Any]) -> str:
	unknown = summary["clone_audit_status"].get("unknown_count")
	return f"""# Clone Generation Policy

{NOTICE}

## Upstream / Downstream Model

- VetEdge remains the upstream source.
- Veterinary becomes a downstream generated app.
- Future Veterinary output must be a separate app package/repo named `veterinary`.
- Clone generation must be source-tree based, not live-site database conversion.

## Write Gate

Clone generation write mode is not allowed in Phase 2J.

Write mode may only be reconsidered after:

- clone audit unknown count is `0` (current observed value: `{unknown}`),
- dangerous items have explicit reviewed policy decisions,
- path/text transformations are token-aware and file-type-aware,
- generated package identity is reviewed before installation,
- no broad find-and-replace is used.

## Contract Decision

`clone_generation_write_allowed = false`.
"""


def migration_policy_md() -> str:
	return f"""# Existing-Client Migration Policy

{NOTICE}

## Frozen Client Policy

- Existing white-label clients already on VetEdge stay on VetEdge unless a separate migration project is approved.
- New white-label clients should use Veterinary once it is stable.
- Existing client migration must use staging-first business-data migration or an explicitly approved site-conversion strategy.
- Do not uninstall VetEdge from production first.
- Do not import into Veterinary without staging validation and signed go/no-go approval.
- Submitted ERPNext accounting and stock documents must not be rewritten directly.

## Contract Decision

Existing-client migration remains a separate approved project, not an automatic consequence of clone generation.
"""


def app_lineage_policy_md() -> str:
	return f"""# App Lineage Policy

{NOTICE}

## Patch Lineage

- VetEdge patches remain VetEdge lineage.
- Veterinary must have its own reviewed patch lineage.
- Patch Log must not be migrated blindly.
- Existing VetEdge patch history must not be copied blindly into Veterinary.
- A clean Veterinary install baseline must be planned separately.

## Contract Decision

Patch/application lineage is excluded from automatic migration and must be handled by a reviewed Veterinary baseline plan.
"""


def role_route_branding_policy_md() -> str:
	lines = [
		"# Role / Route / Branding Policy",
		"",
		NOTICE,
		"",
		"No roles are renamed and no redirects are created in Phase 2J.",
		"",
		"| Type | VetEdge Source | Future Veterinary Target | Decision |",
		"| --- | --- | --- | --- |",
	]
	for mapping_type, source, target, decision in ROLE_ROUTE_MAPPINGS:
		lines.append(f"| {mapping_type} | `{source}` | `{target}` | {decision} |")
	lines.extend(
		[
			"",
			"Existing clients on VetEdge may use visible branding overrides without app identity migration.",
			"",
			"Email, portal, and client-facing copy should use reviewed branding tokens where practical.",
		]
	)
	return "\n".join(lines) + "\n"


def phase_2j_signoff_md(summary: dict[str, Any]) -> str:
	return f"""# Phase 2J Sign-Off

{NOTICE}

## Policy Status

- CoreEdge contract defined: `{str(summary['coreedge_contract_defined']).lower()}`
- DocType identity policy defined: `{str(summary['doctype_identity_policy_defined']).lower()}`
- Clone policy defined: `{str(summary['clone_policy_defined']).lower()}`
- Migration policy defined: `{str(summary['migration_policy_defined']).lower()}`
- Migration rehearsal allowed: `{str(summary['migration_rehearsal_allowed']).lower()}`
- Clone generation write allowed: `{str(summary['clone_generation_write_allowed']).lower()}`

## Required Sign-Off

| Role | Name | Date | Decision | Comments |
| --- | --- | --- | --- | --- |
| Product owner |  |  | approve / reject / approve with conditions |  |
| Technical lead |  |  | approve / reject / approve with conditions |  |
| CoreEdge/platform owner |  |  | approve / reject / approve with conditions |  |
| Data owner/client representative |  |  | approve / reject / approve with conditions |  |
| Finance/accounting reviewer |  |  | approve / reject / approve with conditions |  |
| Operations/support reviewer |  |  | approve / reject / approve with conditions |  |
"""


def generate_blocker_resolution_contract(
	go_no_go_dir: Path,
	resolution_dir: Path,
	output_dir: Path,
	clone_audit_json: Path | None = None,
) -> dict[str, Any]:
	go_no_go_summary = load_json(go_no_go_dir / "go_no_go_summary.json")
	blockers = read_csv(go_no_go_dir / "blockers_register.csv")
	_required_decisions = read_text(go_no_go_dir / "required_decisions.md")
	_risks = read_csv(go_no_go_dir / "risk_register.csv")
	_coreedge_mapping = read_text(resolution_dir / "coreedge_mapping.md")
	_future_contract = read_text(resolution_dir / "future_import_contract_draft.md")
	registry = load_registry(Path(__file__))
	clone_audit = clone_audit_status(clone_audit_json, registry)
	remaining_rows = remaining_no_go_rows(blockers)
	summary = build_summary(go_no_go_summary, remaining_rows, clone_audit, registry)

	output_dir.mkdir(parents=True, exist_ok=True)
	write_json(output_dir / "blocker_resolution_summary.json", summary)
	(output_dir / "coreedge_distribution_contract.md").write_text(coreedge_distribution_contract_md(), encoding="utf-8")
	(output_dir / "doctype_identity_policy.md").write_text(doctype_identity_policy_md(), encoding="utf-8")
	(output_dir / "clone_generation_policy.md").write_text(clone_generation_policy_md(summary), encoding="utf-8")
	(output_dir / "migration_policy.md").write_text(migration_policy_md(), encoding="utf-8")
	(output_dir / "app_lineage_policy.md").write_text(app_lineage_policy_md(), encoding="utf-8")
	(output_dir / "role_route_branding_policy.md").write_text(role_route_branding_policy_md(), encoding="utf-8")
	write_csv(
		output_dir / "remaining_no_go_items.csv",
		["item_id", "area", "source_blocker", "policy_decision", "status", "still_blocks_migration_rehearsal", "notes"],
		remaining_rows,
	)
	(output_dir / "phase_2j_signoff.md").write_text(phase_2j_signoff_md(summary), encoding="utf-8")
	return summary


def validate_no_forbidden_outputs(output_dir: Path) -> list[str]:
	if not output_dir.exists():
		return []
	forbidden = []
	for path in output_dir.rglob("*"):
		if path.is_file() and (path.name in FORBIDDEN_OUTPUT_NAMES or path.suffix in FORBIDDEN_OUTPUT_SUFFIXES):
			forbidden.append(str(path))
	return forbidden


def print_summary(summary: dict[str, Any], output_dir: Path, verbose: bool) -> None:
	print("VetEdge blocker resolution contract package")
	print(f"Output directory: {output_dir}")
	print(f"CoreEdge contract defined: {summary['coreedge_contract_defined']}")
	print(f"DocType identity policy defined: {summary['doctype_identity_policy_defined']}")
	print(f"Migration rehearsal allowed: {summary['migration_rehearsal_allowed']}")
	print(f"Clone generation write allowed: {summary['clone_generation_write_allowed']}")
	print(f"Remaining no-go count: {summary['remaining_no_go_count']}")
	if verbose:
		for item in summary["remaining_no_go_items"]:
			print(f"  - {item['item_id']}: {item['area']} ({item['status']})")


def main() -> int:
	args = parse_args()
	clone_audit_json = Path(args.clone_audit_json) if args.clone_audit_json else None
	output_dir = Path(args.output_dir)
	summary = generate_blocker_resolution_contract(
		Path(args.go_no_go_dir),
		Path(args.resolution_dir),
		output_dir,
		clone_audit_json,
	)
	forbidden = validate_no_forbidden_outputs(output_dir)
	if forbidden:
		raise RuntimeError(f"Forbidden output files generated: {forbidden}")
	print_summary(summary, output_dir, args.verbose)
	return 0


if __name__ == "__main__":
	raise SystemExit(main())
