from __future__ import annotations

from collections import Counter

from frappe import _
from frappe.utils import cint, cstr, flt


MONEY_REPORTS = {"Revenue Summary", "Unpaid Invoice Report", "Hospitalisation Charge Summary"}


def insight_card(label, value, indicator="Blue", datatype=None, subtitle=None):
	card = {
		"label": _(label),
		"value": value,
		"indicator": indicator,
	}
	if datatype:
		card["datatype"] = datatype
	if subtitle:
		card["subtitle"] = _(subtitle)
	return card


def percent(numerator, denominator, precision=1):
	denominator = flt(denominator)
	if not denominator:
		return 0
	return flt((flt(numerator) / denominator) * 100, precision)


def build_report_summary(report_name, rows, filters=None, existing_summary=None):
	rows = list(rows or [])
	builders = {
		"Consultation Register": consultation_summary,
		"Appointment Report": appointment_summary,
		"Missed Appointment Report": missed_appointment_summary,
		"Lab Order Report": lab_order_summary,
		"Vaccination Report": vaccination_summary,
		"Boarding Report": boarding_summary,
		"Grooming Report": grooming_summary,
		"Patient Register": patient_summary,
		"Revenue Summary": revenue_summary,
		"Unpaid Invoice Report": unpaid_invoice_summary,
		"Stock Expiry Status": stock_expiry_summary,
		"Active Hospitalisations": active_hospitalisations_summary,
		"Hospitalisation Charge Summary": hospitalisation_charge_summary,
		"Care Location Occupancy": care_location_occupancy_summary,
		"Hospitalisation Discharge Watch": discharge_watch_summary,
		"Pending Hospitalisation Actions": pending_hospitalisation_actions_summary,
	}
	builder = builders.get(cstr(report_name))
	if not builder:
		return existing_summary or []
	return builder(rows, filters or {})


def consultation_summary(rows, filters=None):
	total = len(rows)
	completed = _count_status(rows, "status", {"completed"})
	active = _count_status(rows, "status", {"active", "in progress", "open", "draft", "ready for treatment"})
	awaiting_payment = sum(1 for row in rows if _is_unpaid(row.get("payment_status")) or _is_unpaid(row.get("invoice_status")))
	cancelled = _count_status(rows, "status", {"cancelled", "canceled"})
	follow_up = sum(1 for row in rows if _has_value(row.get("follow_up_date")) or _has_value(row.get("next_appointment")))
	avg_value = _average(row.get("planned_treatment_total") for row in rows)
	return [
		insight_card("Total Consultations", total, "Blue"),
		insight_card("Completed", completed, "Green"),
		insight_card("Active / In Progress", active, "Orange"),
		insight_card("Awaiting Payment", awaiting_payment, "Orange"),
		insight_card("Cancelled", cancelled, "Red"),
		insight_card("Completion Rate", percent(completed, total), "Green", "Percent"),
		insight_card("Average Consultation Value", avg_value, "Blue", "Currency"),
		insight_card("Follow-up Required", follow_up, "Purple"),
	]


def lab_order_summary(rows, filters=None):
	total = len(rows)
	completed = _count_status(rows, "status", {"completed", "reviewed"})
	pending = _count_status(rows, "status", {"pending", "requested", "open", "draft", "pending collection"})
	in_progress = _count_status(rows, "status", {"in progress", "sample collected", "processing"})
	cancelled = _count_status(rows, "status", {"cancelled", "canceled"})
	unbilled = sum(1 for row in rows if not _has_value(row.get("linked_invoice") or row.get("invoice")))
	return [
		insight_card("Total Lab Orders", total, "Blue"),
		insight_card("Pending Collection", pending, "Orange"),
		insight_card("In Progress", in_progress, "Blue"),
		insight_card("Completed", completed, "Green"),
		insight_card("Cancelled", cancelled, "Red"),
		insight_card("Completion Rate", percent(completed, total), "Green", "Percent"),
		insight_card("Unbilled / Unpaid Labs", unbilled, "Orange"),
	]


def appointment_summary(rows, filters=None):
	total = len(rows)
	scheduled = _count_status(rows, "status", {"scheduled", "confirmed", "booked"})
	checked_in = _count_status(rows, "status", {"checked in", "arrived"})
	completed = _count_status(rows, "status", {"completed"})
	no_show = _count_status(rows, "status", {"no show", "missed"})
	converted = sum(1 for row in rows if _has_value(row.get("consultation") or row.get("linked_consultation")))
	return [
		insight_card("Total Appointments", total, "Blue"),
		insight_card("Scheduled / Confirmed", scheduled, "Blue"),
		insight_card("Checked In", checked_in, "Orange"),
		insight_card("Completed", completed, "Green"),
		insight_card("No Show", no_show, "Red"),
		insight_card("No-show Rate", percent(no_show, total), "Red" if no_show else "Green", "Percent"),
		insight_card("Converted to Consultation", converted, "Green"),
	]


