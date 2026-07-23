from __future__ import annotations

from typing import Any

import frappe
from frappe import _
from frappe.utils import cint, getdate, now_datetime, nowdate

from vetedge.services.consultation_flow import (
    CONSULTATION_SCOPE_LOCKED_STATUSES,
    VALID_CONSULTATION_STATUS_TRANSITIONS,
    create_follow_up_from_consultation,
    ensure_consultations_enabled,
    get_consultation_appointment_summary,
    get_default_consulting_practitioner,
    transition_consultation_status,
)
from vetedge.services.feature_flags import is_enabled
from vetedge.services.medical_history import get_patient_medical_history_view
from vetedge.services.permissions import (
    can_access_branch_data,
    can_access_consultation,
    can_access_medical_history,
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
    ensure_vitals_enabled,
    get_latest_vitals_for_consultation,
)

PAGE_LENGTH_MAX = 100
CONSULTATION_DOCTYPE = "Veterinary Consultation"
VITALS_DOCTYPE = "Veterinary Vital Signs"
PATIENT_DOCTYPE = "Veterinary Patient"

CONSULTATION_WRITABLE_FIELDS = {
    "patient",
    "consultation_datetime",
    "consultation_type",
    "service_branch",
    "company",
    "consulting_practitioner",
    "linked_appointment",
    "presenting_complaint",
    "examination_notes",
    "assessment_notes",
    "treatment_plan_summary",
    "follow_up_date",
}
CONSULTATION_CHILD_WRITABLE_FIELDS = {
    "symptoms": {"symptom", "notes"},
    "diagnoses": {"diagnosis", "diagnosis_type", "notes"},
    "planned_treatments": {
        "item",
        "description",
        "qty",
        "uom",
        "rate",
        "service_type",
        "treatment_type",
        "notes",
    },
}
CONSULTATION_READ_FIELDS = {
    *CONSULTATION_WRITABLE_FIELDS,
    "name",
    "consultation_title",
    "daily_consultation_number",
    "status",
    "primary_owner",
    "consulting_practitioner_name",
    "follow_up_appointment",
    "dispensary_status",
    "dispensed_treatments",
    "dispensary_confirmed_on",
    "dispensary_confirmed_by",
    "dispensary_stock_entry",
    "linked_invoice",
    "payment_status",
    "consultation_invoices",
    "modified",
}

VITALS_WRITABLE_FIELDS = {
    "patient",
    "consultation",
    "service_branch",
    "recorded_on",
    "temperature",
    "weight",
    "heart_rate",
    "respiratory_rate",
    "body_condition_score",
    "hydration_status",
    "mucous_membrane",
    "capillary_refill_time",
    "pain_score",
    "appetite_status",
    "notes",
}
VITALS_READ_FIELDS = {*VITALS_WRITABLE_FIELDS, "name", "vitals_title", "recorded_by", "modified"}

SYSTEM_CHILD_FIELDS = {
    "doctype",
    "parent",
    "parenttype",
    "parentfield",
    "idx",
    "owner",
    "creation",
    "modified",
    "modified_by",
    "docstatus",
}


def _require_clinical_context(*, consultations: bool = False, vitals: bool = False) -> str:
    require_internal_user()
    if consultations:
        ensure_consultations_enabled()
    if vitals:
        ensure_vitals_enabled()
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


def _parse_json_list(value: str | list | None) -> list:
    if not value:
        return []
    if isinstance(value, list):
        return value
    parsed = frappe.parse_json(value)
    if not isinstance(parsed, list):
        frappe.throw(_("Expected a JSON list."), frappe.ValidationError)
    return parsed


def _page_values(start: int, page_length: int) -> tuple[int, int]:
    return max(cint(start), 0), min(max(cint(page_length) or 25, 1), PAGE_LENGTH_MAX)


def _assert_timestamp(doctype: str, name: str, expected_modified: str | None) -> None:
    if not expected_modified:
        return
    current = frappe.db.get_value(doctype, name, "modified")
    if current and str(current) != str(expected_modified):
        raise frappe.TimestampMismatchError(
            _("This clinical record changed after it was opened. Refresh the Clinical Workspace and try again.")
        )


def _validate_branch(branch: str | None) -> None:
    if branch:
        can_access_branch_data(get_current_user(), branch, raise_exception=True)


def _branch_filters(fieldname: str, branch: str | None = None) -> dict[str, Any]:
    _validate_branch(branch)
    if branch:
        return {fieldname: branch}
    user = get_current_user()
    if user_has_global_branch_access(user):
        return {}
    assigned = get_assigned_branches(user)
    return {fieldname: ["in", assigned]} if assigned else {}


def _permission_count(doctype: str, filters: dict, or_filters: list | None = None) -> int:
    rows = frappe.get_list(
        doctype,
        fields=[{"COUNT": "*", "as": "total"}],
        filters=filters,
        or_filters=or_filters,
        page_length=1,
    )
    return cint(rows[0].get("total")) if rows else 0


def _field_payload(doctype: str, fieldname: str, *, read_only: bool | None = None, hidden: bool | None = None) -> dict:
    field = frappe.get_meta(doctype).get_field(fieldname)
    if not field:
        return {"fieldname": fieldname, "fieldtype": "Data", "label": frappe.unscrub(fieldname)}
    payload = {
        "fieldname": field.fieldname,
        "fieldtype": field.fieldtype,
        "label": field.label or frappe.unscrub(field.fieldname),
        "options": field.options or "",
        "description": field.description or "",
        "default": field.default,
        "reqd": cint(field.reqd),
        "read_only": cint(field.read_only),
        "hidden": cint(field.hidden),
        "depends_on": field.depends_on or "",
        "mandatory_depends_on": field.mandatory_depends_on or "",
        "read_only_depends_on": field.read_only_depends_on or "",
        "in_list_view": cint(field.in_list_view),
    }
    if read_only is not None:
        payload["read_only"] = cint(read_only)
    if hidden is not None:
        payload["hidden"] = cint(hidden)
    return payload


