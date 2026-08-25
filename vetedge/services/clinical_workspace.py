from __future__ import annotations

from typing import Any

import frappe
from frappe import _
from frappe.utils import cint, flt

from vetedge.services.consultation_flow import (
	CONSULTATION_SCOPE_LOCKED_STATUSES,
	VALID_CONSULTATION_STATUS_TRANSITIONS,
	ensure_consultations_enabled,
	transition_consultation_status,
)
from vetedge.services.dispensary import consultation_requires_dispensary
from vetedge.services.feature_flags import is_enabled
from vetedge.services.medical_history import get_patient_medical_history_view
from vetedge.services.permissions import (
	can_access_branch_data,
	can_access_consultation,
	get_assigned_branches,
	get_current_user,
	get_veterinary_doctor_users,
	user_has_global_branch_access,
)
from vetedge.services.platform_access import require_vetedge_platform_access
from vetedge.services.portal_access import require_internal_user
from vetedge.services.treatment_items import (
	get_treatment_item_defaults_for_consultation,
	get_treatment_item_link_options,
)
from vetedge.services.vitals import (
	create_vitals_from_consultation,
	get_latest_vitals_for_consultation,
)

PAGE_LENGTH_MAX = 100
STATUS_ACTION_ORDER = (
	"In Progress",
	"Awaiting Payment",
	"Pending Dispensary",
	"Ready for Treatment",
	"Completed",
	"Cancelled",
)
EDITABLE_SCALAR_FIELDS = (
	"patient",
	"consultation_datetime",
	"consultation_type",
	"service_branch",
	"consulting_practitioner",
	"linked_appointment",
	"presenting_complaint",
	"examination_notes",
	"assessment_notes",
	"treatment_plan_summary",
	"follow_up_date",
)
SYMPTOM_FIELDS = ("name", "symptom", "notes")
DIAGNOSIS_FIELDS = ("name", "diagnosis", "diagnosis_type", "notes")
PLANNED_TREATMENT_EDITABLE_FIELDS = (
	"name",
	"item",
	"description",
	"qty",
	"uom",
	"rate",
	"service_type",
	"treatment_type",
	"notes",
)
PLANNED_TREATMENT_IMMUTABLE_FIELDS = (
	"source_type",
	"source_doctype",
	"source_document",
	"source_detail_name",
	"billing_status",
	"payment_status",
)
PROTECTED_TREATMENT_SOURCE_TYPES = {"Consultation", "Lab Order", "Vaccination"}
EDITABLE_TREATMENT_BILLING_STATUSES = {"Pending", "Skipped", "Cancelled"}


def _require_clinical_context() -> str:
	require_internal_user()
	ensure_consultations_enabled()
	return get_current_user() or frappe.session.user


def _parse_json_object(value: str | dict | None) -> dict[str, Any]:
	if not value:
		return {}
	if isinstance(value, dict):
		return value
	parsed = frappe.parse_json(value)
	if not isinstance(parsed, dict):
		frappe.throw(_("Expected a JSON object."), frappe.ValidationError)
	return parsed


def _page_values(start: int, page_length: int) -> tuple[int, int]:
	return max(cint(start), 0), min(max(cint(page_length) or 25, 1), PAGE_LENGTH_MAX)


def _assert_timestamp(doctype: str, name: str, expected_modified: str | None) -> None:
	if not expected_modified:
		return
	current = frappe.db.get_value(doctype, name, "modified")
	if current and str(current) != str(expected_modified):
		raise frappe.TimestampMismatchError(
			_("This consultation changed after it was opened. Refresh the Clinical Workspace and try again.")
		)


def _validate_branch(branch: str | None) -> None:
	if branch:
		can_access_branch_data(get_current_user(), branch, raise_exception=True)


def _branch_filters(branch: str | None = None) -> dict:
	_validate_branch(branch)
	if branch:
		return {"service_branch": branch}
	user = get_current_user()
	if user_has_global_branch_access(user):
		return {}
	assigned = get_assigned_branches(user)
	return {"service_branch": ["in", assigned]} if assigned else {"service_branch": ["in", []]}


def _permission_count(filters: dict, or_filters: list | None = None) -> int:
	rows = frappe.get_list(
		"Veterinary Consultation",
		fields=[{"COUNT": "*", "as": "total"}],
		filters=filters,
		or_filters=or_filters,
		limit_page_length=1,
	)
	return cint(rows[0].get("total")) if rows else 0


def _document_title(doctype: str, name: str | None) -> str | None:
	if not name:
		return None
	meta = frappe.get_meta(doctype)
	fieldname = meta.title_field or "name"
	return frappe.db.get_value(doctype, name, fieldname) or name


