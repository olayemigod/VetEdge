#!/usr/bin/env python3
"""Build a read-only VetEdge staging migration package skeleton.

The package contains manifests, mapping templates, and schema/sample CSV files
derived from the Phase 2D audit report. It does not export business row payloads
and does not provide any import/write behavior.
"""

from __future__ import annotations

import argparse
import csv
import json
import sys
from pathlib import Path
from typing import Any


WRITE_DISABLED_MESSAGE = "write mode intentionally disabled for migration package planning"

MAPPING_COLUMNS = [
	"source_value",
	"target_value",
	"source_doctype",
	"target_doctype",
	"source_name",
	"target_name",
	"confidence",
	"migration_action",
	"notes",
	"reviewed_by",
	"reviewed_on",
]

MIGRATION_ACTIONS = ["preserve", "map", "create_if_missing", "skip", "manual_review", "blocked"]

MAPPING_TEMPLATE_NAMES = [
	"company_mapping.template.csv",
	"branch_mapping.template.csv",
	"warehouse_mapping.template.csv",
	"item_mapping.template.csv",
	"customer_owner_mapping.template.csv",
	"user_mapping.template.csv",
	"role_mapping.template.csv",
	"cost_center_mapping.template.csv",
	"price_list_mapping.template.csv",
	"route_mapping.template.csv",
	"file_mapping.template.csv",
]

SAMPLE_DOCTYPES = [
	"Veterinary Patient",
	"Veterinary Appointment",
	"Veterinary Consultation",
	"Veterinary Lab Order",
	"Veterinary Vaccination",
	"Veterinary Hospitalisation",
]

SAMPLE_COLUMNS = {
	"Veterinary Patient": ["name", "patient_name", "owner", "species", "breed", "default_branch", "migration_notes"],
	"Veterinary Appointment": ["name", "patient", "owner", "appointment_datetime", "branch", "status", "migration_notes"],
	"Veterinary Consultation": ["name", "patient", "appointment", "service_branch", "practitioner", "status", "migration_notes"],
	"Veterinary Lab Order": ["name", "patient", "consultation", "branch", "status", "migration_notes"],
	"Veterinary Vaccination": ["name", "patient", "vaccine", "vaccination_date", "branch", "migration_notes"],
	"Veterinary Hospitalisation": ["name", "patient", "admission_datetime", "care_location", "status", "migration_notes"],
}

DANGEROUS_NEVER_AUTO_MIGRATE = [
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
]

CATEGORY_FILES = {
	"directly_portable": "directly_portable.json",
	"portable_with_mapping": "requires_mapping.json",
	"requires_manual_review": "requires_manual_review.json",
	"dangerous_do_not_auto_migrate": "dangerous_excluded.json",
	"erpnext_native_dependency": "erpnext_native_dependencies.json",
}

DEPENDENCY_ONLY_DOCTYPES = {
	"Sales Invoice",
	"Sales Invoice Item",
	"Payment Entry",
	"Stock Entry",
	"GL Entry",
	"Stock Ledger Entry",
	"Company",
	"Account",
	"Cost Center",
	"Item",
	"Warehouse",
	"Batch",
	"Price List",
	"Item Price",
}


def parse_args() -> argparse.Namespace:
	parser = argparse.ArgumentParser(description="Build a read-only VetEdge migration package skeleton.")
	parser.add_argument("--audit-json", required=True, help="Phase 2D audit JSON path.")
	parser.add_argument("--export-manifest", help="Optional Phase 2D export manifest path.")
	parser.add_argument("--output-dir", required=True, help="Package output directory.")
	parser.add_argument("--site", help="Optional site label to record in package metadata only.")
	parser.add_argument("--write", action="store_true", help="Intentionally disabled.")
	args = parser.parse_args()
	if args.write:
		parser.error(WRITE_DISABLED_MESSAGE)
	return args


def load_json(path: str | Path) -> dict[str, Any]:
	return json.loads(Path(path).read_text(encoding="utf-8"))


def sorted_doctypes(audit: dict[str, Any]) -> list[dict[str, Any]]:
	return sorted(audit.get("doctypes") or [], key=lambda row: row.get("doctype") or "")


def doctype_rows_by_category(audit: dict[str, Any]) -> dict[str, list[dict[str, Any]]]:
	grouped = {category: [] for category in CATEGORY_FILES}
	for row in sorted_doctypes(audit):
		category = row.get("category")
		if category in grouped:
			grouped[category].append(summarize_doctype_row(row))
	return grouped


def summarize_doctype_row(row: dict[str, Any]) -> dict[str, Any]:
	doctype = row.get("doctype")
	return {
		"doctype": doctype,
		"category": row.get("category"),
		"record_count": row.get("record_count"),
		"reason": row.get("reason"),
		"dependency_only": doctype in DEPENDENCY_ONLY_DOCTYPES or row.get("category") == "erpnext_native_dependency",
		"finding_count": len(row.get("findings") or []),
	}