def _child_field_payload(doctype: str, fieldname: str, *, read_only: bool | None = None) -> dict:
    payload = _field_payload(doctype, fieldname, read_only=read_only)
    field = frappe.get_meta(doctype).get_field(fieldname)
    payload["columns"] = cint(getattr(field, "columns", 0)) if field else 0
    return payload


def _table_field_payload(parent_doctype: str, fieldname: str, child_fields: list[dict], *, read_only: bool = False) -> dict:
    payload = _field_payload(parent_doctype, fieldname, read_only=read_only)
    payload["child_fields"] = child_fields
    return payload


def _consultation_schema() -> dict:
    visit_fields = [
        _field_payload(CONSULTATION_DOCTYPE, "patient"),
        _field_payload(CONSULTATION_DOCTYPE, "consultation_datetime"),
        _field_payload(CONSULTATION_DOCTYPE, "consultation_type"),
        _field_payload(CONSULTATION_DOCTYPE, "primary_owner", read_only=True),
        _field_payload(CONSULTATION_DOCTYPE, "service_branch"),
        _field_payload(CONSULTATION_DOCTYPE, "company"),
        _field_payload(CONSULTATION_DOCTYPE, "consulting_practitioner"),
        _field_payload(CONSULTATION_DOCTYPE, "consulting_practitioner_name", read_only=True),
        _field_payload(CONSULTATION_DOCTYPE, "linked_appointment"),
        _field_payload(CONSULTATION_DOCTYPE, "follow_up_appointment", read_only=True),
    ]
    visit_fields[0]["clear_fields"] = ["linked_appointment"]
    visit_fields[4]["description"] = _("Clinical, billing and stock actions remain restricted to this branch.")

    symptoms = _table_field_payload(
        CONSULTATION_DOCTYPE,
        "symptoms",
        [
            _child_field_payload("Consultation Symptom", "symptom"),
            _child_field_payload("Consultation Symptom", "notes"),
        ],
    )
    diagnoses = _table_field_payload(
        CONSULTATION_DOCTYPE,
        "diagnoses",
        [
            _child_field_payload("Consultation Diagnosis", "diagnosis"),
            _child_field_payload("Consultation Diagnosis", "diagnosis_type"),
            _child_field_payload("Consultation Diagnosis", "notes"),
        ],
    )
    planned = _table_field_payload(
        CONSULTATION_DOCTYPE,
        "planned_treatments",
        [
            _child_field_payload("Planned Treatment Item", "item"),
            _child_field_payload("Planned Treatment Item", "description"),
            _child_field_payload("Planned Treatment Item", "qty"),
            _child_field_payload("Planned Treatment Item", "uom"),
            _child_field_payload("Planned Treatment Item", "rate"),
            _child_field_payload("Planned Treatment Item", "amount", read_only=True),
            _child_field_payload("Planned Treatment Item", "billing_status", read_only=True),
            _child_field_payload("Planned Treatment Item", "payment_status", read_only=True),
            _child_field_payload("Planned Treatment Item", "service_type"),
            _child_field_payload("Planned Treatment Item", "treatment_type"),
            _child_field_payload("Planned Treatment Item", "notes"),
        ],
    )
    planned["description"] = _(
        "Treatment rows are locked after Ready for Treatment. Billing and payment state are system controlled."
    )

    return {
        "tabs": [
            {
                "key": "visit",
                "label": _("Visit"),
                "sections": [
                    {
                        "key": "patient-and-visit",
                        "label": _("Patient and Visit"),
                        "description": _("Select the patient, branch, practitioner and appointment context."),
                        "columns": 2,
                        "fields": visit_fields,
                    },
                    {
                        "key": "presenting-complaint",
                        "label": _("Presenting Complaint"),
                        "columns": 1,
                        "fields": [_field_payload(CONSULTATION_DOCTYPE, "presenting_complaint")],
                    },
                ],
            },
            {
                "key": "clinical",
                "label": _("Clinical"),
                "sections": [
                    {
                        "key": "symptoms",
                        "label": _("Symptoms"),
                        "columns": 1,
                        "fields": [symptoms],
                    },
                    {
                        "key": "examination",
                        "label": _("Examination and Assessment"),
                        "columns": 2,
                        "fields": [
                            _field_payload(CONSULTATION_DOCTYPE, "examination_notes"),
                            _field_payload(CONSULTATION_DOCTYPE, "assessment_notes"),
                        ],
                    },
                    {
                        "key": "diagnoses",
                        "label": _("Diagnoses"),
                        "description": _("Diagnosis and treatment capture is restricted to Veterinary Doctors."),
                        "columns": 1,
                        "fields": [diagnoses],
                    },
                ],
            },
            {
                "key": "treatment",
                "label": _("Treatment Plan"),
                "sections": [
                    {
                        "key": "planned-treatments",
                        "label": _("Planned Treatments"),
                        "columns": 1,
                        "fields": [planned],
                    },
                    {
                        "key": "plan-summary",
                        "label": _("Plan and Follow-up"),
                        "columns": 2,
                        "fields": [
                            _field_payload(CONSULTATION_DOCTYPE, "treatment_plan_summary"),
                            _field_payload(CONSULTATION_DOCTYPE, "follow_up_date"),
                        ],
                    },
                ],
            },
        ]
    }


