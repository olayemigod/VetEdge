from __future__ import annotations

from collections.abc import Iterable

import frappe
from frappe import _
from frappe.utils import cint, getdate, nowdate

from vetedge.coreedge_adapter import get_current_vetedge_branch, get_current_vetedge_company
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
HOME_PAGE_LENGTH = 25
HOME_PAGE_LENGTH_MAX = 100
ALL_BRANCHES_KEY = "__all__"
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

DRILLDOWN_FIELD_CANDIDATES = {
	"Veterinary Appointment": (
		"patient",
		"appointment_datetime",
		"status",
		"practitioner",
		"service_branch",
		"branch",
	),
	"Veterinary Consultation": (
		"patient",
		"consultation_datetime",
		"status",
		"consulting_practitioner",
		"service_branch",
		"branch",
	),
	"Veterinary Lab Order": (
		"patient",
		"consultation",
		"status",
		"ordered_on",
		"sample_collected_on",
		"service_branch",
		"branch",
	),
	"Veterinary Missed Appointment": (
		"appointment",
		"patient",
		"status",
		"missed_on",
		"resolved",
		"service_branch",
		"branch",
	),
	"Pet Grooming Appointment": (
		"patient",
		"pet",
		"scheduled_datetime",
		"status",
		"groomer",
		"service_branch",
		"branch",
	),
	"Sales Invoice": (
		"customer",
		"posting_date",
		"status",
		"grand_total",
		"outstanding_amount",
		"branch",
	),
}

DRILLDOWN_ORDER_CANDIDATES = {
	"Veterinary Appointment": ("appointment_datetime", "modified"),
	"Veterinary Consultation": ("consultation_datetime", "modified"),
	"Veterinary Lab Order": ("ordered_on", "modified"),
	"Veterinary Missed Appointment": ("missed_on", "modified"),
	"Pet Grooming Appointment": ("scheduled_datetime", "modified"),
	"Sales Invoice": ("posting_date", "modified"),
}


def _require_access() -> str:
	user = getattr(frappe.session, "user", None)
	if not user or user == "Guest" or not is_internal_staff_user(user):
		frappe.throw(_("Veterinary Home is available to authorised clinic staff only."), frappe.PermissionError)
	return user


def _existing_doctype(doctype: str) -> bool:
	return bool(doctype and frappe.db.exists("DocType", doctype))


def _feature_enabled(fieldname: str) -> bool:
	# Existing installations may pre-date a field. Preserve compatibility when
	# the switch itself is absent, but respect an explicitly disabled master.
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


def _resolve_operational_date(value: str | None) -> str:
	if not value:
		return nowdate()
	try:
		return str(getdate(value))
	except Exception:
		frappe.throw(_("Select a valid operational date."), frappe.ValidationError)


def _current_branch(
	user: str,
	requested_branch: str | None = None,
) -> tuple[str, list[str], bool]:
	assigned = list(dict.fromkeys(get_assigned_branches(user) or []))
	global_access = user_has_global_branch_access(user)

	if requested_branch == ALL_BRANCHES_KEY:
		return "", assigned, global_access

	branch = str(requested_branch or "").strip()
	if not branch:
		try:
			branch = str(get_current_vetedge_branch() or "").strip()
		except Exception:
			branch = ""
	if not branch:
		try:
			branch = str(frappe.defaults.get_user_default("branch") or "").strip()
		except Exception:
			branch = ""
	if not branch and len(assigned) == 1:
		branch = assigned[0]

	if branch.lower() in {"all", "all branches"}:
		branch = ""

	if branch:
		can_access_branch_data(user, branch, raise_exception=True)

	return branch, assigned, global_access


