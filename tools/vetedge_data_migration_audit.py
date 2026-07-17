#!/usr/bin/env python3
"""Read-only VetEdge data migration readiness audit.

This tool inspects how existing VetEdge site data could later be migrated to a
future Veterinary downstream app. It never writes business records and never
exports row payloads; the optional manifest is a review plan only.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


WRITE_DISABLED_MESSAGE = "write mode intentionally disabled for data migration audit"

CATEGORY_DIRECT = "directly_portable"
CATEGORY_MAPPING = "portable_with_mapping"
CATEGORY_MANUAL = "requires_manual_review"
CATEGORY_DANGEROUS = "dangerous_do_not_auto_migrate"
CATEGORY_PLATFORM = "platform_coreedge_dependent"
CATEGORY_ERPNEXT = "erpnext_native_dependency"

RISK_PATTERNS = {
	"lowercase_app": re.compile(r"vetedge"),
	"title_app": re.compile(r"VetEdge"),
	"asset_url": re.compile(r"/assets/vetedge"),
	"desk_route": re.compile(r"/desk/vetedge"),
	"portal_route": re.compile(r"/vetedge_portal|/vetedge_guest_booking"),
	"dotted_path": re.compile(r"\bvetedge\.[A-Za-z0-9_.]+"),
}

VETERINARY_DOCTYPES = {
	"Veterinary Patient",
	"Veterinary Appointment",
	"Veterinary Consultation",
	"Veterinary Hospitalisation",
	"Veterinary Vital Signs",
	"Veterinary Notification Item",
	"Veterinary Notification Preference",
	"Veterinary Missed Appointment",
	"Veterinary Lab Order",
	"Veterinary Lab Test",
	"Veterinary Vaccination Record",
	"Veterinary Vaccination Schedule",
	"Veterinary Hospitalisation Activity",
	"Veterinary Hospitalisation Charge Item",
	"Veterinary Care Location",
	"Veterinary Care Location Occupancy Log",
	"Pet Grooming Appointment",
	"Pet Grooming Session",
	"Pet Boarding Booking",
	"Pet Boarding Stay",
	"Pet Boarding Care Record",
	"Kennel",
}

ERPNEXT_DEPENDENCY_DOCTYPES = {
	"Company",
	"Customer",
	"Item",
	"Warehouse",
	"Sales Invoice",
	"Sales Invoice Item",
	"Payment Entry",
	"Stock Entry",
	"Batch",
	"Price List",
	"Item Price",
	"Cost Center",
	"Account",
	"Branch",
}

FRAPPE_MANUAL_REVIEW_DOCTYPES = {
	"User",
	"Role",
	"Has Role",
	"File",
	"Communication",
	"Comment",
	"ToDo",
	"Version",
	"Email Template",
	"Workspace",
	"Workspace Sidebar",
	"Page",
	"Report",
	"Module Def",
	"Portal Settings",
	"Print Format",
	"Notification",
	"Notification Log",
	"Client Script",
	"Server Script",
	"Web Form",
	"Custom Field",
	"Property Setter",
}

DANGEROUS_DOCTYPES = {
	"Patch Log",
	"Installed Applications",
	"DocType",
	"DocField",
	"DocPerm",
	"Module Def",
}

PLATFORM_KEYWORDS = (
	"CoreEdge",
	"coreedge",
	"Product Activation",
	"Tenant",
	"Branding",
	"SMS",
	"WhatsApp",
	"Wallet",
	"EdgeFinder",
)

PROPOSED_MIGRATION_ORDER = [
	"ERPNext masters",
	"Core clinical masters/settings",
	"Patients/owners",
	"Appointments",
	"Consultations",
	"Vaccinations/preventive care",
	"Lab/grooming/boarding/hospitalisation operational records",
	"Items/stock dependencies",
	"Billing references",
	"Files/attachments",
	"Communications/comments",
	"Notifications/preferences",
	"Portal/email/client branding records",
	"CoreEdge activation/branding/service settings",
]

MAPPING_REQUIREMENTS = [
	"company",
	"branch",
	"cost_center",
	"customer_owner",
	"item",
	"warehouse",
	"price_list",
	"roles",
	"users",
	"files",
	"routes",
	"coreedge_product_distribution",
]


@dataclass
class Finding:
	category: str
	doctype: str
	reason: str
	fieldname: str | None = None
	record: str | None = None
	value: str | None = None
	severity: str = "info"

	def as_dict(self) -> dict[str, Any]:
		return {
			"category": self.category,
			"doctype": self.doctype,
			"fieldname": self.fieldname,
			"record": self.record,
			"value": self.value,
			"reason": self.reason,
			"severity": self.severity,
		}


@dataclass
class DoctypeAudit:
	doctype: str
	category: str
	reason: str
	record_count: int | None = None
	samples: list[str] = field(default_factory=list)
	findings: list[Finding] = field(default_factory=list)

	def as_dict(self) -> dict[str, Any]:
		return {
			"doctype": self.doctype,
			"category": self.category,
			"reason": self.reason,
			"record_count": self.record_count,
			"samples": self.samples,
			"findings": [finding.as_dict() for finding in self.findings],
		}


def parse_args() -> argparse.Namespace:
	parser = argparse.ArgumentParser(description="Read-only VetEdge data migration readiness audit.")
	parser.add_argument("--site", help="Frappe site name to inspect.")
	parser.add_argument("--output-json", help="Write JSON report to this path.")
	parser.add_argument("--verbose", action="store_true", help="Print higher-detail console output.")
	parser.add_argument("--include-counts", action="store_true", help="Include DocType record counts.")
	parser.add_argument("--include-samples", action="store_true", help="Include limited record name samples.")
	parser.add_argument("--sample-limit", type=int, default=5, help="Maximum sample records per DocType.")
	parser.add_argument("--export-manifest", help="Write a read-only export manifest plan.")
	parser.add_argument("--no-data-export", action="store_true", default=True, help="Safe default; no row export is performed.")
	parser.add_argument("--write", action="store_true", help="Intentionally disabled.")
	args = parser.parse_args()
	if args.write:
		parser.error(WRITE_DISABLED_MESSAGE)
	if args.sample_limit < 0:
		parser.error("--sample-limit must be non-negative")
	return args


def classify_doctype(doctype: str, module: str | None = None) -> tuple[str, str]:
	if doctype in DANGEROUS_DOCTYPES:
		return CATEGORY_DANGEROUS, "Frappe/app identity or patch lineage record; do not auto-migrate."
	if doctype in ERPNEXT_DEPENDENCY_DOCTYPES:
		return CATEGORY_ERPNEXT, "ERPNext-native dependency; migrate or map through ERPNext ownership rules."
	if any(keyword.lower() in doctype.lower() for keyword in PLATFORM_KEYWORDS):
		return CATEGORY_PLATFORM, "Platform/CoreEdge/service dependent record."
	if doctype in FRAPPE_MANUAL_REVIEW_DOCTYPES:
		return CATEGORY_MANUAL, "Frappe/platform configuration record requiring manual review."
	if doctype in VETERINARY_DOCTYPES:
		return CATEGORY_DIRECT, "Generic Veterinary domain DocType; directly portable if links resolve."
	if module and module.lower() == "vetedge":
		return CATEGORY_MAPPING, "VetEdge-owned module record; portable only with package/app mapping."
	if doctype.startswith("Veterinary ") or doctype.startswith("Pet ") or doctype == "Kennel":
		return CATEGORY_DIRECT, "Veterinary/domain-generic naming."
	return CATEGORY_MANUAL, "Unregistered DocType; requires migration review."


def detect_string_risks(doctype: str, record: str, fields: dict[str, Any]) -> list[Finding]:
	findings: list[Finding] = []
	for fieldname, value in fields.items():
		if value is None:
			continue
		text = str(value)
		for risk_name, pattern in RISK_PATTERNS.items():
			if pattern.search(text):
				category = CATEGORY_MANUAL
				severity = "medium"
				reason = f"Field contains VetEdge/package-sensitive reference: {risk_name}."
				if risk_name in {"desk_route", "portal_route"}:
					category = CATEGORY_DANGEROUS
					severity = "high"
				elif risk_name == "dotted_path":
					category = CATEGORY_MAPPING
				findings.append(
					Finding(
						category=category,
						doctype=doctype,
						record=record,
						fieldname=fieldname,
						value=text[:240],
						reason=reason,
						severity=severity,
					)
				)
	return findings


def classify_record(doctype: str, record: dict[str, Any], module: str | None = None) -> tuple[str, list[Finding]]:
	category, _reason = classify_doctype(doctype, module=module)
	name = str(record.get("name") or "")
	findings = detect_string_risks(doctype, name, record)
	if doctype in {"Sales Invoice", "Payment Entry", "Stock Entry"} and int(record.get("docstatus") or 0) == 1:
		findings.append(
			Finding(
				category=CATEGORY_DANGEROUS,
				doctype=doctype,
				record=name,
				reason="Submitted financial/stock document internals must not be rewritten directly.",
				severity="high",
			)
		)
	if doctype == "Email Template" and any("VetEdge" in str(value) for value in record.values()):
		findings.append(
			Finding(
				category=CATEGORY_MANUAL,
				doctype=doctype,
				record=name,
				reason="Email template contains VetEdge branding and needs manual review.",
				severity="medium",
			)
		)
	if doctype == "Role" and "VetEdge" in name:
		findings.append(
			Finding(
				category=CATEGORY_MANUAL,
				doctype=doctype,
				record=name,
				reason="Role name contains VetEdge and needs role mapping.",
				severity="medium",
			)
		)
	if any(keyword.lower() in json.dumps(record, default=str).lower() for keyword in ("coreedge", "wallet", "whatsapp")):
		findings.append(
			Finding(
				category=CATEGORY_PLATFORM,
				doctype=doctype,
				record=name,
				reason="Record references CoreEdge/platform service dependency.",
				severity="medium",
			)
		)
	return category, findings


def build_export_manifest(audits: list[DoctypeAudit]) -> dict[str, Any]:
	return {
		"mode": "manifest_only_no_data_export",
		"destructive_operations": [],
		"doctypes": [
			{
				"doctype": audit.doctype,
				"category": audit.category,
				"record_count": audit.record_count,
				"requires_mapping": audit.category
				in {CATEGORY_MAPPING, CATEGORY_MANUAL, CATEGORY_PLATFORM, CATEGORY_ERPNEXT},
			}
			for audit in audits
		],
		"migration_order": PROPOSED_MIGRATION_ORDER,
		"mapping_requirements": MAPPING_REQUIREMENTS,
	}


def connect_frappe(site: str):
	try:
		import frappe
	except ImportError as exc:
		raise RuntimeError("Frappe is required for --site audits. Run through bench or a bench Python environment.") from exc
	cwd_site_path = Path.cwd() / "sites" / site
	if cwd_site_path.is_dir():
		os.chdir(cwd_site_path.parent)
		frappe.init(site=site, sites_path=".")
	else:
		sites_path = infer_sites_path()
		if not sites_path:
			frappe.init(site=site)
		else:
			frappe.init(site=site, sites_path=str(sites_path))
	frappe.connect()
	return frappe


def infer_sites_path() -> Path | None:
	for parent in Path(__file__).resolve().parents:
		candidate = parent / "sites"
		if candidate.is_dir():
			return candidate
	return None


def get_candidate_doctypes(frappe) -> list[str]:
	candidates = set(VETERINARY_DOCTYPES | ERPNEXT_DEPENDENCY_DOCTYPES | FRAPPE_MANUAL_REVIEW_DOCTYPES | DANGEROUS_DOCTYPES)
	try:
		for row in frappe.get_all("DocType", filters={"module": ["in", ["VetEdge", "Veterinary"]]}, fields=["name"]):
			candidates.add(row.name)
	except Exception:
		pass
	return sorted(candidates)


def doctype_exists(frappe, doctype: str) -> bool:
	try:
		return bool(frappe.db.exists("DocType", doctype))
	except Exception:
		return False


def get_doctype_module(frappe, doctype: str) -> str | None:
	try:
		return frappe.db.get_value("DocType", doctype, "module")
	except Exception:
		return None


def get_text_fields(frappe, doctype: str) -> list[str]:
	try:
		meta = frappe.get_meta(doctype)
	except Exception:
		return []
	fieldtypes = {"Data", "Text", "Small Text", "Long Text", "Code", "HTML", "Markdown", "Select", "Link", "Dynamic Link"}
	fields = ["name"]
	for field in meta.fields:
		if field.fieldname and field.fieldtype in fieldtypes:
			fields.append(field.fieldname)
	if getattr(meta, "has_field", None) and meta.has_field("docstatus"):
		fields.append("docstatus")
	return sorted(set(fields))


def get_count(frappe, doctype: str) -> int | None:
	try:
		return int(frappe.db.count(doctype))
	except Exception:
		return None


def get_samples(frappe, doctype: str, fields: list[str], limit: int) -> list[dict[str, Any]]:
	if limit <= 0:
		return []
	try:
		return list(frappe.get_all(doctype, fields=fields, limit=limit, order_by="modified desc"))
	except Exception:
		try:
			return list(frappe.get_all(doctype, fields=["name"], limit=limit))
		except Exception:
			return []


def audit_site(
	site: str,
	include_counts: bool = False,
	include_samples: bool = False,
	sample_limit: int = 5,
) -> dict[str, Any]:
	frappe = connect_frappe(site)
	audits: list[DoctypeAudit] = []
	global_findings: list[Finding] = []
	try:
		for doctype in get_candidate_doctypes(frappe):
			if not doctype_exists(frappe, doctype):
				continue
			module = get_doctype_module(frappe, doctype)
			category, reason = classify_doctype(doctype, module=module)
			audit = DoctypeAudit(doctype=doctype, category=category, reason=reason)
			if include_counts:
				audit.record_count = get_count(frappe, doctype)
			fields = get_text_fields(frappe, doctype)
			if include_samples:
				for record in get_samples(frappe, doctype, fields, sample_limit):
					record_dict = dict(record)
					if record_dict.get("name"):
						audit.samples.append(str(record_dict["name"]))
					_record_category, findings = classify_record(doctype, record_dict, module=module)
					audit.findings.extend(findings)
			audits.append(audit)
		global_findings.extend(audit_configuration_records(frappe, sample_limit if include_samples else 0))
	finally:
		try:
			frappe.destroy()
		except Exception:
			pass

	return build_report(site, audits, global_findings)


def audit_configuration_records(frappe, sample_limit: int) -> list[Finding]:
	findings: list[Finding] = []
	for doctype in ("Custom Field", "Property Setter", "Print Format", "Notification", "Client Script", "Server Script", "Web Form"):
		if not doctype_exists(frappe, doctype):
			continue
		fields = get_text_fields(frappe, doctype)
		for record in get_samples(frappe, doctype, fields, sample_limit):
			findings.extend(detect_string_risks(doctype, str(record.get("name") or ""), dict(record)))
	return findings


def build_report(site: str | None, audits: list[DoctypeAudit], global_findings: list[Finding] | None = None) -> dict[str, Any]:
	global_findings = global_findings or []
	counts = {
		CATEGORY_DIRECT: 0,
		CATEGORY_MAPPING: 0,
		CATEGORY_MANUAL: 0,
		CATEGORY_DANGEROUS: 0,
		CATEGORY_PLATFORM: 0,
		CATEGORY_ERPNEXT: 0,
	}
	for audit in audits:
		counts[audit.category] = counts.get(audit.category, 0) + 1
	all_findings = [finding for audit in audits for finding in audit.findings] + global_findings
	risky_doctypes = sorted(
		[
			{
				"doctype": audit.doctype,
				"category": audit.category,
				"finding_count": len(audit.findings),
				"record_count": audit.record_count,
			}
			for audit in audits
			if audit.category in {CATEGORY_DANGEROUS, CATEGORY_PLATFORM, CATEGORY_MANUAL} or audit.findings
		],
		key=lambda row: (row["finding_count"], row["record_count"] or 0),
		reverse=True,
	)
	return {
		"mode": "read_only_data_migration_audit",
		"site": site,
		"category_counts": counts,
		"doctypes": [audit.as_dict() for audit in audits],
		"top_risky_doctypes": risky_doctypes[:20],
		"top_risky_fields": [finding.as_dict() for finding in all_findings[:50]],
		"proposed_migration_order": PROPOSED_MIGRATION_ORDER,
		"missing_mapping_requirements": MAPPING_REQUIREMENTS,
		"export_policy": {
			"data_export_performed": False,
			"business_records_mutated": False,
			"destructive_operations": [],
		},
	}


def print_summary(report: dict[str, Any], verbose: bool = False) -> None:
	print("VetEdge data migration readiness audit")
	print(f"Site: {report.get('site') or '(offline/test report)'}")
	print("Category counts:")
	for category, count in report["category_counts"].items():
		print(f"  - {category}: {count}")
	print("Top risky DocTypes:")
	for row in report["top_risky_doctypes"][:10]:
		print(f"  - {row['doctype']}: {row['category']} ({row['finding_count']} findings)")
	if verbose:
		print("Top risky fields:")
		for finding in report["top_risky_fields"][:20]:
			print(
				f"  - {finding['doctype']} {finding.get('record') or ''} "
				f"{finding.get('fieldname') or ''}: {finding['reason']}"
			)
	print("Export policy: manifest/read-only only; no data export performed.")


def write_json(path: str | None, payload: dict[str, Any]) -> None:
	if not path:
		return
	target = Path(path)
	target.parent.mkdir(parents=True, exist_ok=True)
	target.write_text(json.dumps(payload, indent=2, sort_keys=True, default=str), encoding="utf-8")


def main() -> int:
	args = parse_args()
	if not args.site:
		print("--site is required for live data audits.", file=sys.stderr)
		return 2
	report = audit_site(
		args.site,
		include_counts=args.include_counts,
		include_samples=args.include_samples,
		sample_limit=args.sample_limit,
	)
	print_summary(report, verbose=args.verbose)
	write_json(args.output_json, report)
	if args.export_manifest:
		audits = [
			DoctypeAudit(
				doctype=row["doctype"],
				category=row["category"],
				reason=row["reason"],
				record_count=row.get("record_count"),
			)
			for row in report["doctypes"]
		]
		write_json(args.export_manifest, build_export_manifest(audits))
	return 0


if __name__ == "__main__":
	raise SystemExit(main())