def _vitals_schema() -> dict:
    return {
        "tabs": [
            {
                "key": "vitals",
                "label": _("Vital Signs"),
                "sections": [
                    {
                        "key": "context",
                        "label": _("Patient Context"),
                        "columns": 2,
                        "fields": [
                            _field_payload(VITALS_DOCTYPE, "patient"),
                            _field_payload(VITALS_DOCTYPE, "consultation"),
                            _field_payload(VITALS_DOCTYPE, "service_branch"),
                            _field_payload(VITALS_DOCTYPE, "recorded_on"),
                            _field_payload(VITALS_DOCTYPE, "recorded_by", read_only=True),
                        ],
                    },
                    {
                        "key": "core-metrics",
                        "label": _("Core Metrics"),
                        "columns": 2,
                        "fields": [
                            _field_payload(VITALS_DOCTYPE, "temperature"),
                            _field_payload(VITALS_DOCTYPE, "weight"),
                            _field_payload(VITALS_DOCTYPE, "heart_rate"),
                            _field_payload(VITALS_DOCTYPE, "respiratory_rate"),
                        ],
                    },
                    {
                        "key": "clinical-observations",
                        "label": _("Clinical Observations"),
                        "columns": 2,
                        "fields": [
                            _field_payload(VITALS_DOCTYPE, "body_condition_score"),
                            _field_payload(VITALS_DOCTYPE, "hydration_status"),
                            _field_payload(VITALS_DOCTYPE, "mucous_membrane"),
                            _field_payload(VITALS_DOCTYPE, "capillary_refill_time"),
                            _field_payload(VITALS_DOCTYPE, "pain_score"),
                            _field_payload(VITALS_DOCTYPE, "appetite_status"),
                            _field_payload(VITALS_DOCTYPE, "notes"),
                        ],
                    },
                ],
            }
        ]
    }


def _document_values(doc, fields: set[str], child_fields: dict[str, set[str]] | None = None) -> dict[str, Any]:
    child_fields = child_fields or {}
    values: dict[str, Any] = {}
    for fieldname in fields:
        if fieldname == "modified":
            continue
        value = doc.get(fieldname)
        if fieldname in child_fields:
            values[fieldname] = [row.as_dict(no_nulls=False) for row in value or []]
        elif isinstance(value, list):
            values[fieldname] = [row.as_dict(no_nulls=False) if hasattr(row, "as_dict") else row for row in value]
        else:
            values[fieldname] = value
    return values


def _permissions(doctype: str, doc=None) -> dict[str, bool]:
    return {
        "read": bool(doc.has_permission("read") if doc else frappe.has_permission(doctype, "read")),
        "write": bool(doc.has_permission("write") if doc else frappe.has_permission(doctype, "write")),
        "create": bool(frappe.has_permission(doctype, "create")),
        "delete": False,
    }


def _consultation_transitions(doc) -> list[dict[str, Any]]:
    if not doc or not doc.name or not doc.has_permission("write"):
        return []
    if doc.status in {"Completed", "Cancelled"}:
        return []
    transitions = []
    for target in sorted(VALID_CONSULTATION_STATUS_TRANSITIONS.get(doc.status, set())):
        if target == "Cancelled":
            transitions.append(
                {
                    "key": "cancel",
                    "label": _("Cancel Consultation"),
                    "status": target,
                    "danger": True,
                    "requires_preflight": True,
                }
            )
            continue
        transitions.append(
            {
                "key": f"status-{frappe.scrub(target)}",
                "label": {
                    "In Progress": _("Start Consultation"),
                    "Awaiting Payment": _("Move to Awaiting Payment"),
                    "Pending Dispensary": _("Move to Pending Dispensary"),
                    "Ready for Treatment": _("Mark Ready for Treatment"),
                    "Completed": _("Complete Consultation"),
                }.get(target, target),
                "status": target,
                "primary": target in {"In Progress", "Ready for Treatment", "Completed"},
            }
        )
    return transitions


def _consultation_actions(doc) -> list[dict[str, Any]]:
    if not doc or not doc.name:
        return []
    actions: list[dict[str, Any]] = [
        {"key": "medical_history", "label": _("Medical History"), "kind": "history"},
        {"key": "appointments", "label": _("Appointments"), "kind": "appointments"},
        {"key": "latest_vitals", "label": _("Latest Vitals"), "kind": "latest_vitals"},
    ]
    if is_enabled("vitals") and frappe.has_permission(VITALS_DOCTYPE, "create") and doc.status not in {"Completed", "Cancelled"}:
        actions.append({"key": "new_vitals", "label": _("New Vitals"), "kind": "new_vitals", "primary": True})
    if doc.status != "Cancelled":
        actions.append({"key": "billing", "label": _("Billing / Payment"), "kind": "billing"})
    if doc.status not in CONSULTATION_SCOPE_LOCKED_STATUSES:
        if frappe.has_permission("Veterinary Lab Order", "create"):
            actions.append({"key": "new_lab", "label": _("New Lab Order"), "kind": "new_lab"})
        if frappe.has_permission("Veterinary Vaccination Record", "create"):
            actions.append({"key": "new_vaccination", "label": _("New Vaccination"), "kind": "new_vaccination"})
    if doc.status not in {"Completed", "Cancelled"}:
        actions.extend(
            [
                {"key": "follow_up", "label": _("Create Follow-up"), "kind": "follow_up"},
                {"key": "hospitalisation", "label": _("Admit for Hospitalisation"), "kind": "hospitalisation"},
            ]
        )
    if doc.dispensary_status == "Pending Dispensary":
        actions.append({"key": "dispensary", "label": _("Confirm Dispensary Issue"), "kind": "dispensary"})
    return actions


