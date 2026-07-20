from __future__ import annotations

from datetime import datetime
from typing import Any

import frappe
from frappe import _
from frappe.utils import nowdate

from vetedge.services.branch_context import get_active_veterinary_branch_context
from vetedge.services.permissions import ELEVATED_ROLES, get_user_roles, is_internal_staff_user


ALL_OPERATIONAL_ROLES = {
	"VetEdge Administrator",
	"VetEdge Doctor",
	"VetEdge Nurse",
	"Veterinary Nurse",
	"VetEdge Front Desk",
	"VetEdge Groomer",
	"Dispensary User",
	"VetEdge Dispensary User",
	"Lab Technician",
	"VetEdge Lab Technician",
	"Branch Manager",
	"VetEdge Branch Manager",
	"Accounts/Cashier",
	"VetEdge Accounts/Cashier",
	"Accounts Manager",
	"Accounts User",
	"System Manager",
}
FRONT_DESK = {"VetEdge Front Desk", "Branch Manager", "VetEdge Branch Manager", *ELEVATED_ROLES}
CLINICAL = {
	"VetEdge Doctor",
	"VetEdge Nurse",
	"Veterinary Nurse",
	"Branch Manager",
	"VetEdge Branch Manager",
	*ELEVATED_ROLES,
}
LAB = {"Lab Technician", "VetEdge Lab Technician", "VetEdge Doctor", *ELEVATED_ROLES}
PHARMACY = {"Dispensary User", "VetEdge Dispensary User", "VetEdge Doctor", "Branch Manager", *ELEVATED_ROLES}
SERVICES = {"VetEdge Groomer", "VetEdge Front Desk", "Branch Manager", "VetEdge Branch Manager", *ELEVATED_ROLES}
FINANCE = {
	"Accounts/Cashier",
	"VetEdge Accounts/Cashier",
	"Accounts Manager",
	"Accounts User",
	"VetEdge Front Desk",
	"Branch Manager",
	"VetEdge Branch Manager",
	*ELEVATED_ROLES,
}
ADMIN = {"VetEdge Administrator", "System Manager"}


