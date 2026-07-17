#!/usr/bin/env python3
"""Controlled staging export rehearsal for VetEdge migration review.

Default behavior is dry-run / manifest-only. Redacted row samples are exported
only when --include-row-samples is explicitly supplied. No import behavior,
clone generation, or business-data mutation is included.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
from pathlib import Path
from typing import Any


WRITE_DISABLED_MESSAGE = "write mode intentionally disabled for staging export rehearsal"
STAGING_NOTICE = "STAGING REVIEW ONLY — NOT AN IMPORT PACKAGE"

CATEGORY_DIRECT = "directly_portable"
CATEGORY_DANGEROUS = "dangerous_do_not_auto_migrate"
CATEGORY_ERPNEXT = "erpnext_native_dependency"

HARD_EXCLUDED_DOCTYPES = {
	"Patch Log",
	"GL Entry",
	"Stock Ledger Entry",
	"DocField",
	"DocPerm",
	"Module Def",
	"Role",
	"Has Role",
	"Workspace",
	"Page",
	"Installed Applications",
	"DocType",
	"DocShare",
	"DocField",
	"DocPerm",
}

SENSITIVE_FIELD_PATTERNS = [
	re.compile(pattern, re.I)
	for pattern in (
		r"email",
		r"phone",
		r"mobile",
		r"address",
		r"contact",
		r"secret",
		r"token",
		r"key",
		r"password",
		r"auth",
		r"credential",
		r"webhook",
		r"api",
		r"provider",
		r"comment",
		r"note",
	)
]

SAFE_SYSTEM_FIELDS = {"name", "owner", "creation", "modified", "modified_by", "docstatus", "idx"}
FILE_METADATA_FIELDS = {"name", "file_name", "attached_to_doctype", "attached_to_name", "file_url", "is_private"}


def parse_args() -> argparse.Namespace:
	parser = argparse.ArgumentParser(description="Controlled staging export rehearsal for VetEdge data migration.")
	parser.add_argument("--site", help="Frappe site name for optional sample reads.")
	parser.add_argument("--audit-json", required=True, help="Phase 2D audit JSON path.")
	parser.add_argument("--package-dir", required=True, help="Phase 2E package directory.")
	parser.add_argument("--output-dir", help="Directory for rehearsal report files.")
	parser.add_argument("--sample-limit", type=int, default=2, help="Maximum records per directly-portable DocType.")
	parser.add_argument("--include-row-samples", action="store_true", help="Export small redacted JSONL row samples.")
	parser.add_argument("--redact-sensitive", action="store_true", help="Redact sensitive fields in row samples.")
	parser.add_argument("--dry-run", action="store_true", default=True, help="Manifest/count mode; enabled by default.")
	parser.add_argument("--verbose", action="store_true", help="Print detailed summary.")
	parser.add_argument("--write", action="store_true", help="Intentionally disabled.")
	args = parser.parse_args()
	if args.write:
		parser.error(WRITE_DISABLED_MESSAGE)
	if args.sample_limit < 0:
		parser.error("--sample-limit must be non-negative")
	if args.include_row_samples and not args.site:
		parser.error("--site is required when --include-row-samples is used")
	return args


def load_json(path: str | Path) -> dict[str, Any]:
	target = Path(path)
	if not target.exists():
		raise FileNotFoundError(f"Required file not found: {target}")
	return json.loads(target.read_text(encoding="utf-8"))


def validate_audit(audit: dict[str, Any]) -> list[str]:
	warnings = []
	for key in ("mode", "category_counts", "doctypes"):
		if key not in audit:
			warnings.append(f"Audit JSON missing expected key: {key}")
	if not isinstance(audit.get("doctypes"), list):
		warnings.append("Audit JSON doctypes must be a list.")
	return warnings


def validate_package(package_dir: Path) -> tuple[dict[str, Any], list[str]]:
	manifest_path = package_dir / "manifest.json"
	if not manifest_path.exists():
		raise FileNotFoundError(f"Package manifest not found: {manifest_path}")
	manifest = load_json(manifest_path)
	warnings = []
	if manifest.get("mode") != "manifest_templates_samples_only":
		warnings.append("Package manifest mode is not manifest_templates_samples_only.")
	if manifest.get("import_behavior_included"):
		warnings.append("Package manifest indicates import behavior; this is not allowed.")
	if manifest.get("business_row_payload_exported"):
		warnings.append("Package manifest indicates business rows already exported.")
	return manifest, warnings


def audit_doctype_rows(audit: dict[str, Any]) -> list[dict[str, Any]]:
	return sorted(audit.get("doctypes") or [], key=lambda row: row.get("doctype") or "")


def directly_portable_doctypes(audit: dict[str, Any]) -> list[str]:
	return [
		row["doctype"]
		for row in audit_doctype_rows(audit)
		if row.get("category") == CATEGORY_DIRECT and row.get("doctype") not in HARD_EXCLUDED_DOCTYPES
	]


def excluded_doctypes(audit: dict[str, Any]) -> list[dict[str, Any]]:
	excluded = []
	for row in audit_doctype_rows(audit):
		doctype = row.get("doctype")
		category = row.get("category")
		if doctype in HARD_EXCLUDED_DOCTYPES or category in {CATEGORY_DANGEROUS, CATEGORY_ERPNEXT}:
			excluded.append(
				{
					"doctype": doctype,
					"category": category,
					"reason": "Hard-excluded or dependency-only; never exported by staging rehearsal.",
				}
			)
	return excluded


def export_plan(audit: dict[str, Any], include_row_samples: bool, sample_limit: int) -> dict[str, Any]:
	allowed = directly_portable_doctypes(audit)
	return {
		"notice": STAGING_NOTICE,
		"mode": "redacted_sample_rows" if include_row_samples else "manifest_only_no_rows",
		"include_row_samples": include_row_samples,
		"sample_limit": sample_limit,
		"allowed_sample_doctypes": allowed,
		"excluded_doctypes": excluded_doctypes(audit),
		"forbidden_doctypes": sorted(HARD_EXCLUDED_DOCTYPES),
		"import_files_created": False,
		"destructive_commands": [],
	}


def is_sensitive_field(fieldname: str, fieldtype: str | None = None) -> bool:
	if fieldtype and fieldtype.lower() == "password":
		return True
	if fieldname in SAFE_SYSTEM_FIELDS:
		return False
	return any(pattern.search(fieldname) for pattern in SENSITIVE_FIELD_PATTERNS)


def redact_record(
	record: dict[str, Any],
	fieldtypes: dict[str, str] | None = None,
	redact_sensitive: bool = True,
) -> tuple[dict[str, Any], list[dict[str, str]]]:
	fieldtypes = fieldtypes or {}
	redacted: dict[str, Any] = {}
	report: list[dict[str, str]] = []
	for fieldname, value in record.items():
		if redact_sensitive and is_sensitive_field(fieldname, fieldtypes.get(fieldname)):
			redacted[fieldname] = "[REDACTED]"
			report.append({"fieldname": fieldname, "reason": "sensitive field"})
		else:
			redacted[fieldname] = value
	return redacted, report


def infer_sites_path(site: str) -> Path | None:
	cwd_site = Path.cwd() / "sites" / site
	if cwd_site.is_dir():
		return cwd_site.parent
	for parent in Path(__file__).resolve().parents:
		candidate = parent / "sites" / site
		if candidate.is_dir():
			return candidate.parent
	return None


def connect_frappe(site: str):
	try:
		import frappe
	except ImportError as exc:
		raise RuntimeError("Frappe is required for row samples. Run through bench or the bench virtualenv.") from exc
	sites_path = infer_sites_path(site)
	if sites_path:
		os.chdir(sites_path)
		frappe.init(site=site, sites_path=".")
	else:
		frappe.init(site=site)
	frappe.connect()
	return frappe


def get_sample_fields(frappe, doctype: str) -> tuple[list[str], dict[str, str]]:
	meta = frappe.get_meta(doctype)
	fields = ["name", "owner", "creation", "modified", "docstatus"]
	fieldtypes = {field: "Data" for field in fields}
	for field in meta.fields:
		if not field.fieldname:
			continue
		if field.fieldtype in {"Table", "Table MultiSelect", "Section Break", "Column Break", "HTML", "Button"}:
			continue
		fields.append(field.fieldname)
		fieldtypes[field.fieldname] = field.fieldtype
	return sorted(set(fields)), fieldtypes


def sample_rows(site: str, doctypes: list[str], sample_limit: int, redact_sensitive: bool) -> tuple[dict[str, list[dict[str, Any]]], list[dict[str, Any]], list[str]]:
	frappe = connect_frappe(site)
	samples: dict[str, list[dict[str, Any]]] = {}
	redactions: list[dict[str, Any]] = []
	warnings: list[str] = []
	try:
		for doctype in doctypes:
			try:
				if not frappe.db.exists("DocType", doctype):
					warnings.append(f"DocType missing on site: {doctype}")
					continue
				fields, fieldtypes = get_sample_fields(frappe, doctype)
				try:
					rows = frappe.get_all(doctype, fields=fields, limit=sample_limit, order_by="modified desc")
				except Exception as exc:
					warnings.append(f"Could not sample full field set for {doctype}; fell back to name-only sample: {exc}")
					fields = ["name"]
					fieldtypes = {"name": "Data"}
					rows = frappe.get_all(doctype, fields=fields, limit=sample_limit, order_by="modified desc")
				samples[doctype] = []
				for row in rows:
					clean, report = redact_record(dict(row), fieldtypes, redact_sensitive=redact_sensitive)
					samples[doctype].append(clean)
					for item in report:
						redactions.append({"doctype": doctype, "record": clean.get("name"), **item})
			except Exception as exc:
				warnings.append(f"Could not sample {doctype}: {exc}")
	finally:
		try:
			frappe.destroy()
		except Exception:
			pass
	return samples, redactions, warnings


def build_rehearsal(
	audit: dict[str, Any],
	package_manifest: dict[str, Any],
	include_row_samples: bool = False,
	sample_limit: int = 2,
) -> dict[str, Any]:
	plan = export_plan(audit, include_row_samples, sample_limit)
	return {
		"notice": STAGING_NOTICE,
		"mode": "staging_export_rehearsal",
		"source_site": audit.get("site"),
		"package_mode": package_manifest.get("mode"),
		"include_row_samples": include_row_samples,
		"sample_limit": sample_limit,
		"allowed_sample_doctype_count": len(plan["allowed_sample_doctypes"]),
		"excluded_doctype_count": len(plan["excluded_doctypes"]),
		"business_data_mutated": False,
		"import_behavior_included": False,
	}


def write_json(path: Path, payload: Any) -> None:
	path.parent.mkdir(parents=True, exist_ok=True)
	path.write_text(json.dumps(payload, indent=2, sort_keys=True, default=str), encoding="utf-8")


def write_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
	path.parent.mkdir(parents=True, exist_ok=True)
	with path.open("w", encoding="utf-8") as handle:
		for row in rows:
			handle.write(json.dumps(row, sort_keys=True, default=str) + "\n")


def write_outputs(
	output_dir: Path,
	summary: dict[str, Any],
	plan: dict[str, Any],
	redactions: list[dict[str, Any]],
	excluded: list[dict[str, Any]],
	warnings: list[str],
	samples: dict[str, list[dict[str, Any]]] | None = None,
) -> None:
	output_dir.mkdir(parents=True, exist_ok=True)
	write_json(output_dir / "rehearsal_summary.json", summary)
	write_json(output_dir / "export_plan.json", plan)
	write_json(output_dir / "redaction_report.json", {"redactions": redactions, "count": len(redactions)})
	write_json(output_dir / "excluded_doctypes.json", excluded)
	write_json(output_dir / "validation_warnings.json", {"warnings": warnings})
	if samples:
		for doctype, rows in samples.items():
			write_jsonl(output_dir / "samples" / f"{doctype}.jsonl", rows)


def validate_no_import_files(output_dir: Path) -> list[str]:
	if not output_dir.exists():
		return []
	bad_suffixes = {".sql"}
	bad_names = {"import.py", "import.sh", "restore.py", "migrate.py"}
	warnings = []
	for path in output_dir.rglob("*"):
		if path.is_file() and (path.name in bad_names or path.suffix in bad_suffixes):
			warnings.append(f"Import/destructive-looking file is not allowed: {path}")
	return warnings


def print_summary(summary: dict[str, Any], plan: dict[str, Any], redaction_count: int, warnings: list[str], verbose: bool) -> None:
	print("VetEdge staging export rehearsal")
	print(summary["notice"])
	print(f"Mode: {plan['mode']}")
	print(f"Allowed sample DocTypes: {summary['allowed_sample_doctype_count']}")
	print(f"Excluded DocTypes: {summary['excluded_doctype_count']}")
	print(f"Sample limit: {summary['sample_limit']}")
	print(f"Business data mutated: {summary['business_data_mutated']}")
	print(f"Import behavior included: {summary['import_behavior_included']}")
	print(f"Redactions: {redaction_count}")
	if verbose and warnings:
		print("Validation warnings:")
		for warning in warnings:
			print(f"  - {warning}")


def main() -> int:
	args = parse_args()
	audit = load_json(args.audit_json)
	package_manifest = load_json(Path(args.package_dir) / "manifest.json")
	warnings = []
	warnings.extend(validate_audit(audit))
	if package_manifest.get("mode") != "manifest_templates_samples_only":
		warnings.append("Package manifest mode is not manifest_templates_samples_only.")

	plan = export_plan(audit, args.include_row_samples, args.sample_limit)
	summary = build_rehearsal(audit, package_manifest, args.include_row_samples, args.sample_limit)
	samples: dict[str, list[dict[str, Any]]] = {}
	redactions: list[dict[str, Any]] = []

	if args.include_row_samples:
		samples, redactions, sample_warnings = sample_rows(
			args.site,
			plan["allowed_sample_doctypes"],
			args.sample_limit,
			redact_sensitive=args.redact_sensitive,
		)
		warnings.extend(sample_warnings)

	output_dir = Path(args.output_dir) if args.output_dir else None
	if output_dir:
		warnings.extend(validate_no_import_files(output_dir))
		write_outputs(output_dir, summary, plan, redactions, plan["excluded_doctypes"], warnings, samples)

	print_summary(summary, plan, len(redactions), warnings, args.verbose)
	return 0


if __name__ == "__main__":
	raise SystemExit(main())