def _consultation_related(doc) -> dict[str, Any]:
    latest_vitals = None
    if is_enabled("vitals") and frappe.has_permission(VITALS_DOCTYPE, "read"):
        latest_vitals = get_latest_vitals_for_consultation(doc.name)
    lab_orders = []
    if frappe.has_permission("Veterinary Lab Order", "read"):
        lab_orders = frappe.get_list(
            "Veterinary Lab Order",
            filters={"consultation": doc.name},
            fields=["name", "lab_order_title", "status", "requested_on", "requested_by", "linked_invoice"],
            order_by="requested_on desc, modified desc",
            page_length=25,
        )
    vaccinations = []
    if frappe.has_permission("Veterinary Vaccination Record", "read"):
        vaccinations = frappe.get_list(
            "Veterinary Vaccination Record",
            filters={"linked_consultation": doc.name},
            fields=["name", "vaccination_title", "vaccine", "status", "administered_on", "next_due_date", "linked_invoice"],
            order_by="modified desc",
            page_length=25,
        )
    hospitalisations = []
    if frappe.db.exists("DocType", "Veterinary Hospitalisation") and frappe.has_permission(
        "Veterinary Hospitalisation", "read"
    ):
        meta = frappe.get_meta("Veterinary Hospitalisation")
        consultation_field = "consultation" if meta.has_field("consultation") else "linked_consultation"
        hospitalisations = frappe.get_list(
            "Veterinary Hospitalisation",
            filters={consultation_field: doc.name},
            fields=["name", "status", "admission_datetime", "discharge_datetime", "service_branch"],
            order_by="modified desc",
            page_length=10,
        )
    return {
        "appointments": get_consultation_appointment_summary(doc.name),
        "latest_vitals": latest_vitals,
        "lab_orders": lab_orders,
        "vaccinations": vaccinations,
        "hospitalisations": hospitalisations,
    }


def _apply_scalar_values(doc, values: dict[str, Any], allowed: set[str]) -> None:
    for fieldname in allowed:
        if fieldname in values:
            doc.set(fieldname, values.get(fieldname))


def _replace_child_rows_preserving_protected(
    doc,
    fieldname: str,
    rows: list,
    editable_fields: set[str],
) -> None:
    existing = {row.name: row.as_dict(no_nulls=False) for row in doc.get(fieldname) or [] if row.name}
    doc.set(fieldname, [])
    for incoming in rows:
        if not isinstance(incoming, dict):
            continue
        row_name = incoming.get("name")
        payload: dict[str, Any] = {}
        if row_name and row_name in existing:
            payload = {
                key: value
                for key, value in existing[row_name].items()
                if key not in SYSTEM_CHILD_FIELDS
            }
            payload["name"] = row_name
        for key in editable_fields:
            if key in incoming:
                payload[key] = incoming.get(key)
        doc.append(fieldname, payload)


def _apply_consultation_values(doc, values: dict[str, Any]) -> None:
    _apply_scalar_values(doc, values, CONSULTATION_WRITABLE_FIELDS)
    for fieldname, editable_fields in CONSULTATION_CHILD_WRITABLE_FIELDS.items():
        if fieldname in values:
            _replace_child_rows_preserving_protected(
                doc,
                fieldname,
                _parse_json_list(values.get(fieldname)),
                editable_fields,
            )


def _apply_vitals_values(doc, values: dict[str, Any]) -> None:
    _apply_scalar_values(doc, values, VITALS_WRITABLE_FIELDS)


@frappe.whitelist()
def get_clinical_definition() -> dict[str, Any]:
    _require_clinical_context()
    return {
        "consultations": {
            "doctype": CONSULTATION_DOCTYPE,
            "title": _("Consultations"),
            "singular": _("Consultation"),
            "columns": [
                {"fieldname": "name", "label": _("Consultation"), "fieldtype": "Data"},
                {"fieldname": "patient", "label": _("Patient"), "fieldtype": "Link"},
                {"fieldname": "consultation_datetime", "label": _("Date / Time"), "fieldtype": "Datetime"},
                {"fieldname": "consulting_practitioner_name", "label": _("Practitioner"), "fieldtype": "Data"},
                {"fieldname": "service_branch", "label": _("Branch"), "fieldtype": "Link"},
                {"fieldname": "payment_status", "label": _("Payment"), "fieldtype": "Select", "status": True},
                {"fieldname": "status", "label": _("Status"), "fieldtype": "Select", "status": True},
            ],
            "filters": [
                _field_payload(CONSULTATION_DOCTYPE, "status"),
                _field_payload(CONSULTATION_DOCTYPE, "service_branch"),
                _field_payload(CONSULTATION_DOCTYPE, "consulting_practitioner"),
                _field_payload(CONSULTATION_DOCTYPE, "patient"),
            ],
            "permissions": _permissions(CONSULTATION_DOCTYPE),
        },
        "vitals": {
            "doctype": VITALS_DOCTYPE,
            "title": _("Vital Signs"),
            "singular": _("Vital Signs"),
            "columns": [
                {"fieldname": "name", "label": _("Vitals"), "fieldtype": "Data"},
                {"fieldname": "patient", "label": _("Patient"), "fieldtype": "Link"},
                {"fieldname": "consultation", "label": _("Consultation"), "fieldtype": "Link"},
                {"fieldname": "recorded_on", "label": _("Recorded On"), "fieldtype": "Datetime"},
                {"fieldname": "weight", "label": _("Weight"), "fieldtype": "Float"},
                {"fieldname": "temperature", "label": _("Temperature"), "fieldtype": "Float"},
                {"fieldname": "service_branch", "label": _("Branch"), "fieldtype": "Link"},
            ],
            "filters": [
                _field_payload(VITALS_DOCTYPE, "service_branch"),
                _field_payload(VITALS_DOCTYPE, "patient"),
                _field_payload(VITALS_DOCTYPE, "consultation"),
            ],
            "permissions": _permissions(VITALS_DOCTYPE),
            "enabled": is_enabled("vitals"),
        },
        "history": {
            "title": _("Medical History"),
            "subtitle": _("Review the patient's consultation, vitals, diagnosis, treatment, lab and vaccination timeline."),
        },
    }