def _branch_options(
	user: str,
	assigned: list[str],
	global_access: bool,
	current_branch: str,
) -> list[dict]:
	options = [{"value": ALL_BRANCHES_KEY, "label": _("All permitted branches"), "company": ""}]
	if not _existing_doctype("Branch"):
		return options + [{"value": name, "label": name, "company": ""} for name in assigned if name]

	meta = frappe.get_meta("Branch")
	fields = ["name"]
	if meta.has_field("branch"):
		fields.append("branch")
	if meta.has_field("company"):
		fields.append("company")

	filters: dict = {}
	if assigned and not global_access:
		filters["name"] = ["in", assigned]
	else:
		try:
			company = str(get_current_vetedge_company() or "").strip()
		except Exception:
			company = ""
		if company and meta.has_field("company"):
			filters["company"] = company

	rows = []
	if frappe.has_permission("Branch", "read"):
		try:
			rows = frappe.get_list(
				"Branch",
				fields=fields,
				filters=filters,
				order_by="name asc",
				limit_page_length=500,
			)
		except frappe.PermissionError:
			rows = []

	names_seen = set()
	for row in rows:
		name = row.get("name")
		if not name or name in names_seen:
			continue
		names_seen.add(name)
		options.append(
			{
				"value": name,
				"label": row.get("branch") or name,
				"company": row.get("company") or "",
			}
		)

	for name in [*assigned, current_branch]:
		if name and name not in names_seen:
			names_seen.add(name)
			options.append({"value": name, "label": name, "company": ""})

	if len(options) == 2 and options[1]["value"] != ALL_BRANCHES_KEY:
		return options[1:]
	return options


def _branch_field(meta) -> str:
	for fieldname in ("service_branch", "branch", "default_branch", "reporting_branch"):
		if meta.has_field(fieldname):
			return fieldname
	return ""


def _branch_filters(
	doctype: str,
	branch: str,
	assigned: list[str],
	global_access: bool,
) -> dict | None:
	if not _existing_doctype(doctype):
		return {}
	meta = frappe.get_meta(doctype)
	fieldname = _branch_field(meta)
	if not fieldname:
		# Do not present a company-wide number under an explicit/restricted branch
		# label when the source DocType cannot be branch-filtered.
		if branch or (assigned and not global_access):
			return None
		return {}
	if branch:
		return {fieldname: branch}
	if assigned and not global_access:
		return {fieldname: ["in", assigned]}
	return {}


def _permission_count(doctype: str, filters: dict | None = None) -> int | None:
	if filters is None or not _existing_doctype(doctype) or not frappe.has_permission(doctype, "read"):
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


def _with(filters: dict | None, **values) -> dict | None:
	if filters is None:
		return None
	result = dict(filters)
	for key, value in values.items():
		if value is not None:
			result[key] = value
	return result


def _date_range(operational_date: str) -> list:
	return [
		"between",
		[f"{operational_date} 00:00:00", f"{operational_date} 23:59:59"],
	]


def _date_metric_label(today_label: str, dated_label: str, operational_date: str) -> str:
	return _(today_label) if operational_date == nowdate() else _(dated_label).format(date=operational_date)


def _drilldown_fields(doctype: str) -> tuple[list[str], list[dict]]:
	if not _existing_doctype(doctype):
		return ["name"], [{"fieldname": "name", "label": doctype}]
	meta = frappe.get_meta(doctype)
	fields = ["name"]
	columns = [{"fieldname": "name", "label": meta.name}]
	for fieldname in DRILLDOWN_FIELD_CANDIDATES.get(doctype, ()):
		if fieldname in fields or not meta.has_field(fieldname):
			continue
		field = meta.get_field(fieldname)
		fields.append(fieldname)
		columns.append(
			{
				"fieldname": fieldname,
				"label": field.label or fieldname.replace("_", " ").title(),
				"fieldtype": field.fieldtype or "Data",
			}
		)
	return fields, columns


def _drilldown_order_by(doctype: str) -> str:
	if not _existing_doctype(doctype):
		return "modified desc"
	meta = frappe.get_meta(doctype)
	for fieldname in DRILLDOWN_ORDER_CANDIDATES.get(doctype, ("modified",)):
		if fieldname == "modified" or meta.has_field(fieldname):
			return f"{fieldname} desc"
	return "modified desc"


def _metric(
	key: str,
	label: str,
	value: int | None,
	helper: str,
	route: str,
	*,
	doctype: str,
	filters: dict | None,
	date_scope: str,
	scope_label: str,
	tone: str = "neutral",
) -> dict | None:
	if value is None or filters is None:
		return None
	return {
		"key": key,
		"label": label,
		"value": value,
		"helper": helper,
		"route": route,
		"tone": tone,
		"date_scope": date_scope,
		"scope_label": scope_label,
		"drilldown_available": True,
		"_query": {
			"doctype": doctype,
			"filters": filters,
			"order_by": _drilldown_order_by(doctype),
		},
	}


