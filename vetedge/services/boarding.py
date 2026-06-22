from __future__ import annotations

import frappe
from frappe.utils import date_diff, flt, get_datetime, getdate, now_datetime, nowdate

from vetedge.services.billing import PAID_STATUS, build_invoice_item, get_invoice_payment_status, is_active_sales_invoice, validate_sales_item
from vetedge.services.feature_flags import is_enabled
from vetedge.services.notifications import emit_notification_event
from vetedge.services.portal_access import require_internal_user
from vetedge.services.registration_billing import get_billing_cost_center, get_default_company

PET_BOARDING_BOOKING_DOCTYPE = "Pet Boarding Booking"
PET_BOARDING_STAY_DOCTYPE = "Pet Boarding Stay"
PET_BOARDING_CARE_RECORD_DOCTYPE = "Pet Boarding Care Record"
KENNEL_DOCTYPE = "Kennel"
BOARDING_INVOICE_REMARK_PREFIX = "Boarding billing for "

BOOKING_STATUSES = {"Draft", "Reserved", "Checked In", "Checked Out", "Cancelled"}
STAY_STATUSES = {"Active", "Completed"}
CARE_RECORD_STATUSES = {"Completed", "Skipped", "Needs Attention"}
CARE_TYPES = {"Routine Check", "Feeding", "Hydration", "Walk / Exercise", "Elimination", "Grooming Check", "Comfort / Behavior", "Check Out Prep"}
VALID_BOOKING_STATUS_TRANSITIONS = {
    "Draft": {"Reserved", "Cancelled"},
    "Reserved": {"Checked In", "Cancelled"},
    "Checked In": {"Checked Out"},
    "Checked Out": set(),
    "Cancelled": set(),
}


def ensure_boarding_enabled() -> None:
    if not frappe.db.exists("DocType", "Veterinary Settings"):
        return
    if not is_enabled("boarding"):
        frappe.throw("Boarding is not enabled in Veterinary Settings.", frappe.ValidationError)



def get_patient_owner(patient: str) -> str | None:
    if not patient:
        return None
    return frappe.db.get_value("Veterinary Patient", patient, "primary_owner")



def get_patient_display_name(patient: str | None) -> str | None:
    if not patient:
        return None
    return frappe.db.get_value("Veterinary Patient", patient, "patient_name") or patient


def get_default_boarding_billing_item() -> str | None:
    if not frappe.db.exists("DocType", "Veterinary Settings"):
        return None
    get_single_value = getattr(frappe.db, "get_single_value", None)
    if not get_single_value:
        return None
    return get_single_value("Veterinary Settings", "default_boarding_billing_item")


def get_default_boarding_daily_rate() -> float | None:
    if not frappe.db.exists("DocType", "Veterinary Settings"):
        return None
    get_single_value = getattr(frappe.db, "get_single_value", None)
    if not get_single_value:
        return None
    value = get_single_value("Veterinary Settings", "default_boarding_daily_rate")
    if value in (None, ""):
        return None
    return flt(value)


def boarding_requires_payment_before_check_in() -> bool:
    if not frappe.db.exists("DocType", "Veterinary Settings"):
        return False
    get_single_value = getattr(frappe.db, "get_single_value", None)
    if not get_single_value:
        return False
    return bool(int(get_single_value("Veterinary Settings", "boarding_requires_payment_before_check_in") or 0))



def set_pet_boarding_stay_title(doc) -> None:
    parts = []
    patient_title = get_patient_display_name(doc.patient)
    if patient_title:
        parts.append(str(patient_title))
    if doc.kennel:
        parts.append(str(doc.kennel))
    if doc.check_in_datetime:
        parts.append(str(getdate(doc.check_in_datetime)))
    doc.boarding_stay_title = " - ".join(part for part in parts if part)



def resolve_boarding_owner(doc, booking_mode: bool = False, stay_mode: bool = False) -> None:
    if stay_mode and doc.booking:
        booking = frappe.db.get_value(
            PET_BOARDING_BOOKING_DOCTYPE,
            doc.booking,
            ["patient", "primary_owner", "service_branch", "kennel", "feeding_instructions", "special_notes"],
            as_dict=True,
        )
        if not booking:
            frappe.throw("Pet Boarding Stay must reference a valid Pet Boarding Booking.", frappe.ValidationError)
        if not doc.patient:
            doc.patient = booking.patient
        if not doc.primary_owner:
            doc.primary_owner = booking.primary_owner
        if not doc.service_branch:
            doc.service_branch = booking.service_branch
        if not doc.kennel:
            doc.kennel = booking.kennel
        if not doc.feeding_instructions:
            doc.feeding_instructions = booking.feeding_instructions
        if not doc.special_notes:
            doc.special_notes = booking.special_notes

    if not doc.patient:
        frappe.throw("Patient is required.", frappe.ValidationError)

    if not doc.primary_owner:
        doc.primary_owner = get_patient_owner(doc.patient)
    if not doc.primary_owner:
        frappe.throw("Patient must have a Primary Owner before boarding can be saved.", frappe.ValidationError)
    if not doc.service_branch:
        frappe.throw("Service Branch is required.", frappe.ValidationError)
    if booking_mode and not doc.created_by:
        doc.created_by = frappe.session.user



