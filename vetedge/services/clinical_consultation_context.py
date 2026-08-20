from __future__ import annotations

import frappe
from frappe import _
from frappe.utils import cint, cstr

from vetedge.services.permissions import can_access_consultation
from vetedge.services.portal_access import require_internal_user


CONSULTATION_DOCTYPE = "Veterinary Consultation"
CLOSED_CONSULTATION_STATUSES = {"Completed", "Cancelled"}
LAB_CONTEXT_EDITABLE_STATUSES = {"Draft", "Ordered"}
VACCINATION_CONTEXT_EDITABLE_STATUSES = {"Draft"}
PAGE_LENGTH_MAX = 50

CONTEXT_FIELDS = {
    "Veterinary Lab Order": "consultation",
    "Veterinary Vaccination Record": "linked_consultation",
}
CREATE_CONTEXT_FIELDS = {
    **CONTEXT_FIELDS,
    "Veterinary Vital Signs": "consultation",
}


def _clean(value) -> str:
    return cstr(value or "").strip()


def _consultation_context(consultation: str) -> frappe._dict:
    row = frappe.db.get_value(
        CONSULTATION_DOCTYPE,
        consultation,
        [
            "name",
            "consultation_title",
            "patient",
            "status",
            "consultation_datetime",
            "service_branch",
            "consulting_practitioner_name",
        ],
        as_dict=True,
    )
    if not row:
        frappe.throw(_("Consultation must be a valid Veterinary Consultation."), frappe.ValidationError)
    return row


def _previous_link(doc, fieldname: str) -> str:
    previous = doc.get_doc_before_save() if getattr(doc, "get_doc_before_save", None) else None
    return _clean(previous.get(fieldname)) if previous else ""


def _is_new_or_changed_link(doc, fieldname: str) -> bool:
    return _clean(doc.get(fieldname)) != _previous_link(doc, fieldname)


def _validate_requested_consultation(patient: str, consultation: str) -> None:
    context = _consultation_context(consultation)
    if _clean(context.get("patient")) != _clean(patient):
        frappe.throw(
            _("The selected Consultation must belong to patient {0}.").format(patient),
            frappe.ValidationError,
        )
    if context.get("status") in CLOSED_CONSULTATION_STATUSES:
        frappe.throw(
            _("Only an open Consultation for this patient can be linked."),
            frappe.ValidationError,
        )
    can_access_consultation(frappe.session.user, consultation, raise_exception=True)


def validate_consultation_context_link(doc, fieldname: str) -> None:
    consultation = _clean(doc.get(fieldname))
    if not consultation:
        return

    context = _consultation_context(consultation)
    if _clean(context.get("patient")) != _clean(doc.get("patient")):
        frappe.throw(
            _("The selected Consultation must belong to patient {0}.").format(doc.get("patient")),
            frappe.ValidationError,
        )

    if not _is_new_or_changed_link(doc, fieldname):
        # A consultation may legitimately close after a Lab/Vaccination record
        # was linked. Existing lineage stays valid and must not block later
        # clinical workflow saves merely because the consultation has closed.
        return

    if context.get("status") in CLOSED_CONSULTATION_STATUSES:
        frappe.throw(
            _("Only an open Consultation for this patient can be linked."),
            frappe.ValidationError,
        )

    can_access_consultation(frappe.session.user, consultation, raise_exception=True)


def enforce_lab_consultation_context(doc, method: str | None = None) -> None:
    validate_consultation_context_link(doc, "consultation")


def enforce_vaccination_consultation_context(doc, method: str | None = None) -> None:
    validate_consultation_context_link(doc, "linked_consultation")


def _lab_has_result_content(doc) -> bool:
    return any(
        any(
            row.get(fieldname) not in (None, "")
            for fieldname in ("result_value", "result_text", "result_attachment", "remarks")
        )
        for row in doc.get("lab_tests") or []
    )


def can_assign_consultation_link(doc) -> bool:
    fieldname = CONTEXT_FIELDS.get(doc.doctype)
    if not fieldname or _clean(doc.get(fieldname)):
        return False

    if doc.doctype == "Veterinary Lab Order":
        if _clean(doc.get("status")) not in LAB_CONTEXT_EDITABLE_STATUSES:
            return False
        if _clean(doc.get("linked_invoice")) or _lab_has_result_content(doc):
            return False
        return True

    if doc.doctype == "Veterinary Vaccination Record":
        if _clean(doc.get("status")) not in VACCINATION_CONTEXT_EDITABLE_STATUSES:
            return False
        if _clean(doc.get("linked_invoice")) or _clean(doc.get("stock_entry_reference")):
            return False
        return True

    return False


