from __future__ import annotations

from collections.abc import Iterable

import frappe
from frappe import _
from frappe.utils import cint, nowdate

from vetedge.coreedge_adapter import get_current_vetedge_branch
from vetedge.services.permissions import (
	ROLE_ACCOUNTS_CASHIER,
	ROLE_ACCOUNTS_MANAGER,
	ROLE_ACCOUNTS_USER,
	ROLE_BRANCH_MANAGER,
	ROLE_DISPENSARY_USER,
	ROLE_LAB_TECHNICIAN,
	ROLE_SYSTEM_MANAGER,
	ROLE_VETEDGE_ADMINISTRATOR,
	ROLE_VETEDGE_DOCTOR,
	ROLE_VETEDGE_FRONT_DESK,
	ROLE_VETEDGE_GROOMER,
	ROLE_VETEDGE_NURSE,
	ROLE_VETERINARY_NURSE,
	can_access_branch_data,
	get_assigned_branches,
	get_user_roles,
	get_veterinary_settings_flag,
	is_internal_staff_user,
	user_has_global_branch_access,
)

HOME_REFRESH_SECONDS = 30
GENERIC_ACCOUNTS_ROLES = {ROLE_ACCOUNTS_MANAGER, ROLE_ACCOUNTS_USER}

PERSONA_DEFINITIONS = (
	{
		"key": "administrator",
		"label": _("Administrator"),
		"roles": {ROLE_SYSTEM_MANAGER, ROLE_VETEDGE_ADMINISTRATOR},
	},
	{
		"key": "branch-manager",
		"label": _("Branch Manager"),
		"roles": {ROLE_BRANCH_MANAGER, "VetEdge Branch Manager"},
	},
	{
		"key": "doctor",
		"label": _("Veterinary Doctor"),
		"roles": {ROLE_VETEDGE_DOCTOR},
	},
	{
		"key": "front-desk",
		"label": _("Front Desk"),
		"roles": {ROLE_VETEDGE_FRONT_DESK},
	},
	{
		"key": "accounts",
		"label": _("Accounts / Cashier"),
		"roles": {ROLE_ACCOUNTS_CASHIER, "VetEdge Accounts/Cashier"},
	},
	{
		"key": "lab",
		"label": _("Laboratory"),
		"roles": {ROLE_LAB_TECHNICIAN, "VetEdge Lab Technician"},
	},
	{
		"key": "nurse",
		"label": _("Veterinary Nurse"),
		"roles": {ROLE_VETEDGE_NURSE, ROLE_VETERINARY_NURSE},
	},
	{
		"key": "dispensary",
		"label": _("Dispensary"),
		"roles": {ROLE_DISPENSARY_USER, "VetEdge Dispensary User"},
	},
	{
		"key": "groomer",
		"label": _("Grooming"),
		"roles": {ROLE_VETEDGE_GROOMER},
	},
)