def validate_kennel(doc) -> None:
    ensure_boarding_enabled()
    if not doc.kennel_name:
        frappe.throw("Kennel Name is required.", frappe.ValidationError)
    doc.kennel_name = str(doc.kennel_name).strip()
    if not doc.branch:
        frappe.throw("Branch is required for Kennel.", frappe.ValidationError)
    capacity = int(doc.capacity or 1)
    if capacity < 1:
        frappe.throw("Kennel capacity must be at least 1.", frappe.ValidationError)
    doc.capacity = capacity



def get_booking_date_range(doc) -> tuple:
    if not doc.check_in_date:
        frappe.throw("Check In Date is required.", frappe.ValidationError)
    if not doc.expected_check_out_date:
        frappe.throw("Expected Check Out Date is required.", frappe.ValidationError)
    check_in_date = getdate(doc.check_in_date)
    expected_check_out_date = getdate(doc.expected_check_out_date)
    if expected_check_out_date < check_in_date:
        frappe.throw("Expected Check Out Date must be the same day or later than Check In Date.", frappe.ValidationError)
    if doc.actual_check_out_date and getdate(doc.actual_check_out_date) < check_in_date:
        frappe.throw("Actual Check Out Date must be the same day or later than Check In Date.", frappe.ValidationError)
    end_date = getdate(doc.actual_check_out_date or expected_check_out_date)
    return check_in_date, end_date



def calculate_boarding_billable_days(check_in_date, end_date) -> int:
    return max(1, int(date_diff(end_date, check_in_date)) + 1)



def get_boarding_daily_rate(doc) -> float:
    if doc.daily_rate not in (None, ""):
        rate = flt(doc.daily_rate)
        if rate < 0:
            frappe.throw("Daily Rate cannot be negative.", frappe.ValidationError)
        return rate
    settings_rate = get_default_boarding_daily_rate()
    if settings_rate not in (None, ""):
        settings_rate = flt(settings_rate)
        if settings_rate < 0:
            frappe.throw("Default Boarding Daily Rate cannot be negative.", frappe.ValidationError)
        doc.daily_rate = settings_rate
        return settings_rate
    if doc.billing_item:
        standard_rate = flt(frappe.db.get_value("Item", doc.billing_item, "standard_rate") or 0)
        doc.daily_rate = standard_rate
        return standard_rate
    return 0.0



def sync_boarding_charge_fields(doc) -> None:
    check_in_date, end_date = get_booking_date_range(doc)
    if not doc.billing_item:
        doc.billing_item = get_default_boarding_billing_item()
    if doc.billing_item:
        validate_sales_item(doc.billing_item, "Boarding Billing Item", allow_stock=False)
    doc.billable_days = calculate_boarding_billable_days(check_in_date, end_date)
    rate = get_boarding_daily_rate(doc)
    doc.total_boarding_charge = flt(doc.billable_days) * flt(rate)



def get_kennel_context(kennel: str | None) -> frappe._dict:
    if not kennel:
        frappe.throw("Kennel is required.", frappe.ValidationError)
    kennel_doc = frappe.db.get_value(KENNEL_DOCTYPE, kennel, ["branch", "capacity", "is_active"], as_dict=True)
    if not kennel_doc:
        frappe.throw("A valid Kennel is required.", frappe.ValidationError)
    return kennel_doc



def validate_kennel_assignment(kennel: str | None, service_branch: str | None) -> frappe._dict:
    kennel_doc = get_kennel_context(kennel)
    if not int(kennel_doc.is_active or 0):
        frappe.throw(f"Kennel {kennel} is inactive.", frappe.ValidationError)
    if service_branch and kennel_doc.branch and kennel_doc.branch != service_branch:
        frappe.throw(f"Kennel {kennel} belongs to branch {kennel_doc.branch}, not {service_branch}.", frappe.ValidationError)
    return kennel_doc



def date_ranges_overlap(start_a, end_a, start_b, end_b) -> bool:
    return start_a <= end_b and start_b <= end_a



def normalize_availability_range(from_date=None, to_date=None):
    start_date = getdate(from_date or nowdate())
    end_date = getdate(to_date or start_date)
    if end_date < start_date:
        frappe.throw("To Date must be the same day or later than From Date.", frappe.ValidationError)
    return start_date, end_date



def get_overlapping_reserved_bookings(kennel: str, from_date, to_date, branch: str | None = None, exclude_booking: str | None = None) -> list[frappe._dict]:
    filters = {"kennel": kennel, "status": "Reserved"}
    if branch:
        filters["service_branch"] = branch
    rows = []
    for row in frappe.get_all(
        PET_BOARDING_BOOKING_DOCTYPE,
        filters=filters,
        fields=["name", "patient", "primary_owner", "service_branch", "check_in_date", "expected_check_out_date", "actual_check_out_date"],
    ):
        if exclude_booking and row.name == exclude_booking:
            continue
        row_start = getdate(row.check_in_date)
        row_end = getdate(row.actual_check_out_date or row.expected_check_out_date or row.check_in_date)
        if date_ranges_overlap(from_date, to_date, row_start, row_end):
            rows.append(frappe._dict({**row, "occupancy_end_date": row_end, "occupancy_type": "Reserved Booking"}))
    return rows



