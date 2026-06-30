#!/usr/bin/env python3
"""Validate Phase 2K CoreEdge distribution and DocType identity readiness.

This is validation/reporting only. It does not generate a clone, import data,
mutate business data, rename roles, create redirects, modify CoreEdge, or write
executable SQL/shell/import/restore/migrate scripts.
"""

from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path
from typing import Any


WRITE_DISABLED_MESSAGE = "write mode intentionally disabled for distribution identity validator"
NOTICE = "VALIDATION ONLY - NOT A CLONE, NOT AN IMPORT PACKAGE"

CONTRACT_RULES = {
	"product_family": "product_family = veterinary_practice",
	"vetedge_distribution": "distribution = vetedge",
	"veterinary_distribution": "distribution = veterinary",
	"separate_activation_paths": "Separate",
	"distribution_aware_feature_gates": "distribution-aware",
	"stock_expiry_gate": "Stock Expiry",
	"financial_dashboard_gate": "Financial Dashboard",
	"hospitalisation_dashboard_gate": "Hospitalisation Dashboard",
	"sms_service": "SMS",
	"email_service": "Email",
	"whatsapp_service": "WhatsApp",
	"edgefinder_service": "EdgeFinder",
	"wallet_service": "Wallet",
}

DOCIDENTITY_POLICY_PHRASES = {
	"not_business_payload": "must not be treated as client data migration payload",
	"source_tree_only": "source-tree clone generation process",
	"automatic_migration_blocked": "Automatic migration of DocType JSON identity fields remains blocked",
	"patch_log_blocked": "Patch Log",
}

SOURCE_SCAN_PATTERNS = [
	"vetedge",
	"VetEdge",
	"VETEDGE",
	"/assets/vetedge",
	"/desk/vetedge",
	"/vetedge_portal",
	"/vetedge_guest_booking",
]

PRESERVE_TERMS = [
	"Veterinary Patient",
	"Veterinary Appointment",
	"Veterinary Consultation",
	"Veterinary Hospitalisation",
	"Veterinary Records",
	"Veterinary Settings",
	"Veterinary Financial Dashboard",
	"Veterinary Hospitalisation Dashboard",
	"Stock Expiry Status",
]

FORBIDDEN_OUTPUT_NAMES = {"import.py", "restore.py", "migrate.py"}
FORBIDDEN_OUTPUT_SUFFIXES = {".sql", ".sh"}
EXCLUDED_DIRS = {".git", "__pycache__", ".pytest_cache", "node_modules", "dist", "build", "logs"}
TEXT_SUFFIXES = {".py", ".js", ".json", ".toml", ".txt", ".md", ".html", ".css", ".csv", ".yml", ".yaml"}


def parse_args() -> argparse.Namespace:
	parser = argparse.ArgumentParser(description="Validate VetEdge distribution and DocType identity readiness.")
	parser.add_argument("--source-dir", required=True)
	parser.add_argument("--blocker-contract-dir", required=True)
	parser.add_argument("--clone-audit-json")
	parser.add_argument("--go-no-go-dir", required=True)
	parser.add_argument("--output-dir", required=True)
	parser.add_argument("--coreedge-dir")
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


def clone_audit_status(path: Path | None) -> dict[str, Any]:
	if not path:
		return {
			"provided": False,
			"unknown_count": None,
			"safe_transform_count": None,
			"dangerous_count": None,
			"unknown_count_accepted": False,
			"safe_transform_preview_only": True,
			"clone_write_mode_disabled": True,
		}
	payload = load_json(path, required=False)
	if payload is None:
		return {
			"provided": True,
			"path": str(path),
			"unknown_count": None,
			"safe_transform_count": None,
			"dangerous_count": None,
			"unknown_count_accepted": False,
			"safe_transform_preview_only": True,
			"clone_write_mode_disabled": True,
		}
	counts = payload.get("category_counts") or payload.get("reference_category_counts") or payload.get("counts") or {}
	unknown_count = count_value(counts.get("unknown", 0))
	return {
		"provided": True,
		"path": str(path),
		"unknown_count": unknown_count,
		"safe_transform_count": count_value(counts.get("safe_transform", 0)),
		"dangerous_count": count_value(counts.get("dangerous", 0)),
		"unknown_count_accepted": unknown_count == 0,
		"safe_transform_preview_only": True,
		"clone_write_mode_disabled": True,
		"audit_mode": payload.get("mode"),
		"write_disabled_message": payload.get("write_disabled_message"),
	}