def _append_metric(metrics: list[dict | None], metric: dict | None) -> None:
	if metric is not None:
		metrics.append(metric)


def _build_appointment_metrics(
	metrics: list[dict | None],
	user: str,
	persona_keys: set[str],
	filters: dict | None,
	operational_date: str,
) -> None:
	if filters is None or not _feature_enabled("enable_appointments") or not _existing_doctype("Veterinary Appointment"):
		return

	meta = frappe.get_meta("Veterinary Appointment")
	date_filters = dict(filters)
	if meta.has_field("appointment_datetime"):
		date_filters["appointment_datetime"] = _date_range(operational_date)

	broad_personas = {"administrator", "branch-manager", "front-desk", "nurse"}
	if persona_keys & broad_personas:
		label = _date_metric_label("Today's Appointments", "Appointments — {date}", operational_date)
		_append_metric(
			metrics,
			_metric(
				"today-appointments",
				label,
				_permission_count("Veterinary Appointment", date_filters),
				_("Appointments on the selected operational date"),
				"/desk/vetedge-resource-center?resource=appointments",
				doctype="Veterinary Appointment",
				filters=date_filters,
				date_scope="operational_date",
				scope_label=_("Selected operational date"),
			),
		)
		waiting_filters = _with(
			date_filters,
			status=["in", ["Confirmed", "Checked In"]],
		)
		_append_metric(
			metrics,
			_metric(
				"waiting-appointments",
				_date_metric_label("Waiting / Checked In Today", "Waiting / Checked In — {date}", operational_date),
				_permission_count("Veterinary Appointment", waiting_filters),
				_("Confirmed or checked-in appointments on the selected date"),
				"/desk/vetedge-front-desk-action-center?tab=queue",
				doctype="Veterinary Appointment",
				filters=waiting_filters,
				date_scope="operational_date",
				scope_label=_("Selected operational date"),
				tone="warning",
			),
		)

	if "doctor" in persona_keys:
		my_filters = dict(filters)
		if meta.has_field("practitioner"):
			my_filters["practitioner"] = user
		my_date_filters = dict(my_filters)
		if meta.has_field("appointment_datetime"):
			my_date_filters["appointment_datetime"] = _date_range(operational_date)
		_append_metric(
			metrics,
			_metric(
				"my-appointments-today",
				_date_metric_label("My Appointments Today", "My Appointments — {date}", operational_date),
				_permission_count("Veterinary Appointment", my_date_filters),
				_("Appointments assigned to you on the selected date"),
				"/desk/vetedge-resource-center?resource=appointments",
				doctype="Veterinary Appointment",
				filters=my_date_filters,
				date_scope="operational_date",
				scope_label=_("Selected operational date"),
			),
		)
		waiting_for_me_filters = _with(
			my_date_filters,
			status=["in", ["Confirmed", "Checked In"]],
		)
		_append_metric(
			metrics,
			_metric(
				"waiting-for-me",
				_date_metric_label("Waiting for Me Today", "Waiting for Me — {date}", operational_date),
				_permission_count("Veterinary Appointment", waiting_for_me_filters),
				_("Your confirmed or checked-in patients on the selected date"),
				"/desk/vetedge-front-desk-action-center?tab=queue",
				doctype="Veterinary Appointment",
				filters=waiting_for_me_filters,
				date_scope="operational_date",
				scope_label=_("Selected operational date"),
				tone="warning",
			),
		)


