from __future__ import annotations

from typing import Any

import frappe
from frappe.utils import cint, cstr, get_datetime

from vetedge.services.permissions import can_access_medical_history
from vetedge.services.portal_access import require_internal_user


LAB_HISTORY_STATUSES = {"Completed"}
VACCINATION_HISTORY_STATUSES = {"Administered"}
HOSPITALISATION_DOCTYPE = "Veterinary Hospitalisation"
HOSPITALISATION_ACTIVITY_DOCTYPE = "Veterinary Hospitalisation Activity"
HOSPITALISATION_HISTORY_MAX_LIMIT = 100


def _dedupe(rows: list[dict]) -> list[dict]:
    seen: set[tuple[Any, ...]] = set()
    result: list[dict] = []
    for row in rows or []:
        name = row.get("name") or row.get("vaccination")
        key = (
            row.get("type"),
            name,
        ) if name else (
            row.get("type"),
            row.get("timestamp"),
            row.get("consultation") or row.get("linked_consultation") or row.get("hospitalisation"),
            row.get("tests_summary") or row.get("vaccine") or row.get("event_type"),
        )
        if key in seen:
            continue
        seen.add(key)
        result.append(row)
    return result


def _rows_already_have_workflow_truth(rows: list[dict]) -> bool:
    return bool(rows) and all(
        row.get("workflow_status") not in (None, "") and "docstatus" in row
        for row in rows
    )


def filter_medical_history_rows(section: str, rows: list[dict]) -> list[dict]:
    section = str(section or "").strip().lower()
    if section not in {"labs", "vaccinations"}:
        return _dedupe(rows)

    required_status = "Completed" if section == "labs" else "Administered"
    if _rows_already_have_workflow_truth(rows):
        return _dedupe(
            [row for row in rows if row.get("workflow_status") == required_status]
        )

    # The canonical clinical-history helper re-reads each source record's
    # workflow status and Frappe docstatus separately. Inclusion is based only
    # on workflow status; docstatus remains document-lifecycle metadata.
    from vetedge.services.medical_history_lazy import _apply_clinical_history_workflow_contract

    return _dedupe(_apply_clinical_history_workflow_contract(section, rows))


def _filter_view(payload: dict) -> dict:
    result = dict(payload or {})
    result["labs"] = filter_medical_history_rows("labs", list(result.get("labs") or []))
    result["vaccinations"] = filter_medical_history_rows(
        "vaccinations", list(result.get("vaccinations") or [])
    )
    return result


def _normalize_history_limit(limit: int | str | None) -> int:
    try:
        resolved = int(limit or 50)
    except (TypeError, ValueError):
        resolved = 50
    return min(max(resolved, 1), HOSPITALISATION_HISTORY_MAX_LIMIT)


def _history_bounds(from_date: str, to_date: str):
    return (
        get_datetime(f"{from_date} 00:00:00"),
        get_datetime(f"{to_date} 23:59:59"),
    )


def _timestamp_in_range(value, start, end) -> bool:
    if not value:
        return False
    try:
        resolved = get_datetime(value)
    except Exception:
        return False
    return start <= resolved <= end


def _activity_details(row) -> str:
    return cstr(row.get("clinical_notes") or "").strip()


def get_hospitalisation_history(
    patient: str,
    limit: int = 50,
    from_date: str | None = None,
    to_date: str | None = None,
) -> list[dict]:
    """Return permission-aware Hospitalisation events for the patient timeline.

    Hospitalisation remains the operational parent. Dedicated clinical events
    such as Vitals, Vaccination and Lab are also linked to their authoritative
    records, so Medical History can open either the episode or the source record
    without creating a second clinical truth.
    """
    require_internal_user()
    can_access_medical_history(getattr(frappe.session, "user", None), patient, raise_exception=True)
    if not frappe.has_permission(HOSPITALISATION_DOCTYPE, "read"):
        return []

    from vetedge.services.medical_history import normalize_date_range

    from_date, to_date = normalize_date_range(from_date, to_date)
    page_limit = _normalize_history_limit(limit)
    start, end = _history_bounds(from_date, to_date)

    parents = frappe.get_list(
        HOSPITALISATION_DOCTYPE,
        filters={"patient": patient},
        fields=[
            "name",
            "hospitalisation_title",
            "status",
            "admission_datetime",
            "discharge_datetime",
            "admission_reason",
            "discharge_summary",
            "condition_at_discharge",
            "service_branch",
            "care_level",
            "attending_veterinarian",
        ],
        order_by="admission_datetime desc, modified desc",
        page_length=page_limit,
    )
    if not parents:
        return []

    parent_names = [row.get("name") for row in parents if row.get("name")]
    activities = frappe.get_list(
        HOSPITALISATION_ACTIVITY_DOCTYPE,
        filters={"parent": ["in", parent_names]},
        fields=[
            "name",
            "parent",
            "idx",
            "activity_datetime",
            "activity_type",
            "performed_by",
            "clinical_notes",
            "item",
            "qty",
            "uom",
            "linked_doctype",
            "linked_document",
            "billing_status",
            "stock_status",
        ],
        parent_doctype=HOSPITALISATION_DOCTYPE,
        order_by="activity_datetime desc, idx desc",
        page_length=min(max(page_limit * 20, page_limit), 1000),
    )
    activities_by_parent: dict[str, list] = {}
    for row in activities:
        activities_by_parent.setdefault(cstr(row.get("parent")), []).append(row)

    result: list[dict] = []
    for parent in parents:
        hospitalisation = cstr(parent.get("name"))
        common = {
            "type": "hospitalisation",
            "hospitalisation": hospitalisation,
            "title": parent.get("hospitalisation_title") or hospitalisation,
            "service_branch": parent.get("service_branch"),
            "care_level": parent.get("care_level"),
            "practitioner": parent.get("attending_veterinarian"),
            "status": parent.get("status"),
        }

        if _timestamp_in_range(parent.get("admission_datetime"), start, end):
            result.append(
                {
                    **common,
                    "name": f"{hospitalisation}::admission",
                    "timestamp": parent.get("admission_datetime"),
                    "event_type": "Admission",
                    "activity_type": "Admission",
                    "details": parent.get("admission_reason") or "Patient admitted for Hospitalisation.",
                    "item": None,
                    "qty": None,
                    "uom": None,
                    "linked_doctype": HOSPITALISATION_DOCTYPE,
                    "linked_document": hospitalisation,
                }
            )

        for activity in activities_by_parent.get(hospitalisation, []):
            if not _timestamp_in_range(activity.get("activity_datetime"), start, end):
                continue
            activity_type = activity.get("activity_type") or "Hospitalisation Activity"
            result.append(
                {
                    **common,
                    "name": activity.get("name") or f"{hospitalisation}::activity::{activity.get('idx')}",
                    "timestamp": activity.get("activity_datetime"),
                    "event_type": activity_type,
                    "activity_type": activity_type,
                    "details": _activity_details(activity),
                    "performed_by": activity.get("performed_by"),
                    "item": activity.get("item"),
                    "qty": activity.get("qty"),
                    "uom": activity.get("uom"),
                    "billing_status": activity.get("billing_status"),
                    "stock_status": activity.get("stock_status"),
                    "linked_doctype": activity.get("linked_doctype"),
                    "linked_document": activity.get("linked_document"),
                }
            )

        if _timestamp_in_range(parent.get("discharge_datetime"), start, end):
            result.append(
                {
                    **common,
                    "name": f"{hospitalisation}::discharge",
                    "timestamp": parent.get("discharge_datetime"),
                    "event_type": "Discharge",
                    "activity_type": "Discharge",
                    "details": parent.get("discharge_summary") or parent.get("condition_at_discharge") or "Patient discharged.",
                    "item": None,
                    "qty": None,
                    "uom": None,
                    "linked_doctype": HOSPITALISATION_DOCTYPE,
                    "linked_document": hospitalisation,
                }
            )

    result.sort(key=lambda row: cstr(row.get("timestamp")), reverse=True)
    return _dedupe(result)[:page_limit]