@frappe.whitelist()
def get_clinical_summary(branch: str | None = None, reference_date: str | None = None) -> dict[str, Any]:
    _require_clinical_context()
    day = getdate(reference_date or nowdate())
    consultation_filters = _branch_filters("service_branch", branch)
    vitals_filters = _branch_filters("service_branch", branch)
    return {
        "active_consultations": _permission_count(
            CONSULTATION_DOCTYPE,
            {**consultation_filters, "status": ["not in", ["Completed", "Cancelled"]]},
        ) if frappe.has_permission(CONSULTATION_DOCTYPE, "read") else 0,
        "awaiting_payment": _permission_count(
            CONSULTATION_DOCTYPE,
            {**consultation_filters, "status": "Awaiting Payment"},
        ) if frappe.has_permission(CONSULTATION_DOCTYPE, "read") else 0,
        "pending_dispensary": _permission_count(
            CONSULTATION_DOCTYPE,
            {**consultation_filters, "dispensary_status": "Pending Dispensary"},
        ) if frappe.has_permission(CONSULTATION_DOCTYPE, "read") else 0,
        "today_vitals": _permission_count(
            VITALS_DOCTYPE,
            {
                **vitals_filters,
                "recorded_on": ["between", [f"{day} 00:00:00", f"{day} 23:59:59"]],
            },
        ) if is_enabled("vitals") and frappe.has_permission(VITALS_DOCTYPE, "read") else 0,
        "reference_date": str(day),
    }


@frappe.whitelist()
def get_consultation_list(
    search: str = "",
    status: str | None = None,
    branch: str | None = None,
    practitioner: str | None = None,
    patient: str | None = None,
    start: int = 0,
    page_length: int = 25,
) -> dict[str, Any]:
    _require_clinical_context(consultations=True)
    if not frappe.has_permission(CONSULTATION_DOCTYPE, "read"):
        frappe.throw(_("You are not permitted to view consultations."), frappe.PermissionError)
    filters = _branch_filters("service_branch", branch)
    for fieldname, value in (
        ("status", status),
        ("consulting_practitioner", practitioner),
        ("patient", patient),
    ):
        if value:
            filters[fieldname] = value
    query = str(search or "").strip()
    or_filters = None
    if query:
        or_filters = [
            [CONSULTATION_DOCTYPE, fieldname, "like", f"%{query}%"]
            for fieldname in (
                "name",
                "consultation_title",
                "patient",
                "primary_owner",
                "consulting_practitioner_name",
                "presenting_complaint",
            )
        ]
    start, page_length = _page_values(start, page_length)
    rows = frappe.get_list(
        CONSULTATION_DOCTYPE,
        fields=[
            "name",
            "consultation_title",
            "patient",
            "primary_owner",
            "consultation_datetime",
            "consultation_type",
            "consulting_practitioner",
            "consulting_practitioner_name",
            "service_branch",
            "status",
            "payment_status",
            "dispensary_status",
            "modified",
        ],
        filters=filters,
        or_filters=or_filters,
        order_by="consultation_datetime desc, modified desc",
        start=start,
        page_length=page_length,
    )
    return {
        "rows": rows,
        "total": _permission_count(CONSULTATION_DOCTYPE, filters, or_filters),
        "start": start,
        "page_length": page_length,
    }


@frappe.whitelist()
def get_consultation_document(name: str | None = None, defaults: str | dict | None = None) -> dict[str, Any]:
    _require_clinical_context(consultations=True)
    is_new = not name
    if name:
        doc = frappe.get_doc(CONSULTATION_DOCTYPE, name)
        doc.check_permission("read")
        can_access_consultation(get_current_user(), name, raise_exception=True)
    else:
        if not frappe.has_permission(CONSULTATION_DOCTYPE, "create"):
            frappe.throw(_("You are not permitted to create consultations."), frappe.PermissionError)
        doc = frappe.new_doc(CONSULTATION_DOCTYPE)
        incoming = _parse_json_object(defaults)
        _apply_scalar_values(doc, incoming, CONSULTATION_WRITABLE_FIELDS)
        if not doc.consulting_practitioner:
            doc.consulting_practitioner = get_default_consulting_practitioner()
        if not doc.consultation_datetime:
            doc.consultation_datetime = now_datetime()
    permissions = _permissions(CONSULTATION_DOCTYPE, doc)
    return {
        "doctype": CONSULTATION_DOCTYPE,
        "name": None if is_new else doc.name,
        "is_new": is_new,
        "title": _("New Consultation") if is_new else (doc.consultation_title or doc.name),
        "schema": _consultation_schema(),
        "values": _document_values(doc, CONSULTATION_READ_FIELDS, CONSULTATION_CHILD_WRITABLE_FIELDS),
        "state": doc.status or "Draft",
        "docstatus": cint(doc.docstatus),
        "permissions": permissions,
        "modified": None if is_new else doc.modified,
        "transitions": [] if is_new else _consultation_transitions(doc),
        "actions": [] if is_new else _consultation_actions(doc),
        "scope_locked": bool(doc.status in CONSULTATION_SCOPE_LOCKED_STATUSES),
        "related": {} if is_new else _consultation_related(doc),
    }