def package_manifest(audit: dict[str, Any], export_manifest: dict[str, Any] | None, site: str | None) -> dict[str, Any]:
	grouped = doctype_rows_by_category(audit)
	return {
		"package_type": "vetedge_staging_migration_planning_package",
		"mode": "manifest_templates_samples_only",
		"site": site or audit.get("site"),
		"source_audit_site": audit.get("site"),
		"business_row_payload_exported": False,
		"import_behavior_included": False,
		"destructive_operations": [],
		"migration_actions": MIGRATION_ACTIONS,
		"category_counts": audit.get("category_counts") or {},
		"doctype_file_counts": {category: len(rows) for category, rows in grouped.items()},
		"mapping_templates": MAPPING_TEMPLATE_NAMES,
		"sample_files": [f"{doctype}.sample.csv" for doctype in SAMPLE_DOCTYPES],
		"proposed_migration_order": audit.get("proposed_migration_order") or [],
		"missing_mapping_requirements": audit.get("missing_mapping_requirements") or [],
		"source_export_manifest_mode": (export_manifest or {}).get("mode"),
		"warnings": [
			"No import or write behavior is included.",
			"No submitted ERPNext accounting or stock internals should be rewritten.",
			"Dangerous and manual-review records require explicit staging decisions.",
		],
	}


def readme_text(manifest: dict[str, Any]) -> str:
	never = ", ".join(DANGEROUS_NEVER_AUTO_MIGRATE)
	actions = ", ".join(MIGRATION_ACTIONS)
	order = "\n".join(f"{idx}. {item}" for idx, item in enumerate(manifest["proposed_migration_order"], start=1))
	return f"""# VetEdge Staging Migration Package

This package is a planning artifact for a future Veterinary downstream migration rehearsal.
It contains manifests, mapping templates, and sample CSV schemas only.

It does not contain full business row payloads, import behavior, clone-generation behavior, or destructive operations.

## What Can Migrate Directly

Records listed under `doctypes/directly_portable.json` use Veterinary/domain-generic DocType names and may be portable after link validation.

## What Needs Mapping

Records listed under `doctypes/requires_mapping.json` and the CSV files in `mappings/` require explicit source-to-target decisions.
Supported migration actions are: {actions}.

## What Requires Manual Review

Review `doctypes/requires_manual_review.json` before any staging rehearsal. This includes users, roles, portal records, email templates, workspaces, pages, reports, notifications, print formats, and other presentation/configuration records.

## What Must Never Auto-Migrate

Do not auto-migrate or rewrite these without explicit engineering review: {never}.
Patch lineage, app/module identity, submitted accounting internals, submitted stock internals, and production routes are not safe for automated migration.

## ERPNext Dependencies

Records under `doctypes/erpnext_native_dependencies.json` are dependency-only. Company, Account, Customer, Item, Warehouse, Sales Invoice, Payment Entry, Stock Entry, Batch, Price List, Cost Center, and related records must remain governed by ERPNext migration and reconciliation rules.

## Staging Rehearsal Order

{order}

## Staging Rules

1. Run this package against staging first.
2. Complete every mapping template before any import rehearsal exists.
3. Validate owners, companies, branches, cost centers, items, warehouses, users, roles, routes, and files.
4. Do not rewrite submitted Sales Invoice, Payment Entry, Stock Entry, GL Entry, or Stock Ledger Entry internals.
5. Review CoreEdge activation, branding, wallet, SMS, email, WhatsApp, and service settings separately.
"""


def write_json(path: Path, payload: Any) -> None:
	path.parent.mkdir(parents=True, exist_ok=True)
	path.write_text(json.dumps(payload, indent=2, sort_keys=True, default=str), encoding="utf-8")


def write_csv(path: Path, columns: list[str], rows: list[dict[str, Any]] | None = None) -> None:
	path.parent.mkdir(parents=True, exist_ok=True)
	with path.open("w", encoding="utf-8", newline="") as handle:
		writer = csv.DictWriter(handle, fieldnames=columns)
		writer.writeheader()
		for row in rows or []:
			writer.writerow({column: row.get(column, "") for column in columns})


def write_package(audit: dict[str, Any], export_manifest: dict[str, Any] | None, output_dir: Path, site: str | None = None) -> dict[str, Any]:
	manifest = package_manifest(audit, export_manifest, site)
	grouped = doctype_rows_by_category(audit)

	output_dir.mkdir(parents=True, exist_ok=True)
	write_json(output_dir / "manifest.json", manifest)
	(output_dir / "README.md").write_text(readme_text(manifest), encoding="utf-8")

	for category, filename in CATEGORY_FILES.items():
		write_json(output_dir / "doctypes" / filename, grouped.get(category) or [])

	for filename in MAPPING_TEMPLATE_NAMES:
		write_csv(output_dir / "mappings" / filename, MAPPING_COLUMNS)

	for doctype in SAMPLE_DOCTYPES:
		write_csv(output_dir / "samples" / f"{doctype}.sample.csv", SAMPLE_COLUMNS[doctype])

	return manifest


def print_summary(output_dir: Path, manifest: dict[str, Any]) -> None:
	print("VetEdge migration package planning output")
	print(f"Output directory: {output_dir}")
	print(f"Mode: {manifest['mode']}")
	print(f"Business row payload exported: {manifest['business_row_payload_exported']}")
	print(f"Import behavior included: {manifest['import_behavior_included']}")
	print("Doctype file counts:")
	for category, count in manifest["doctype_file_counts"].items():
		print(f"  - {category}: {count}")


def main() -> int:
	args = parse_args()
	audit = load_json(args.audit_json)
	export_manifest = load_json(args.export_manifest) if args.export_manifest else None
	output_dir = Path(args.output_dir)
	manifest = write_package(audit, export_manifest, output_dir, site=args.site)
	print_summary(output_dir, manifest)
	return 0


if __name__ == "__main__":
	raise SystemExit(main())