def _serialize_rows(rows, fields: tuple[str, ...]) -> list[dict[str, Any]]:
	return [{field: row.get(field) for field in fields} for row in rows or []]


def _status_actions(doc) -> list[dict[str, Any]]:
	if not doc.has_permission("write"):
		return []
	labels = {
		"In Progress": _("Start Consultation"),
		"Awaiting Payment": _("Move to Awaiting Payment"),
		"Pending Dispensary": _("Move to Pending Dispensary"),
		"Ready for Treatment": _("Mark Ready for Treatment"),
		"Completed": _("Complete Consultation"),
		"Cancelled": _("Cancel Consultation"),
	}
	allowed = set(VALID_CONSULTATION_STATUS_TRANSITIONS.get(doc.status, set()))
	if not consultation_requires_dispensary(doc):
		allowed.discard("Pending Dispensary")
	return [
		{"key": f"status:{target}", "label": labels.get(target, target), "primary": target in {"In Progress", "Completed"}, "danger": target == "Cancelled"}
		for target in STATUS_ACTION_ORDER if target in allowed
	]


@frappe.whitelist()
def get_clinical_summary(branch: str | None = None) -> dict:
	_require_clinical_context()
	base = _branch_filters(branch)
	return {
		"draft": _permission_count({**base, "status": "Draft"}),
		"in_progress": _permission_count({**base, "status": "In Progress"}),
		"awaiting_payment": _permission_count({**base, "status": "Awaiting Payment"}),
		"ready_for_treatment": _permission_count({**base, "status": "Ready for Treatment"}),
		"completed": _permission_count({**base, "status": "Completed"}),
	}


@frappe.whitelist()
def get_consultations(search: str = "", status: str | None = None, branch: str | None = None, practitioner: str | None = None, patient: str | None = None, start: int = 0, page_length: int = 25) -> dict:
	_require_clinical_context()
	if not frappe.has_permission("Veterinary Consultation", "read"):
		frappe.throw(_("You are not permitted to view consultations."), frappe.PermissionError)
	filters = _branch_filters(branch)
	if status: filters["status"] = status
	if practitioner: filters["consulting_practitioner"] = practitioner
	if patient: filters["patient"] = patient
	query = str(search or "").strip()
	or_filters = [["Veterinary Consultation", fieldname, "like", f"%{query}%"] for fieldname in ("name", "consultation_title", "patient", "primary_owner", "presenting_complaint")] if query else None
	start, page_length = _page_values(start, page_length)
	rows = frappe.get_list("Veterinary Consultation", fields=["name", "modified", "consultation_title", "patient", "primary_owner", "status", "consultation_datetime", "consultation_type", "service_branch", "consulting_practitioner", "consulting_practitioner_name", "presenting_complaint", "payment_status", "dispensary_status"], filters=filters, or_filters=or_filters, order_by="consultation_datetime desc, modified desc", start=start, page_length=page_length)
	for row in rows:
		row["patient_label"] = _document_title("Veterinary Patient", row.get("patient"))
		row["owner_label"] = _document_title("Customer", row.get("primary_owner"))
	return {"rows": rows, "total": _permission_count(filters, or_filters), "start": start, "page_length": page_length}


@frappe.whitelist()
def get_consultation_detail(name: str) -> dict:
	_require_clinical_context()
	doc = frappe.get_doc("Veterinary Consultation", name)
	doc.check_permission("read")
	can_access_consultation(frappe.session.user, doc.name, raise_exception=True)
	_validate_branch(doc.service_branch)
	vitals_enabled = is_enabled("vitals")
	can_read_vitals = vitals_enabled and frappe.has_permission("Veterinary Vital Signs", "read")
	latest_vitals = get_latest_vitals_for_consultation(doc.name) if can_read_vitals else None
	return {
		"name": doc.name, "modified": doc.modified, "status": doc.status,
		"can_write": bool(doc.has_permission("write")),
		"scope_locked": doc.status in CONSULTATION_SCOPE_LOCKED_STATUSES,
		"values": {
			**{field: doc.get(field) for field in EDITABLE_SCALAR_FIELDS},
			"consultation_title": doc.consultation_title, "daily_consultation_number": doc.daily_consultation_number,
			"primary_owner": doc.primary_owner, "primary_owner_label": _document_title("Customer", doc.primary_owner),
			"company": doc.company, "consulting_practitioner_name": doc.consulting_practitioner_name,
			"follow_up_appointment": doc.follow_up_appointment, "dispensary_status": doc.dispensary_status,
			"dispensary_confirmed_on": doc.dispensary_confirmed_on, "dispensary_confirmed_by": doc.dispensary_confirmed_by,
			"dispensary_stock_entry": doc.dispensary_stock_entry, "linked_invoice": doc.linked_invoice, "payment_status": doc.payment_status,
			"symptoms": _serialize_rows(doc.get("symptoms"), SYMPTOM_FIELDS),
			"diagnoses": _serialize_rows(doc.get("diagnoses"), DIAGNOSIS_FIELDS),
			"planned_treatments": _serialize_rows(doc.get("planned_treatments"), PLANNED_TREATMENT_EDITABLE_FIELDS + PLANNED_TREATMENT_IMMUTABLE_FIELDS + ("amount",)),
			"consultation_invoices": [row.as_dict(no_nulls=False) for row in doc.get("consultation_invoices") or []],
		},
		"patient_label": _document_title("Veterinary Patient", doc.patient), "latest_vitals": latest_vitals,
		"actions": _status_actions(doc),
		"capabilities": {"create_vitals": vitals_enabled and bool(frappe.has_permission("Veterinary Vital Signs", "create")) and doc.status not in {"Completed", "Cancelled"}, "view_history": bool(frappe.has_permission("Veterinary Consultation", "read")), "open_billing": bool(doc.name)},
	}