ACTION_DEFINITIONS = {
	"administrator": (
		("Executive Dashboard", "/desk/vetedge-executive-dashboard", "dashboard", None, "read"),
		("Veterinary Administration", "/desk/vetedge-administration", "settings", None, "read"),
		("Veterinary Settings", "/desk/veterinary-settings-center", "settings", "Veterinary Settings", "read"),
		("Resource Center", "/desk/vetedge-resource-center", "folder", "Veterinary Patient", "read"),
		("Training Centre", "/desk/veterinary-training-centre", "education", None, "read"),
	),
	"branch-manager": (
		("Executive Dashboard", "/desk/vetedge-executive-dashboard", "dashboard", None, "read"),
		("Front Desk Action Centre", "/desk/vetedge-front-desk-action-center", "calendar", "Veterinary Appointment", "read"),
		("Clinical Workspace", "/desk/vetedge-clinical-workspace", "clipboard", "Veterinary Consultation", "read"),
		("Hospitalisation Operations", "/desk/vetedge-hospitalisation-operations", "heart", "Veterinary Hospitalisation", "read"),
		("Stock Expiry Monitor", "/desk/stock-expiry-monitor", "stock", "Item", "read"),
	),
	"doctor": (
		("Start / Continue Consultation", "/desk/vetedge-clinical-workspace", "clipboard", "Veterinary Consultation", "read"),
		("Find Patient", "/desk/vetedge-resource-center?resource=patients", "users", "Veterinary Patient", "read"),
		("Medical & Lab Work", "/desk/vetedge-resource-center?resource=lab-orders", "assessment", "Veterinary Lab Order", "read"),
		("Vaccinations", "/desk/vetedge-resource-center?resource=vaccinations", "heart", "Veterinary Vaccination Record", "read"),
		("Hospitalised Patients", "/desk/vetedge-hospitalisation-operations", "home", "Veterinary Hospitalisation", "read"),
	),
	"front-desk": (
		("Register / Find Patient", "/desk/vetedge-resource-center?resource=patients", "users", "Veterinary Patient", "read"),
		("New Appointment", "/desk/vetedge-resource-center?resource=appointments&new=1", "calendar", "Veterinary Appointment", "create"),
		("Appointment Queue", "/desk/vetedge-front-desk-action-center?tab=queue", "list", "Veterinary Appointment", "read"),
		("Guest Booking Requests", "/desk/vetedge-front-desk-action-center?tab=guest", "globe", "Veterinary Guest Booking Request", "read"),
		("Missed Appointments", "/desk/vetedge-front-desk-action-center?tab=missed", "alert", "Veterinary Missed Appointment", "read"),
	),
	"accounts": (
		("Sales Invoices", "/desk/sales-invoice", "invoice", "Sales Invoice", "read"),
		("Payments", "/desk/payment-entry", "payment", "Payment Entry", "read"),
		("Patient Records", "/desk/vetedge-resource-center?resource=patients", "users", "Veterinary Patient", "read"),
	),
	"lab": (
		("Pending Lab Orders", "/desk/vetedge-resource-center?resource=lab-orders", "assessment", "Veterinary Lab Order", "read"),
	),
	"nurse": (
		("Patient Records", "/desk/vetedge-resource-center?resource=patients", "users", "Veterinary Patient", "read"),
		("Clinical Workspace", "/desk/vetedge-clinical-workspace", "clipboard", "Veterinary Consultation", "read"),
		("Lab Orders", "/desk/vetedge-resource-center?resource=lab-orders", "assessment", "Veterinary Lab Order", "read"),
		("Vaccinations", "/desk/vetedge-resource-center?resource=vaccinations", "heart", "Veterinary Vaccination Record", "read"),
		("Hospitalised Patients", "/desk/vetedge-hospitalisation-operations", "home", "Veterinary Hospitalisation", "read"),
	),
	"dispensary": (
		("Pending Dispensary Work", "/desk/vetedge-clinical-workspace", "package", "Veterinary Consultation", "read"),
		("Stock Expiry Monitor", "/desk/stock-expiry-monitor", "stock", "Item", "read"),
	),
	"groomer": (
		("Grooming Appointments", "/desk/vetedge-resource-center?resource=grooming", "calendar", "Pet Grooming Appointment", "read"),
		("Grooming Sessions", "/desk/vetedge-service-operations?resource=grooming-sessions", "scissors", "Pet Grooming Session", "read"),
	),
}

# Keep operational Home composition aligned with existing Veterinary Settings.
# Routes without a feature mapping remain governed by role/DocType permissions.
FEATURE_ROUTE_FLAGS = (
	("/desk/vetedge-front-desk-action-center", "enable_appointments"),
	("/desk/vetedge-resource-center?resource=appointments", "enable_appointments"),
	("/desk/vetedge-clinical-workspace", "enable_consultations"),
	("/desk/vetedge-resource-center?resource=lab-orders", "enable_vetedge"),
	("/desk/vetedge-resource-center?resource=vaccinations", "enable_vaccination"),
	("/desk/vetedge-hospitalisation-operations", "enable_veterinary_hospitalisation"),
	("/desk/stock-expiry-monitor", "enable_stock_expiry_monitor"),
	("/desk/vetedge-resource-center?resource=grooming", "enable_grooming"),
	("/desk/vetedge-service-operations?resource=grooming-sessions", "enable_grooming"),
)


def _require_access() -> str:
	user = getattr(frappe.session, "user", None)
	if not user or user == "Guest" or not is_internal_staff_user(user):
		frappe.throw(_("Veterinary Home is available to authorised clinic staff only."), frappe.PermissionError)
	return user


