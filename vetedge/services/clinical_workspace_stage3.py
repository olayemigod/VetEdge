from __future__ import annotations

from typing import Any

import frappe
from frappe import _
from frappe.utils import flt

from vetedge.services.billing import (
	can_edit_default_consultation_billing_item,
	get_consultation_billing_settings,
)
from vetedge.services.clinical_workspace import (
	DIAGNOSIS_FIELDS,
	EDITABLE_SCALAR_FIELDS,
	EDITABLE_TREATMENT_BILLING_STATUSES,
	PLANNED_TREATMENT_EDITABLE_FIELDS,
	PLANNED_TREATMENT_IMMUTABLE_FIELDS,
	SYMPTOM_FIELDS,
	_assert_timestamp,
	_parse_json_object,
	_replace_simple_table,
	_require_clinical_context,
	_same_editable_treatment,
	_validate_branch,
	get_consultation_detail,
)
from vetedge.services.clinical_workspace_context import assert_consultation_write_ownership
from vetedge.services.consultation_billing_plan import DEFAULT_CONSULTATION_SOURCE_DETAIL
from vetedge.services.consultation_related_records import (
	apply_consultation_source_billing_edits,
	consultation_source_billing_edit_policy,
)
from vetedge.services.permissions import can_access_consultation
from vetedge.services.platform_access import require_vetedge_platform_access

PROTECTED_TREATMENT_SOURCE_TYPES = {"Consultation", "Lab Order", "Vaccination"}
LOCKED_TREATMENT_PAYMENT_STATUSES = {"Paid", "Partly Paid", "Cancelled"}
SOURCE_BILLING_EDITABLE_STATUSES = {"", "Pending", "Draft Invoiced"}
SOURCE_BILLING_EDITABLE_FIELDS = {"rate"}


def _source_treatment_row(row) -> bool:
	return bool(
		row.get("source_document")
		or row.get("source_detail_name")
		or row.get("source_type") in PROTECTED_TREATMENT_SOURCE_TYPES
	)


def _is_default_consultation_fee_row(row) -> bool:
	return bool(
		row.get("source_type") == "Consultation"
		and row.get("source_detail_name") == DEFAULT_CONSULTATION_SOURCE_DETAIL
	)


def _treatment_row_billing_is_locked(row) -> bool:
	return bool(
		(row.get("billing_status") or "Pending") not in EDITABLE_TREATMENT_BILLING_STATUSES
		or (row.get("payment_status") or "Not Billed") in LOCKED_TREATMENT_PAYMENT_STATUSES
	)


def _default_consultation_fee_edit_is_allowed(row, settings=None) -> bool:
	settings = settings or get_consultation_billing_settings()
	return bool(
		_is_default_consultation_fee_row(row)
		and getattr(settings, "enabled", False)
		and getattr(settings, "auto_add_default_consultation_billing_item", True)
		and can_edit_default_consultation_billing_item(settings)
		and not _treatment_row_billing_is_locked(row)
	)


def _treatment_row_edit_is_protected(row, settings=None) -> bool:
	if _treatment_row_billing_is_locked(row):
		return True
	if _default_consultation_fee_edit_is_allowed(row, settings):
		return False
	return _source_treatment_row(row)


def _treatment_row_removal_is_protected(row) -> bool:
	return bool(_source_treatment_row(row) or _treatment_row_billing_is_locked(row))


def _changed_treatment_fields(existing, incoming: dict) -> set[str]:
	changed: set[str] = set()
	for fieldname in PLANNED_TREATMENT_EDITABLE_FIELDS:
		if fieldname == "name":
			continue
		left = existing.get(fieldname)
		right = incoming.get(fieldname)
		if fieldname in {"qty", "rate"}:
			if flt(left) != flt(right):
				changed.add(fieldname)
		elif (left or "") != (right or ""):
			changed.add(fieldname)
	return changed


def _source_billing_edit_is_allowed(existing, incoming: dict, policy: dict[str, bool]) -> bool:
	source_type = existing.get("source_type")
	if source_type == "Lab Order":
		policy_allows = policy.get("allow_editing_lab_billing", False)
	elif source_type == "Vaccination":
		policy_allows = policy.get("allow_editing_vaccination_billing", False)
	else:
		return False
	if not policy_allows:
		return False
	if (existing.get("billing_status") or "") not in SOURCE_BILLING_EDITABLE_STATUSES:
		return False
	if (existing.get("payment_status") or "Not Billed") in LOCKED_TREATMENT_PAYMENT_STATUSES:
		return False
	changed = _changed_treatment_fields(existing, incoming)
	return bool(changed and changed.issubset(SOURCE_BILLING_EDITABLE_FIELDS))


def _source_billing_edit_payload(existing, incoming: dict) -> dict | None:
	changed = _changed_treatment_fields(existing, incoming)
	if not changed:
		return None
	return {
		"source_type": existing.get("source_type"),
		"source_document": existing.get("source_document"),
		"source_detail_name": existing.get("source_detail_name"),
		"item": existing.get("item"),
		"rate": flt(incoming.get("rate")),
	}


