from __future__ import annotations

import frappe


SETTINGS_DOCTYPE = "Veterinary Settings"

FEATURE_FLAG_FIELDS = {
	"vetedge": "enable_vetedge",
	"consultations": "enable_consultations",
	"vitals": "enable_vitals",
	"appointments": "enable_appointments",
	"owner_portal": "enable_owner_portal",
	"guest_booking": "enable_guest_booking",
	"notifications": "enable_notifications",
	"treatment_billing": "enable_treatment_billing",
	"dispensary_flow": "enable_dispensary_flow",
	"vaccination": "enable_vaccination",
	"boarding": "enable_boarding",
	"demo_tools": "enable_demo_tools",
	"advanced_reports": "enable_advanced_reports",
}

DEFAULT_FEATURE_FLAGS = {
	"enable_vetedge": 0,
	"enable_consultations": 0,
	"enable_vitals": 0,
	"enable_appointments": 0,
	"enable_owner_portal": 0,
	"enable_guest_booking": 0,
	"enable_notifications": 0,
	"enable_treatment_billing": 0,
	"enable_dispensary_flow": 0,
	"enable_vaccination": 0,
	"enable_boarding": 0,
	"enable_demo_tools": 0,
	"enable_advanced_reports": 0,
}


def is_enabled(flag: str) -> bool:
	if flag not in FEATURE_FLAG_FIELDS:
		frappe.throw(f"Unknown VetEdge feature flag: {flag}", frappe.ValidationError)

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
