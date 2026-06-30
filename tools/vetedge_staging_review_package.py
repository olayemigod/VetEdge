#!/usr/bin/env python3
"""Generate staging migration review artifacts from existing audit packages.

This tool reads Phase 2D/2E/2F outputs and creates human review artifacts only.
It does not export new business rows, import data, generate a clone, or create
destructive scripts.
"""

from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path
from typing import Any


WRITE_DISABLED_MESSAGE = "write mode intentionally disabled for staging review package"
STAGING_NOTICE = "STAGING REVIEW ONLY — NOT AN IMPORT PACKAGE"

CHECKLIST_SECTIONS = [
	"business data completeness",
	"clinical records",
	"appointments",
	"consultations",
	"vaccination/preventive care",
	"lab records",
	"hospitalisation records",
	"grooming/boarding records",
	"billing links",
	"stock/item dependencies",
	"attachments/files",
	"communication/comments",
	"portal routes",
	"email templates",
	"roles/permissions",
	"CoreEdge activation/branding/settings",
	"dashboards/reports/sidebar",
	"client branding",
	"final cutover readiness",
]

MANUAL_REVIEW_AREAS = [
	"email templates",
	"roles",
	"portal routes",
	"Desk routes",
	"reports",
	"pages",
	"workspaces",
	"CoreEdge/product references",
	"fixtures",
	"DocType JSON identity fields",
	"report JSON identity fields",
]

CUTOVER_QUESTIONS = [
	"Which client/site is being migrated?",
	"Is this business-data migration or site-conversion migration?",
	"Which roles should be renamed or preserved?",
	"Which portal routes should be redirected?",
	"Which email templates need client branding?",
	"How will CoreEdge activation map from VetEdge to Veterinary?",
	"Are submitted invoices/stock records being carried as historical ERPNext data or re-linked?",
	"What is the rollback plan?",
	"What is the downtime window?",
	"Who signs off on the reconciliation workbook?",
]

MATRIX_COLUMNS = [
	"area",
	"source",
	"category",
	"doctype",
	"source_count",
	"sample_count",
	"excluded",
	"redacted",
	"risk_level",
	"review_required",
	"reviewer_notes",
]

DANGEROUS_BASELINE = {
	"Patch Log",
	"GL Entry",
	"Stock Ledger Entry",
	"DocField",
	"DocPerm",
	"DocType",
	"Module Def",
	"Role",
	"Has Role",
	"Workspace",
	"Page",
	"Installed Applications",
	"Account",
	"Batch",
	"Branch",
	"Company",
	"Cost Center",
	"Customer",
	"Item",
}


def parse_args() -> argparse.Namespace:
	parser = argparse.ArgumentParser(description="Generate VetEdge staging review package artifacts.")
	parser.add_argument("--audit-json", required=True)
	parser.add_argument("--migration-package-dir", required=True)
	parser.add_argument("--rehearsal-dir", required=True)
	parser.add_argument("--output-dir", required=True)
	parser.add_argument("--format", choices=["json", "csv", "markdown"], action="append", help="Accepted for future selective output; all review artifacts are generated in Phase 2G.")
	parser.add_argument("--verbose", action="store_true")
	parser.add_argument("--write", action="store_true", help="Intentionally disabled.")
	args = parser.parse_args()
	if args.write:
		parser.error(WRITE_DISABLED_MESSAGE)
	return args


def load_json(path: str | Path) -> Any:
	target = Path(path)
	if not target.exists():
		raise FileNotFoundError(f"Required input file not found: {target}")
	return json.loads(target.read_text(encoding="utf-8"))


def read_optional_json(path: Path, default: Any) -> Any:
	if not path.exists():
		return default
	return json.loads(path.read_text(encoding="utf-8"))