def _treatment_label(row) -> str:
	return row.get("description") or row.get("item") or row.get("source_detail_name") or row.get("name") or _("Treatment row")


def _replace_planned_treatments(doc, rows: list[dict]) -> list[dict]:
	settings = get_consultation_billing_settings()
	policy = consultation_source_billing_edit_policy()
	existing_by_name = {row.name: row for row in doc.get("planned_treatments") or [] if row.name}
	incoming_names = {row.get("name") for row in rows or [] if row.get("name")}
	for existing in existing_by_name.values():
		if existing.name in incoming_names:
			continue
		if _treatment_row_removal_is_protected(existing):
			frappe.throw(
				_("Source-generated or billed treatment row {0} cannot be removed from the Clinical Workspace. Delete the source Lab Order or Vaccination from its related-record popup when permitted.").format(_treatment_label(existing)),
				frappe.ValidationError,
			)
	prepared: list[dict[str, Any]] = []
	source_edits: list[dict] = []
	for raw in rows or []:
		name = raw.get("name")
		existing = existing_by_name.get(name)
		if existing and not _same_editable_treatment(existing, raw):
			if existing.get("source_type") in {"Lab Order", "Vaccination"}:
				if not _source_billing_edit_is_allowed(existing, raw, policy):
					frappe.throw(
						_("Only the Rate of source-generated Lab/Vaccination rows can be edited while draft billing is open and policy permits it. The ERPNext Item remains fixed by the clinical master: {0}.").format(_treatment_label(existing)),
						frappe.ValidationError,
					)
				payload = _source_billing_edit_payload(existing, raw)
				if payload:
					source_edits.append(payload)
			elif _treatment_row_edit_is_protected(existing, settings):
				frappe.throw(
					_("Source-generated or billed treatment row {0} cannot be edited. Create a new treatment row instead.").format(_treatment_label(existing)),
					frappe.ValidationError,
				)
		row = {
			field: raw.get(field)
			for field in PLANNED_TREATMENT_EDITABLE_FIELDS
			if raw.get(field) not in (None, "")
		}
		if existing:
			for fieldname in PLANNED_TREATMENT_IMMUTABLE_FIELDS:
				row[fieldname] = existing.get(fieldname)
		else:
			row["source_type"] = "Treatment"
			row["billing_status"] = "Pending"
			row["payment_status"] = "Not Billed"
		row["qty"] = flt(row.get("qty") or 1)
		row["rate"] = flt(row.get("rate") or 0)
		row["amount"] = row["qty"] * row["rate"]
		prepared.append(row)
	doc.set("planned_treatments", [])
	for row in prepared:
		doc.append("planned_treatments", row)
	return source_edits


@frappe.whitelist()
def get_default_consultation_fee_policy() -> dict:
	_require_clinical_context()
	settings = get_consultation_billing_settings()
	return {
		"allow_editing_default_consultation_fee": bool(
			getattr(settings, "enabled", False)
			and getattr(settings, "auto_add_default_consultation_billing_item", True)
			and can_edit_default_consultation_billing_item(settings)
		),
		"default_consultation_source_detail": DEFAULT_CONSULTATION_SOURCE_DETAIL,
		**consultation_source_billing_edit_policy(),
	}


@frappe.whitelist()
def save_consultation(payload: str | dict) -> dict:
	_require_clinical_context()
	values = _parse_json_object(payload)
	name = values.get("name")
	if name:
		doc = frappe.get_doc("Veterinary Consultation", name)
		doc.check_permission("write")
		can_access_consultation(frappe.session.user, name, raise_exception=True)
		assert_consultation_write_ownership(doc=doc, action="save")
		_assert_timestamp(doc.doctype, doc.name, values.get("modified"))
	else:
		if not frappe.has_permission("Veterinary Consultation", "create"):
			frappe.throw(_("You are not permitted to create consultations."), frappe.PermissionError)
		doc = frappe.new_doc("Veterinary Consultation")
		doc.status = "Draft"

	require_vetedge_platform_access(
		action="clinical_workspace_save_consultation",
		reference_doctype="Veterinary Consultation",
		reference_name=name,
	)
	for fieldname in EDITABLE_SCALAR_FIELDS:
		if fieldname in values:
			doc.set(fieldname, values.get(fieldname))
	_validate_branch(doc.get("service_branch"))
	if "symptoms" in values:
		_replace_simple_table(doc, "symptoms", values.get("symptoms") or [], SYMPTOM_FIELDS)
	if "diagnoses" in values:
		_replace_simple_table(doc, "diagnoses", values.get("diagnoses") or [], DIAGNOSIS_FIELDS)
	source_billing_edits: list[dict] = []
	if "planned_treatments" in values:
		source_billing_edits = _replace_planned_treatments(doc, values.get("planned_treatments") or [])
	if doc.is_new():
		doc.insert()
	else:
		doc.save()
	if source_billing_edits:
		apply_consultation_source_billing_edits(source_billing_edits)
	return get_consultation_detail(doc.name)