def get_overlapping_active_stays(kennel: str, from_date, to_date, branch: str | None = None, exclude_stay: str | None = None) -> list[frappe._dict]:
    filters = {"kennel": kennel, "status": "Active"}
    if branch:
        filters["service_branch"] = branch
    rows = []
    for row in frappe.get_all(
        PET_BOARDING_STAY_DOCTYPE,
        filters=filters,
        fields=["name", "booking", "patient", "primary_owner", "service_branch", "check_in_datetime", "check_out_datetime"],
    ):
        if exclude_stay and row.name == exclude_stay:
            continue
        row_start = getdate(row.check_in_datetime)
        row_end = getdate(row.check_out_datetime) if row.check_out_datetime else to_date
        if date_ranges_overlap(from_date, to_date, row_start, row_end):
            rows.append(frappe._dict({**row, "occupancy_end_date": row_end, "occupancy_type": "Active Stay"}))
    return rows



def build_kennel_availability_row(kennel_doc, branch: str, from_date, to_date, reserved_bookings: list[frappe._dict], active_stays: list[frappe._dict]) -> frappe._dict:
    capacity = max(1, int(kennel_doc.capacity or 1))
    current_occupancy = len(reserved_bookings) + len(active_stays)
    available_slots = max(0, capacity - current_occupancy)
    next_release_candidates = [row.occupancy_end_date for row in [*reserved_bookings, *active_stays] if row.occupancy_end_date]
    expected_check_out_date = min(next_release_candidates) if next_release_candidates else None
    active_refs = [f"Stay: {row.name}" for row in active_stays] + [f"Booking: {row.name}" for row in reserved_bookings]
    if not int(kennel_doc.is_active or 0):
        status = "Out of Service / Inactive"
    elif current_occupancy >= capacity:
        status = "Full"
    elif active_stays:
        status = "Occupied"
    elif reserved_bookings:
        status = "Reserved"
    else:
        status = "Available"
    return frappe._dict(
        {
            "kennel": kennel_doc.name,
            "kennel_name": kennel_doc.kennel_name or kennel_doc.name,
            "branch": branch,
            "capacity": capacity,
            "current_occupancy": current_occupancy,
            "available_slots": available_slots,
            "status": status,
            "active_reference": ", ".join(active_refs[:3]),
            "expected_check_out_date": expected_check_out_date,
            "from_date": from_date,
            "to_date": to_date,
            "reserved_count": len(reserved_bookings),
            "active_stay_count": len(active_stays),
        }
    )



def get_kennel_availability(branch: str | None, from_date, to_date, kennel: str | None = None, exclude_booking: str | None = None, exclude_stay: str | None = None) -> list[frappe._dict]:
    ensure_boarding_enabled()
    from_date, to_date = normalize_availability_range(from_date, to_date)
    filters = {}
    if branch:
        filters["branch"] = branch
    if kennel:
        filters["name"] = kennel
    kennels = frappe.get_all(
        KENNEL_DOCTYPE,
        filters=filters,
        fields=["name", "kennel_name", "branch", "capacity", "is_active"],
        order_by="kennel_name asc",
    )
    rows = []
    for kennel_doc in kennels:
        reserved = get_overlapping_reserved_bookings(
            kennel_doc.name,
            from_date,
            to_date,
            branch=kennel_doc.branch,
            exclude_booking=exclude_booking,
        )
        active = get_overlapping_active_stays(
            kennel_doc.name,
            from_date,
            to_date,
            branch=kennel_doc.branch,
            exclude_stay=exclude_stay,
        )
        rows.append(build_kennel_availability_row(kennel_doc, kennel_doc.branch, from_date, to_date, reserved, active))
    status_order = {"Available": 0, "Reserved": 1, "Occupied": 2, "Full": 3, "Out of Service / Inactive": 4}
    rows.sort(key=lambda row: (status_order.get(row.status, 99), row.branch or "", row.kennel_name or row.kennel))
    return rows



def validate_kennel_available(kennel: str, from_date, to_date, requested_slots: int = 1, service_branch: str | None = None, exclude_booking: str | None = None, exclude_stay: str | None = None) -> frappe._dict:
    kennel_doc = validate_kennel_assignment(kennel, service_branch)
    rows = get_kennel_availability(
        branch=service_branch or kennel_doc.branch,
        from_date=from_date,
        to_date=to_date,
        kennel=kennel,
        exclude_booking=exclude_booking,
        exclude_stay=exclude_stay,
    )
    if not rows:
        frappe.throw(f"Kennel {kennel} is unavailable for the selected dates.", frappe.ValidationError)
    row = rows[0]
    if row.status == "Out of Service / Inactive":
        frappe.throw(f"Kennel {kennel} is inactive and unavailable for boarding.", frappe.ValidationError)
    if int(row.available_slots or 0) < int(requested_slots or 1):
        frappe.throw(f"Kennel {kennel} is unavailable for the selected dates because capacity is already occupied.", frappe.ValidationError)
    return row