def detect_contract_rules(contract_dir: Path) -> dict[str, bool]:
	text = read_text(contract_dir / "coreedge_distribution_contract.md")
	return {rule: phrase in text for rule, phrase in CONTRACT_RULES.items()}


def detect_doctype_policy(contract_dir: Path) -> dict[str, bool]:
	text = read_text(contract_dir / "doctype_identity_policy.md")
	return {rule: phrase in text for rule, phrase in DOCIDENTITY_POLICY_PHRASES.items()}


def is_text_file(path: Path) -> bool:
	return path.suffix in TEXT_SUFFIXES or path.name in {"hooks.py", "modules.txt", "patches.txt"}


def should_skip(path: Path) -> bool:
	return any(part in EXCLUDED_DIRS for part in path.parts) or path.suffix in {".pyc", ".pyo"}


def source_file_kind(relative_path: str) -> str:
	lower = relative_path.lower()
	if lower == "hooks.py" or lower.endswith("/hooks.py"):
		return "hooks"
	if lower == "pyproject.toml":
		return "pyproject"
	if lower.endswith("modules.txt"):
		return "modules"
	if lower.endswith("patches.txt") or "/patches/" in lower:
		return "patch"
	if "/desktop_icon/" in lower:
		return "desktop_icon"
	if "/workspace_sidebar/" in lower:
		return "workspace_sidebar"
	if "/doctype/" in lower and lower.endswith(".json"):
		return "doctype_json"
	if "/report/" in lower and lower.endswith(".json"):
		return "report_json"
	if "/page/" in lower and lower.endswith(".json"):
		return "page_json"
	if "/fixture" in lower or "/fixtures/" in lower:
		return "fixture"
	if "portal" in lower:
		return "portal"
	if "email" in lower or "template" in lower:
		return "email_template"
	if "coreedge" in lower:
		return "coreedge_adapter"
	return "source"


def classify_source_finding(relative_path: str, matched_text: str) -> str:
	kind = source_file_kind(relative_path)
	if any(term in matched_text for term in PRESERVE_TERMS):
		return "preserve_domain_identity"
	if kind in {"doctype_json"}:
		return "blocked_from_business_migration"
	if kind in {"patch"}:
		return "dangerous"
	if kind in {"report_json", "page_json", "workspace_sidebar", "fixture", "portal", "email_template"}:
		return "manual_review"
	if kind == "coreedge_adapter":
		return "CoreEdge_contract_required"
	if kind in {"hooks", "pyproject", "modules", "desktop_icon"}:
		return "clone_source_transform_required"
	if matched_text in {"/desk/vetedge", "/vetedge_portal", "/vetedge_guest_booking"}:
		return "manual_review"
	return "clone_source_transform_required"


def relevant_source_file(path: Path, source_dir: Path) -> bool:
	relative = path.relative_to(source_dir).as_posix()
	kind = source_file_kind(relative)
	if kind != "source":
		return True
	return any(segment in relative.lower() for segment in ["portal", "email", "template", "coreedge", "fixture"])


def scan_source_metadata(source_dir: Path) -> list[dict[str, Any]]:
	rows: list[dict[str, Any]] = []
	for path in sorted(source_dir.rglob("*")):
		if not path.is_file() or should_skip(path.relative_to(source_dir)) or not is_text_file(path):
			continue
		if not relevant_source_file(path, source_dir):
			continue
		relative = path.relative_to(source_dir).as_posix()
		try:
			lines = path.read_text(encoding="utf-8").splitlines()
		except UnicodeDecodeError:
			continue
		for line_number, line in enumerate(lines, start=1):
			matches = [pattern for pattern in SOURCE_SCAN_PATTERNS + PRESERVE_TERMS if pattern in line]
			for match in matches:
				rows.append(
					{
						"file_path": relative,
						"line_number": line_number,
						"matched_text": match,
						"file_kind": source_file_kind(relative),
						"classification": classify_source_finding(relative, match),
						"notes": "static source metadata finding; no files changed",
					}
				)
	return rows