def _existing_doctype(doctype: str) -> bool:
	return bool(doctype and frappe.db.exists("DocType", doctype))


def _feature_enabled(fieldname: str) -> bool:
	# Existing installations may pre-date a field. In that case preserve current
	# compatibility rather than removing a capability solely because Home is new.
	if fieldname != "enable_vetedge" and not get_veterinary_settings_flag("enable_vetedge", default=True):
		return False
	return get_veterinary_settings_flag(fieldname, default=True)


def _route_feature_enabled(route: str) -> bool:
	for prefix, fieldname in FEATURE_ROUTE_FLAGS:
		if route.startswith(prefix):
			return _feature_enabled(fieldname)
	return True


def _matched_personas(roles: set[str]) -> list[dict]:
	personas = [
		{"key": definition["key"], "label": definition["label"]}
		for definition in PERSONA_DEFINITIONS
		if roles & definition["roles"]
	]

	# VetEdge starter bundles deliberately add generic ERPNext support roles such
	# as Accounts User to Doctors, Front Desk and Administrators. Those generic
	# roles must not silently turn a clinical/front-desk Home into Accounts.
	if not personas and roles & GENERIC_ACCOUNTS_ROLES:
		personas.append({"key": "accounts", "label": _("Accounts / Cashier")})

	return personas


def _current_branch(user: str) -> tuple[str, list[str], bool]:
	try:
		branch = str(get_current_vetedge_branch() or "").strip()
	except Exception:
		branch = ""
	if branch.lower() in {"all", "all branches"}:
		branch = ""
	if branch:
		can_access_branch_data(user, branch, raise_exception=True)
	assigned = list(dict.fromkeys(get_assigned_branches(user) or []))
	return branch, assigned, user_has_global_branch_access(user)


def _branch_field(meta) -> str:
	for fieldname in ("service_branch", "branch", "default_branch", "reporting_branch"):
		if meta.has_field(fieldname):
			return fieldname
	return ""


def _branch_filters(doctype: str, branch: str, assigned: list[str], global_access: bool) -> dict:
	if not _existing_doctype(doctype):
		return {}
	meta = frappe.get_meta(doctype)
	fieldname = _branch_field(meta)
	if not fieldname:
		return {}
	if branch:
		return {fieldname: branch}
	if assigned and not global_access:
		return {fieldname: ["in", assigned]}
	return {}


def _permission_count(doctype: str, filters: dict | None = None) -> int | None:
	if not _existing_doctype(doctype) or not frappe.has_permission(doctype, "read"):
		return None
	try:
		rows = frappe.get_list(
			doctype,
			fields=[{"COUNT": "*", "as": "total"}],
			filters=filters or {},
			limit_page_length=1,
		)
		return cint(rows[0].get("total")) if rows else 0
	except frappe.PermissionError:
		return None


def _with(filters: dict, **values) -> dict:
	result = dict(filters)
	for key, value in values.items():
		if value is not None:
			result[key] = value
	return result


def _today_range() -> list:
	today = nowdate()
	return ["between", [f"{today} 00:00:00", f"{today} 23:59:59"]]


def _metric(
	key: str,
	label: str,
	value: int | None,
	helper: str,
	route: str,
	tone: str = "neutral",
) -> dict | None:
	if value is None:
		return None
	return {
		"key": key,
		"label": label,
		"value": value,
		"helper": helper,
		"route": route,
		"tone": tone,
	}