def validate_pet_boarding_booking(doc) -> None:
    ensure_boarding_enabled()
    resolve_boarding_owner(doc, booking_mode=True)
    previous = doc.get_doc_before_save() if getattr(doc, "get_doc_before_save", None) else None
    if not doc.status:
        doc.status = "Draft"
    if doc.status not in BOOKING_STATUSES:
        frappe.throw(f"Invalid boarding booking status: {doc.status}", frappe.ValidationError)
    if previous and previous.status != doc.status:
        ensure_booking_transition_allowed(previous.status, doc.status)
    sync_boarding_charge_fields(doc)
    if doc.status in {"Reserved", "Checked In"} and not doc.kennel:
        frappe.throw("Kennel is required before a boarding booking can be reserved or checked in.", frappe.ValidationError)
    if doc.status == "Checked In" and (not previous or previous.status != "Checked In"):
        validate_boarding_payment_before_check_in(doc)
    if doc.status == "Checked In" and not doc.linked_stay:
        frappe.throw("Use the Check In action to create the boarding stay before saving a checked-in booking.", frappe.ValidationError)
    if doc.status == "Checked Out" and not doc.actual_check_out_date:
        frappe.throw("Actual Check Out Date is required before a boarding booking can be checked out.", frappe.ValidationError)
    if doc.kennel:
        check_in_date, end_date = get_booking_date_range(doc)
        validate_kennel_assignment(doc.kennel, doc.service_branch)
        if doc.status in {"Reserved", "Checked In"}:
            validate_kennel_available(
                doc.kennel,
                check_in_date,
                end_date,
                service_branch=doc.service_branch,
                exclude_booking=doc.name,
                exclude_stay=doc.linked_stay,
            )



def validate_pet_boarding_stay(doc) -> None:
    ensure_boarding_enabled()
    resolve_boarding_owner(doc, stay_mode=True)
    set_pet_boarding_stay_title(doc)
    if not doc.status:
        doc.status = "Active"
    if doc.status not in STAY_STATUSES:
        frappe.throw(f"Invalid boarding stay status: {doc.status}", frappe.ValidationError)
    if not doc.kennel:
        frappe.throw("Kennel is required.", frappe.ValidationError)
    if not doc.check_in_datetime:
        frappe.throw("Check In Datetime is required.", frappe.ValidationError)
    check_in_datetime = get_datetime(doc.check_in_datetime)
    if doc.check_out_datetime and get_datetime(doc.check_out_datetime) < check_in_datetime:
        frappe.throw("Check Out Datetime cannot be earlier than Check In Datetime.", frappe.ValidationError)
    validate_kennel_assignment(doc.kennel, doc.service_branch)



def validate_pet_boarding_care_record(doc) -> None:
    ensure_boarding_enabled()
    if not doc.stay:
        frappe.throw("Stay is required for Pet Boarding Care Record.", frappe.ValidationError)
    stay = frappe.db.get_value(
        PET_BOARDING_STAY_DOCTYPE,
        doc.stay,
        ["booking", "patient", "primary_owner", "service_branch", "kennel", "status"],
        as_dict=True,
    )
    if not stay:
        frappe.throw("Pet Boarding Care Record must reference a valid Pet Boarding Stay.", frappe.ValidationError)
    doc.booking = stay.booking
    doc.patient = stay.patient
    doc.primary_owner = stay.primary_owner
    doc.service_branch = stay.service_branch
    doc.kennel = stay.kennel
    if not doc.recorded_by:
        doc.recorded_by = frappe.session.user
    if stay.status != "Active":
        frappe.throw("Care records can only be logged for active boarding stays.", frappe.ValidationError)
    if not doc.care_datetime:
        frappe.throw("Care Datetime is required.", frappe.ValidationError)
    get_datetime(doc.care_datetime)
    if doc.record_status not in CARE_RECORD_STATUSES:
        frappe.throw(f"Invalid boarding care record status: {doc.record_status}", frappe.ValidationError)
    if doc.care_type not in CARE_TYPES:
        frappe.throw(f"Invalid boarding care type: {doc.care_type}", frappe.ValidationError)
    if doc.food_portion_percent is not None and float(doc.food_portion_percent or 0) < 0:
        frappe.throw("Food Portion Consumed (%) cannot be negative.", frappe.ValidationError)
    if doc.water_intake_ml is not None and float(doc.water_intake_ml or 0) < 0:
        frappe.throw("Water Intake (ml) cannot be negative.", frappe.ValidationError)
    if doc.walk_duration_minutes is not None and int(doc.walk_duration_minutes or 0) < 0:
        frappe.throw("Walk Duration (Minutes) cannot be negative.", frappe.ValidationError)



def get_existing_active_stay(booking_name: str) -> str | None:
    rows = frappe.get_all(PET_BOARDING_STAY_DOCTYPE, filters={"booking": booking_name}, fields=["name", "status"], limit=1)
    if not rows:
        return None
    return rows[0].name



def create_boarding_stay_from_booking_doc(doc) -> str:
    existing_stay = doc.linked_stay or get_existing_active_stay(doc.name)
    if existing_stay:
        if not doc.linked_stay:
            doc.linked_stay = existing_stay
        return existing_stay
    stay = frappe.get_doc(
        {
            "doctype": PET_BOARDING_STAY_DOCTYPE,
            "booking": doc.name,
            "patient": doc.patient,
            "primary_owner": doc.primary_owner,
            "service_branch": doc.service_branch,
            "kennel": doc.kennel,
            "check_in_datetime": now_datetime(),
            "status": "Active",
            "feeding_instructions": doc.feeding_instructions,
            "special_notes": doc.special_notes,
        }
    )
    stay.insert(ignore_permissions=True)
    doc.linked_stay = stay.name
    return stay.name