def assert_consultation_link_change_allowed(doc, requested_value) -> None:
    fieldname = CONTEXT_FIELDS.get(doc.doctype)
    if not fieldname:
        frappe.throw(_("Consultation context is not supported for this clinical record."), frappe.ValidationError)

    current = _clean(doc.get(fieldname))
    requested = _clean(requested_value)
    if current == requested:
        return
    if current:
        frappe.throw(
            _("Consultation is read-only after it has been linked to this clinical record."),
            frappe.ValidationError,
        )
    if not requested:
        return
    if not can_assign_consultation_link(doc):
        frappe.throw(
            _("Consultation can only be linked before billing or clinical processing has started."),
            frappe.ValidationError,
        )

    _validate_requested_consultation(doc.get("patient"), requested)


def apply_editor_consultation_link_change(doctype: str, name: str, payload: dict) -> None:
    fieldname = CONTEXT_FIELDS.get(doctype)
    if not fieldname or fieldname not in payload:
        return

    requested = payload.pop(fieldname, None)
    doc = frappe.get_doc(doctype, name)
    assert_consultation_link_change_allowed(doc, requested)
    if _clean(doc.get(fieldname)) == _clean(requested):
        return
    doc.set(fieldname, requested or None)
    doc.save()


def decorate_consultation_link_field(state: dict, doctype: str, name: str | None = None) -> dict:
    fieldname = CONTEXT_FIELDS.get(doctype)
    if not fieldname:
        return state

    fields = state.get("fields") or []
    field = next((row for row in fields if row.get("fieldname") == fieldname), None)
    if not field:
        return state

    field["link_search_method"] = "vetedge.services.clinical_consultation_context.search_open_patient_consultations"
    field["link_search_context_field"] = "patient"
    field["description"] = _(
        "Optional. Shows only open consultations for the selected patient. Once linked, billed, or clinically progressed, this field becomes read-only."
    )

    if not name or not frappe.db.exists(doctype, name):
        return state

    doc = frappe.get_doc(doctype, name)
    can_write = bool(doc.docstatus == 0 and frappe.has_permission(doctype, "write", doc=doc))
    field["read_only"] = cint(not (can_write and can_assign_consultation_link(doc)))
    if field.get("value"):
        field["read_only"] = 1
    if can_write and not field.get("read_only"):
        state["can_save"] = True
    return state


def decorate_create_schema(state: dict, doctype: str) -> dict:
    fieldname = CREATE_CONTEXT_FIELDS.get(doctype)
    if not fieldname:
        return state
    field = next((row for row in state.get("fields") or [] if row.get("fieldname") == fieldname), None)
    if not field:
        return state
    field["link_search_method"] = "vetedge.services.clinical_consultation_context.search_open_patient_consultations"
    field["link_search_context_field"] = "patient"
    field["description"] = _("Optional. Shows only open consultations for the selected patient.")
    return state


@frappe.whitelist()
def get_clinical_record_create_schema(doctype: str) -> dict:
    require_internal_user()
    from vetedge.services.clinical_record_editor import get_clinical_record_create_schema as original

    return decorate_create_schema(original(doctype=doctype), doctype)


@frappe.whitelist()
def search_open_patient_consultations(
    patient: str,
    txt: str = "",
    page_length: int = 20,
) -> list[dict]:
    require_internal_user()
    patient = _clean(patient)
    if not patient or not frappe.db.exists("Veterinary Patient", patient):
        return []
    if not frappe.has_permission(CONSULTATION_DOCTYPE, "read"):
        return []

    page_length = min(max(cint(page_length) or 20, 1), PAGE_LENGTH_MAX)
    filters = {
        "patient": patient,
        "status": ["not in", sorted(CLOSED_CONSULTATION_STATUSES)],
    }
    txt = _clean(txt)
    or_filters = None
    if txt:
        pattern = f"%{txt}%"
        or_filters = [
            [CONSULTATION_DOCTYPE, "name", "like", pattern],
            [CONSULTATION_DOCTYPE, "consultation_title", "like", pattern],
            [CONSULTATION_DOCTYPE, "consulting_practitioner_name", "like", pattern],
        ]

    rows = frappe.get_list(
        CONSULTATION_DOCTYPE,
        filters=filters,
        or_filters=or_filters,
        fields=[
            "name",
            "consultation_title",
            "status",
            "consultation_datetime",
            "service_branch",
            "consulting_practitioner_name",
        ],
        order_by="consultation_datetime desc, modified desc",
        page_length=page_length,
    )
    return [
        {
            "value": row.name,
            "label": row.consultation_title or row.name,
            "description": " · ".join(
                filter(
                    None,
                    [
                        row.status,
                        str(row.consultation_datetime or ""),
                        row.service_branch,
                        row.consulting_practitioner_name,
                    ],
                )
            ),
        }
        for row in rows
    ]