def _build_metrics(
	user: str,
	persona_keys: set[str],
	branch: str,
	assigned: list[str],
	global_access: bool,
) -> list[dict]:
	metrics: list[dict | None] = []

	appointment_filters = _branch_filters("Veterinary Appointment", branch, assigned, global_access)
	consultation_filters = _branch_filters("Veterinary Consultation", branch, assigned, global_access)
	lab_filters = _branch_filters("Veterinary Lab Order", branch, assigned, global_access)
	missed_filters = _branch_filters("Veterinary Missed Appointment", branch, assigned, global_access)

	appointment_personas = {"administrator", "branch-manager", "doctor", "front-desk", "nurse"}
	if (
		persona_keys & appointment_personas
		and _feature_enabled("enable_appointments")
		and _existing_doctype("Veterinary Appointment")
	):
		meta = frappe.get_meta("Veterinary Appointment")
		today_filters = dict(appointment_filters)
		waiting_filters = _with(appointment_filters, status=["in", ["Confirmed", "Checked In"]])

		if "doctor" in persona_keys and meta.has_field("practitioner"):
			today_filters["practitioner"] = user
			waiting_filters["practitioner"] = user

		if meta.has_field("appointment_datetime"):
			today_filters["appointment_datetime"] = _today_range()
			metrics.append(
				_metric(
					"today-appointments",
					_("My Appointments Today") if "doctor" in persona_keys else _("Today's Appointments"),
					_permission_count("Veterinary Appointment", today_filters),
					_("Visible in your current access scope"),
					"/desk/vetedge-resource-center?resource=appointments",
				)
			)

		metrics.append(
			_metric(
				"waiting-appointments",
				_("Waiting for Me") if "doctor" in persona_keys else _("Waiting / Checked In"),
				_permission_count("Veterinary Appointment", waiting_filters),
				_("Patients requiring operational attention"),
				"/desk/vetedge-front-desk-action-center?tab=queue",
				"warning",
			)
		)

	consultation_personas = {"administrator", "branch-manager", "doctor", "nurse", "dispensary"}
	if (
		persona_keys & consultation_personas
		and _feature_enabled("enable_consultations")
		and _existing_doctype("Veterinary Consultation")
	):
		meta = frappe.get_meta("Veterinary Consultation")
		active_filters = _with(consultation_filters, status=["not in", ["Completed", "Cancelled"]])
		completed_filters = _with(consultation_filters, status="Completed")

		if "doctor" in persona_keys and meta.has_field("consulting_practitioner"):
			active_filters["consulting_practitioner"] = user
			completed_filters["consulting_practitioner"] = user

		if "dispensary" not in persona_keys or persona_keys & {"administrator", "branch-manager", "doctor", "nurse"}:
			metrics.append(
				_metric(
					"active-consultations",
					_("My Active Consultations") if "doctor" in persona_keys else _("Active Consultations"),
					_permission_count("Veterinary Consultation", active_filters),
					_("Not completed or cancelled"),
					"/desk/vetedge-clinical-workspace",
					"primary",
				)
			)

			if meta.has_field("consultation_datetime"):
				completed_filters["consultation_datetime"] = _today_range()
				metrics.append(
					_metric(
						"completed-today",
						_("Completed Today"),
						_permission_count("Veterinary Consultation", completed_filters),
						_("Completed consultations today"),
						"/desk/vetedge-clinical-workspace",
						"success",
					)
				)

		if (
			"dispensary" in persona_keys
			and _feature_enabled("enable_dispensary_flow")
			and meta.has_field("dispensary_status")
		):
			metrics.append(
				_metric(
					"pending-dispensary",
					_("Pending Dispensary"),
					_permission_count(
						"Veterinary Consultation",
						_with(consultation_filters, dispensary_status="Pending Dispensary"),
					),
					_("Consultations awaiting fulfilment"),
					"/desk/vetedge-clinical-workspace",
					"warning",
				)
			)

	if (
		_feature_enabled("enable_vetedge")
		and _existing_doctype("Veterinary Lab Order")
		and frappe.get_meta("Veterinary Lab Order").has_field("status")
	):
		if persona_keys & {"lab"}:
			metrics.append(
				_metric(
					"lab-pending",
					_("Pending Lab Work"),
					_permission_count(
						"Veterinary Lab Order",
						_with(
							lab_filters,
							status=[
								"in",
								["Ordered", "Sample Collected", "Sent to Lab", "In Progress", "Result Pending"],
							],
						),
					),
					_("Laboratory orders still requiring processing"),
					"/desk/vetedge-resource-center?resource=lab-orders",
					"warning",
				)
			)
		if persona_keys & {"administrator", "branch-manager", "doctor", "nurse"}:
			metrics.append(
				_metric(
					"lab-review",
					_("Lab Results to Review"),
					_permission_count(
						"Veterinary Lab Order",
						_with(lab_filters, status=["in", ["Result Entered", "Awaiting Review"]]),
					),
					_("Results ready for clinical review"),
					"/desk/vetedge-resource-center?resource=lab-orders",
					"warning",
				)
			)

	if (
		persona_keys & {"administrator", "branch-manager", "front-desk"}
		and _feature_enabled("enable_appointments")
		and _existing_doctype("Veterinary Missed Appointment")
	):
		meta = frappe.get_meta("Veterinary Missed Appointment")
		filters = dict(missed_filters)
		if meta.has_field("resolved"):
			filters["resolved"] = 0
		metrics.append(
			_metric(
				"missed-follow-up",
				_("Missed Follow-up"),
				_permission_count("Veterinary Missed Appointment", filters),
				_("Unresolved missed appointments"),
				"/desk/vetedge-front-desk-action-center?tab=missed",
				"danger",
			)
		)

	if persona_keys & {"accounts", "branch-manager", "administrator"} and _existing_doctype("Sales Invoice"):
		meta = frappe.get_meta("Sales Invoice")
		filters = _branch_filters("Sales Invoice", branch, assigned, global_access)
		filters["docstatus"] = 1
		if meta.has_field("outstanding_amount"):
			filters["outstanding_amount"] = [">", 0]
		metrics.append(
			_metric(
				"outstanding-invoices",
				_("Outstanding Invoices"),
				_permission_count("Sales Invoice", filters),
				_("Submitted invoices with balance due"),
				"/desk/sales-invoice",
				"warning",
			)
		)

	return [metric for metric in metrics if metric is not None]