def _build_consultation_metrics(
	metrics: list[dict | None],
	user: str,
	persona_keys: set[str],
	filters: dict | None,
	operational_date: str,
) -> None:
	if filters is None or not _feature_enabled("enable_consultations") or not _existing_doctype("Veterinary Consultation"):
		return

	meta = frappe.get_meta("Veterinary Consultation")
	broad_personas = {"administrator", "branch-manager", "nurse"}
	if persona_keys & broad_personas:
		active_filters = _with(filters, status=["not in", ["Completed", "Cancelled"]])
		_append_metric(
			metrics,
			_metric(
				"active-consultations",
				_("Active Consultations"),
				_permission_count("Veterinary Consultation", active_filters),
				_("Current open work; not limited to the selected date"),
				"/desk/vetedge-clinical-workspace",
				doctype="Veterinary Consultation",
				filters=active_filters,
				date_scope="current_open",
				scope_label=_("Current open work"),
				tone="primary",
			),
		)
		if meta.has_field("consultation_datetime"):
			completed_filters = _with(
				filters,
				status="Completed",
				consultation_datetime=_date_range(operational_date),
			)
			_append_metric(
				metrics,
				_metric(
					"completed-today",
					_date_metric_label("Completed Today", "Completed — {date}", operational_date),
					_permission_count("Veterinary Consultation", completed_filters),
					_("Completed consultations on the selected date"),
					"/desk/vetedge-clinical-workspace",
					doctype="Veterinary Consultation",
					filters=completed_filters,
					date_scope="operational_date",
					scope_label=_("Selected operational date"),
					tone="success",
				),
			)

	if "doctor" in persona_keys:
		my_filters = dict(filters)
		if meta.has_field("consulting_practitioner"):
			my_filters["consulting_practitioner"] = user
		my_active_filters = _with(my_filters, status=["not in", ["Completed", "Cancelled"]])
		_append_metric(
			metrics,
			_metric(
				"my-active-consultations",
				_("My Active Consultations"),
				_permission_count("Veterinary Consultation", my_active_filters),
				_("Your current open consultations; not limited to the selected date"),
				"/desk/vetedge-clinical-workspace",
				doctype="Veterinary Consultation",
				filters=my_active_filters,
				date_scope="current_open",
				scope_label=_("Current open work"),
				tone="primary",
			),
		)
		if meta.has_field("consultation_datetime"):
			my_completed_filters = _with(
				my_filters,
				status="Completed",
				consultation_datetime=_date_range(operational_date),
			)
			_append_metric(
				metrics,
				_metric(
					"my-completed-today",
					_date_metric_label("My Completed Today", "My Completed — {date}", operational_date),
					_permission_count("Veterinary Consultation", my_completed_filters),
					_("Your consultations completed on the selected date"),
					"/desk/vetedge-clinical-workspace",
					doctype="Veterinary Consultation",
					filters=my_completed_filters,
					date_scope="operational_date",
					scope_label=_("Selected operational date"),
					tone="success",
				),
			)

	if "dispensary" in persona_keys and _feature_enabled("enable_dispensary_flow") and meta.has_field("dispensary_status"):
		pending_filters = _with(filters, dispensary_status="Pending Dispensary")
		_append_metric(
			metrics,
			_metric(
				"pending-dispensary",
				_("Pending Dispensary"),
				_permission_count("Veterinary Consultation", pending_filters),
				_("Current consultations awaiting fulfilment"),
				"/desk/vetedge-clinical-workspace",
				doctype="Veterinary Consultation",
				filters=pending_filters,
				date_scope="current_open",
				scope_label=_("Current open work"),
				tone="warning",
			),
		)