def sample_counts(rehearsal_dir: Path) -> dict[str, int]:
	counts: dict[str, int] = {}
	samples_dir = rehearsal_dir / "samples"
	if not samples_dir.exists():
		return counts
	for path in sorted(samples_dir.glob("*.jsonl")):
		doctype = path.stem
		with path.open(encoding="utf-8") as handle:
			counts[doctype] = sum(1 for line in handle if line.strip())
	return counts


def risk_level(category: str, excluded: bool, redacted: bool) -> str:
	if excluded or category == "dangerous_do_not_auto_migrate":
		return "high"
	if category in {"requires_manual_review", "platform_coreedge_dependent"} or redacted:
		return "medium"
	if category == "erpnext_native_dependency":
		return "medium"
	return "low"


def area_for_doctype(doctype: str) -> str:
	text = doctype.lower()
	if "appointment" in text:
		return "appointments"
	if "consultation" in text:
		return "consultations"
	if "vaccination" in text or "vaccine" in text:
		return "vaccination/preventive care"
	if "lab" in text:
		return "lab records"
	if "hospitalisation" in text or "care location" in text:
		return "hospitalisation records"
	if "grooming" in text or "boarding" in text or "kennel" in text:
		return "grooming/boarding records"
	if doctype in {"Sales Invoice", "Payment Entry"}:
		return "billing links"
	if doctype in {"Item", "Warehouse", "Stock Entry", "Batch"}:
		return "stock/item dependencies"
	if doctype in {"File"}:
		return "attachments/files"
	if doctype in {"Communication", "Comment"}:
		return "communication/comments"
	if "email" in text:
		return "email templates"
	if doctype in {"Role", "Has Role"}:
		return "roles/permissions"
	if doctype in {"Page", "Report", "Workspace", "Workspace Sidebar"}:
		return "dashboards/reports/sidebar"
	if "coreedge" in text:
		return "CoreEdge activation/branding/settings"
	return "clinical records"


def build_matrix(audit: dict[str, Any], excluded: list[dict[str, Any]], redaction_count: int, samples: dict[str, int]) -> list[dict[str, Any]]:
	excluded_map = {row.get("doctype"): row for row in excluded}
	rows: list[dict[str, Any]] = []
	for row in sorted(audit.get("doctypes") or [], key=lambda item: item.get("doctype") or ""):
		doctype = row.get("doctype") or ""
		is_excluded = doctype in excluded_map
		is_redacted = samples.get(doctype, 0) > 0 and redaction_count > 0
		category = row.get("category") or ""
		rows.append(
			{
				"area": area_for_doctype(doctype),
				"source": "Phase 2D audit / Phase 2F rehearsal",
				"category": category,
				"doctype": doctype,
				"source_count": row.get("record_count"),
				"sample_count": samples.get(doctype, 0),
				"excluded": str(is_excluded).lower(),
				"redacted": str(is_redacted).lower(),
				"risk_level": risk_level(category, is_excluded, is_redacted),
				"review_required": str(is_excluded or category != "directly_portable" or is_redacted).lower(),
				"reviewer_notes": "",
			}
		)
	return rows


def readiness_status(matrix: list[dict[str, Any]], warnings: list[str]) -> tuple[str, int]:
	high = sum(1 for row in matrix if row["risk_level"] == "high")
	medium = sum(1 for row in matrix if row["risk_level"] == "medium")
	score = max(0, 100 - high * 6 - medium * 2 - len(warnings) * 3)
	if high or warnings:
		return "needs_review", score
	if medium:
		return "conditionally_ready_for_staging_review", score
	return "ready_for_staging_review", score