MENU_DEFINITIONS = (
	{"section": "Overview", "sectionIcon": "home", "label": "Veterinary Home", "route": "/app/vetedge-home", "icon": "home", "description": "Working branch and daily operations", "roles": ALL_OPERATIONAL_ROLES},
	{"section": "Overview", "sectionIcon": "home", "label": "Executive Dashboard", "route": "/app/vetedge-executive-dashboard", "icon": "dashboard", "description": "Management overview", "roles": {"Branch Manager", "VetEdge Branch Manager", *ELEVATED_ROLES}},
	{"section": "Front Desk", "sectionIcon": "calendar", "label": "Patients", "route": "/app/vetedge-resource-center?resource=patients", "icon": "students", "description": "Patient registration and records", "roles": FRONT_DESK | CLINICAL, "doctype": "Veterinary Patient"},
	{"section": "Front Desk", "sectionIcon": "calendar", "label": "Appointments", "route": "/app/vetedge-resource-center?resource=appointments", "icon": "calendar", "description": "Bookings and appointment records", "roles": FRONT_DESK | CLINICAL, "doctype": "Veterinary Appointment"},
	{"section": "Front Desk", "sectionIcon": "calendar", "label": "Appointment Queue", "route": "/app/veterinary-appointment-queue", "icon": "list", "description": "Today's clinic queue", "roles": FRONT_DESK | CLINICAL},
	{"section": "Front Desk", "sectionIcon": "calendar", "label": "Missed Appointments", "route": "/app/vetedge-resource-center?resource=missed-appointments", "icon": "notification", "description": "Follow-up and resolution", "roles": FRONT_DESK, "doctype": "Veterinary Missed Appointment"},
	{"section": "Clinical", "sectionIcon": "stethoscope", "label": "Consultations", "route": "/app/vetedge-resource-center?resource=consultations", "icon": "stethoscope", "description": "Clinical consultations and history", "roles": CLINICAL, "doctype": "Veterinary Consultation"},
	{"section": "Clinical", "sectionIcon": "stethoscope", "label": "Clinical Dashboard", "route": "/app/vetedge-clinical-dashboard", "icon": "chart", "description": "Clinical activity and outcomes", "roles": CLINICAL},
	{"section": "Clinical", "sectionIcon": "stethoscope", "label": "Laboratory Orders", "route": "/app/vetedge-resource-center?resource=lab-orders", "icon": "assessment", "description": "Requests, results, and review", "roles": LAB, "doctype": "Veterinary Lab Order"},
	{"section": "Clinical", "sectionIcon": "stethoscope", "label": "Vaccinations", "route": "/app/vetedge-resource-center?resource=vaccinations", "icon": "shield", "description": "Vaccination history and due care", "roles": CLINICAL, "doctype": "Veterinary Vaccination Record"},
	{"section": "Hospital & Services", "sectionIcon": "building", "label": "Hospitalisations", "route": "/app/veterinary-hospitalisation", "icon": "building", "description": "Admissions, care, and discharge", "roles": CLINICAL, "doctype": "Veterinary Hospitalisation"},
	{"section": "Hospital & Services", "sectionIcon": "building", "label": "Grooming", "route": "/app/vetedge-resource-center?resource=grooming", "icon": "scissors", "description": "Grooming bookings and sessions", "roles": SERVICES, "doctype": "Pet Grooming Appointment"},
	{"section": "Hospital & Services", "sectionIcon": "building", "label": "Boarding", "route": "/app/vetedge-resource-center?resource=boarding", "icon": "hotel", "description": "Boarding bookings and stays", "roles": SERVICES, "doctype": "Pet Boarding Booking"},
	{"section": "Hospital & Services", "sectionIcon": "building", "label": "Kennels", "route": "/app/vetedge-resource-center?resource=kennels", "icon": "layers", "description": "Kennels and care locations", "roles": SERVICES | CLINICAL, "doctype": "Kennel"},
	{"section": "Pharmacy & Stock", "sectionIcon": "stock", "label": "Stock Expiry Monitor", "route": "/app/stock-expiry-monitor", "icon": "stock", "description": "Expiry risk and stock action", "roles": PHARMACY},
	{"section": "Pharmacy & Stock", "sectionIcon": "stock", "label": "Inventory Dashboard", "route": "/app/vetedge-inventory-dispensary-dashboard", "icon": "dashboard", "description": "Dispensary and inventory activity", "roles": PHARMACY},
	{"section": "Billing & Finance", "sectionIcon": "money", "label": "Financial Dashboard", "route": "/app/veterinary-financial-dashboard", "icon": "chart", "description": "Revenue, receivables, and collections", "roles": FINANCE},
	{"section": "Billing & Finance", "sectionIcon": "money", "label": "Sales Invoices", "route": "/app/sales-invoice", "icon": "file-text", "description": "ERPNext accounting invoices", "roles": FINANCE, "doctype": "Sales Invoice", "native": True},
	{"section": "Billing & Finance", "sectionIcon": "money", "label": "Payment Entries", "route": "/app/payment-entry", "icon": "money", "description": "ERPNext payment allocation", "roles": FINANCE, "doctype": "Payment Entry", "native": True},
	{"section": "Administration", "sectionIcon": "settings", "label": "Branches", "route": "/app/branch", "icon": "building", "description": "Company and operational defaults", "roles": ADMIN, "doctype": "Branch", "native": True},
	{"section": "Administration", "sectionIcon": "settings", "label": "Veterinary Settings", "route": "/app/veterinary-settings", "icon": "settings", "description": "Product workflow and billing controls", "roles": ADMIN, "doctype": "Veterinary Settings", "native": True},
	{"section": "Administration", "sectionIcon": "settings", "label": "Role Bundles", "route": "/app/veterinary-role-bundle", "icon": "shield", "description": "Role-based user access", "roles": ADMIN, "doctype": "Veterinary Role Bundle", "native": True},
)

MODULE_DEFINITIONS = (
	{"eyebrow": "Front desk", "title": "Register and book", "description": "Find a patient, create the patient and owner where necessary, and book an appointment in the working branch.", "action": "Open appointments", "route": "/app/vetedge-resource-center?resource=appointments", "roles": FRONT_DESK | CLINICAL},
	{"eyebrow": "Clinical care", "title": "Run consultations", "description": "Review active consultations, laboratory requests, vaccinations, treatment plans, and medical history.", "action": "Open consultations", "route": "/app/vetedge-resource-center?resource=consultations", "roles": CLINICAL},
	{"eyebrow": "Laboratory", "title": "Process laboratory orders", "description": "Track test requests, results, review state, billing status, and patient follow-up.", "action": "Open laboratory", "route": "/app/vetedge-resource-center?resource=lab-orders", "roles": LAB},
	{"eyebrow": "Pharmacy and stock", "title": "Protect dispensary stock", "description": "Review expiry exposure and branch inventory activity before dispensing.", "action": "Open stock monitor", "route": "/app/stock-expiry-monitor", "roles": PHARMACY},
	{"eyebrow": "Hospital and services", "title": "Coordinate care services", "description": "Manage hospitalisation, grooming, boarding, kennels, and service handovers.", "action": "Open service bookings", "route": "/app/vetedge-resource-center?resource=boarding", "roles": SERVICES | CLINICAL},
	{"eyebrow": "Billing and collections", "title": "Review financial operations", "description": "Track invoices, payments, receivables, and branch-level financial performance using ERPNext accounting truth.", "action": "Open financial dashboard", "route": "/app/veterinary-financial-dashboard", "roles": FINANCE},
	{"eyebrow": "Administration", "title": "Configure Veterinary operations", "description": "Maintain branches, working defaults, settings, and role bundles for each user group.", "action": "Open Veterinary Settings", "route": "/app/veterinary-settings", "roles": ADMIN, "native": True},
)