def missed_appointment_summary(rows, filters=None):
	total = len(rows)
	contacted = _count_status(rows, "owner_contact_status", {"contacted", "owner contacted"})
	rescheduled = _count_status(rows, "status", {"rescheduled"}) + sum(1 for row in rows if _has_value(row.get("rescheduled_appointment")))
	lost = max(total - rescheduled, 0)
	revenue_at_risk = sum(flt(row.get("estimated_revenue") or row.get("amount")) for row in rows)
	return [
		insight_card("Missed Appointments", total, "Red" if total else "Green"),
		insight_card("Owner Contacted", contacted, "Blue"),
		insight_card("Rescheduled", rescheduled, "Green"),
		insight_card("Lost Visits", lost, "Orange"),
		insight_card("Recovery Rate", percent(rescheduled, total), "Green", "Percent"),
		insight_card("Estimated Revenue at Risk", revenue_at_risk, "Orange", "Currency"),
	]


def vaccination_summary(rows, filters=None):
	total = len(rows)
	administered = _count_status(rows, "status", {"administered", "completed"})
	due_soon = _count_status(rows, "due_status", {"due soon"})
	overdue = _count_status(rows, "due_status", {"overdue"})
	cancelled = _count_status(rows, "status", {"cancelled", "canceled"})
	linked_invoice = sum(1 for row in rows if _has_value(row.get("linked_invoice")))
	return [
		insight_card("Total Vaccinations", total, "Blue"),
		insight_card("Administered", administered, "Green"),
		insight_card("Due Soon", due_soon, "Orange"),
		insight_card("Overdue", overdue, "Red"),
		insight_card("Cancelled", cancelled, "Red"),
		insight_card("Coverage Rate", percent(administered, total), "Green", "Percent"),
		insight_card("Linked to Billing", linked_invoice, "Blue"),
	]


def boarding_summary(rows, filters=None):
	total = len(rows)
	active = _count_status(rows, "status", {"active", "checked in", "admitted", "in house"})
	upcoming = _count_status(rows, "status", {"booked", "scheduled", "confirmed", "reserved"})
	checked_out = _count_status(rows, "status", {"checked out", "completed"})
	cancelled = _count_status(rows, "status", {"cancelled", "canceled"})
	charges = sum(flt(row.get("total_boarding_charge")) for row in rows)
	unbilled = sum(1 for row in rows if not _has_value(row.get("linked_invoice")))
	return [
		insight_card("Active Stays", active, "Green"),
		insight_card("Upcoming Bookings", upcoming, "Blue"),
		insight_card("Checked Out", checked_out, "Green"),
		insight_card("Cancelled", cancelled, "Red"),
		insight_card("Boarding Charges", charges, "Blue", "Currency"),
		insight_card("Unbilled Boarding", unbilled, "Orange"),
		insight_card("Occupancy Rate", percent(active, total), "Blue", "Percent"),
	]


def grooming_summary(rows, filters=None):
	total = len(rows)
	active = _count_status(rows, "status", {"active", "scheduled", "confirmed", "in progress"})
	completed = _count_status(rows, "status", {"completed"})
	cancelled = _count_status(rows, "status", {"cancelled", "canceled"})
	revenue = sum(flt(row.get("total_charge")) for row in rows)
	unpaid = sum(1 for row in rows if not _has_value(row.get("linked_invoice")))
	popular = _most_common_value(row.get("grooming_service") for row in rows)
	return [
		insight_card("Total Grooming Sessions", total, "Blue"),
		insight_card("Scheduled / Active", active, "Orange"),
		insight_card("Completed", completed, "Green"),
		insight_card("Cancelled", cancelled, "Red"),
		insight_card("Completion Rate", percent(completed, total), "Green", "Percent"),
		insight_card("Grooming Revenue", revenue, "Blue", "Currency"),
		insight_card("Unpaid Grooming", unpaid, "Orange"),
		insight_card("Popular Service", popular or _("No data"), "Purple"),
	]