def _replace_simple_table(doc, fieldname: str, rows: list[dict], fields: tuple[str, ...]) -> None:
	doc.set(fieldname, [])
	for raw in rows or []:
		doc.append(fieldname, {field: raw.get(field) for field in fields if raw.get(field) not in (None, "")})


def _same_editable_treatment(existing, incoming: dict) -> bool:
	for fieldname in PLANNED_TREATMENT_EDITABLE_FIELDS:
		if fieldname == "name": continue
		left, right = existing.get(fieldname), incoming.get(fieldname)
		if fieldname in {"qty", "rate"}:
			if flt(left) != flt(right): return False
		elif (left or "") != (right or ""): return False
	return True


def _source_treatment_is_protected(row) -> bool:
	return bool(row.get("source_document") or row.get("source_detail_name") or row.get("source_type") in PROTECTED_TREATMENT_SOURCE_TYPES)


def _treatment_row_is_protected(row) -> bool:
	return bool(_source_treatment_is_protected(row) or (row.get("billing_status") or "Pending") not in EDITABLE_TREATMENT_BILLING_STATUSES)


def _replace_planned_treatments(doc, rows: list[dict]) -> None:
	existing_by_name = {row.name: row for row in doc.get("planned_treatments") or [] if row.name}
	incoming_names = {row.get("name") for row in rows or [] if row.get("name")}
	for existing in existing_by_name.values():
		if existing.name not in incoming_names and _treatment_row_is_protected(existing):
			frappe.throw(_("Source-generated or billed treatment row {0} cannot be removed from the Clinical Workspace.").format(existing.item), frappe.ValidationError)
	prepared = []
	for raw in rows or []:
		name = raw.get("name"); existing = existing_by_name.get(name)
		if existing and _treatment_row_is_protected(existing) and not _same_editable_treatment(existing, raw):
			frappe.throw(_("Source-generated or billed treatment row {0} cannot be edited. Create a new treatment row instead.").format(existing.item), frappe.ValidationError)
		row = {field: raw.get(field) for field in PLANNED_TREATMENT_EDITABLE_FIELDS if raw.get(field) not in (None, "")}
		if existing:
			for fieldname in PLANNED_TREATMENT_IMMUTABLE_FIELDS: row[fieldname] = existing.get(fieldname)
		else:
			row["source_type"] = "Treatment"; row["billing_status"] = "Pending"; row["payment_status"] = "Not Billed"
		row["qty"] = flt(row.get("qty") or 1); row["rate"] = flt(row.get("rate") or 0); row["amount"] = row["qty"] * row["rate"]
		prepared.append(row)
	doc.set("planned_treatments", [])
	for row in prepared: doc.append("planned_treatments", row)