def build_summary(audit: dict[str, Any], package_manifest: dict[str, Any], rehearsal_summary: dict[str, Any], redaction_report: dict[str, Any], excluded: list[dict[str, Any]], warnings: list[str], matrix: list[dict[str, Any]]) -> dict[str, Any]:
	status, score = readiness_status(matrix, warnings)
	missing_review_items = sorted({row["area"] for row in matrix if row["review_required"] == "true"})
	return {
		"notice": STAGING_NOTICE,
		"audit_category_counts": audit.get("category_counts") or {},
		"package_doctype_file_counts": package_manifest.get("doctype_file_counts") or {},
		"rehearsal": {
			"allowed_sample_doctype_count": rehearsal_summary.get("allowed_sample_doctype_count"),
			"excluded_doctype_count": rehearsal_summary.get("excluded_doctype_count"),
			"business_data_mutated": rehearsal_summary.get("business_data_mutated"),
			"import_behavior_included": rehearsal_summary.get("import_behavior_included"),
		},
		"sample_counts": {row["doctype"]: row["sample_count"] for row in matrix if row["sample_count"]},
		"excluded_doctypes": excluded,
		"dangerous_doctypes": sorted(DANGEROUS_BASELINE | {row.get("doctype") for row in excluded if row.get("doctype")}),
		"redaction_count": redaction_report.get("count", 0),
		"validation_warnings": warnings,
		"missing_review_items": missing_review_items,
		"readiness_status": status,
		"readiness_score": score,
	}


def readme() -> str:
	return f"""# VetEdge Staging Review Package

{STAGING_NOTICE}

This package is for human migration readiness review only. It includes reconciliation summaries, checklists, warnings, and CSV review matrices.

No import behavior is included. No clone generation is included. No SQL, shell, or import scripts are generated.

Phase 2F sample files, when present, are redacted and sample-limited. Dangerous/system DocTypes are excluded from row sampling.
"""


def checklist() -> str:
	lines = ["# Staging Review Checklist", "", STAGING_NOTICE, ""]
	for section in CHECKLIST_SECTIONS:
		lines.extend([f"## {section.title()}", "", "- [ ] Reviewed", "- [ ] Exceptions documented", "- [ ] Sign-off captured", ""])
	return "\n".join(lines)


def warnings_markdown(warnings: list[str]) -> str:
	lines = ["# Staging Rehearsal Warnings", "", STAGING_NOTICE, ""]
	if not warnings:
		lines.append("No validation warnings were reported.")
	else:
		for warning in warnings:
			lines.append(f"- {warning}")
	return "\n".join(lines) + "\n"


def manual_review_rows() -> list[dict[str, str]]:
	return [
		{"area": area, "reason": "Human review required before any future migration/import behavior.", "reviewer_notes": ""}
		for area in MANUAL_REVIEW_AREAS
	]


def dangerous_rows(excluded: list[dict[str, Any]]) -> list[dict[str, str]]:
	seen = {row.get("doctype") for row in excluded}
	rows = [
		{"doctype": row.get("doctype") or "", "category": row.get("category") or "", "reason": row.get("reason") or "", "reviewer_notes": ""}
		for row in excluded
	]
	for doctype in sorted(DANGEROUS_BASELINE - seen):
		rows.append({"doctype": doctype, "category": "baseline_dangerous_or_dependency", "reason": "Must not auto-migrate without explicit review.", "reviewer_notes": ""})
	return sorted(rows, key=lambda row: row["doctype"])


def cutover_questions() -> str:
	lines = ["# Cutover Questions", "", STAGING_NOTICE, ""]
	for question in CUTOVER_QUESTIONS:
		lines.append(f"- [ ] {question}")
	return "\n".join(lines) + "\n"


def write_json(path: Path, payload: Any) -> None:
	path.parent.mkdir(parents=True, exist_ok=True)
	path.write_text(json.dumps(payload, indent=2, sort_keys=True, default=str), encoding="utf-8")


def write_csv(path: Path, columns: list[str], rows: list[dict[str, Any]]) -> None:
	path.parent.mkdir(parents=True, exist_ok=True)
	with path.open("w", encoding="utf-8", newline="") as handle:
		writer = csv.DictWriter(handle, fieldnames=columns)
		writer.writeheader()
		for row in rows:
			writer.writerow({column: row.get(column, "") for column in columns})