def _can_use_action(doctype: str | None, permission_type: str) -> bool:
	if not doctype:
		return True
	if not _existing_doctype(doctype):
		return False
	return bool(frappe.has_permission(doctype, permission_type))


def _build_actions(personas: Iterable[dict]) -> list[dict]:
	result: list[dict] = []
	seen_routes: set[str] = set()
	for persona in personas:
		for label, route, icon, doctype, permission_type in ACTION_DEFINITIONS.get(persona["key"], ()):
			if route in seen_routes or not _route_feature_enabled(route) or not _can_use_action(doctype, permission_type):
				continue
			seen_routes.add(route)
			result.append(
				{
					"key": f"{persona['key']}:{route}",
					"group": persona["label"],
					"label": _(label),
					"route": route,
					"icon": icon,
				}
			)
	return result


def _build_attention(metrics: list[dict]) -> list[dict]:
	attention = []
	priority = {
		"missed-follow-up": (90, _("Follow up missed appointments")),
		"waiting-appointments": (80, _("Patients are waiting for service")),
		"lab-review": (70, _("Laboratory results are ready for review")),
		"lab-pending": (68, _("Laboratory orders still require processing")),
		"pending-dispensary": (65, _("Dispensary fulfilment is pending")),
		"outstanding-invoices": (60, _("Outstanding invoices need collection follow-up")),
		"active-consultations": (50, _("Consultations are still active")),
	}
	for metric in metrics:
		value = cint(metric.get("value"))
		if value <= 0 or metric.get("key") not in priority:
			continue
		rank, message = priority[metric["key"]]
		attention.append(
			{
				"key": metric["key"],
				"priority": rank,
				"title": metric["label"],
				"message": message,
				"count": value,
				"route": metric["route"],
				"tone": metric.get("tone") or "warning",
			}
		)
	return sorted(attention, key=lambda row: (-row["priority"], row["title"]))[:6]


@frappe.whitelist()
def get_home_payload() -> dict:
	user = _require_access()
	roles = get_user_roles(user)
	personas = _matched_personas(roles)
	if not personas:
		frappe.throw(_("No Veterinary operational role is assigned to this user."), frappe.PermissionError)

	branch, assigned_branches, global_access = _current_branch(user)
	persona_keys = {persona["key"] for persona in personas}
	metrics = _build_metrics(user, persona_keys, branch, assigned_branches, global_access)

	return {
		"user": user,
		"primary_persona": personas[0],
		"personas": personas,
		"context": {
			"branch": branch,
			"branch_label": branch or _("All permitted branches"),
			"assigned_branches": assigned_branches,
			"global_branch_access": global_access,
			"date": nowdate(),
		},
		"metrics": metrics,
		"attention": _build_attention(metrics),
		"quick_actions": _build_actions(personas),
		"refresh_seconds": HOME_REFRESH_SECONDS,
	}