def emit_boarding_event(doc, event: str, extra: dict | None = None) -> dict:
    payload = {
        "booking": doc.name,
        "patient": doc.patient,
        "primary_owner": doc.primary_owner,
        "service_branch": doc.service_branch,
        "kennel": doc.kennel,
        "check_in_date": doc.check_in_date,
        "expected_check_out_date": doc.expected_check_out_date,
        "actual_check_out_date": doc.actual_check_out_date,
        "status": doc.status,
        "linked_invoice": doc.linked_invoice,
        "linked_stay": doc.linked_stay,
    }
    if extra:
        payload.update(extra)
    return emit_notification_event(event, PET_BOARDING_BOOKING_DOCTYPE, doc.name, payload)



def ensure_booking_transition_allowed(current_status: str, target_status: str) -> None:
    allowed = VALID_BOOKING_STATUS_TRANSITIONS.get(current_status, set())
    if target_status not in allowed:
        frappe.throw(
            f"Pet Boarding Booking status cannot move from {current_status} to {target_status}.",
            frappe.ValidationError,
        )


def validate_boarding_payment_before_check_in(doc) -> None:
    if not boarding_requires_payment_before_check_in():
        return
    if use_billing_core_for_boarding():
        from vetedge.services.billing_core import get_payment_gate_status, resolve_billing_session, sync_source_to_billing_session

        if not resolve_billing_session(PET_BOARDING_BOOKING_DOCTYPE, doc.name):
            sync_source_to_billing_session(PET_BOARDING_BOOKING_DOCTYPE, doc.name)
        session = resolve_billing_session(PET_BOARDING_BOOKING_DOCTYPE, doc.name)
        status = get_payment_gate_status(session) if session else {"can_proceed": False, "message": "Create and pay the boarding invoice before this booking can be checked in."}
        if not status.get("can_proceed"):
            frappe.throw(status.get("message") or "The boarding invoice must be fully paid before this booking can be checked in.", frappe.ValidationError)
        return
    if not doc.linked_invoice or not is_active_sales_invoice(doc.linked_invoice):
        frappe.throw(
            "Create and pay the boarding invoice before this booking can be checked in.",
            frappe.ValidationError,
        )
    invoice = frappe.get_doc("Sales Invoice", doc.linked_invoice)
    if get_invoice_payment_status(invoice) != PAID_STATUS:
        frappe.throw(
            "The boarding invoice must be fully paid before this booking can be checked in.",
            frappe.ValidationError,
        )


def cancel_boarding_booking_doc(doc) -> dict:
    if doc.status == "Cancelled":
        return {"name": doc.name, "status": doc.status}
    ensure_booking_transition_allowed(doc.status, "Cancelled")
    doc.status = "Cancelled"
    doc.save(ignore_permissions=True)
    return {"name": doc.name, "status": doc.status}



def reserve_boarding_booking_doc(doc) -> dict:
    if doc.status == "Cancelled":
        frappe.throw("Cancelled boarding bookings cannot be reserved.", frappe.ValidationError)
    ensure_booking_transition_allowed(doc.status, "Reserved")
    check_in_date, end_date = get_booking_date_range(doc)
    if not doc.kennel:
        frappe.throw("Kennel is required before a boarding booking can be reserved.", frappe.ValidationError)
    validate_kennel_available(doc.kennel, check_in_date, end_date, service_branch=doc.service_branch, exclude_booking=doc.name)
    doc.status = "Reserved"
    doc.save(ignore_permissions=True)
    emit_boarding_event(doc, "boarding_reserved")
    return {"name": doc.name, "status": doc.status}



def check_in_boarding_booking_doc(doc) -> dict:
    if doc.status == "Cancelled":
        frappe.throw("Cancelled boarding bookings cannot be checked in.", frappe.ValidationError)
    ensure_booking_transition_allowed(doc.status, "Checked In")
    check_in_date, end_date = get_booking_date_range(doc)
    if not doc.kennel:
        frappe.throw("Kennel is required before check in.", frappe.ValidationError)
    validate_boarding_payment_before_check_in(doc)
    validate_kennel_available(doc.kennel, check_in_date, end_date, service_branch=doc.service_branch, exclude_booking=doc.name, exclude_stay=doc.linked_stay)
    stay_name = create_boarding_stay_from_booking_doc(doc)
    doc.status = "Checked In"
    doc.save(ignore_permissions=True)
    emit_boarding_event(doc, "boarding_checked_in", extra={"stay": stay_name})
    return {"name": doc.name, "status": doc.status, "stay": stay_name}



def check_out_boarding_booking_doc(doc) -> dict:
    ensure_booking_transition_allowed(doc.status, "Checked Out")
    if not doc.linked_stay and not get_existing_active_stay(doc.name):
        frappe.throw("Boarding stay must exist before check out.", frappe.ValidationError)
    if not doc.actual_check_out_date:
        doc.actual_check_out_date = nowdate()
    validate_boarding_checkout_billing(doc)
    stay_name = doc.linked_stay or get_existing_active_stay(doc.name)
    if stay_name:
        stay_doc = frappe.get_doc(PET_BOARDING_STAY_DOCTYPE, stay_name)
        if stay_doc.status != "Completed":
            stay_doc.status = "Completed"
            stay_doc.check_out_datetime = now_datetime()
            stay_doc.save(ignore_permissions=True)
        doc.linked_stay = stay_doc.name
    doc.status = "Checked Out"
    doc.save(ignore_permissions=True)
    emit_boarding_event(doc, "boarding_checked_out", extra={"stay": stay_name})
    return {"name": doc.name, "status": doc.status, "stay": stay_name, "billable_days": doc.billable_days}