def _require_login() -> None:
	if frappe.session.user == "Guest" or not is_internal_staff_user(frappe.session.user):
		frappe.throw(_("Veterinary Desk access is required."), frappe.PermissionError)


def _visible(definition: dict, roles: set[str]) -> bool:
	if roles.intersection(ELEVATED_ROLES):
		return True
	if not roles.intersection(definition.get("roles") or set()):
		return False
	doctype = definition.get("doctype")
	return not doctype or bool(frappe.has_permission(doctype, "read"))


def _public_item(definition: dict) -> dict:
	return {key: value for key, value in definition.items() if key not in {"roles", "doctype"}}


def _branch_field(meta) -> str:
	for fieldname in ("branch", "service_branch", "default_branch", "care_branch"):
		if meta.has_field(fieldname):
			return fieldname
	return ""


def _permission_aware_count(
	doctype: str,
	*,
	branch: str = "",
	company: str = "",
	filters: dict | None = None,
) -> int:
	if not frappe.db.exists("DocType", doctype) or not frappe.has_permission(doctype, "read"):
		return 0
	meta = frappe.get_meta(doctype)
	resolved = dict(filters or {})
	branch_field = _branch_field(meta)
	if branch and branch_field:
		resolved[branch_field] = branch
	if company and meta.has_field("company"):
		resolved["company"] = company
	rows = frappe.get_list(
		doctype,
		fields=[{"COUNT": "*", "as": "total"}],
		filters=resolved,
		page_length=1,
	)
	return int((rows[0] or {}).get("total") or 0) if rows else 0


@frappe.whitelist()
def get_home_context() -> dict:
	_require_login()
	roles = get_user_roles(frappe.session.user)
	branch_context = get_active_veterinary_branch_context()
	current = branch_context.get("current_branch") or {}
	branch = current.get("name") or ""
	company = current.get("company") or branch_context.get("active_company") or ""
	full_name = frappe.db.get_value("User", frappe.session.user, "full_name") or frappe.session.user

	menu_items = [_public_item(item) for item in MENU_DEFINITIONS if _visible(item, roles)]
	modules = [_public_item(item) for item in MODULE_DEFINITIONS if _visible(item, roles)]
	today_start = f"{nowdate()} 00:00:00"
	today_end = f"{nowdate()} 23:59:59"

	return {
		"product": "VetEdge",
		"tenant_name": company,
		"user": {"name": frappe.session.user, "full_name": full_name, "roles": sorted(roles)},
		"current_branch": current or None,
		"allowed_branches": branch_context.get("configured_branches") or [],
		"active_branch": branch,
		"active_company": company,
		"active_label": branch_context.get("active_label"),
		"active_defaults": branch_context.get("active_defaults") or {},
		"can_switch_branch": branch_context.get("can_switch_branch"),
		"requires_branch_selection": branch_context.get("requires_branch_selection"),
		"unconfigured_branch_count": branch_context.get("unconfigured_branch_count") or 0,
		"menu_items": menu_items,
		"modules": modules,
		"counts": {
			"patients": _permission_aware_count("Veterinary Patient", branch=branch, company=company, filters={"status": ["!=", "Deceased"]}),
			"today_appointments": _permission_aware_count("Veterinary Appointment", branch=branch, company=company, filters={"appointment_datetime": ["between", [today_start, today_end]], "status": ["not in", ["Cancelled", "No Show"]]}),
			"active_consultations": _permission_aware_count("Veterinary Consultation", branch=branch, company=company, filters={"status": ["not in", ["Completed", "Cancelled"]]}),
			"open_lab_orders": _permission_aware_count("Veterinary Lab Order", branch=branch, company=company, filters={"status": ["not in", ["Completed", "Cancelled"]]}),
			"active_hospitalisations": _permission_aware_count("Veterinary Hospitalisation", branch=branch, company=company, filters={"status": ["not in", ["Discharged", "Cancelled"]]}),
			"open_grooming": _permission_aware_count("Pet Grooming Appointment", branch=branch, company=company, filters={"status": ["not in", ["Completed", "Cancelled"]]}),
			"open_boarding": _permission_aware_count("Pet Boarding Booking", branch=branch, company=company, filters={"status": ["not in", ["Completed", "Cancelled"]]}),
			"outstanding_invoices": _permission_aware_count("Sales Invoice", branch=branch, company=company, filters={"docstatus": 1, "outstanding_amount": [">", 0]}),
		},
		"generated_at": datetime.now().isoformat(),
	}
