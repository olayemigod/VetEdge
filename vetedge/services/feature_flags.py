from __future__ import annotations

import frappe


SETTINGS_DOCTYPE = "Veterinary Settings"

FEATURE_FLAG_FIELDS = {
	"vetedge": "enable_vetedge",
	"registration_billing": "enable_registration_billing",
	"consultations": "enable_consultations",
	"consultation_billing": "enable_consultation_billing",
	"vitals": "enable_vitals",
	"appointments": "enable_appointments",
	"owner_portal": "enable_owner_portal",
	"guest_booking": "enable_guest_booking",
	"notifications": "enable_notifications",
	"treatment_billing": "enable_treatment_billing",
	"dispensary_flow": "enable_dispensary_flow",
	"vaccination": "enable_vaccination",
	"grooming": "enable_grooming",
	"boarding": "enable_boarding",
	"demo_tools": "enable_demo_tools",
	"advanced_reports": "enable_advanced_reports",
}

DEFAULT_FEATURE_FLAGS = {
	"enable_vetedge": 0,
	"enable_registration_billing": 0,
	"enforce_cost_center_on_billing": 1,
	"enable_consultations": 0,
	"enable_consultation_billing": 0,
	"allow_doctor_collect_payment": 0,
	"consultation_requires_payment_before_treatment": 0,
	"enable_vitals": 0,
	"require_vitals_before_completion": 0,
	"enable_appointments": 0,
	"enable_owner_portal": 0,
	"enable_guest_booking": 0,
	"allow_owner_cancel_appointment": 0,
	"allow_owner_reschedule_appointment": 0,
	"enable_portal_payments": 0,
	"portal_show_consultation_summary_only": 1,
	"enable_notifications": 0,
	"notify_on_appointment_create": 0,
	"notify_on_appointment_reminder": 0,
	"notify_on_reschedule": 0,
	"notify_on_cancellation": 0,
	"appointment_reminder_hours_before": 24,
	"enable_treatment_billing": 0,
	"enable_dispensary_flow": 0,
	"enable_vaccination": 0,
	"enable_grooming": 0,
	"enable_boarding": 0,
	"enable_demo_tools": 0,
	"enable_advanced_reports": 0,
}


def is_enabled(flag: str) -> bool:
	if flag not in FEATURE_FLAG_FIELDS:
		frappe.throw(f"Unknown feature flag: {flag}", frappe.ValidationError)

	flags = get_feature_flags()
	if flag != "vetedge" and not flags["vetedge"]:
		return False

	return flags[flag]


def get_feature_flags() -> dict[str, bool]:
	if not frappe.db.exists("DocType", SETTINGS_DOCTYPE):
		return _default_flags()

	settings = frappe.get_single(SETTINGS_DOCTYPE)
	meta = frappe.get_meta(SETTINGS_DOCTYPE)

	return {
		flag: bool(
			settings.get(fieldname)
			if meta.has_field(fieldname) and settings.get(fieldname) is not None
			else DEFAULT_FEATURE_FLAGS[fieldname]
		)
		for flag, fieldname in FEATURE_FLAG_FIELDS.items()
	}


def _default_flags() -> dict[str, bool]:
	return {flag: bool(DEFAULT_FEATURE_FLAGS[fieldname]) for flag, fieldname in FEATURE_FLAG_FIELDS.items()}