@frappe.whitelist()
def save_consultation_document(
    values: str | dict,
    name: str | None = None,
    modified: str | None = None,
) -> dict[str, Any]:
    _require_clinical_context(consultations=True)
    require_vetedge_platform_access(
        action="save_clinical_workspace_consultation",
        reference_doctype=CONSULTATION_DOCTYPE,
        reference_name=name,
    )
    incoming = _parse_json_object(values)
    if name:
        doc = frappe.get_doc(CONSULTATION_DOCTYPE, name)
        doc.check_permission("write")
        can_access_consultation(get_current_user(), name, raise_exception=True)
        _assert_timestamp(CONSULTATION_DOCTYPE, name, modified)
    else:
        if not frappe.has_permission(CONSULTATION_DOCTYPE, "create"):
            frappe.throw(_("You are not permitted to create consultations."), frappe.PermissionError)
        doc = frappe.new_doc(CONSULTATION_DOCTYPE)
        doc.status = "Draft"
    _apply_consultation_values(doc, incoming)
    if doc.is_new():
        doc.insert()
    else:
        doc.save()
    return get_consultation_document(doc.name)


@frappe.whitelist()
def transition_clinical_consultation(
    name: str,
    status: str,
    modified: str | None = None,
) -> dict[str, Any]:
    _require_clinical_context(consultations=True)
    doc = frappe.get_doc(CONSULTATION_DOCTYPE, name)
    doc.check_permission("write")
    can_access_consultation(get_current_user(), name, raise_exception=True)
    _assert_timestamp(CONSULTATION_DOCTYPE, name, modified)
    result = transition_consultation_status(name, status)
    return {"result": result, "document": get_consultation_document(name)}


@frappe.whitelist()
def get_consultation_cancellation_context(name: str) -> dict[str, Any]:
    _require_clinical_context(consultations=True)
    doc = frappe.get_doc(CONSULTATION_DOCTYPE, name)
    doc.check_permission("read")
    can_access_consultation(get_current_user(), name, raise_exception=True)
    from vetedge.services.consultation_cancellation import get_consultation_cancellation_preflight

    return get_consultation_cancellation_preflight(name)


@frappe.whitelist()
def get_consultation_context_from_appointment(appointment: str) -> dict[str, Any]:
    _require_clinical_context(consultations=True)
    if not appointment:
        return {}
    doc = frappe.get_doc("Veterinary Appointment", appointment)
    doc.check_permission("read")
    _validate_branch(doc.branch)
    if doc.status not in {"Confirmed", "Checked In"}:
        frappe.throw(_("Only Confirmed or Checked In appointments can start a consultation."), frappe.ValidationError)
    if doc.linked_consultation:
        frappe.throw(_("This appointment is already linked to a consultation."), frappe.ValidationError)
    return {
        "appointment": doc.name,
        "patient": doc.patient,
        "service_branch": doc.branch,
        "consulting_practitioner": doc.practitioner,
        "presenting_complaint": doc.notes,
        "appointment_type": doc.appointment_type,
    }


@frappe.whitelist()
def get_patient_clinical_defaults(patient: str) -> dict[str, Any]:
    _require_clinical_context()
    if not patient:
        return {}
    doc = frappe.get_doc(PATIENT_DOCTYPE, patient)
    doc.check_permission("read")
    _validate_branch(doc.default_branch)
    return {
        "patient": doc.name,
        "primary_owner": doc.primary_owner,
        "service_branch": doc.default_branch,
        "species": doc.species,
        "breed": doc.breed,
        "status": doc.status,
    }


@frappe.whitelist()
def get_clinical_treatment_defaults(
    item: str,
    company: str | None = None,
    customer: str | None = None,
    branch: str | None = None,
) -> dict[str, Any]:
    _require_clinical_context(consultations=True)
    _validate_branch(branch)
    return get_treatment_item_defaults_for_consultation(item, company, customer, branch)


@frappe.whitelist()
def get_vitals_list(
    search: str = "",
    branch: str | None = None,
    patient: str | None = None,
    consultation: str | None = None,
    start: int = 0,
    page_length: int = 25,
) -> dict[str, Any]:
    _require_clinical_context(vitals=True)
    if not frappe.has_permission(VITALS_DOCTYPE, "read"):
        frappe.throw(_("You are not permitted to view vital signs."), frappe.PermissionError)
    filters = _branch_filters("service_branch", branch)
    if patient:
        filters["patient"] = patient
    if consultation:
        filters["consultation"] = consultation
    query = str(search or "").strip()
    or_filters = None
    if query:
        or_filters = [
            [VITALS_DOCTYPE, fieldname, "like", f"%{query}%"]
            for fieldname in ("name", "vitals_title", "patient", "consultation", "recorded_by")
        ]
    start, page_length = _page_values(start, page_length)
    rows = frappe.get_list(
        VITALS_DOCTYPE,
        fields=[
            "name",
            "vitals_title",
            "patient",
            "consultation",
            "service_branch",
            "recorded_on",
            "recorded_by",
            "temperature",
            "weight",
            "heart_rate",
            "respiratory_rate",
            "body_condition_score",
            "pain_score",
            "modified",
        ],
        filters=filters,
        or_filters=or_filters,
        order_by="recorded_on desc, modified desc",
        start=start,
        page_length=page_length,
    )
    return {
        "rows": rows,
        "total": _permission_count(VITALS_DOCTYPE, filters, or_filters),
        "start": start,
        "page_length": page_length,
    }


