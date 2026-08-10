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
from vetedge.services.permissions import can_access_consultation
from vetedge.services.platform_access import require_vetedge_platform_access

PROTECTED_TREATMENT_SOURCE_TYPES = {"Consultation", "Lab Order", "Vaccination"}
LOCKED_TREATMENT_PAYMENT_STATUSES = {"Paid", "Partly Paid", "Cancelled"}


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


def _replace_planned_treatments(doc, rows: list[dict]) -> None:
	settings = get_consultation_billing_settings()
	existing_by_name = {row.name: row for row in doc.get("planned_treatments") or [] if row.name}
	incoming_names = {row.get("name") for row in rows or [] if row.get("name")}
	for existing in existing_by_name.values():
		if existing.name in incoming_names:
			continue
		if _treatment_row_removal_is_protected(existing):
			frappe.throw(
				_("Source-generated or billed treatment row {0} cannot be removed from the Clinical Workspace.").format(existing.item),
				frappe.ValidationError,
			)
	prepared: list[dict[str, Any]] = []
	for raw in rows or []:
		name = raw.get("name")
		existing = existing_by_name.get(name)
		if existing and _treatment_row_edit_is_protected(existing, settings) and not _same_editable_treatment(existing, raw):
			frappe.throw(
				_("Source-generated or billed treatment row {0} cannot be edited. Create a new treatment row instead.").format(existing.item),
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
	if "planned_treatments" in values:
		_replace_planned_treatments(doc, values.get("planned_treatments") or [])
	if doc.is_new():
		doc.insert()
	else:
		doc.save()
	return get_consultation_detail(doc.name)