def patient_summary(rows, filters=None):
	total = len(rows)
	active = _count_status(rows, "registration_status", {"active", "registered", "enabled"})
	inactive = _count_status(rows, "registration_status", {"inactive", "disabled", "deceased", "archived"})
	species_count = len({cstr(row.get("species")).strip() for row in rows if cstr(row.get("species")).strip()})
	return [
		insight_card("Total Patients", total, "Blue"),
		insight_card("New Patients", total, "Green", subtitle="Filtered period"),
		insight_card("Active Patients", active, "Green"),
		insight_card("Inactive Patients", inactive, "Orange"),
		insight_card("Species Mix", species_count, "Purple"),
	]


def revenue_summary(rows, filters=None):
	total_billed = sum(flt(row.get("grand_total")) for row in rows)
	total_paid = sum(flt(row.get("paid_amount")) for row in rows)
	outstanding = sum(flt(row.get("outstanding_amount")) for row in rows)
	draft = _count_status(rows, "status", {"draft"})
	partly_paid = _count_status(rows, "status", {"partly paid", "partially paid"})
	return [
		insight_card("Total Billed", total_billed, "Blue", "Currency"),
		insight_card("Total Paid", total_paid, "Green", "Currency"),
		insight_card("Outstanding", outstanding, "Orange", "Currency"),
		insight_card("Draft Invoices", draft, "Gray"),
		insight_card("Partly Paid", partly_paid, "Orange"),
		insight_card("Payment Completion Rate", percent(total_paid, total_billed), "Green", "Percent"),
		insight_card("Current Service Outstanding", outstanding, "Orange", "Currency"),
	]


def unpaid_invoice_summary(rows, filters=None):
	outstanding = sum(flt(row.get("outstanding_amount")) for row in rows)
	aged_30 = sum(1 for row in rows if cint(row.get("age_days")) >= 30)
	aged_60 = sum(1 for row in rows if cint(row.get("age_days")) >= 60)
	aged_90 = sum(1 for row in rows if cint(row.get("age_days")) >= 90)
	return [
		insight_card("Current Service Outstanding", outstanding, "Orange", "Currency"),
		insight_card("Unpaid Invoices", len(rows), "Orange"),
		insight_card("Average Outstanding", _average(row.get("outstanding_amount") for row in rows), "Blue", "Currency"),
		insight_card("30+ Days", aged_30, "Orange"),
		insight_card("60+ Days", aged_60, "Red"),
		insight_card("90+ Days", aged_90, "Red"),
	]


def stock_expiry_summary(rows, filters=None):
	expired = _count_status(rows, "expiry_status", {"expired"})
	expiring = _count_status(rows, "expiry_status", {"expiring soon"})
	safe = _count_status(rows, "expiry_status", {"safe"})
	affected_items = len({row.get("item_code") for row in rows if row.get("item_code")})
	affected_warehouses = len({row.get("warehouse") for row in rows if row.get("warehouse")})
	return [
		insight_card("Total Items", len(rows), "Blue"),
		insight_card("Expired Batches", expired, "Red"),
		insight_card("Expiring Soon", expiring, "Orange"),
		insight_card("Safe", safe, "Green"),
		insight_card("Affected Items", affected_items, "Purple"),
		insight_card("Affected Warehouses", affected_warehouses, "Blue"),
		insight_card("Suggested Action", _("Review oldest batches first") if expired or expiring else _("No immediate action"), "Orange" if expired or expiring else "Green"),
	]


def active_hospitalisations_summary(rows, filters=None):
	total = len(rows)
	critical = _count_status(rows, "care_level", {"critical", "high", "high care", "intensive"})
	pending_charges = sum(flt(row.get("pending_charges")) for row in rows)
	discharge_ready = sum(1 for row in rows if "ready" in _norm(row.get("discharge_readiness_summary")))
	avg_stay = _average(row.get("days_admitted") for row in rows)
	return [
		insight_card("Active Admissions", total, "Blue"),
		insight_card("Critical / High Care", critical, "Red" if critical else "Green"),
		insight_card("Pending Clinical Actions", sum(1 for row in rows if not _has_value(row.get("latest_activity_datetime"))), "Orange"),
		insight_card("Pending Owner Updates", 0, "Gray"),
		insight_card("Unbilled Charges", pending_charges, "Orange", "Currency"),
		insight_card("Discharge Ready", discharge_ready, "Green"),
		insight_card("Average Length of Stay", avg_stay, "Blue"),
	]