def scan_coreedge(coreedge_dir: Path | None) -> list[dict[str, Any]]:
	if not coreedge_dir or not coreedge_dir.exists():
		return []
	rows: list[dict[str, Any]] = []
	for path in sorted(coreedge_dir.rglob("*")):
		if not path.is_file() or should_skip(path.relative_to(coreedge_dir)) or not is_text_file(path):
			continue
		try:
			lines = path.read_text(encoding="utf-8").splitlines()
		except UnicodeDecodeError:
			continue
		for line_number, line in enumerate(lines, start=1):
			for match in ["vetedge", "VetEdge", "product_family", "distribution", "activation", "feature_gate"]:
				if match in line:
					rows.append(
						{
							"file_path": path.relative_to(coreedge_dir).as_posix(),
							"line_number": line_number,
							"matched_text": match,
							"file_kind": "coreedge_source",
							"classification": "CoreEdge_contract_required",
							"notes": "CoreEdge static review only; no files changed",
						}
					)
	return rows


def coreedge_gap_rows(coreedge_provided: bool) -> list[dict[str, str]]:
	status = "not_validated_in_source" if not coreedge_provided else "requires_review"
	return [
		{"gap_id": "COREEDGE-GAP-001", "area": "product_family", "gap": "product_family implementation not yet validated", "status": status, "recommendation": "Plan CoreEdge support for veterinary_practice."},
		{"gap_id": "COREEDGE-GAP-002", "area": "distribution", "gap": "distribution field/decision not yet implemented or validated", "status": status, "recommendation": "Support vetedge and veterinary distributions explicitly."},
		{"gap_id": "COREEDGE-GAP-003", "area": "activation", "gap": "separate activation path not yet implemented or validated", "status": status, "recommendation": "Create separate activation paths; do not reuse VetEdge blindly."},
		{"gap_id": "COREEDGE-GAP-004", "area": "feature gates", "gap": "feature gates not yet distribution-aware", "status": status, "recommendation": "Validate Stock Expiry and dashboard gates by distribution."},
		{"gap_id": "COREEDGE-GAP-005", "area": "product identity", "gap": "product identity may still rely on package/app name", "status": status, "recommendation": "Separate product identity from package identity."},
	]


def doctype_identity_gap_rows() -> list[dict[str, str]]:
	return [
		{"gap_id": "DOCTYPE-GAP-001", "area": "DocType JSON", "gap": "DocType JSON identity fields blocked from business migration", "status": "blocked_from_business_migration", "recommendation": "Transform only in reviewed source-tree clone generation."},
		{"gap_id": "DOCTYPE-GAP-002", "area": "fixtures", "gap": "fixture identity fields require clone-generation review", "status": "manual_review", "recommendation": "Review fixture record names separately from business data."},
		{"gap_id": "DOCTYPE-GAP-003", "area": "Report/Page/Workspace", "gap": "Report/Page/Workspace identity records require clone-generation review", "status": "manual_review", "recommendation": "Keep live-site migration and source clone paths separate."},
		{"gap_id": "DOCTYPE-GAP-004", "area": "patch lineage", "gap": "patch lineage requires separate Veterinary baseline decision", "status": "dangerous", "recommendation": "Do not copy Patch Log blindly."},
		{"gap_id": "DOCTYPE-GAP-005", "area": "roles", "gap": "role identity requires future clone and permission tests", "status": "manual_review", "recommendation": "Validate permissions after any future source clone rehearsal."},
	]


def finding_counts(rows: list[dict[str, Any]], key: str) -> dict[str, int]:
	counts: dict[str, int] = {}
	for row in rows:
		value = str(row.get(key) or "")
		counts[value] = counts.get(value, 0) + 1
	return dict(sorted(counts.items()))