@frappe.whitelist()
def get_patient_medical_history_view(
    patient: str,
    from_date: str | None = None,
    to_date: str | None = None,
    limit: int = 100,
) -> dict:
    require_internal_user()
    from vetedge.services.medical_history import get_patient_medical_history_view as original

    result = _filter_view(
        original(patient=patient, from_date=from_date, to_date=to_date, limit=limit)
    )
    result["hospitalisations"] = get_hospitalisation_history(
        patient=patient,
        limit=limit,
        from_date=result.get("from_date") or from_date,
        to_date=result.get("to_date") or to_date,
    )
    return result


@frappe.whitelist()
def get_patient_medical_history(
    patient: str,
    limit: int = 50,
    from_date: str | None = None,
    to_date: str | None = None,
) -> list[dict]:
    require_internal_user()
    from vetedge.services.medical_history import get_patient_medical_history as original

    rows = original(patient=patient, limit=limit, from_date=from_date, to_date=to_date)
    lab_rows = filter_medical_history_rows(
        "labs", [row for row in rows if row.get("type") == "lab"]
    )
    vaccination_rows = filter_medical_history_rows(
        "vaccinations", [row for row in rows if row.get("type") == "vaccination"]
    )
    lab_by_name = {row.get("name"): row for row in lab_rows if row.get("name")}
    vaccination_by_name = {
        row.get("name") or row.get("vaccination"): row
        for row in vaccination_rows
        if row.get("name") or row.get("vaccination")
    }

    filtered = []
    for row in rows:
        if row.get("type") == "lab":
            enriched = lab_by_name.get(row.get("name"))
            if enriched:
                filtered.append(enriched)
            continue
        if row.get("type") == "vaccination":
            enriched = vaccination_by_name.get(row.get("name") or row.get("vaccination"))
            if enriched:
                filtered.append(enriched)
            continue
        filtered.append(row)

    filtered.extend(
        get_hospitalisation_history(
            patient=patient,
            limit=limit,
            from_date=from_date,
            to_date=to_date,
        )
    )
    filtered = _dedupe(filtered)
    filtered.sort(key=lambda row: cstr(row.get("timestamp")), reverse=True)
    return filtered[: int(limit or 50)]


@frappe.whitelist()
def get_patient_medical_history_section(
    patient: str,
    section: str,
    limit: int = 50,
    from_date: str | None = None,
    to_date: str | None = None,
) -> dict:
    require_internal_user()
    section = cstr(section or "").strip().lower()
    if section == "hospitalisations":
        from vetedge.services.medical_history import normalize_date_range

        can_access_medical_history(getattr(frappe.session, "user", None), patient, raise_exception=True)
        from_date, to_date = normalize_date_range(from_date, to_date)
        page_limit = _normalize_history_limit(limit)
        return {
            "patient": patient,
            "section": section,
            "from_date": from_date,
            "to_date": to_date,
            "limit": page_limit,
            "rows": get_hospitalisation_history(
                patient=patient,
                limit=page_limit,
                from_date=from_date,
                to_date=to_date,
            ),
        }

    from vetedge.services.medical_history_lazy import get_patient_medical_history_section as original

    payload = dict(
        original(
            patient=patient,
            section=section,
            limit=limit,
            from_date=from_date,
            to_date=to_date,
        )
        or {}
    )
    payload["rows"] = filter_medical_history_rows(section, list(payload.get("rows") or []))
    return payload
