from __future__ import annotations

from typing import Any

import frappe

from vetedge.services.portal_access import require_internal_user


LAB_HISTORY_STATUSES = {
    "Ordered",
    "Sample Collected",
    "Sent to Lab",
    "In Progress",
    "Result Pending",
    "Result Entered",
    "Awaiting Review",
    "Reviewed",
    "Completed",
}
VACCINATION_HISTORY_STATUSES = {"Administered"}


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
            row.get("consultation") or row.get("linked_consultation"),
            row.get("tests_summary") or row.get("vaccine"),
        )
        if key in seen:
            continue
        seen.add(key)
        result.append(row)
    return result


def filter_medical_history_rows(section: str, rows: list[dict]) -> list[dict]:
    section = str(section or "").strip().lower()
    if section == "labs":
        rows = [row for row in rows or [] if row.get("status") in LAB_HISTORY_STATUSES]
    elif section == "vaccinations":
        rows = [row for row in rows or [] if row.get("status") in VACCINATION_HISTORY_STATUSES]
    return _dedupe(rows)


def _filter_view(payload: dict) -> dict:
    result = dict(payload or {})
    result["labs"] = filter_medical_history_rows("labs", list(result.get("labs") or []))
    result["vaccinations"] = filter_medical_history_rows(
        "vaccinations", list(result.get("vaccinations") or [])
    )
    return result


@frappe.whitelist()
def get_patient_medical_history_view(
    patient: str,
    from_date: str | None = None,
    to_date: str | None = None,
    limit: int = 100,
) -> dict:
    require_internal_user()
    from vetedge.services.medical_history import get_patient_medical_history_view as original

    return _filter_view(
        original(patient=patient, from_date=from_date, to_date=to_date, limit=limit)
    )


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
    filtered = []
    for row in rows:
        if row.get("type") == "lab" and row.get("status") not in LAB_HISTORY_STATUSES:
            continue
        if row.get("type") == "vaccination" and row.get("status") not in VACCINATION_HISTORY_STATUSES:
            continue
        filtered.append(row)
    return _dedupe(filtered)[: int(limit or 50)]


@frappe.whitelist()
def get_patient_medical_history_section(
    patient: str,
    section: str,
    limit: int = 50,
    from_date: str | None = None,
    to_date: str | None = None,
) -> dict:
    require_internal_user()
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