@frappe.whitelist()
def save_consultation(payload: str | dict) -> dict:
	_require_clinical_context(); values = _parse_json_object(payload); name = values.get("name")
	if name:
		doc = frappe.get_doc("Veterinary Consultation", name); doc.check_permission("write"); can_access_consultation(frappe.session.user, name, raise_exception=True); _assert_timestamp(doc.doctype, doc.name, values.get("modified"))
	else:
		if not frappe.has_permission("Veterinary Consultation", "create"): frappe.throw(_("You are not permitted to create consultations."), frappe.PermissionError)
		doc = frappe.new_doc("Veterinary Consultation"); doc.status = "Draft"
	require_vetedge_platform_access(action="clinical_workspace_save_consultation", reference_doctype="Veterinary Consultation", reference_name=name)
	for fieldname in EDITABLE_SCALAR_FIELDS:
		if fieldname in values: doc.set(fieldname, values.get(fieldname))
	_validate_branch(doc.get("service_branch"))
	if "symptoms" in values: _replace_simple_table(doc, "symptoms", values.get("symptoms") or [], SYMPTOM_FIELDS)
	if "diagnoses" in values: _replace_simple_table(doc, "diagnoses", values.get("diagnoses") or [], DIAGNOSIS_FIELDS)
	if "planned_treatments" in values: _replace_planned_treatments(doc, values.get("planned_treatments") or [])
	doc.insert() if doc.is_new() else doc.save()
	return get_consultation_detail(doc.name)


@frappe.whitelist()
def perform_consultation_action(name: str, action: str, modified: str | None = None) -> dict:
	_require_clinical_context(); doc = frappe.get_doc("Veterinary Consultation", name); doc.check_permission("write"); can_access_consultation(frappe.session.user, name, raise_exception=True); _assert_timestamp(doc.doctype, doc.name, modified)
	if not action.startswith("status:"): frappe.throw(_("Unsupported consultation action."), frappe.ValidationError)
	transition_consultation_status(name, action.split(":", 1)[1]); return get_consultation_detail(name)


@frappe.whitelist()
def create_consultation_vitals(name: str, values: str | dict | None = None, modified: str | None = None) -> dict:
	_require_clinical_context(); doc = frappe.get_doc("Veterinary Consultation", name); doc.check_permission("read"); can_access_consultation(frappe.session.user, name, raise_exception=True); _assert_timestamp(doc.doctype, doc.name, modified)
	require_vetedge_platform_access(action="clinical_workspace_create_vitals", reference_doctype=doc.doctype, reference_name=doc.name)
	vitals_name = create_vitals_from_consultation(name, values); return {"vitals": vitals_name, "detail": get_consultation_detail(name)}


@frappe.whitelist()
def get_consultation_history(name: str, limit: int = 20) -> dict:
	_require_clinical_context(); doc = frappe.get_doc("Veterinary Consultation", name); doc.check_permission("read"); can_access_consultation(frappe.session.user, name, raise_exception=True)
	return get_patient_medical_history_view(doc.patient, limit=min(max(cint(limit) or 20, 1), 50))


@frappe.whitelist()
def get_treatment_defaults(item: str, company: str | None = None, customer: str | None = None, branch: str | None = None) -> dict:
	_require_clinical_context(); _validate_branch(branch)
	return get_treatment_item_defaults_for_consultation(item, company=company, customer=customer, branch=branch)


@frappe.whitelist()
def get_clinical_link_options(kind: str, search: str = "", branch: str | None = None, limit: int = 20) -> list[dict]:
	_require_clinical_context(); query = str(search or "").strip(); page_len = min(max(cint(limit) or 20, 1), 50)
	if kind == "practitioner":
		return [{"value": row[0], "label": row[1]} for row in get_veterinary_doctor_users("User", query, "name", 0, page_len, {})]
	if kind == "treatment_item":
		return [{"value": row[0], "label": row[1]} for row in get_treatment_item_link_options("Item", query, "name", 0, page_len, {})]
	config = {"patient": ("Veterinary Patient", "patient_name", {"status": ["!=", "Deceased"]}), "branch": ("Branch", "name", {}), "consultation_type": ("Consultation Type", "consultation_type", {}), "symptom": ("Veterinary Symptom", "name", {}), "diagnosis": ("Veterinary Diagnosis", "name", {})}
	if kind not in config: frappe.throw(_("Unsupported clinical link type."), frappe.ValidationError)
	doctype, label_field, filters = config[kind]; meta = frappe.get_meta(doctype)
	if meta.has_field("disabled"): filters["disabled"] = 0
	if kind == "branch":
		_validate_branch(branch); user = get_current_user()
		if not user_has_global_branch_access(user): filters["name"] = ["in", get_assigned_branches(user)]
	fields = ["name"]
	if label_field != "name" and meta.has_field(label_field): fields.append(label_field)
	or_filters = [[doctype, field, "like", f"%{query}%"] for field in fields] if query else None
	rows = frappe.get_list(doctype, fields=fields, filters=filters, or_filters=or_filters, order_by=f"{label_field if label_field in fields else 'name'} asc", page_length=page_len)
	return [{"value": row.get("name"), "label": row.get(label_field) or row.get("name")} for row in rows]