def _build_metrics(
	user: str,
	persona_keys: set[str],
	branch: str,
	assigned: list[str],
	global_access: bool,
	operational_date: str,
) -> list[dict]:
	metrics: list[dict | None] = []

	appointment_filters = _branch_filters("Veterinary Appointment", branch, assigned, global_access)
	consultation_filters = _branch_filters("Veterinary Consultation", branch, assigned, global_access)
	lab_filters = _branch_filters("Veterinary Lab Order", branch, assigned, global_access)
	missed_filters = _branch_filters("Veterinary Missed Appointment", branch, assigned, global_access)

	_build_appointment_metrics(metrics, user, persona_keys, appointment_filters, operational_date)
	_build_consultation_metrics(metrics, user, persona_keys, consultation_filters, operational_date)

	if (
		lab_filters is not None
		and _feature_enabled("enable_vetedge")
		and _existing_doctype("Veterinary Lab Order")
		and frappe.get_meta("Veterinary Lab Order").has_field("status")
	):
		if persona_keys & {"lab"}:
			pending_filters = _with(
				lab_filters,
				status=[
					"in",
					["Ordered", "Sample Collected", "Sent to Lab", "In Progress", "Result Pending"],
				],
			)
			_append_metric(
				metrics,
				_metric(
					"lab-pending",
					_("Pending Lab Work"),
					_permission_count("Veterinary Lab Order", pending_filters),
					_("Current laboratory orders still requiring processing"),
					"/desk/vetedge-resource-center?resource=lab-orders",
					doctype="Veterinary Lab Order",
					filters=pending_filters,
					date_scope="current_open",
					scope_label=_("Current open work"),
					tone="warning",
				),
			)
		if persona_keys & {"administrator", "branch-manager", "doctor", "nurse"}:
			review_filters = _with(
				lab_filters,
				status=["in", ["Result Entered", "Awaiting Review"]],
			)
			_append_metric(
				metrics,
				_metric(
					"lab-review",
					_("Lab Results to Review"),
					_permission_count("Veterinary Lab Order", review_filters),
					_("Current results ready for clinical review"),
					"/desk/vetedge-resource-center?resource=lab-orders",
					doctype="Veterinary Lab Order",
					filters=review_filters,
					date_scope="current_open",
					scope_label=_("Current open work"),
					tone="warning",
				),
			)

	if "groomer" in persona_keys and _feature_enabled("enable_grooming") and _existing_doctype("Pet Grooming Appointment"):
		meta = frappe.get_meta("Pet Grooming Appointment")
		filters = _branch_filters("Pet Grooming Appointment", branch, assigned, global_access)
		if filters is not None:
			if meta.has_field("groomer"):
				filters["groomer"] = user
			if meta.has_field("scheduled_datetime"):
				filters["scheduled_datetime"] = _date_range(operational_date)
			_append_metric(
				metrics,
				_metric(
					"grooming-today",
					_date_metric_label("My Grooming Appointments Today", "My Grooming Appointments — {date}", operational_date),
					_permission_count("Pet Grooming Appointment", filters),
					_("Grooming appointments assigned to you on the selected date"),
					"/desk/vetedge-resource-center?resource=grooming",
					doctype="Pet Grooming Appointment",
					filters=filters,
					date_scope="operational_date",
					scope_label=_("Selected operational date"),
				),
			)

	if (
		missed_filters is not None
		and persona_keys & {"administrator", "branch-manager", "front-desk"}
		and _feature_enabled("enable_appointments")
		and _existing_doctype("Veterinary Missed Appointment")
	):
		meta = frappe.get_meta("Veterinary Missed Appointment")
		filters = dict(missed_filters)
		if meta.has_field("resolved"):
			filters["resolved"] = 0
		_append_metric(
			metrics,
			_metric(
				"missed-follow-up",
				_("Missed Follow-up"),
				_permission_count("Veterinary Missed Appointment", filters),
				_("Current unresolved missed appointments"),
				"/desk/vetedge-front-desk-action-center?tab=missed",
				doctype="Veterinary Missed Appointment",
				filters=filters,
				date_scope="current_open",
				scope_label=_("Current open work"),
				tone="danger",
			),
		)

	if persona_keys & {"accounts", "branch-manager", "administrator"} and _existing_doctype("Sales Invoice"):
		meta = frappe.get_meta("Sales Invoice")
		filters = _branch_filters("Sales Invoice", branch, assigned, global_access)
		if filters is not None:
			filters["docstatus"] = 1
			if meta.has_field("outstanding_amount"):
				filters["outstanding_amount"] = [">", 0]
			_append_metric(
				metrics,
				_metric(
					"outstanding-invoices",
					_("Outstanding Invoices"),
					_permission_count("Sales Invoice", filters),
					_("Current submitted invoices with balance due"),
					"/desk/sales-invoice",
					doctype="Sales Invoice",
					filters=filters,
					date_scope="current_open",
					scope_label=_("Current open work"),
					tone="warning",
				),
			)

	return [metric for metric in metrics if metric is not None]


def _public_metric(metric: dict) -> dict:
	return {key: value for key, value in metric.items() if not key.startswith("_")}


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
		"waiting-for-me": (85, _("Your patients are waiting for service")),
		"waiting-appointments": (80, _("Patients are waiting for service")),
		"lab-review": (70, _("Laboratory results are ready for review")),
		"lab-pending": (68, _("Laboratory orders still require processing")),
		"pending-dispensary": (65, _("Dispensary fulfilment is pending")),
		"outstanding-invoices": (60, _("Outstanding invoices need collection follow-up")),
		"my-active-consultations": (55, _("You have consultations still in progress")),
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
				"date_scope": metric.get("date_scope"),
				"scope_label": metric.get("scope_label"),
			}
		)
	return sorted(attention, key=lambda row: (-row["priority"], row["title"]))[:6]