@frappe.whitelist()
def get_vitals_document(name: str | None = None, defaults: str | dict | None = None) -> dict[str, Any]:
    _require_clinical_context(vitals=True)
    is_new = not name
    if name:
        doc = frappe.get_doc(VITALS_DOCTYPE, name)
        doc.check_permission("read")
        _validate_branch(doc.service_branch)
    else:
        if not frappe.has_permission(VITALS_DOCTYPE, "create"):
            frappe.throw(_("You are not permitted to create vital signs."), frappe.PermissionError)
        doc = frappe.new_doc(VITALS_DOCTYPE)
        _apply_vitals_values(doc, _parse_json_object(defaults))
        if doc.consultation:
            context = frappe.db.get_value(
                CONSULTATION_DOCTYPE,
                doc.consultation,
                ["patient", "service_branch"],
                as_dict=True,
            )
            if context:
                doc.patient = context.patient
                doc.service_branch = context.service_branch
        if not doc.recorded_on:
            doc.recorded_on = now_datetime()
    return {
        "doctype": VITALS_DOCTYPE,
        "name": None if is_new else doc.name,
        "is_new": is_new,
        "title": _("New Vital Signs") if is_new else (doc.vitals_title or doc.name),
        "schema": _vitals_schema(),
        "values": _document_values(doc, VITALS_READ_FIELDS),
        "state": _("New") if is_new else _("Recorded"),
        "docstatus": cint(doc.docstatus),
        "permissions": _permissions(VITALS_DOCTYPE, doc),
        "modified": None if is_new else doc.modified,
    }


@frappe.whitelist()
def save_vitals_document(
    values: str | dict,
    name: str | None = None,
    modified: str | None = None,
) -> dict[str, Any]:
    _require_clinical_context(vitals=True)
    require_vetedge_platform_access(
        action="save_clinical_workspace_vitals",
        reference_doctype=VITALS_DOCTYPE,
        reference_name=name,
    )
    incoming = _parse_json_object(values)
    if name:
        doc = frappe.get_doc(VITALS_DOCTYPE, name)
        doc.check_permission("write")
        _validate_branch(doc.service_branch)
        _assert_timestamp(VITALS_DOCTYPE, name, modified)
    else:
        if not frappe.has_permission(VITALS_DOCTYPE, "create"):
            frappe.throw(_("You are not permitted to create vital signs."), frappe.PermissionError)
        doc = frappe.new_doc(VITALS_DOCTYPE)
    _apply_vitals_values(doc, incoming)
    if doc.is_new():
        doc.insert()
    else:
        doc.save()
    return get_vitals_document(doc.name)


@frappe.whitelist()
def get_clinical_medical_history(
    patient: str,
    from_date: str | None = None,
    to_date: str | None = None,
    limit: int = 100,
) -> dict[str, Any]:
    _require_clinical_context()
    can_access_medical_history(get_current_user(), patient, raise_exception=True)
    return get_patient_medical_history_view(patient, from_date, to_date, limit)


@frappe.whitelist()
def perform_consultation_action(
    name: str,
    action: str,
    modified: str | None = None,
    values: str | dict | None = None,
) -> dict[str, Any]:
    _require_clinical_context(consultations=True)
    doc = frappe.get_doc(CONSULTATION_DOCTYPE, name)
    doc.check_permission("write")
    can_access_consultation(get_current_user(), name, raise_exception=True)
    _assert_timestamp(CONSULTATION_DOCTYPE, name, modified)
    require_vetedge_platform_access(
        action=f"clinical_workspace_{action}",
        reference_doctype=CONSULTATION_DOCTYPE,
        reference_name=name,
    )
    payload = _parse_json_object(values)
    result: Any
    if action == "create_vitals":
        result = create_vitals_from_consultation(name, payload)
    elif action == "create_follow_up":
        result = create_follow_up_from_consultation(
            name,
            payload.get("appointment_datetime"),
            payload.get("notes"),
        )
    elif action == "create_lab_order":
        from vetedge.services.lab import create_lab_order_from_consultation

        result = create_lab_order_from_consultation(
            consultation=name,
            lab_tests=payload.get("lab_tests") or [],
            sample_notes=payload.get("sample_notes"),
        )
    elif action == "create_vaccination":
        from vetedge.services.vaccination import create_vaccination_from_consultation

        result = create_vaccination_from_consultation(name, values=payload)
    elif action == "admit_hospitalisation":
        from vetedge.services.hospitalisation import create_hospitalisation_from_consultation

        result = create_hospitalisation_from_consultation(consultation_name=name)
    elif action == "confirm_dispensary":
        from vetedge.services.dispensary import confirm_dispensary_issue

        result = confirm_dispensary_issue(name, payload.get("dispensed_items"))
    else:
        frappe.throw(_("Unsupported clinical action."), frappe.ValidationError)
    return {"result": result, "document": get_consultation_document(name)}


@frappe.whitelist()
def get_clinical_action_options(name: str, action: str) -> dict[str, Any]:
    _require_clinical_context(consultations=True)
    doc = frappe.get_doc(CONSULTATION_DOCTYPE, name)
    doc.check_permission("read")
    can_access_consultation(get_current_user(), name, raise_exception=True)
    if action == "lab":
        from vetedge.services.lab import get_active_lab_tests_for_picker

        return {"lab_tests": get_active_lab_tests_for_picker()}
    if action == "vaccination":
        vaccine_meta = frappe.get_meta("Veterinary Vaccine")
        vaccine_filters: dict[str, Any] = {}
        if vaccine_meta.has_field("is_active"):
            vaccine_filters["is_active"] = 1
        elif vaccine_meta.has_field("disabled"):
            vaccine_filters["disabled"] = 0
        rows = frappe.get_list(
            "Veterinary Vaccine",
            filters=vaccine_filters,
            fields=["name", "vaccine_name", "species", "default_item", "default_price", "default_next_due_days"],
            order_by="vaccine_name asc",
            page_length=100,
        )
        patient_species = frappe.db.get_value(PATIENT_DOCTYPE, doc.patient, "species")
        return {
            "vaccines": [row for row in rows if not row.get("species") or row.get("species") == patient_species],
            "patient_species": patient_species,
        }
    if action == "dispensary":
        from vetedge.services.dispensary import get_dispensed_item_preview

        return get_dispensed_item_preview(name)
    if action == "cancellation":
        return get_consultation_cancellation_context(name)
    return {}