def hospitalisation_charge_summary(rows, filters=None):
	total_charges = sum(flt(row.get("charge_sheet_total") or row.get("total_charges")) for row in rows)
	billed = sum(flt(row.get("charge_sheet_invoiced") or row.get("invoiced_charges")) for row in rows)
	unbilled = sum(flt(row.get("charge_sheet_pending") or row.get("pending_charges")) for row in rows)
	outstanding = sum(flt(row.get("billing_session_outstanding") or row.get("outstanding_amount")) for row in rows)
	return [
		insight_card("Total Charges", total_charges, "Blue", "Currency"),
		insight_card("Billed Charges", billed, "Green", "Currency"),
		insight_card("Unbilled Charges", unbilled, "Orange", "Currency"),
		insight_card("Stock Charges", 0, "Gray", "Currency"),
		insight_card("Average Charge per Admission", _average(row.get("charge_sheet_total") or row.get("total_charges") for row in rows), "Blue", "Currency"),
		insight_card("Billing Completion Rate", percent(billed, total_charges), "Green", "Percent"),
		insight_card("Outstanding Hospitalisation Billing", outstanding, "Orange", "Currency"),
	]


def care_location_occupancy_summary(rows, filters=None):
	total_locations = len(rows)
	occupied = sum(cint(row.get("active_occupancy")) for row in rows)
	capacity = sum(cint(row.get("capacity")) for row in rows)
	available = sum(cint(row.get("available_slots")) for row in rows)
	reserved_cleaning = sum(1 for row in rows if _norm(row.get("status")) in {"reserved", "cleaning"})
	return [
		insight_card("Total Locations", total_locations, "Blue"),
		insight_card("Occupied", occupied, "Orange" if occupied else "Green"),
		insight_card("Available", available, "Green"),
		insight_card("Reserved / Cleaning", reserved_cleaning, "Orange"),
		insight_card("Occupancy Rate", percent(occupied, capacity), "Blue", "Percent"),
		insight_card("Expected Discharges", 0, "Gray"),
	]


def discharge_watch_summary(rows, filters=None):
	ready = _count_status(rows, "discharge_readiness", {"ready"})
	blocked_payment = sum(1 for row in rows if flt(row.get("pending_charges")) > 0)
	blocked_stock = sum(1 for row in rows if cint(row.get("pending_stock_posting")) > 0)
	blocked_clinical = sum(1 for row in rows if _has_value(row.get("warning_summary")))
	avg_outstanding = _average(row.get("pending_charges") for row in rows)
	return [
		insight_card("Ready for Discharge", ready, "Green"),
		insight_card("Blocked by Payment", blocked_payment, "Orange"),
		insight_card("Blocked by Stock Posting", blocked_stock, "Orange"),
		insight_card("Blocked by Clinical Action", blocked_clinical, "Red" if blocked_clinical else "Green"),
		insight_card("Owner Update Pending", 0, "Gray"),
		insight_card("Average Outstanding Balance", avg_outstanding, "Orange", "Currency"),
	]


def pending_hospitalisation_actions_summary(rows, filters=None):
	total = len(rows)
	high = _count_status(rows, "priority", {"high", "critical"})
	medium = _count_status(rows, "priority", {"medium"})
	stock = _count_status(rows, "action_type", {"pending stock posting"})
	medication = sum(1 for row in rows if "medication" in _norm(row.get("action_type")))
	vitals = sum(1 for row in rows if "vital" in _norm(row.get("action_type")))
	owner_updates = sum(1 for row in rows if "owner" in _norm(row.get("action_type")))
	return [
		insight_card("Pending Actions", total, "Orange" if total else "Green"),
		insight_card("Overdue Actions", high, "Red" if high else "Green"),
		insight_card("Critical Actions", high, "Red" if high else "Green"),
		insight_card("Medication Due", medication, "Orange"),
		insight_card("Vitals Due", vitals, "Orange"),
		insight_card("Owner Updates Due", owner_updates, "Orange"),
		insight_card("Completion Rate", percent(max(total - high - medium, 0), total), "Green", "Percent"),
		insight_card("Pending Stock Posting", stock, "Orange"),
	]


def _count_status(rows, fieldname, accepted):
	accepted = {_norm(value) for value in accepted}
	return sum(1 for row in rows if _norm(row.get(fieldname)) in accepted)


def _norm(value):
	return cstr(value or "").strip().lower()


def _has_value(value):
	value = cstr(value or "").strip()
	return bool(value and value.lower() not in {"not set", "none", "null", "no data"})


def _is_unpaid(value):
	value = _norm(value)
	return any(token in value for token in ("unpaid", "partly", "partial", "awaiting payment", "overdue"))


def _average(values):
	values = [flt(value) for value in values if value not in (None, "")]
	if not values:
		return 0
	return flt(sum(values) / len(values), 2)


def _most_common_value(values):
	values = [cstr(value).strip() for value in values if cstr(value).strip()]
	if not values:
		return ""
	return Counter(values).most_common(1)[0][0]
