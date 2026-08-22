from __future__ import annotations

from typing import Any

import frappe
from frappe import _
from frappe.utils import cint, flt, now_datetime

from vetedge.services.permissions import can_access_branch_data
from vetedge.services.portal_access import require_internal_user


RECORD_CONFIG: dict[str, dict[str, Any]] = {
    "Veterinary Lab Order": {
        "branch_field": "service_branch",
        "billing": True,
        "safe_after_invoice": {"sample_notes"},
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
        "create_fields": ["patient", "service_branch", "sample_notes"],
    },
    "Veterinary Vaccination Record": {
        "branch_field": "service_branch",
        "billing": True,
        "safe_after_invoice": {"notes", "next_due_date"},
        "price_fields": {"rate", "billing_item", "vaccine"},
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
        "create_fields": [
            "patient",
            "service_branch",
            "vaccine",
            "linked_consultation",
            "dose",
            "route",
            "next_due_date",
            "notes",
            "rate",
        ],
    },
    "Veterinary Vital Signs": {
        "branch_field": "service_branch",
        "billing": False,
        "safe_after_invoice": set(),
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
        "create_fields": [
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

LAB_RESULT_FORMATS = {"Value Driven", "Text / Narrative", "Document Upload", "Mixed"}
LAB_FINAL_STATUSES = {"Reviewed", "Completed", "Cancelled"}


def _config(doctype: str) -> dict[str, Any]:
    config = RECORD_CONFIG.get(str(doctype or "").strip())
    if not config:
        frappe.throw(_("This clinical record is not available in the EdgeSuite editor."), frappe.PermissionError)
    return config


def _parse_values(values: str | dict | None) -> dict[str, Any]:
    if not values:
        return {}
    parsed = values if isinstance(values, dict) else frappe.parse_json(values)
    if not isinstance(parsed, dict):
        frappe.throw(_("Expected a JSON object."), frappe.ValidationError)
    return parsed


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


def _link_display_value(doctype: str | None, name: str | None) -> str:
    if not doctype or not name:
        return str(name or "")
    if doctype == "Veterinary Patient":
        return frappe.db.get_value(doctype, name, "patient_name") or name
    meta = frappe.get_meta(doctype)
    title_field = meta.get_title_field()
    if title_field and title_field != "name":
        return frappe.db.get_value(doctype, name, title_field) or name
    return name


def _billing_edit_state(doc, config: dict[str, Any]) -> dict[str, Any]:
    state = {
        "has_invoice": False,
        "has_draft_invoice": False,
        "has_submitted_invoice": False,
        "is_paid": False,
        "locked": False,
        "message": "",
    }
    if not config.get("billing") or not doc.get("name"):
        return state

    try:
        from vetedge.services.billing_modal import get_billing_modal_state

        billing = get_billing_modal_state(doc.doctype, doc.name)
        history = billing.get("invoice_history") or []
        invoice = billing.get("invoice") or {}
        if not history and invoice.get("name"):
            history = [invoice]
        active = [row for row in history if cint(row.get("docstatus")) != 2]
        state["has_invoice"] = bool(active)
        state["has_draft_invoice"] = any(cint(row.get("docstatus")) == 0 for row in active)
        state["has_submitted_invoice"] = any(cint(row.get("docstatus")) == 1 for row in active)
        state["is_paid"] = bool(
            active
            and all(
                cint(row.get("docstatus")) == 1 and flt(row.get("outstanding_amount")) <= 0
                for row in active
            )
        )
    except Exception:
        invoice_name = doc.get("linked_invoice")
        if invoice_name and frappe.db.exists("Sales Invoice", invoice_name):
            invoice = frappe.db.get_value(
                "Sales Invoice", invoice_name, ["docstatus", "outstanding_amount"], as_dict=True
            )
            if invoice:
                state["has_invoice"] = cint(invoice.docstatus) != 2
                state["has_draft_invoice"] = cint(invoice.docstatus) == 0
                state["has_submitted_invoice"] = cint(invoice.docstatus) == 1
                state["is_paid"] = cint(invoice.docstatus) == 1 and flt(invoice.outstanding_amount) <= 0

    state["locked"] = state["has_submitted_invoice"]
    if state["is_paid"]:
        state["message"] = _(
            "This clinical service is paid. Service identity, pricing and billing fields are locked; only safe follow-up fields remain editable."
        )
    elif state["has_submitted_invoice"]:
        state["message"] = _(
            "A submitted invoice exists. Service identity, pricing and billing fields are locked; only safe clinical fields remain editable."
        )
    elif state["has_draft_invoice"]:
        state["message"] = _(
            "A draft invoice exists. Permitted price changes will be synchronized to the draft invoice when this record is saved."
        )
    return state


def _field_schema(
    doc,
    fieldname: str,
    editable: bool,
    can_write: bool,
    billing_state: dict[str, Any] | None = None,
    config: dict[str, Any] | None = None,
) -> dict[str, Any] | None:
    meta = frappe.get_meta(doc.doctype)
    field = meta.get_field(fieldname)
    if not field or field.fieldtype not in SUPPORTED_FIELD_TYPES:
        return None

    billing_state = billing_state or {}
    config = config or {}
    if billing_state.get("locked") and editable and fieldname not in config.get("safe_after_invoice", set()):
        editable = False
    read_only = bool(field.read_only or not editable or not can_write)
    value = _serialize(doc.get(fieldname))
    schema = {
        "fieldname": fieldname,
        "fieldtype": field.fieldtype,
        "label": field.label or fieldname.replace("_", " ").title(),
        "options": field.options or "",
        "description": field.description or "",
        "reqd": cint(field.reqd),
        "read_only": cint(read_only),
        "value": value,
    }
    if field.fieldtype == "Link" and value:
        schema["selected_label"] = _link_display_value(field.options, str(value))
    return schema


def _lab_tests_section(doc, billing_state: dict[str, Any], can_write: bool) -> dict[str, Any] | None:
    if doc.doctype != "Veterinary Lab Order":
        return None
    rows = []
    can_edit_rate = bool(can_write and not billing_state.get("has_submitted_invoice"))
    for row in doc.get("lab_tests") or []:
        result_summary = (
            row.get("result_summary")
            or row.get("result_value")
            or row.get("result_text")
            or (_("Document uploaded") if row.get("result_attachment") else "")
        )
        rows.append(
            {
                "name": row.name,
                "lab_test": row.get("lab_test_name") or row.get("lab_test_template"),
                "sample_type": row.get("sample_type"),
                "status": row.get("status"),
                "result_format": row.get("result_format") or "Value Driven",
                "result": result_summary,
                "result_status": row.get("result_status"),
                "result_attachment": row.get("result_attachment"),
                "rate": flt(row.get("rate")),
                "billing_status": row.get("billing_status"),
                "can_edit_result": bool(can_write and row.get("status") not in LAB_FINAL_STATUSES),
                "can_edit_rate": can_edit_rate,
            }
        )
    return {
        "kind": "lab_results",
        "title": _("Laboratory Tests, Results & Pricing"),
        "message": _(
            "Result entry follows each Lab Test's configured result type. Uploaded reports and entered results remain viewable here. Prices can change only while billing is unsubmitted."
        ),
        "columns": [
            {"fieldname": "lab_test", "label": _("Lab Test")},
            {"fieldname": "result_format", "label": _("Report Type")},
            {"fieldname": "status", "label": _("Order Status"), "fieldtype": "Status"},
            {"fieldname": "result", "label": _("Result")},
            {"fieldname": "rate", "label": _("Rate"), "fieldtype": "Currency"},
            {"fieldname": "billing_status", "label": _("Billing"), "fieldtype": "Status"},
        ],
        "rows": rows,
        "row_key": "name",
    }


def _can_delete_record(doc, config: dict[str, Any], billing_state: dict[str, Any]) -> tuple[bool, str]:
    if not frappe.has_permission(doc.doctype, "delete", doc=doc):
        return False, _("You do not have delete permission for this record.")
    if doc.docstatus != 0:
        return False, _("Submitted or cancelled documents cannot be deleted here.")

    if doc.doctype == "Veterinary Lab Order":
        if doc.get("status") not in {"Draft", "Ordered"}:
            return False, _("Lab orders with active/result workflow history cannot be deleted.")
        if any(
            row.get("result_summary")
            or row.get("result_value")
            or row.get("result_text")
            or row.get("result_attachment")
            for row in doc.get("lab_tests") or []
        ):
            return False, _("Lab orders with entered or uploaded results cannot be deleted.")

        from vetedge.services.lab_cancellation import build_lab_order_cancellation_preflight

        preflight = build_lab_order_cancellation_preflight(doc)
        if not preflight.get("can_cancel"):
            return False, preflight.get("message") or _("This Lab Order cannot be deleted safely.")
        return True, ""

    if billing_state.get("has_invoice"):
        return False, _("Delete is blocked because billing already exists for this clinical service.")
    if doc.doctype == "Veterinary Vaccination Record":
        if doc.get("status") == "Administered" or doc.get("stock_entry_reference"):
            return False, _("Administered or stock-posted vaccination records cannot be deleted.")
    return True, ""


def _create_field_schema(doctype: str, fieldname: str) -> dict[str, Any] | None:
    meta = frappe.get_meta(doctype)
    field = meta.get_field(fieldname)
    if not field or field.fieldtype not in SUPPORTED_FIELD_TYPES:
        return None
    schema = {
        "fieldname": fieldname,
        "fieldtype": field.fieldtype,
        "label": field.label or fieldname.replace("_", " ").title(),
        "options": field.options or "",
        "description": field.description or "",
        "reqd": cint(field.reqd),
        "read_only": 0,
        "value": "",
    }
    if field.fieldtype == "Datetime" and field.default == "Now":
        schema["value"] = str(now_datetime())
    return schema


@frappe.whitelist()
def get_clinical_record_editor(doctype: str, name: str) -> dict[str, Any]:
    require_internal_user()
    config = _config(doctype)
    if not name or not frappe.db.exists(doctype, name):
        frappe.throw(_("The selected clinical record could not be found."), frappe.DoesNotExistError)

    doc = frappe.get_doc(doctype, name)
    _assert_access(doc, config, "read")
    can_write = bool(doc.docstatus == 0 and frappe.has_permission(doctype, "write", doc=doc))
    billing_state = _billing_edit_state(doc, config)

    fields = []
    for fieldname, editable in config["fields"]:
        schema = _field_schema(doc, fieldname, editable, can_write, billing_state, config)
        if schema:
            fields.append(schema)

    sections = []
    lab_section = _lab_tests_section(doc, billing_state, can_write)
    if lab_section:
        sections.append(lab_section)

    can_delete, delete_reason = _can_delete_record(doc, config, billing_state)
    meta = frappe.get_meta(doctype)
    title_field = meta.get_title_field()
    title = doc.get(title_field) if title_field else doc.name
    if doctype == "Veterinary Vital Signs":
        title = _("Vitals for {0}").format(_link_display_value("Veterinary Patient", doc.get("patient")))
    return {
        "doctype": doctype,
        "name": doc.name,
        "title": title or doc.name,
        "status": doc.get("status") or ("Submitted" if doc.docstatus == 1 else "Draft"),
        "patient_name": _link_display_value("Veterinary Patient", doc.get("patient")),
        "fields": fields,
        "sections": sections,
        "can_save": can_write and any(not field.get("read_only") for field in fields),
        "can_delete": can_delete,
        "delete_reason": delete_reason,
        "can_bill": bool(config.get("billing")),
        "billing_state": billing_state,
        "native_route": f"/desk/{frappe.scrub(doctype).replace('_', '-')}/{doc.name}",
    }


@frappe.whitelist()
def get_clinical_record_create_schema(doctype: str) -> dict[str, Any]:
    require_internal_user()
    config = _config(doctype)
    if not frappe.has_permission(doctype, "create"):
        frappe.throw(_("You are not permitted to create this clinical record."), frappe.PermissionError)

    fields = [schema for fieldname in config.get("create_fields", []) if (schema := _create_field_schema(doctype, fieldname))]
    if doctype == "Veterinary Lab Order":
        from vetedge.services.lab import get_active_lab_tests_for_picker

        lab_tests = get_active_lab_tests_for_picker()
        fields.append(
            {
                "fieldname": "lab_tests",
                "fieldtype": "MultiSelect",
                "label": _("Lab Tests"),
                "reqd": 1,
                "read_only": 0,
                "value": [],
                "options": [
                    {
                        "value": row.get("name"),
                        "label": row.get("test_name") or row.get("name"),
                        "description": _("{0} · {1}").format(
                            row.get("result_format") or "Value Driven",
                            frappe.format_value(row.get("default_rate") or 0, {"fieldtype": "Currency"}),
                        ),
                    }
                    for row in lab_tests
                ],
                "description": _("Each selected test keeps its configured result format, upload rules and default price."),
            }
        )
    return {
        "doctype": doctype,
        "title": _("Create {0}").format(doctype.replace("Veterinary ", "")),
        "fields": fields,
        "can_create": True,
    }


@frappe.whitelist()
def create_clinical_record(doctype: str, values: str | dict | None = None) -> dict[str, Any]:
    require_internal_user()
    config = _config(doctype)
    if not frappe.has_permission(doctype, "create"):
        frappe.throw(_("You are not permitted to create this clinical record."), frappe.PermissionError)
    payload = _parse_values(values)

    if doctype == "Veterinary Lab Order":
        from vetedge.services.lab import create_standalone_lab_order

        result = create_standalone_lab_order(
            patient=payload.get("patient"),
            lab_tests=payload.get("lab_tests"),
            service_branch=payload.get("service_branch"),
            sample_notes=payload.get("sample_notes"),
        )
        return get_clinical_record_editor(doctype, result["name"])

    allowed = set(config.get("create_fields") or [])
    document = {"doctype": doctype}
    for fieldname in allowed:
        if fieldname in payload:
            document[fieldname] = payload[fieldname]
    if doctype == "Veterinary Vital Signs" and not document.get("recorded_on"):
        document["recorded_on"] = now_datetime()
    if doctype == "Veterinary Vaccination Record":
        document.setdefault("status", "Draft")

    doc = frappe.get_doc(document)
    doc.insert()
    return get_clinical_record_editor(doctype, doc.name)


def _sync_draft_billing_after_price_change(doc, config: dict[str, Any], previous_values: dict[str, Any]) -> None:
    if not config.get("billing") or not config.get("price_fields"):
        return
    changed = any(str(doc.get(fieldname) or "") != str(previous_values.get(fieldname) or "") for fieldname in config["price_fields"])
    if not changed:
        return
    billing_state = _billing_edit_state(doc, config)
    if not billing_state.get("has_draft_invoice"):
        return
    from vetedge.services.billing_modal import create_or_update_modal_invoice

    create_or_update_modal_invoice(doc.doctype, doc.name)


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

    payload = _parse_values(values)
    billing_state = _billing_edit_state(doc, config)
    editable_fields = {fieldname for fieldname, editable in config["fields"] if editable}
    if billing_state.get("locked"):
        editable_fields &= set(config.get("safe_after_invoice") or set())
    meta = frappe.get_meta(doctype)
    previous_values = {fieldname: doc.get(fieldname) for fieldname in config.get("price_fields", set())}
    for fieldname, value in payload.items():
        if fieldname not in editable_fields:
            continue
        field = meta.get_field(fieldname)
        if not field or field.read_only or field.fieldtype not in SUPPORTED_FIELD_TYPES:
            continue
        doc.set(fieldname, value)

    doc.save()
    _sync_draft_billing_after_price_change(doc, config, previous_values)
    return get_clinical_record_editor(doctype, doc.name)


@frappe.whitelist()
def delete_clinical_record(doctype: str, name: str) -> dict[str, Any]:
    require_internal_user()
    config = _config(doctype)
    if not name or not frappe.db.exists(doctype, name):
        frappe.throw(_("The selected clinical record could not be found."), frappe.DoesNotExistError)
    doc = frappe.get_doc(doctype, name)
    _assert_access(doc, config, "read")
    billing_state = _billing_edit_state(doc, config)
    can_delete, reason = _can_delete_record(doc, config, billing_state)
    if not can_delete:
        frappe.throw(reason or _("This record cannot be deleted."), frappe.PermissionError)
    frappe.delete_doc(doctype, name)
    return {"deleted": True, "doctype": doctype, "name": name}


def _find_lab_row(doc, row_name: str):
    for row in doc.get("lab_tests") or []:
        if row.name == row_name:
            return row
    frappe.throw(_("The selected laboratory result row could not be found."), frappe.DoesNotExistError)


@frappe.whitelist()
def get_lab_result_editor(lab_order: str, row_name: str) -> dict[str, Any]:
    require_internal_user()
    from vetedge.services.permissions import can_access_lab_order, can_enter_lab_results, can_upload_lab_results

    can_access_lab_order(frappe.session.user, lab_order, raise_exception=True)
    doc = frappe.get_doc("Veterinary Lab Order", lab_order)
    row = _find_lab_row(doc, row_name)
    result_format = row.get("result_format") or "Value Driven"
    if result_format not in LAB_RESULT_FORMATS:
        result_format = "Value Driven"
    can_enter = bool(row.get("status") not in LAB_FINAL_STATUSES and can_enter_lab_results(frappe.session.user, doc, raise_exception=False))
    can_upload = bool(can_enter and can_upload_lab_results(frappe.session.user, doc, raise_exception=False))

    fields: list[dict[str, Any]] = []
    if result_format in {"Value Driven", "Mixed"}:
        fields.extend(
            [
                {"fieldname": "result_value", "fieldtype": "Data", "label": _("Result Value"), "value": row.get("result_value") or "", "read_only": cint(not can_enter)},
                {"fieldname": "result_unit", "fieldtype": "Data", "label": _("Result Unit"), "value": row.get("result_unit") or "", "read_only": 1},
                {"fieldname": "reference_range", "fieldtype": "Small Text", "label": _("Reference Range"), "value": row.get("reference_range") or "", "read_only": 1},
                {"fieldname": "abnormal_flag", "fieldtype": "Check", "label": _("Abnormal"), "value": cint(row.get("abnormal_flag")), "read_only": cint(not can_enter)},
            ]
        )
    if result_format in {"Text / Narrative", "Mixed"}:
        fields.append({"fieldname": "result_text", "fieldtype": "Text", "label": _("Narrative Result"), "value": row.get("result_text") or "", "read_only": cint(not can_enter)})
    if result_format in {"Document Upload", "Mixed"}:
        fields.append(
            {
                "fieldname": "result_attachment",
                "fieldtype": "Attach",
                "label": _("Uploaded Result"),
                "value": row.get("result_attachment") or "",
                "read_only": cint(not can_upload),
                "description": _("Upload the laboratory report. Existing uploads can be opened directly from this modal."),
            }
        )
    fields.append({"fieldname": "remarks", "fieldtype": "Small Text", "label": _("Remarks"), "value": row.get("remarks") or "", "read_only": cint(not can_enter)})
    return {
        "lab_order": lab_order,
        "row_name": row.name,
        "title": row.get("lab_test_name") or row.get("lab_test_template"),
        "result_format": result_format,
        "status": row.get("status"),
        "result_status": row.get("result_status"),
        "result_attachment": row.get("result_attachment"),
        "fields": fields,
        "can_save": can_enter,
        "can_upload": can_upload,
    }


@frappe.whitelist()
def save_lab_result_editor(lab_order: str, row_name: str, values: str | dict | None = None) -> dict[str, Any]:
    require_internal_user()
    from vetedge.services.permissions import can_access_lab_order, can_enter_lab_results

    can_access_lab_order(frappe.session.user, lab_order, raise_exception=True)
    doc = frappe.get_doc("Veterinary Lab Order", lab_order)
    can_enter_lab_results(frappe.session.user, doc, raise_exception=True)
    row = _find_lab_row(doc, row_name)
    if row.get("status") in LAB_FINAL_STATUSES:
        frappe.throw(_("Reviewed, completed or cancelled laboratory results are read-only."), frappe.ValidationError)
    payload = _parse_values(values)
    allowed = {"result_value", "abnormal_flag", "result_text", "result_attachment", "remarks"}
    for fieldname in allowed:
        if fieldname in payload:
            row.set(fieldname, payload[fieldname])
    doc.save()
    return get_lab_result_editor(lab_order, row_name)


@frappe.whitelist()
def save_lab_test_rate(lab_order: str, row_name: str, rate: float | str) -> dict[str, Any]:
    require_internal_user()
    from vetedge.services.permissions import can_access_lab_order

    can_access_lab_order(frappe.session.user, lab_order, raise_exception=True)
    doc = frappe.get_doc("Veterinary Lab Order", lab_order)
    config = _config(doc.doctype)
    _assert_access(doc, config, "write")
    billing_state = _billing_edit_state(doc, config)
    if billing_state.get("has_submitted_invoice"):
        frappe.throw(_("Lab prices cannot change after an invoice is submitted."), frappe.ValidationError)
    row = _find_lab_row(doc, row_name)
    row.rate = flt(rate)
    doc.save()
    if billing_state.get("has_draft_invoice"):
        from vetedge.services.billing_modal import create_or_update_modal_invoice

        create_or_update_modal_invoice(doc.doctype, doc.name)
    return get_clinical_record_editor(doc.doctype, doc.name)