def calculate_boarding_charges(booking_doc) -> dict:
    sync_boarding_charge_fields(booking_doc)
    return {
        "daily_rate": flt(booking_doc.daily_rate),
        "billable_days": int(booking_doc.billable_days or 0),
        "total_boarding_charge": flt(booking_doc.total_boarding_charge),
    }



def build_boarding_invoice_item(booking_doc, cost_center: str) -> dict:
    if not booking_doc.billing_item:
        frappe.throw("Billing Item is required before a boarding invoice can be created.", frappe.ValidationError)
    charges = calculate_boarding_charges(booking_doc)
    booking_doc.daily_rate = charges["daily_rate"]
    booking_doc.billable_days = charges["billable_days"]
    booking_doc.total_boarding_charge = charges["total_boarding_charge"]
    return build_invoice_item(booking_doc.billing_item, booking_doc.billable_days, None, booking_doc.daily_rate, cost_center)



def get_boarding_invoice_remark(booking_name: str, adjustment: bool = False) -> str:
    suffix = " (Balance Adjustment)" if adjustment else ""
    return f"{BOARDING_INVOICE_REMARK_PREFIX}{booking_name}{suffix}"



def get_boarding_invoice_names(booking_doc) -> list[str]:
    names = []
    if booking_doc.linked_invoice:
        names.append(booking_doc.linked_invoice)
    for row in frappe.get_all(
        "Sales Invoice",
        filters={"remarks": ["like", get_boarding_invoice_remark(booking_doc.name) + "%"]},
        fields=["name"],
        order_by="creation asc",
    ):
        if row.name not in names:
            names.append(row.name)
    return names



def get_boarding_invoice_documents(booking_doc):
    docs = []
    for name in get_boarding_invoice_names(booking_doc):
        invoice = frappe.get_doc("Sales Invoice", name)
        if invoice.docstatus == 2:
            continue
        docs.append(invoice)
    return docs



def get_boarding_invoice_totals(invoice, booking_doc) -> tuple[float, float]:
    qty = 0.0
    amount = 0.0
    items = invoice.get("items") if hasattr(invoice, "get") else getattr(invoice, "items", None)
    for row in items or []:
        item_code = row.get("item_code") if hasattr(row, "get") else getattr(row, "item_code", None)
        if booking_doc.billing_item and item_code and item_code != booking_doc.billing_item:
            continue
        row_qty = flt(row.get("qty") if hasattr(row, "get") else getattr(row, "qty", 0))
        row_amount = row.get("amount") if hasattr(row, "get") else getattr(row, "amount", None)
        row_rate = row.get("rate") if hasattr(row, "get") else getattr(row, "rate", None)
        qty += row_qty
        amount += flt(row_amount if row_amount not in (None, "") else row_qty * flt(row_rate))
    return qty, amount



def build_boarding_invoice_reference(invoice) -> dict:
    getter = getattr(invoice, "get", None)
    get_value = (lambda key, default=None: getter(key, default)) if callable(getter) else (lambda key, default=None: getattr(invoice, key, default))
    status = get_value("status") or get_invoice_payment_status(invoice)
    return {
        "sales_invoice": get_value("name"),
        "invoice_status": status,
        "posting_date": get_value("posting_date"),
        "grand_total": get_value("grand_total"),
        "outstanding_amount": get_value("outstanding_amount"),
        "currency": get_value("currency"),
        "invoice_docstatus": get_value("docstatus"),
    }



def replace_child_rows(doc, fieldname: str, rows: list[dict]) -> None:
    new_rows = [frappe._dict(row) for row in rows]
    setter = getattr(doc, "set", None)
    if callable(setter):
        doc.set(fieldname, new_rows)
    else:
        setattr(doc, fieldname, new_rows)



def sync_boarding_invoice_references(booking_doc, invoices) -> None:
    replace_child_rows(booking_doc, "booking_invoices", [build_boarding_invoice_reference(invoice) for invoice in invoices])



def get_submitted_boarding_billed_totals(booking_doc, invoices) -> tuple[float, float]:
    billed_days = 0.0
    billed_amount = 0.0
    for invoice in invoices:
        if invoice.docstatus != 1:
            continue
        qty, amount = get_boarding_invoice_totals(invoice, booking_doc)
        billed_days += qty
        billed_amount += amount
    return billed_days, billed_amount



def get_boarding_total_billed_amounts(booking_doc, invoices) -> tuple[float, float]:
    billed_days = 0.0
    billed_amount = 0.0
    for invoice in invoices:
        if invoice.docstatus == 2:
            continue
        qty, amount = get_boarding_invoice_totals(invoice, booking_doc)
        billed_days += qty
        billed_amount += amount
    return billed_days, billed_amount



