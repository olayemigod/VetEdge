from __future__ import annotations

from typing import Any

import frappe
from frappe import _
from frappe.utils import cint

from vetedge.services.permissions import can_access_branch_data
from vetedge.services.portal_access import require_internal_user


RECORD_CONFIG: dict[str, dict[str, Any]] = {
    "Veterinary Lab Order": {
        "branch_field": "service_branch",
        "billing": True,
        "fields": [
            ("patient", False),
            ("primary_owner", False),
            ("service_branch", True),
            ("consultation", False),
            ("status", False),
            ("requested_on", True),
            ("requested_by", False),
            ("sample_notes", True),
            ("doctor_reviewed_by", False),
            ("doctor_reviewed_on", False),
            ("linked_invoice", False),
        ],
    },
    "Veterinary Vaccination Record": {
        "branch_field": "service_branch",
        "billing": True,
        "fields": [
            ("patient", False),
            ("primary_owner", False),
            ("service_branch", True),
            ("company", False),
            ("vaccine", True),
            ("status", False),
            ("administered_by", True),
            ("administered_on", True),
            ("linked_consultation", False),
            ("dose", True),
            ("route", True),
            ("next_due_date", True),
            ("next_vaccination_appointment", False),
            ("batch_no", False),
            ("expiry_date", False),
            ("notes", True),
            ("billing_item", True),
            ("rate", True),
            ("amount", False),
            ("linked_invoice", False),
            ("stock_entry_reference", False),
        ],
    },
    "Veterinary Vital Signs": {
        "branch_field": "service_branch",
        "billing": False,
        "fields": [
            ("patient", False),
            ("consultation", False),
            ("service_branch", True),
            ("recorded_on", True),
            ("recorded_by", False),
            ("temperature", True),
            ("weight", True),
            ("heart_rate", True),
            ("respiratory_rate", True),
            ("body_condition_score", True),
            ("hydration_status", True),
            ("mucous_membrane", True),
            ("capillary_refill_time", True),
            ("pain_score", True),
            ("appetite_status", True),
            ("notes", True),
        ],
    },
}

SUPPORTED_FIELD_TYPES = {
    "Data",
    "Small Text",
    "Text",
    "Long Text",
    "Select",
    "Check",
    "Int",
    "Float",
    "Currency",
    "Percent",
    "Date",
    "Datetime",
    "Time",
    "Link",
    "Phone",
    "Email",
}


def _config(doctype: str) -> dict[str, Any]:
    config = RECORD_CONFIG.get(str(doctype or "").strip())
    if not config:
        frappe.throw(_("This clinical record is not available in the EdgeSuite editor."), frappe.PermissionError)
    return config


def _assert_access(doc, config: dict[str, Any], ptype: str = "read") -> None:
    if not frappe.has_permission(doc.doctype, ptype, doc=doc):
        frappe.throw(_("You do not have permission to {0} this record.").format(ptype), frappe.PermissionError)
    branch = doc.get(config.get("branch_field"))
    if branch:
        can_access_branch_data(frappe.session.user, branch, raise_exception=True)


def _serialize(value):
    if value is None:
        return None
    if isinstance(value, (str, int, float, bool)):
        return value
    return str(value)


def _field_schema(doc, fieldname: str, editable: bool, can_write: bool) -> dict[str, Any] | None:
    meta = frappe.get_meta(doc.doctype)
    field = meta.get_field(fieldname)
    if not field or field.fieldtype not in SUPPORTED_FIELD_TYPES:
        return None
    read_only = bool(field.read_only or not editable or not can_write)
    return {
        "fieldname": fieldname,
        "fieldtype": field.fieldtype,
        "label": field.label or fieldname.replace("_", " ").title(),
        "options": field.options or "",
        "description": field.description or "",
        "reqd": cint(field.reqd),
        "read_only": cint(read_only),
        "value": _serialize(doc.get(fieldname)),
    }


