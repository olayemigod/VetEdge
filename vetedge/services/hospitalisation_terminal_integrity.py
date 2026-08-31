from __future__ import annotations

import frappe
from frappe.utils import cint, now


HOSPITALISATION_DOCTYPE = "Veterinary Hospitalisation"
CARE_LOCATION_DOCTYPE = "Veterinary Care Location"
OCCUPANCY_LOG_DOCTYPE = "Veterinary Care Location Occupancy Log"
TERMINAL_STATUSES = {"Discharged", "Cancelled"}
BLOCKED_LOCATION_STATUSES = {"Inactive", "Maintenance", "Cleaning"}


def reconcile_terminal_hospitalisation_care_location(doc) -> None:
    """Release live occupancy after a Hospitalisation enters a terminal state.

    This is a system integrity action that runs only after the caller has already
    passed normal Hospitalisation save permissions and validation. Direct DB
    updates avoid requiring the clinical user to hold separate occupancy-log or
    Care Location maintenance permissions merely to complete discharge.
    """
    if not getattr(doc, "name", None):
        return
    if doc.get("status") not in TERMINAL_STATUSES:
        return

    care_location = doc.get("care_location")
    if not care_location:
        return

    released_on = now()
    log_status = "Cancelled" if doc.get("status") == "Cancelled" else "Released"

    from vetedge.services.hospitalisation import (
        get_active_care_location_log,
        get_active_care_location_occupancy_count,
    )

    log_name = get_active_care_location_log(doc.name, care_location)
    if log_name:
        existing_notes = frappe.db.get_value(OCCUPANCY_LOG_DOCTYPE, log_name, "notes") or ""
        terminal_note = f"Automatically {log_status.lower()} when Hospitalisation became {doc.get('status')}."
        notes = "\n".join(part for part in (existing_notes, terminal_note) if part)
        frappe.db.set_value(
            OCCUPANCY_LOG_DOCTYPE,
            log_name,
            {
                "status": log_status,
                "released_on": released_on,
                "released_by": frappe.session.user,
                "notes": notes,
            },
            update_modified=False,
        )

    frappe.db.set_value(
        HOSPITALISATION_DOCTYPE,
        doc.name,
        {
            "care_location": None,
            "care_location_status": "Released",
            "care_location_released_on": released_on,
        },
        update_modified=False,
    )

    location = frappe.db.get_value(
        CARE_LOCATION_DOCTYPE,
        care_location,
        ["enabled", "status", "capacity"],
        as_dict=True,
    ) or {}
    if not location or not cint(location.get("enabled")) or location.get("status") in BLOCKED_LOCATION_STATUSES:
        return

    capacity = max(cint(location.get("capacity")) or 1, 1)
    active_count = get_active_care_location_occupancy_count(care_location)
    target_status = "Occupied" if active_count >= capacity else "Available"
    if location.get("status") != target_status:
        frappe.db.set_value(
            CARE_LOCATION_DOCTYPE,
            care_location,
            "status",
            target_status,
            update_modified=False,
        )