def build_summary(
	contract_rules: dict[str, bool],
	doctype_policy: dict[str, bool],
	clone_audit: dict[str, Any],
	source_rows: list[dict[str, Any]],
	coreedge_rows: list[dict[str, Any]],
	coreedge_gaps: list[dict[str, str]],
	doctype_gaps: list[dict[str, str]],
) -> dict[str, Any]:
	return {
		"notice": NOTICE,
		"coreedge_contract_valid": all(contract_rules.values()),
		"coreedge_contract_rules": contract_rules,
		"doctype_identity_policy_valid": all(doctype_policy.values()),
		"doctype_identity_policy_rules": doctype_policy,
		"clone_audit": clone_audit,
		"clone_audit_unknown_count_accepted": clone_audit.get("unknown_count_accepted"),
		"safe_transform_is_write_approval": False,
		"migration_import_rehearsal_blocked": True,
		"import_behavior_blocked": True,
		"clone_write_mode_blocked": True,
		"clone_generated": False,
		"import_behavior_created": False,
		"business_data_mutated": False,
		"coreedge_implementation_planning_may_begin": all(contract_rules.values()),
		"clone_source_generation_rehearsal_requires_future_approval": True,
		"source_metadata_findings_count": len(source_rows),
		"source_metadata_classification_counts": finding_counts(source_rows, "classification"),
		"coreedge_static_findings_count": len(coreedge_rows),
		"coreedge_gap_count": len(coreedge_gaps),
		"doctype_identity_gap_count": len(doctype_gaps),
	}


def coreedge_readiness_md(summary: dict[str, Any], coreedge_gaps: list[dict[str, str]]) -> str:
	gap_text = "\n".join(f"- {row['gap_id']}: {row['gap']} ({row['status']})" for row in coreedge_gaps)
	rule_text = "\n".join(f"- {rule}: {str(passed).lower()}" for rule, passed in summary["coreedge_contract_rules"].items())
	return f"""# CoreEdge Distribution Readiness

{NOTICE}

## Contract Rules

{rule_text}

## Result

CoreEdge implementation planning may begin: `{str(summary['coreedge_implementation_planning_may_begin']).lower()}`.

No CoreEdge runtime behavior was modified.

## Gaps

{gap_text}
"""


def doctype_identity_readiness_md(summary: dict[str, Any], gaps: list[dict[str, str]]) -> str:
	gap_text = "\n".join(f"- {row['gap_id']}: {row['gap']} ({row['status']})" for row in gaps)
	rule_text = "\n".join(f"- {rule}: {str(passed).lower()}" for rule, passed in summary["doctype_identity_policy_rules"].items())
	return f"""# DocType Identity Readiness

{NOTICE}

## Policy Rules

{rule_text}

## Result

DocType identity policy is valid: `{str(summary['doctype_identity_policy_valid']).lower()}`.

DocType JSON identity fields remain blocked from automatic business-data migration. No DocType JSON files were changed.

## Gaps

{gap_text}
"""


def future_clone_requirements_md(summary: dict[str, Any]) -> str:
	return f"""# Future Clone Requirements

{NOTICE}

- Clone source generation must remain source-tree based.
- Safe transforms from the clone audit are preview-only and are not write approval.
- Clone audit unknown count accepted: `{str(summary['clone_audit_unknown_count_accepted']).lower()}`.
- Clone write mode remains blocked: `{str(summary['clone_write_mode_blocked']).lower()}`.
- Future clone source generation rehearsal may begin only if explicitly approved in a later phase.
- Client data migration/import remains separate from source-tree clone generation.
"""


def recommendation_md(summary: dict[str, Any]) -> str:
	return f"""# Phase 2K Recommendation

{NOTICE}

## Recommendation

- CoreEdge implementation planning may begin: `{str(summary['coreedge_implementation_planning_may_begin']).lower()}`.
- Clone source generation rehearsal may begin only as future explicitly approved temporary output/dry-run write.
- Migration/import rehearsal remains blocked: `{str(summary['migration_import_rehearsal_blocked']).lower()}`.
- Import behavior remains blocked: `{str(summary['import_behavior_blocked']).lower()}`.
- Clone write mode remains blocked in Phase 2K: `{str(summary['clone_write_mode_blocked']).lower()}`.

## Before Phase 2L

- Decide whether Phase 2L is CoreEdge implementation planning or clone dry-run output rehearsal.
- Keep business-data migration/import out of scope until signed approval.
- Keep DocType identity changes out of live-site data migration.
- Preserve VetEdge runtime behavior.
"""


