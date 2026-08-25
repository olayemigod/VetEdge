from __future__ import annotations

import frappe
from frappe.model.document import Document

from vetedge.services.copy_control import reset_vetedge_copy_state
from vetedge.services.appointment_intelligence import (
	prepare_appointment_service_context,
	validate_appointment_service_context,
)
from vetedge.services.appointment_notifications import (
	notify_appointment_checked_in,
	notify_appointment_completed,
)
from vetedge.services.notifications import notify_appointment_event


def validate_appointment(*args, **kwargs):
	doc = args[0] if args else kwargs.get("doc")
	if doc and doc.get("appointment_type") == "Grooming":
		from vetedge.services.appointment_grooming_bridge import validate_grooming_veterinary_appointment

		return validate_grooming_veterinary_appointment(doc)
	if doc and doc.get("appointment_type") == "Vaccination":
		from vetedge.services.appointment_vaccination_bridge import validate_vaccination_veterinary_appointment

		return validate_vaccination_veterinary_appointment(doc)
	if doc:
		prepare_appointment_service_context(doc)
	from vetedge.services.appointment_flow import validate_appointment as _validate_appointment

	result = _validate_appointment(*args, **kwargs)
	if doc:
		validate_appointment_service_context(doc)
	return result


def sync_missed_appointment_from_source(*args, **kwargs):
	from vetedge.services.appointment_flow import sync_missed_appointment_from_source as _sync_missed_appointment_from_source
	return _sync_missed_appointment_from_source(*args, **kwargs)


class VeterinaryAppointment(Document):
	def validate(self) -> None:
		reset_vetedge_copy_state(self)
		validate_appointment(self)

	def after_insert(self) -> None:
		notify_appointment_event(self, "appointment_created")

	def on_update(self) -> None:
		previous = self.get_doc_before_save()
		sync_missed_appointment_from_source(self)
		if not previous or previous.status == self.status:
			return

		if self.status == "Confirmed":
			notify_appointment_event(self, "appointment_confirmed")
		elif self.status == "Rescheduled":
			notify_appointment_event(self, "appointment_rescheduled")
		elif self.status == "Cancelled":
			notify_appointment_event(self, "appointment_cancelled")
		elif self.status == "Checked In":
			notify_appointment_checked_in(self)
		elif self.status == "Completed":
			notify_appointment_completed(self)

		STATUS_SMS_SETTINGS_MAP = {
			"Owner Requested": "appointment_sms_on_owner_requested",
			"Scheduled": "appointment_sms_on_scheduled",
			"Confirmed": "appointment_sms_on_confirmed",
			"Rescheduled": "appointment_sms_on_rescheduled",
			"Cancelled": "appointment_sms_on_cancelled",
			"Completed": "appointment_sms_on_completed",
			"No Show": "appointment_sms_on_no_show",
		}
		if self.status in STATUS_SMS_SETTINGS_MAP:
			try:
				settings = frappe.get_single("Veterinary Settings")
				if settings.get("enable_notifications") and settings.get("enable_appointment_sms_notifications"):
					setting_field = STATUS_SMS_SETTINGS_MAP[self.status]
					if settings.get(setting_field) and self.primary_owner:
						phone = frappe.db.get_value("Customer", self.primary_owner, "mobile_no") or frappe.db.get_value("Customer", self.primary_owner, "phone")
						if phone:
							tenant = None
							try:
								from vetedge.coreedge_adapter import get_current_vetedge_context
								ctx = get_current_vetedge_context()
								tenant = ctx.get("tenant")
							except Exception:
								pass

							if not tenant:
								try:
									tenant = frappe.db.get_value("CoreEdge Tenant", {}, "name")
								except Exception:
									pass

							from frappe.utils import get_datetime, get_date_str, get_time_str
							
							clinic_name = (
								frappe.db.get_value("Website Settings", "Website Settings", "app_name")
								or (frappe.db.get_value("Company", self.company, "company_name") if getattr(self, "company", None) else None)
								or "our clinic"
							)
							
							owner_name = (
								frappe.db.get_value("Customer", self.primary_owner, "customer_name")
								or self.primary_owner
								or "Customer"
							)
							
							patient_name = "your pet"
							if getattr(self, "patient", None):
								patient_name = (
									frappe.db.get_value("Veterinary Patient", self.patient, "patient_name")
									or self.patient
									or "your pet"
								)
								
							dt_val = get_datetime(self.appointment_datetime) if self.appointment_datetime else None
							app_date = get_date_str(dt_val) if dt_val else ""
							app_time = dt_val.strftime("%H:%M") if dt_val else ""
							app_datetime = str(self.appointment_datetime) if self.appointment_datetime else ""
							
							clinic_phone = ""
							if getattr(self, "branch", None):
								try:
									clinic_phone = frappe.db.get_value("Branch", self.branch, "phone") or ""
								except Exception:
									pass

							sms_context = {
								"clinic_name": clinic_name,
								"branch_name": getattr(self, "branch", "") or "",
								"owner_name": owner_name,
								"patient_name": patient_name,
								"appointment_date": app_date,
								"appointment_time": app_time,
								"appointment_datetime": app_datetime,
								"clinic_phone": clinic_phone
							}

							STATUS_EVENT_MAP = {
								"Owner Requested": "appointment_owner_requested",
								"Scheduled": "appointment_scheduled",
								"Confirmed": "appointment_confirmed",
								"Rescheduled": "appointment_rescheduled",
								"Cancelled": "appointment_cancelled",
								"Completed": "appointment_completed",
								"No Show": "appointment_no_show",
							}
							event_key = STATUS_EVENT_MAP[self.status]

							from vetedge.services.coreedge_sms import send_sms_safe
							send_sms_safe(
								to=phone,
								product_app="VetEdge",
								event=event_key,
								context=sms_context,
								reference_doctype="Veterinary Appointment",
								reference_name=self.name,
								priority="Normal",
								route_type="Normal",
								tenant=tenant,
								idempotency_key=f"VetEdge:Veterinary Appointment:{self.name}:appointment_status:{self.status}"
							)
			except Exception:
				if getattr(frappe, "log_error", None):
					try:
						frappe.log_error(
							title="Appointment Status SMS Failed",
							message=frappe.get_traceback(),
						)
					except Exception:
						pass