def validate_boarding_checkout_billing(doc) -> None:
    charges = calculate_boarding_charges(doc)
    doc.daily_rate = charges["daily_rate"]
    doc.billable_days = charges["billable_days"]
    doc.total_boarding_charge = charges["total_boarding_charge"]
    invoices = get_boarding_invoice_documents(doc)

    if flt(doc.total_boarding_charge) > 0 and not invoices:
        frappe.throw(
            "Create the boarding invoice before checking out this booking.",
            frappe.ValidationError,
        )

    billed_days, billed_amount = get_boarding_total_billed_amounts(doc, invoices)
    delta_days = flt(doc.billable_days) - flt(billed_days)
    delta_amount = flt(doc.total_boarding_charge) - flt(billed_amount)
    if abs(delta_amount) >= 0.01 or abs(delta_days) >= 0.0001:
        frappe.throw(
            "Update or create the boarding invoice to reflect the current stay charges before checkout.",
            frappe.ValidationError,
        )

    for invoice in invoices:
        if invoice.docstatus == 0:
            frappe.throw(
                "Submit and pay all boarding invoices before checking out this booking.",
                frappe.ValidationError,
            )
        if get_invoice_payment_status(invoice) != PAID_STATUS:
            frappe.throw(
                "All boarding invoices must be fully paid before this booking can be checked out.",
                frappe.ValidationError,
            )



def update_draft_boarding_invoice(invoice_name: str, booking_doc, item_payload: dict, cost_center: str):
    invoice = frappe.get_doc("Sales Invoice", invoice_name)
    if invoice.docstatus != 0:
        frappe.throw("Only draft boarding invoices can be updated.", frappe.ValidationError)
    invoice.customer = booking_doc.primary_owner
    invoice.company = booking_doc.get("company") or get_default_company()
    invoice.posting_date = nowdate()
    invoice.due_date = nowdate()
    invoice.remarks = get_boarding_invoice_remark(booking_doc.name)
    invoice.set("items", [item_payload])
    if booking_doc.service_branch and frappe.get_meta("Sales Invoice").has_field("branch"):
        invoice.branch = booking_doc.service_branch
    if cost_center and frappe.get_meta("Sales Invoice").has_field("cost_center"):
        invoice.cost_center = cost_center
    invoice.save(ignore_permissions=True)
    return invoice



def create_boarding_sales_invoice(booking_doc, item_payload: dict, cost_center: str, adjustment: bool = False):
    invoice = frappe.get_doc(
        {
            "doctype": "Sales Invoice",
            "customer": booking_doc.primary_owner,
            "company": booking_doc.get("company") or get_default_company(),
            "posting_date": nowdate(),
            "due_date": nowdate(),
            "items": [item_payload],
            "remarks": get_boarding_invoice_remark(booking_doc.name, adjustment=adjustment),
        }
    )
    if booking_doc.service_branch and frappe.get_meta("Sales Invoice").has_field("branch"):
        invoice.branch = booking_doc.service_branch
    if cost_center and frappe.get_meta("Sales Invoice").has_field("cost_center"):
        invoice.cost_center = cost_center
    invoice.insert(ignore_permissions=True)
    return invoice



def build_boarding_adjustment_invoice_item(booking_doc, cost_center: str, delta_days: float, delta_amount: float) -> dict:
    if abs(delta_days) > 0.0001 and abs(delta_amount - (delta_days * flt(booking_doc.daily_rate))) < 0.01:
        qty = delta_days
        rate = flt(booking_doc.daily_rate)
    else:
        qty = 1 if delta_amount > 0 else -1
        rate = abs(delta_amount)
    return build_invoice_item(booking_doc.billing_item, qty, None, rate, cost_center)



def create_boarding_invoice_doc(booking_doc) -> dict:
    if booking_doc.status == "Cancelled":
        frappe.throw("Cancelled boarding bookings cannot be billed.", frappe.ValidationError)
    if use_billing_core_for_boarding():
        from vetedge.services.billing_core import sync_source_to_billing_session

        sync_boarding_charge_fields(booking_doc)
        result = sync_source_to_billing_session(PET_BOARDING_BOOKING_DOCTYPE, booking_doc.name)
        invoice_name = result.get("invoice")
        if invoice_name:
            booking_doc.linked_invoice = invoice_name
            booking_doc.save()
        return {"name": booking_doc.name, "invoice": invoice_name, "created": bool(result.get("created")), "adjustment": False, "billing_session": result.get("session")}
    charges = calculate_boarding_charges(booking_doc)
    booking_doc.daily_rate = charges["daily_rate"]
    booking_doc.billable_days = charges["billable_days"]
    booking_doc.total_boarding_charge = charges["total_boarding_charge"]
    cost_center = get_billing_cost_center(booking_doc.service_branch, required=True)
    invoices = get_boarding_invoice_documents(booking_doc)
    draft_invoice = next((invoice for invoice in invoices if invoice.docstatus == 0), None)
    if draft_invoice:
        item_payload = build_boarding_invoice_item(booking_doc, cost_center)
        invoice = update_draft_boarding_invoice(draft_invoice.name, booking_doc, item_payload, cost_center)
        refreshed_invoices = [invoice if existing.name == invoice.name else existing for existing in invoices]
        booking_doc.linked_invoice = invoice.name
        sync_boarding_invoice_references(booking_doc, refreshed_invoices)
        booking_doc.save(ignore_permissions=True)
        return {"name": booking_doc.name, "invoice": invoice.name, "created": False, "adjustment": False}

    billed_days, billed_amount = get_submitted_boarding_billed_totals(booking_doc, invoices)
    delta_days = flt(booking_doc.billable_days) - flt(billed_days)
    delta_amount = flt(booking_doc.total_boarding_charge) - flt(billed_amount)
    if abs(delta_amount) < 0.01:
        current_invoice = booking_doc.linked_invoice or (invoices[-1].name if invoices else None)
        sync_boarding_invoice_references(booking_doc, invoices)
        if current_invoice:
            booking_doc.linked_invoice = current_invoice
            booking_doc.save(ignore_permissions=True)
        return {"name": booking_doc.name, "invoice": current_invoice, "created": False, "adjustment": False}

    item_payload = build_boarding_adjustment_invoice_item(booking_doc, cost_center, delta_days, delta_amount)
    invoice = create_boarding_sales_invoice(booking_doc, item_payload, cost_center, adjustment=bool(invoices))
    all_invoices = [*invoices, invoice]
    booking_doc.linked_invoice = invoice.name
    sync_boarding_invoice_references(booking_doc, all_invoices)
    booking_doc.save(ignore_permissions=True)
    emit_boarding_event(
        booking_doc,
        "boarding_invoice_created",
        extra={"invoice": invoice.name, "amount": getattr(invoice, "grand_total", item_payload.get("amount"))},
    )
    return {"name": booking_doc.name, "invoice": invoice.name, "created": True, "adjustment": bool(invoices)}