def generate_review_package(audit_json: Path, migration_package_dir: Path, rehearsal_dir: Path, output_dir: Path) -> dict[str, Any]:
	audit = load_json(audit_json)
	package_manifest = load_json(migration_package_dir / "manifest.json")
	rehearsal_summary = load_json(rehearsal_dir / "rehearsal_summary.json")
	redaction_report = read_optional_json(rehearsal_dir / "redaction_report.json", {"count": 0, "redactions": []})
	excluded = read_optional_json(rehearsal_dir / "excluded_doctypes.json", [])
	warnings_payload = read_optional_json(rehearsal_dir / "validation_warnings.json", {"warnings": []})
	warnings = warnings_payload.get("warnings") or []
	samples = sample_counts(rehearsal_dir)
	matrix = build_matrix(audit, excluded, redaction_report.get("count", 0), samples)
	summary = build_summary(audit, package_manifest, rehearsal_summary, redaction_report, excluded, warnings, matrix)

	output_dir.mkdir(parents=True, exist_ok=True)
	(output_dir / "README.md").write_text(readme(), encoding="utf-8")
	(output_dir / "review_checklist.md").write_text(checklist(), encoding="utf-8")
	write_json(output_dir / "reconciliation_summary.json", summary)
	write_csv(output_dir / "reconciliation_matrix.csv", MATRIX_COLUMNS, matrix)
	(output_dir / "warnings.md").write_text(warnings_markdown(warnings), encoding="utf-8")
	write_csv(output_dir / "manual_review_items.csv", ["area", "reason", "reviewer_notes"], manual_review_rows())
	write_csv(output_dir / "dangerous_exclusions.csv", ["doctype", "category", "reason", "reviewer_notes"], dangerous_rows(excluded))
	(output_dir / "cutover_questions.md").write_text(cutover_questions(), encoding="utf-8")
	return summary


def validate_no_forbidden_outputs(output_dir: Path) -> list[str]:
	if not output_dir.exists():
		return []
	warnings = []
	for path in output_dir.rglob("*"):
		if path.is_file() and (path.suffix in {".sql", ".sh"} or path.name in {"import.py", "restore.py", "migrate.py"}):
			warnings.append(str(path))
	return warnings


def print_summary(output_dir: Path, summary: dict[str, Any], verbose: bool) -> None:
	print("VetEdge staging review package")
	print(f"Output directory: {output_dir}")
	print(f"Readiness status: {summary['readiness_status']}")
	print(f"Readiness score: {summary['readiness_score']}")
	print(f"Redaction count: {summary['redaction_count']}")
	print(f"Validation warnings: {len(summary['validation_warnings'])}")
	print(f"Missing review areas: {len(summary['missing_review_items'])}")
	if verbose:
		for warning in summary["validation_warnings"]:
			print(f"  - {warning}")


def parse_args() -> argparse.Namespace:
	parser = argparse.ArgumentParser(description="Generate VetEdge staging review package artifacts.")
	parser.add_argument("--audit-json", required=True)
	parser.add_argument("--migration-package-dir", required=True)
	parser.add_argument("--rehearsal-dir", required=True)
	parser.add_argument("--output-dir", required=True)
	parser.add_argument("--format", choices=["json", "csv", "markdown"], action="append")
	parser.add_argument("--verbose", action="store_true")
	parser.add_argument("--write", action="store_true")
	args = parser.parse_args()
	if args.write:
		parser.error(WRITE_DISABLED_MESSAGE)
	return args


def main() -> int:
	args = parse_args()
	output_dir = Path(args.output_dir)
	summary = generate_review_package(
		Path(args.audit_json),
		Path(args.migration_package_dir),
		Path(args.rehearsal_dir),
		output_dir,
	)
	forbidden = validate_no_forbidden_outputs(output_dir)
	if forbidden:
		raise RuntimeError(f"Forbidden output files generated: {forbidden}")
	print_summary(output_dir, summary, args.verbose)
	return 0


if __name__ == "__main__":
	raise SystemExit(main())