@frappe.whitelist()
def get_clinical_link_options(
    context: str,
    fieldname: str,
    query: str = "",
    values: str | dict | None = None,
    child_doctype: str | None = None,
    page_length: int = 20,
) -> list[dict[str, Any]]:
    _require_clinical_context()
    text = str(query or "").strip()
    page_length = min(max(cint(page_length) or 20, 1), 50)
    model = _parse_json_object(values)

    if fieldname in {"consulting_practitioner", "practitioner"}:
        rows = get_veterinary_doctor_users("User", text, "name", 0, page_length, {})
        return [{"value": row[0], "label": row[1] or row[0]} for row in rows]

    if context == "consultation" and fieldname == "linked_appointment":
        patient = model.get("patient")
        if not patient:
            return []
        filters: dict[str, Any] = {
            "patient": patient,
            "status": ["in", ["Confirmed", "Checked In"]],
            "linked_consultation": ["in", ["", None]],
        }
        if model.get("service_branch"):
            filters["branch"] = model.get("service_branch")
        rows = frappe.get_list(
            "Veterinary Appointment",
            filters=filters,
            or_filters=[
                ["Veterinary Appointment", "name", "like", f"%{text}%"],
                ["Veterinary Appointment", "appointment_title", "like", f"%{text}%"],
            ] if text else None,
            fields=["name", "appointment_title", "appointment_datetime", "branch", "practitioner", "notes", "patient"],
            order_by="appointment_datetime asc",
            page_length=page_length,
        )
        return [
            {
                "value": row.name,
                "label": row.appointment_title or row.name,
                "description": str(row.appointment_datetime or ""),
                "patient": row.patient,
                "service_branch": row.branch,
                "consulting_practitioner": row.practitioner,
                "presenting_complaint": row.notes,
            }
            for row in rows
        ]

    if child_doctype == "Planned Treatment Item" and fieldname == "item":
        rows = get_treatment_item_link_options("Item", text, "name", 0, page_length, {})
        return [{"value": row[0], "label": row[1] or row[0]} for row in rows]

    option_doctype = None
    filters: dict[str, Any] = {}
    if fieldname == "patient":
        option_doctype = PATIENT_DOCTYPE
        filters["status"] = ["!=", "Deceased"]
    elif fieldname in {"service_branch", "branch"}:
        option_doctype = "Branch"
        assigned_filter = _branch_filters("name")
        filters.update(assigned_filter)
    elif fieldname == "consultation_type":
        option_doctype = "Consultation Type"
        if frappe.get_meta(option_doctype).has_field("disabled"):
            filters["disabled"] = 0
    elif child_doctype == "Consultation Symptom" and fieldname == "symptom":
        option_doctype = "Veterinary Symptom"
        filters["disabled"] = 0
    elif child_doctype == "Consultation Diagnosis" and fieldname == "diagnosis":
        option_doctype = "Veterinary Diagnosis"
        filters["disabled"] = 0
    elif child_doctype == "Planned Treatment Item" and fieldname == "service_type":
        option_doctype = "Veterinary Service Type"
        filters["disabled"] = 0
    elif child_doctype == "Planned Treatment Item" and fieldname == "treatment_type":
        option_doctype = "Veterinary Treatment Type"
        filters["disabled"] = 0
    elif child_doctype == "Planned Treatment Item" and fieldname == "uom":
        option_doctype = "UOM"
        if frappe.get_meta(option_doctype).has_field("enabled"):
            filters["enabled"] = 1
    elif fieldname == "company":
        option_doctype = "Company"
    elif context == "vitals" and fieldname == "consultation":
        option_doctype = CONSULTATION_DOCTYPE
        if model.get("patient"):
            filters["patient"] = model.get("patient")
        if model.get("service_branch"):
            filters["service_branch"] = model.get("service_branch")
        filters["status"] = ["!=", "Cancelled"]

    if not option_doctype:
        frappe.throw(_("Unsupported Clinical Workspace Link field."), frappe.ValidationError)
    meta = frappe.get_meta(option_doctype)
    title_field = meta.title_field if meta.title_field and meta.has_field(meta.title_field) else "name"
    fields = ["name"]
    if title_field != "name":
        fields.append(title_field)
    search_fields = ["name"]
    for candidate in [title_field, *str(meta.search_fields or "").split(",")]:
        candidate = str(candidate or "").strip()
        if candidate and meta.has_field(candidate) and candidate not in search_fields:
            search_fields.append(candidate)
    or_filters = [[option_doctype, candidate, "like", f"%{text}%"] for candidate in search_fields[:5]] if text else None
    extra_fields = []
    if option_doctype == CONSULTATION_DOCTYPE:
        extra_fields = ["patient", "service_branch", "status", "consultation_datetime"]
    rows = frappe.get_list(
        option_doctype,
        filters=filters,
        or_filters=or_filters,
        fields=[*fields, *extra_fields],
        order_by=f"{title_field} asc",
        page_length=page_length,
    )
    return [
        {
            "value": row.get("name"),
            "label": row.get(title_field) or row.get("name"),
            "description": str(row.get("consultation_datetime") or "") if option_doctype == CONSULTATION_DOCTYPE else (
                row.get("name") if title_field != "name" else ""
            ),
            **({
                "patient": row.get("patient"),
                "service_branch": row.get("service_branch"),
            } if option_doctype == CONSULTATION_DOCTYPE else {}),
        }
        for row in rows
    ]