def _home_state(
	operational_date: str | None = None,
	branch: str | None = None,
) -> tuple[str, list[dict], str, list[str], bool, str, list[dict]]:
	user = _require_access()
	roles = get_user_roles(user)
	personas = _matched_personas(roles)
	if not personas:
		frappe.throw(_("No Veterinary operational role is assigned to this user."), frappe.PermissionError)

	resolved_date = _resolve_operational_date(operational_date)
	resolved_branch, assigned_branches, global_access = _current_branch(user, branch)
	persona_keys = {persona["key"] for persona in personas}
	metrics = _build_metrics(
		user,
		persona_keys,
		resolved_branch,
		assigned_branches,
		global_access,
		resolved_date,
	)
	return (
		user,
		personas,
		resolved_branch,
		assigned_branches,
		global_access,
		resolved_date,
		metrics,
	)


@frappe.whitelist()
def get_home_payload(
	operational_date: str | None = None,
	branch: str | None = None,
) -> dict:
	(
		user,
		personas,
		resolved_branch,
		assigned_branches,
		global_access,
		resolved_date,
		metrics,
	) = _home_state(operational_date, branch)

	branch_options = _branch_options(user, assigned_branches, global_access, resolved_branch)
	selected_branch_value = resolved_branch or ALL_BRANCHES_KEY

	return {
		"user": user,
		"primary_persona": personas[0],
		"personas": personas,
		"context": {
			"branch": resolved_branch,
			"branch_value": selected_branch_value,
			"branch_label": resolved_branch or _("All permitted branches"),
			"branch_options": branch_options,
			"assigned_branches": assigned_branches,
			"global_branch_access": global_access,
			"date": resolved_date,
			"operational_date": resolved_date,
			"today": nowdate(),
			"all_branches_key": ALL_BRANCHES_KEY,
		},
		"metrics": [_public_metric(metric) for metric in metrics],
		"attention": _build_attention(metrics),
		"quick_actions": _build_actions(personas),
		"refresh_seconds": HOME_REFRESH_SECONDS,
	}


@frappe.whitelist()
def get_metric_drilldown(
	metric_key: str,
	operational_date: str | None = None,
	branch: str | None = None,
	limit_start: int = 0,
	limit_page_length: int = HOME_PAGE_LENGTH,
) -> dict:
	if not metric_key:
		frappe.throw(_("Select a Veterinary Home metric to open."), frappe.ValidationError)

	(
		_user,
		_personas,
		resolved_branch,
		assigned_branches,
		global_access,
		resolved_date,
		metrics,
	) = _home_state(operational_date, branch)

	metric = next((row for row in metrics if row.get("key") == metric_key), None)
	if not metric or not metric.get("_query"):
		frappe.throw(_("This Veterinary Home metric is not available in your current access."), frappe.PermissionError)

	query = metric["_query"]
	doctype = query["doctype"]
	filters = query["filters"]
	total = _permission_count(doctype, filters)
	if total is None:
		frappe.throw(_("You do not have permission to view this Veterinary Home metric."), frappe.PermissionError)

	start = max(0, cint(limit_start))
	page_length = min(HOME_PAGE_LENGTH_MAX, max(1, cint(limit_page_length) or HOME_PAGE_LENGTH))
	fields, columns = _drilldown_fields(doctype)
	try:
		rows = frappe.get_list(
			doctype,
			fields=fields,
			filters=filters,
			order_by=query["order_by"],
			limit_start=start,
			limit_page_length=page_length,
		)
	except frappe.PermissionError:
		frappe.throw(_("You do not have permission to view this Veterinary Home metric."), frappe.PermissionError)

	return {
		"metric": _public_metric(metric),
		"doctype": doctype,
		"total": cint(total),
		"rows": rows,
		"columns": columns,
		"limit_start": start,
		"limit_page_length": page_length,
		"context": {
			"branch": resolved_branch,
			"branch_label": resolved_branch or _("All permitted branches"),
			"assigned_branches": assigned_branches,
			"global_branch_access": global_access,
			"operational_date": resolved_date,
		},
	}
