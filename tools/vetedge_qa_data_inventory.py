#!/usr/bin/env python3
"""Read-only VetEdge operational QA data inventory.

This tool scans a local/staging Frappe site for candidate records that can be
used during live Desk QA. It never creates, updates, submits, cancels, deletes,
or repairs business records.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


MODE = "read_only_operational_qa_data_inventory"
DEFAULT_SAMPLE_LIMIT = 5


@dataclass(frozen=True)
class ScenarioDefinition:
	key: str
	label: str
	doctype: str | None
	group: str
	notes: str = ""
	not_applicable_when_missing_doctype: bool = True


@dataclass
class ScenarioResult:
	key: str
	label: str
	group: str
	doctype: str | None
	status: str
	candidate_count: int | None = None
	samples: list[str] = field(default_factory=list)
	notes: list[str] = field(default_factory=list)

	def as_dict(self) -> dict[str, Any]:
		return {
			"label": self.label,
			"group": self.group,
			"doctype": self.doctype,
			"status": self.status,
			"candidate_count": self.candidate_count,
			"samples": self.samples,
			"notes": self.notes,
		}


SCENARIOS: tuple[ScenarioDefinition, ...] = (
	ScenarioDefinition("consultation_active_no_invoice", "Active consultation with no invoice", "Veterinary Consultation", "consultations"),
	ScenarioDefinition("consultation_active_draft_invoice", "Active consultation with draft invoice", "Veterinary Consultation", "consultations"),
	ScenarioDefinition("consultation_submitted_unpaid_invoice", "Consultation with submitted unpaid invoice", "Veterinary Consultation", "consultations"),
	ScenarioDefinition("consultation_submitted_partly_paid_invoice", "Consultation with submitted partly paid invoice", "Veterinary Consultation", "consultations"),
	ScenarioDefinition("consultation_submitted_fully_paid_invoice", "Consultation with submitted fully paid invoice", "Veterinary Consultation", "consultations"),
	ScenarioDefinition("consultation_completed_invoice_history", "Completed consultation with invoice history", "Veterinary Consultation", "consultations"),
	ScenarioDefinition("consultation_cancelled_invoice_history", "Cancelled consultation with invoice history", "Veterinary Consultation", "consultations"),
	ScenarioDefinition("consultation_multiple_linked_invoices", "Consultation with multiple linked invoices", "Veterinary Consultation", "consultations"),
	ScenarioDefinition("consultation_old_patient_outstanding", "Consultation with old patient outstanding candidate", "Veterinary Consultation", "consultations"),
	ScenarioDefinition("consultation_posted_dispensary_stock", "Consultation with posted dispensary Stock Entry reference", "Veterinary Consultation", "consultations"),
	ScenarioDefinition("resolution_retain_pending", "Retain-payment resolution Pending Review", "Veterinary Consultation Cancellation Resolution", "cancellation_resolutions"),
	ScenarioDefinition("resolution_retain_approved", "Retain-payment resolution Approved", "Veterinary Consultation Cancellation Resolution", "cancellation_resolutions"),
	ScenarioDefinition("resolution_retain_completed", "Retain-payment resolution Completed", "Veterinary Consultation Cancellation Resolution", "cancellation_resolutions"),
	ScenarioDefinition("resolution_reschedule_completed", "Reschedule resolution with linked new appointment", "Veterinary Consultation Cancellation Resolution", "cancellation_resolutions"),
	ScenarioDefinition("resolution_refund_approved_evidence", "Refund Required resolution Approved with accounting evidence", "Veterinary Consultation Cancellation Resolution", "cancellation_resolutions"),
	ScenarioDefinition("resolution_refund_completed_no_status", "Refund Required Completed with No Status Change", "Veterinary Consultation Cancellation Resolution", "cancellation_resolutions"),
	ScenarioDefinition("resolution_refund_completed_cancel", "Refund Required Completed with Cancel outcome", "Veterinary Consultation Cancellation Resolution", "cancellation_resolutions"),
	ScenarioDefinition("resolution_credit_approved_evidence", "Issue Customer Credit resolution Approved with accounting evidence", "Veterinary Consultation Cancellation Resolution", "cancellation_resolutions"),
	ScenarioDefinition("resolution_credit_completed_no_status", "Issue Customer Credit Completed with No Status Change", "Veterinary Consultation Cancellation Resolution", "cancellation_resolutions"),
	ScenarioDefinition("resolution_credit_completed_cancel", "Issue Customer Credit Completed with Cancel outcome", "Veterinary Consultation Cancellation Resolution", "cancellation_resolutions"),
	ScenarioDefinition("resolution_admin_completed_evidence", "Admin Accounting Correction Completed with evidence", "Veterinary Consultation Cancellation Resolution", "cancellation_resolutions"),
	ScenarioDefinition("lab_completed_invoice_history", "Completed Lab Order with invoice history", "Veterinary Lab Order", "lab"),
	ScenarioDefinition("lab_cancelled_invoice_history", "Cancelled Lab Order with invoice history", "Veterinary Lab Order", "lab"),
	ScenarioDefinition("lab_linked_to_consultation", "Lab Order linked to consultation", "Veterinary Lab Order", "lab"),
	ScenarioDefinition("lab_old_patient_outstanding", "Lab Order with old patient outstanding candidate", "Veterinary Lab Order", "lab"),
	ScenarioDefinition("vaccination_administered_invoice_history", "Administered Vaccination with invoice history", "Veterinary Vaccination Record", "vaccination"),
	ScenarioDefinition("vaccination_cancelled_invoice_history", "Cancelled Vaccination with invoice history", "Veterinary Vaccination Record", "vaccination"),
	ScenarioDefinition("vaccination_stock_context", "Vaccination with stock/batch/warehouse context", "Veterinary Vaccination Record", "vaccination"),
	ScenarioDefinition("vaccination_linked_to_consultation", "Vaccination linked to consultation", "Veterinary Vaccination Record", "vaccination"),
	ScenarioDefinition("vaccination_old_patient_outstanding", "Vaccination with old patient outstanding candidate", "Veterinary Vaccination Record", "vaccination"),
	ScenarioDefinition("hospitalisation_active_charges", "Active hospitalisation with charges", "Veterinary Hospitalisation", "hospitalisation"),
	ScenarioDefinition("hospitalisation_discharged_invoice_history", "Discharged hospitalisation with invoice history", "Veterinary Hospitalisation", "hospitalisation"),
	ScenarioDefinition("hospitalisation_cancelled_history", "Cancelled hospitalisation with preserved history", "Veterinary Hospitalisation", "hospitalisation"),
	ScenarioDefinition("hospitalisation_stock_reference", "Hospitalisation with stock/material issue reference", "Veterinary Hospitalisation", "hospitalisation"),
	ScenarioDefinition("hospitalisation_occupancy_history", "Hospitalisation with care location/occupancy history", "Veterinary Hospitalisation", "hospitalisation"),
	ScenarioDefinition("hospitalisation_old_patient_outstanding", "Hospitalisation with old patient outstanding candidate", "Veterinary Hospitalisation", "hospitalisation"),
	ScenarioDefinition("grooming_completed_invoice_history", "Completed grooming session with invoice history", "Pet Grooming Session", "grooming"),
	ScenarioDefinition("grooming_cancelled_invoice_history", "Cancelled grooming session with invoice history", "Pet Grooming Session", "grooming"),
	ScenarioDefinition("grooming_linked_patient_owner", "Grooming appointment/session linked to patient/owner", "Pet Grooming Session", "grooming"),
	ScenarioDefinition("grooming_old_patient_outstanding", "Grooming with old patient outstanding candidate", "Pet Grooming Session", "grooming"),
	ScenarioDefinition("boarding_checked_out_invoice_history", "Checked-out boarding booking with invoice history", "Pet Boarding Booking", "boarding"),
	ScenarioDefinition("boarding_cancelled_invoice_history", "Cancelled boarding booking with invoice history", "Pet Boarding Booking", "boarding"),
	ScenarioDefinition("boarding_completed_stay_care_records", "Completed boarding stay with care records", "Pet Boarding Stay", "boarding"),
	ScenarioDefinition("boarding_with_charges", "Boarding with charges", "Pet Boarding Booking", "boarding"),
	ScenarioDefinition("boarding_old_patient_outstanding", "Boarding with old patient outstanding candidate", "Pet Boarding Booking", "boarding"),
	ScenarioDefinition("appointment_scheduled", "Scheduled appointment", "Veterinary Appointment", "appointments"),
	ScenarioDefinition("appointment_completed_linked_consultation", "Completed appointment linked to consultation", "Veterinary Appointment", "appointments"),
	ScenarioDefinition("appointment_cancelled_preserves_links", "Cancelled appointment preserving links/notes", "Veterinary Appointment", "appointments"),
	ScenarioDefinition("appointment_no_show_preserves_links", "No-show appointment preserving links/notes", "Veterinary Appointment", "appointments"),
	ScenarioDefinition("appointment_reschedule_created", "Reschedule-created appointment linked from cancellation resolution", "Veterinary Appointment", "appointments"),
	ScenarioDefinition("support_customer", "Test Customer/Owner", "Customer", "erpnext_support"),
	ScenarioDefinition("support_patient", "Test Veterinary Patient", "Veterinary Patient", "erpnext_support"),
	ScenarioDefinition("support_items", "Service/stock Item records", "Item", "erpnext_support"),
	ScenarioDefinition("support_item_prices", "Item Price records", "Item Price", "erpnext_support"),
	ScenarioDefinition("support_uom", "UOM records", "UOM", "erpnext_support"),
	ScenarioDefinition("support_warehouse", "Warehouse records", "Warehouse", "erpnext_support"),
	ScenarioDefinition("support_batch", "Batch records for vaccine/dispensary stock", "Batch", "erpnext_support"),
	ScenarioDefinition("support_mode_of_payment", "Mode of Payment records", "Mode of Payment", "erpnext_support"),
	ScenarioDefinition("support_account", "Account records", "Account", "erpnext_support"),
	ScenarioDefinition("support_company", "Company records", "Company", "erpnext_support"),
	ScenarioDefinition("support_branch", "Branch records", "Branch", "erpnext_support"),
	ScenarioDefinition("support_price_list", "Price List records", "Price List", "erpnext_support"),
	ScenarioDefinition("support_stock_entry", "Stock Entry evidence/reference", "Stock Entry", "erpnext_support"),
	ScenarioDefinition("support_payment_entry", "Payment Entry evidence/reference", "Payment Entry", "erpnext_support"),
	ScenarioDefinition("support_sales_invoice", "Sales Invoice evidence/reference", "Sales Invoice", "erpnext_support"),
	ScenarioDefinition("support_journal_entry", "Journal Entry or accounting evidence reference", "Journal Entry", "erpnext_support"),
)


def parse_args() -> argparse.Namespace:
	parser = argparse.ArgumentParser(description="Read-only VetEdge operational QA data inventory.")
	parser.add_argument("--site", required=True, help="Frappe site name to inspect.")
	parser.add_argument("--output", help="Write JSON inventory report to this path.")
	parser.add_argument("--include-counts", action="store_true", help="Include candidate counts.")
	parser.add_argument("--include-samples", action="store_true", help="Include limited candidate record names.")
	parser.add_argument("--sample-limit", type=int, default=DEFAULT_SAMPLE_LIMIT, help="Maximum samples per scenario.")
	args = parser.parse_args()
	if args.sample_limit < 0:
		parser.error("--sample-limit must be non-negative")
	return args


def build_scenario_result(
	definition: ScenarioDefinition,
	records: list[str] | None,
	*,
	doctype_exists: bool = True,
	include_counts: bool = False,
	include_samples: bool = False,
	sample_limit: int = DEFAULT_SAMPLE_LIMIT,
	notes: list[str] | None = None,
) -> ScenarioResult:
	notes = list(notes or [])
	if not doctype_exists:
		status = "not_applicable" if definition.not_applicable_when_missing_doctype else "missing"
		notes.append(f"DocType {definition.doctype} is not installed on this site.")
		return ScenarioResult(definition.key, definition.label, definition.group, definition.doctype, status, 0 if include_counts else None, [], notes)

	records = records or []
	status = "found" if records else "missing"
	samples = records[:sample_limit] if include_samples else []
	candidate_count = len(records) if include_counts else None
	notes.append("Candidate records for QA only; not validated workflow truth.")
	if definition.notes:
		notes.append(definition.notes)
	return ScenarioResult(definition.key, definition.label, definition.group, definition.doctype, status, candidate_count, samples, notes)


def build_report(
	site: str,
	results: list[ScenarioResult],
	*,
	generated_at: str | None = None,
) -> dict[str, Any]:
	scenarios = {result.key: result.as_dict() for result in results}
	summary = {
		"found": sum(1 for result in results if result.status == "found"),
		"missing": sum(1 for result in results if result.status == "missing"),
		"not_applicable": sum(1 for result in results if result.status == "not_applicable"),
	}
	return {
		"mode": MODE,
		"generated_at": generated_at or datetime.now(timezone.utc).isoformat(),
		"site": site,
		"business_records_mutated": False,
		"destructive_operations": [],
		"summary": summary,
		"scenarios": scenarios,
		"notes": [
			"Read-only inventory for live Desk QA preparation.",
			"Candidate records may still need manual validation before use in workflow QA.",
			"No invoice, payment, stock, or clinical record is created or changed by this tool.",
		],
	}


def write_json(path: str | None, payload: dict[str, Any]) -> None:
	if not path:
		return
	target = Path(path)
	target.parent.mkdir(parents=True, exist_ok=True)
	target.write_text(json.dumps(payload, indent=2, sort_keys=True, default=str), encoding="utf-8")


def find_bench_root(start: Path | None = None) -> Path:
	start = (start or Path.cwd()).resolve()
	for candidate in (start, *start.parents):
		if (candidate / "sites").is_dir() and (candidate / "apps").is_dir():
			return candidate
	raise RuntimeError(f"Could not locate Frappe bench root from {start}")


def get_sites_path(start: Path | None = None) -> Path:
	return find_bench_root(start) / "sites"


def doctype_exists(frappe, doctype: str | None) -> bool:
	if not doctype:
		return False
	try:
		return bool(frappe.db.exists("DocType", doctype))
	except Exception:
		return False


def field_exists(frappe, doctype: str, fieldname: str) -> bool:
	try:
		return bool(frappe.get_meta(doctype).has_field(fieldname))
	except Exception:
		return False


def get_names(frappe, doctype: str, filters: dict[str, Any] | None = None, *, limit: int = 200) -> list[str]:
	try:
		rows = frappe.get_all(doctype, filters=filters or {}, fields=["name"], limit_page_length=limit, order_by="modified desc")
	except Exception:
		return []
	return [str(row.get("name")) for row in rows if row.get("name")]


def get_names_with_field(frappe, doctype: str, fieldname: str, *, filters: dict[str, Any] | None = None) -> list[str]:
	if not field_exists(frappe, doctype, fieldname):
		return []
	query_filters = dict(filters or {})
	query_filters[fieldname] = ["is", "set"]
	return get_names(frappe, doctype, query_filters)


def get_consultations_with_invoice_status(frappe, invoice_filters: dict[str, Any]) -> list[str]:
	if not doctype_exists(frappe, "Consultation Invoice Reference"):
		return []
	try:
		rows = frappe.db.sql(
			"""
			select distinct ref.parent
			from `tabConsultation Invoice Reference` ref
			inner join `tabSales Invoice` si on si.name = ref.sales_invoice
			where ref.parenttype = 'Veterinary Consultation'
			""",
			as_dict=True,
		)
	except Exception:
		return []
	names: list[str] = []
	for row in rows:
		invoice_names = get_names(
			frappe,
			"Consultation Invoice Reference",
			{"parenttype": "Veterinary Consultation", "parent": row.get("parent")},
			limit=50,
		)
		if invoice_names:
			names.append(str(row.get("parent")))
	return names if invoice_filters == {} else _filter_consultations_by_invoice(frappe, names, invoice_filters)


def _filter_consultations_by_invoice(frappe, consultation_names: list[str], invoice_filters: dict[str, Any]) -> list[str]:
	matched: list[str] = []
	for consultation in consultation_names:
		try:
			rows = frappe.db.sql(
				"""
				select si.name
				from `tabConsultation Invoice Reference` ref
				inner join `tabSales Invoice` si on si.name = ref.sales_invoice
				where ref.parenttype = 'Veterinary Consultation'
				  and ref.parent = %(consultation)s
				""",
				{"consultation": consultation},
				as_dict=True,
			)
		except Exception:
			continue
		for row in rows:
			values = frappe.db.get_value("Sales Invoice", row.get("name"), list(invoice_filters), as_dict=True) or {}
			if all(values.get(field) == expected for field, expected in invoice_filters.items()):
				matched.append(consultation)
				break
	return matched


def discover_scenario_records(frappe, definition: ScenarioDefinition) -> tuple[bool, list[str], list[str]]:
	doctype = definition.doctype
	if not doctype_exists(frappe, doctype):
		return False, [], []

	key = definition.key
	if key == "consultation_active_no_invoice":
		names = get_names(frappe, "Veterinary Consultation", {"status": ["not in", ["Completed", "Cancelled"]]})
		with_invoice = set(get_consultations_with_invoice_status(frappe, {}))
		return True, [name for name in names if name not in with_invoice], []
	if key == "consultation_active_draft_invoice":
		return True, _filter_consultations_by_invoice(frappe, get_consultations_with_invoice_status(frappe, {}), {"docstatus": 0}), []
	if key == "consultation_submitted_unpaid_invoice":
		return True, _filter_consultations_by_invoice(frappe, get_consultations_with_invoice_status(frappe, {}), {"docstatus": 1, "status": "Unpaid"}), []
	if key == "consultation_submitted_partly_paid_invoice":
		return True, _filter_consultations_by_invoice(frappe, get_consultations_with_invoice_status(frappe, {}), {"docstatus": 1, "status": "Partly Paid"}), []
	if key == "consultation_submitted_fully_paid_invoice":
		return True, _filter_consultations_by_invoice(frappe, get_consultations_with_invoice_status(frappe, {}), {"docstatus": 1, "status": "Paid"}), []
	if key == "consultation_completed_invoice_history":
		return True, [name for name in get_names(frappe, "Veterinary Consultation", {"status": "Completed"}) if name in set(get_consultations_with_invoice_status(frappe, {}))], []
	if key == "consultation_cancelled_invoice_history":
		return True, [name for name in get_names(frappe, "Veterinary Consultation", {"status": "Cancelled"}) if name in set(get_consultations_with_invoice_status(frappe, {}))], []
	if key == "consultation_multiple_linked_invoices":
		return True, _get_parents_with_multiple_children(frappe, "Consultation Invoice Reference", "Veterinary Consultation"), []
	if key == "consultation_posted_dispensary_stock":
		return True, _get_consultations_with_child_field(frappe, "Dispensed Treatment Item", "stock_entry"), []

	if key.startswith("resolution_"):
		return True, _get_resolution_candidates(frappe, key), []

	if key.startswith("lab_"):
		return True, _get_source_candidates(frappe, "Veterinary Lab Order", key), []
	if key.startswith("vaccination_"):
		return True, _get_source_candidates(frappe, "Veterinary Vaccination Record", key), []
	if key.startswith("hospitalisation_"):
		return True, _get_source_candidates(frappe, "Veterinary Hospitalisation", key), []
	if key.startswith("grooming_"):
		return True, _get_source_candidates(frappe, "Pet Grooming Session", key), []
	if key.startswith("boarding_completed_stay"):
		return True, get_names(frappe, "Pet Boarding Stay", {"status": "Completed"}), []
	if key.startswith("boarding_"):
		return True, _get_source_candidates(frappe, "Pet Boarding Booking", key), []
	if key.startswith("appointment_"):
		return True, _get_appointment_candidates(frappe, key), []
	if key.startswith("support_"):
		return True, get_names(frappe, doctype), []

	return True, get_names(frappe, doctype), ["Generic DocType status query; manually validate candidate suitability."]


def _get_parents_with_multiple_children(frappe, child_doctype: str, parenttype: str) -> list[str]:
	if not doctype_exists(frappe, child_doctype):
		return []
	try:
		rows = frappe.db.sql(
			f"""
			select parent
			from `tab{child_doctype}`
			where parenttype = %(parenttype)s
			group by parent
			having count(name) > 1
			order by max(modified) desc
			limit 200
			""",
			{"parenttype": parenttype},
			as_dict=True,
		)
	except Exception:
		return []
	return [str(row["parent"]) for row in rows if row.get("parent")]


def _get_consultations_with_child_field(frappe, child_doctype: str, fieldname: str) -> list[str]:
	if not doctype_exists(frappe, child_doctype) or not field_exists(frappe, child_doctype, fieldname):
		return []
	try:
		rows = frappe.db.sql(
			f"""
			select distinct parent
			from `tab{child_doctype}`
			where parenttype = 'Veterinary Consultation'
			  and ifnull(`{fieldname}`, '') != ''
			order by modified desc
			limit 200
			""",
			as_dict=True,
		)
	except Exception:
		return []
	return [str(row["parent"]) for row in rows if row.get("parent")]


def _get_resolution_candidates(frappe, key: str) -> list[str]:
	action_by_key = {
		"resolution_retain": "retain_payment_clinical_cancel_only",
		"resolution_reschedule": "reschedule_consultation",
		"resolution_refund": "refund_required",
		"resolution_credit": "issue_customer_credit",
		"resolution_admin": "admin_accounting_correction",
	}
	action = next((value for prefix, value in action_by_key.items() if key.startswith(prefix)), None)
	filters: dict[str, Any] = {"resolution_action": action} if action else {}
	if key.endswith("_pending"):
		filters["resolution_status"] = "Pending Review"
	elif key.endswith("_approved") or "_approved_" in key:
		filters["resolution_status"] = "Approved"
	elif "_completed" in key:
		filters["resolution_status"] = "Completed"
	if key == "resolution_reschedule_completed":
		return get_names_with_field(frappe, "Veterinary Consultation Cancellation Resolution", "linked_new_appointment", filters=filters)
	if "evidence" in key:
		return get_names_with_field(frappe, "Veterinary Consultation Cancellation Resolution", "accounting_reference_name", filters=filters)
	if key.endswith("_cancel"):
		filters["status_outcome"] = "Cancel Consultation After Financial Resolution"
	elif key.endswith("_no_status"):
		filters["status_outcome"] = "No Status Change"
	return get_names(frappe, "Veterinary Consultation Cancellation Resolution", filters)


def _get_source_candidates(frappe, doctype: str, key: str) -> list[str]:
	if "completed" in key:
		status = "Completed"
	elif "administered" in key:
		status = "Administered"
	elif "cancelled" in key:
		status = "Cancelled"
	elif "discharged" in key:
		status = "Discharged"
	elif "active" in key:
		status = ["not in", ["Cancelled", "Discharged", "Completed", "Checked Out"]]
	else:
		status = None
	filters: dict[str, Any] = {}
	if status is not None:
		filters["status"] = status
	if "linked_to_consultation" in key:
		return get_names_with_field(frappe, doctype, "consultation", filters=filters)
	if "stock_context" in key or "stock_reference" in key:
		for fieldname in ("stock_entry", "warehouse", "batch_no", "batch"):
			names = get_names_with_field(frappe, doctype, fieldname, filters=filters)
			if names:
				return names
		return []
	if "charges" in key:
		return _get_parents_with_multiple_children(frappe, "Veterinary Hospitalisation Charge Item", doctype)
	if "occupancy_history" in key:
		return _get_names_from_field(frappe, "Veterinary Care Location Occupancy Log", "hospitalisation")
	if "invoice_history" in key:
		return _get_sources_with_invoice_fields(frappe, doctype, filters)
	if "old_patient_outstanding" in key:
		return get_names(frappe, doctype, filters)
	if "linked_patient_owner" in key:
		return get_names_with_field(frappe, doctype, "patient", filters=filters)
	return get_names(frappe, doctype, filters)


def _get_sources_with_invoice_fields(frappe, doctype: str, filters: dict[str, Any]) -> list[str]:
	for fieldname in ("linked_invoice", "sales_invoice", "invoice", "current_invoice"):
		names = get_names_with_field(frappe, doctype, fieldname, filters=filters)
		if names:
			return names
	return get_names(frappe, doctype, filters)


def _get_names_from_field(frappe, doctype: str, fieldname: str) -> list[str]:
	if not doctype_exists(frappe, doctype) or not field_exists(frappe, doctype, fieldname):
		return []
	try:
		rows = frappe.get_all(doctype, fields=[fieldname], filters={fieldname: ["is", "set"]}, limit_page_length=200, order_by="modified desc")
	except Exception:
		return []
	return sorted({str(row[fieldname]) for row in rows if row.get(fieldname)})


def _get_appointment_candidates(frappe, key: str) -> list[str]:
	if key == "appointment_scheduled":
		return get_names(frappe, "Veterinary Appointment", {"status": "Scheduled"})
	if key == "appointment_completed_linked_consultation":
		return get_names_with_field(frappe, "Veterinary Appointment", "consultation", filters={"status": "Completed"})
	if key == "appointment_cancelled_preserves_links":
		return get_names(frappe, "Veterinary Appointment", {"status": "Cancelled"})
	if key == "appointment_no_show_preserves_links":
		return get_names(frappe, "Veterinary Appointment", {"status": "No Show"})
	if key == "appointment_reschedule_created":
		if not doctype_exists(frappe, "Veterinary Consultation Cancellation Resolution"):
			return []
		return _get_names_from_field(frappe, "Veterinary Consultation Cancellation Resolution", "linked_new_appointment")
	return get_names(frappe, "Veterinary Appointment")


def scan_site(site: str, *, include_counts: bool, include_samples: bool, sample_limit: int) -> dict[str, Any]:
	import frappe

	original_cwd = Path.cwd()
	sites_path = get_sites_path(original_cwd)
	results: list[ScenarioResult] = []
	try:
		frappe.init(site=site, sites_path=str(sites_path))
		os.chdir(sites_path)
		frappe.connect()
		for definition in SCENARIOS:
			exists, records, notes = discover_scenario_records(frappe, definition)
			results.append(
				build_scenario_result(
					definition,
					records,
					doctype_exists=exists,
					include_counts=include_counts,
					include_samples=include_samples,
					sample_limit=sample_limit,
					notes=notes,
				)
			)
	finally:
		try:
			frappe.destroy()
		except Exception:
			pass
		os.chdir(original_cwd)
	return build_report(site, results)


def print_summary(report: dict[str, Any]) -> None:
	print("VetEdge operational QA data inventory")
	print(f"Site: {report['site']}")
	print(f"Mode: {report['mode']}")
	print("Summary:")
	for status, count in report["summary"].items():
		print(f"  - {status}: {count}")
	missing = [key for key, row in report["scenarios"].items() if row["status"] == "missing"]
	if missing:
		print("Missing scenarios:")
		for key in missing[:25]:
			print(f"  - {key}: {report['scenarios'][key]['label']}")
		if len(missing) > 25:
			print(f"  - ... {len(missing) - 25} more")


def main() -> int:
	args = parse_args()
	report = scan_site(
		args.site,
		include_counts=args.include_counts,
		include_samples=args.include_samples,
		sample_limit=args.sample_limit,
	)
	print_summary(report)
	write_json(args.output, report)
	return 0


if __name__ == "__main__":
	raise SystemExit(main())