def _lab_tests_section(doc) -> dict[str, Any] | None:
    if doc.doctype != "Veterinary Lab Order":
        return None
    rows = []
    for row in doc.get("lab_tests") or []:
        rows.append(
            {
                "name": row.name,
                "lab_test": row.get("lab_test_name") or row.get("lab_test_template"),
                "sample_type": row.get("sample_type"),
                "status": row.get("status"),
                "result": row.get("result_summary") or row.get("result_value") or row.get("result_text"),
                "result_status": row.get("result_status"),
                "billing_status": row.get("billing_status"),
            }
        )
    return {
        "title": _("Laboratory Tests & Results"),
        "message": _("Test/result rows are shown in EdgeSuite for clinical context. Dedicated result-entry workflow rules remain authoritative."),
        "columns": [
            {"fieldname": "lab_test", "label": _("Lab Test")},
            {"fieldname": "sample_type", "label": _("Sample Type")},
            {"fieldname": "status", "label": _("Order Status"), "fieldtype": "Status"},
            {"fieldname": "result", "label": _("Result")},
            {"fieldname": "result_status", "label": _("Result Status"), "fieldtype": "Status"},
            {"fieldname": "billing_status", "label": _("Billing"), "fieldtype": "Status"},
        ],
        "rows": rows,
        "row_key": "name",
    }


@frappe.whitelist()
def get_clinical_record_editor(doctype: str, name: str) -> dict[str, Any]:
    require_internal_user()
    config = _config(doctype)
    if not name or not frappe.db.exists(doctype, name):
        frappe.throw(_("The selected clinical record could not be found."), frappe.DoesNotExistError)

    doc = frappe.get_doc(doctype, name)
    _assert_access(doc, config, "read")
    can_write = bool(doc.docstatus == 0 and frappe.has_permission(doctype, "write", doc=doc))

    fields = []
    for fieldname, editable in config["fields"]:
        schema = _field_schema(doc, fieldname, editable, can_write)
        if schema:
            fields.append(schema)

    sections = []
    lab_section = _lab_tests_section(doc)
    if lab_section:
        sections.append(lab_section)

    meta = frappe.get_meta(doctype)
    title_field = meta.get_title_field()
    return {
        "doctype": doctype,
        "name": doc.name,
        "title": doc.get(title_field) if title_field else doc.name,
        "status": doc.get("status") or ("Submitted" if doc.docstatus == 1 else "Draft"),
        "fields": fields,
        "sections": sections,
        "can_save": can_write,
        "can_bill": bool(config.get("billing")),
        "native_route": f"/desk/{frappe.scrub(doctype).replace('_', '-')}/{doc.name}",
    }


@frappe.whitelist()
def save_clinical_record_editor(doctype: str, name: str, values: str | dict | None = None) -> dict[str, Any]:
    require_internal_user()
    config = _config(doctype)
    if not name or not frappe.db.exists(doctype, name):
        frappe.throw(_("The selected clinical record could not be found."), frappe.DoesNotExistError)

    doc = frappe.get_doc(doctype, name)
    _assert_access(doc, config, "write")
    if doc.docstatus != 0:
        frappe.throw(_("Submitted or cancelled records are read-only in the EdgeSuite clinical editor."), frappe.ValidationError)

    payload = values if isinstance(values, dict) else frappe.parse_json(values or "{}")
    if not isinstance(payload, dict):
        frappe.throw(_("Expected a JSON object."), frappe.ValidationError)

    editable_fields = {fieldname for fieldname, editable in config["fields"] if editable}
    meta = frappe.get_meta(doctype)
    for fieldname, value in payload.items():
        if fieldname not in editable_fields:
            continue
        field = meta.get_field(fieldname)
        if not field or field.read_only or field.fieldtype not in SUPPORTED_FIELD_TYPES:
            continue
        doc.set(fieldname, value)

    doc.save()
    return get_clinical_record_editor(doctype, doc.name)