@frappe.whitelist()
def reserve_boarding_booking(booking: str) -> dict:
    require_internal_user()
    ensure_boarding_enabled()
    from vetedge.services.platform_access import require_vetedge_platform_access
    require_vetedge_platform_access(
        action="reserve_boarding_booking",
        reference_doctype=PET_BOARDING_BOOKING_DOCTYPE,
        reference_name=booking
    )
    doc = frappe.get_doc(PET_BOARDING_BOOKING_DOCTYPE, booking)
    return reserve_boarding_booking_doc(doc)


def use_billing_core_for_boarding() -> bool:
    try:
        from vetedge.services.billing_core import is_billing_sessions_enabled

        return is_billing_sessions_enabled()
    except Exception:
        return False


@frappe.whitelist()
def check_in_boarding_booking(booking: str) -> dict:
    require_internal_user()
    ensure_boarding_enabled()
    from vetedge.services.platform_access import require_vetedge_platform_access
    require_vetedge_platform_access(
        action="check_in_boarding_booking",
        reference_doctype=PET_BOARDING_BOOKING_DOCTYPE,
        reference_name=booking
    )
    doc = frappe.get_doc(PET_BOARDING_BOOKING_DOCTYPE, booking)
    return check_in_boarding_booking_doc(doc)



@frappe.whitelist()
def check_out_boarding_booking(booking: str) -> dict:
    require_internal_user()
    ensure_boarding_enabled()
    from vetedge.services.platform_access import require_vetedge_platform_access
    require_vetedge_platform_access(
        action="check_out_boarding_booking",
        reference_doctype=PET_BOARDING_BOOKING_DOCTYPE,
        reference_name=booking
    )
    doc = frappe.get_doc(PET_BOARDING_BOOKING_DOCTYPE, booking)
    return check_out_boarding_booking_doc(doc)



@frappe.whitelist()
def cancel_boarding_booking(booking: str) -> dict:
    require_internal_user()
    ensure_boarding_enabled()
    doc = frappe.get_doc(PET_BOARDING_BOOKING_DOCTYPE, booking)
    return cancel_boarding_booking_doc(doc)


@frappe.whitelist()
def create_boarding_invoice(booking: str) -> dict:
    require_internal_user()
    ensure_boarding_enabled()
    from vetedge.services.platform_access import require_vetedge_platform_access
    require_vetedge_platform_access(
        action="create_boarding_invoice",
        reference_doctype=PET_BOARDING_BOOKING_DOCTYPE,
        reference_name=booking
    )
    doc = frappe.get_doc(PET_BOARDING_BOOKING_DOCTYPE, booking)
    return create_boarding_invoice_doc(doc)



def build_kennel_availability_board_cards(rows: list[frappe._dict]) -> list[dict]:
    total = len(rows)
    available_slots = sum(int(row.available_slots or 0) for row in rows)
    reserved = sum(1 for row in rows if row.status == "Reserved")
    occupied = sum(1 for row in rows if row.status == "Occupied")
    full = sum(1 for row in rows if row.status == "Full")
    inactive = sum(1 for row in rows if row.status == "Out of Service / Inactive")
    current_occupancy = sum(int(row.current_occupancy or 0) for row in rows)
    capacity = sum(int(row.capacity or 0) for row in rows)
    occupancy_rate = round((current_occupancy / capacity) * 100, 1) if capacity else 0
    return [
        {"label": "Total Kennels", "value": total},
        {"label": "Available", "value": available_slots},
        {"label": "Reserved", "value": reserved},
        {"label": "Occupied", "value": occupied},
        {"label": "Full", "value": full},
        {"label": "Occupancy Rate", "value": f"{occupancy_rate}%"},
    ]


@frappe.whitelist()
def get_kennel_availability_board_view(branch: str | None = None, from_date: str | None = None, to_date: str | None = None, kennel: str | None = None, status: str | None = None) -> dict:
    require_internal_user()
    rows = get_kennel_availability(branch=branch, from_date=from_date or nowdate(), to_date=to_date or from_date or nowdate(), kennel=kennel)
    if status:
        rows = [row for row in rows if row.status == status]
    start_date, end_date = normalize_availability_range(from_date or nowdate(), to_date or from_date or nowdate())
    return {
        "cards": build_kennel_availability_board_cards(rows),
        "rows": rows,
        "filters": {
            "branch": branch,
            "from_date": str(start_date),
            "to_date": str(end_date),
            "kennel": kennel,
            "status": status,
        },
    }