def generate_distribution_identity_validator(
	source_dir: Path,
	blocker_contract_dir: Path,
	go_no_go_dir: Path,
	output_dir: Path,
	clone_audit_json: Path | None = None,
	coreedge_dir: Path | None = None,
) -> dict[str, Any]:
	_contract_summary = load_json(blocker_contract_dir / "blocker_resolution_summary.json")
	_go_no_go_summary = load_json(go_no_go_dir / "go_no_go_summary.json")
	_remaining_no_go = read_csv(blocker_contract_dir / "remaining_no_go_items.csv")
	contract_rules = detect_contract_rules(blocker_contract_dir)
	doctype_policy = detect_doctype_policy(blocker_contract_dir)
	clone_audit = clone_audit_status(clone_audit_json)
	source_rows = scan_source_metadata(source_dir)
	coreedge_rows = scan_coreedge(coreedge_dir)
	source_rows.extend(coreedge_rows)
	coreedge_gaps = coreedge_gap_rows(coreedge_dir is not None and coreedge_dir.exists())
	doctype_gaps = doctype_identity_gap_rows()
	summary = build_summary(contract_rules, doctype_policy, clone_audit, source_rows, coreedge_rows, coreedge_gaps, doctype_gaps)

	output_dir.mkdir(parents=True, exist_ok=True)
	write_json(output_dir / "validator_summary.json", summary)
	(output_dir / "coreedge_distribution_readiness.md").write_text(coreedge_readiness_md(summary, coreedge_gaps), encoding="utf-8")
	(output_dir / "doctype_identity_readiness.md").write_text(doctype_identity_readiness_md(summary, doctype_gaps), encoding="utf-8")
	write_csv(
		output_dir / "source_metadata_findings.csv",
		["file_path", "line_number", "matched_text", "file_kind", "classification", "notes"],
		source_rows,
	)
	(output_dir / "future_clone_requirements.md").write_text(future_clone_requirements_md(summary), encoding="utf-8")
	write_csv(output_dir / "coreedge_gap_register.csv", ["gap_id", "area", "gap", "status", "recommendation"], coreedge_gaps)
	write_csv(output_dir / "doctype_identity_gap_register.csv", ["gap_id", "area", "gap", "status", "recommendation"], doctype_gaps)
	(output_dir / "phase_2k_recommendation.md").write_text(recommendation_md(summary), encoding="utf-8")
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
	print("VetEdge distribution identity validator")
	print(f"Output directory: {output_dir}")
	print(f"CoreEdge contract valid: {summary['coreedge_contract_valid']}")
	print(f"DocType identity policy valid: {summary['doctype_identity_policy_valid']}")
	print(f"Clone audit unknown accepted: {summary['clone_audit_unknown_count_accepted']}")
	print(f"CoreEdge gaps: {summary['coreedge_gap_count']}")
	print(f"DocType identity gaps: {summary['doctype_identity_gap_count']}")
	print(f"Migration/import rehearsal blocked: {summary['migration_import_rehearsal_blocked']}")
	print(f"Clone write mode blocked: {summary['clone_write_mode_blocked']}")
	if verbose:
		print("Source metadata classification counts:")
		for classification, count in summary["source_metadata_classification_counts"].items():
			print(f"  - {classification}: {count}")


def main() -> int:
	args = parse_args()
	output_dir = Path(args.output_dir)
	summary = generate_distribution_identity_validator(
		Path(args.source_dir),
		Path(args.blocker_contract_dir),
		Path(args.go_no_go_dir),
		output_dir,
		Path(args.clone_audit_json) if args.clone_audit_json else None,
		Path(args.coreedge_dir) if args.coreedge_dir else None,
	)
	forbidden = validate_no_forbidden_outputs(output_dir)
	if forbidden:
		raise RuntimeError(f"Forbidden output files generated: {forbidden}")
	print_summary(summary, output_dir, args.verbose)
	return 0


if __name__ == "__main__":
	raise SystemExit(main())
