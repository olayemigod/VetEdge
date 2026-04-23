from __future__ import annotations

import frappe
from frappe import _
from frappe.utils import cint, validate_email_address
from werkzeug.routing import RequestRedirect

from vetedge.services.branding import get_owner_portal_brand_name


STAFF_OWNER_PORTAL_ROLES = {
	"System Manager",
	"VetEdge Administrator",
	"VetEdge Front Desk",
}
OWNER_PORTAL_ROLE = "VetEdge Portal User"
LEGACY_PORTAL_PAYMENT_PROVIDER_MAP = {
	"Stub": "stub",
	"ERPNext Payment Request": "erpnext_native",
	"ProcessEdge Core Payment": "processedge_core",
}
PORTAL_OWNER_ALLOWED_PERMISSIONS = {"read", "print"}
DESK_ROUTE_PREFIXES = ("/app", "/desk")
OWNER_PORTAL_HOME_ROUTE = "/vetedge_portal"
OWNER_PORTAL_ALLOWED_ROUTE_PREFIXES = (
	"/vetedge_portal",
	"/vetedge_portal_pets",
	"/vetedge_portal_appointments",
	"/vetedge_portal_billing",
	"/vetedge_portal_history",
	"/vetedge_guest_booking",
	"/api/",
	"/assets/",
	"/files/",
	"/private/files/",
	"/logout",
)
OWNER_PORTAL_REDIRECT_ENTRY_ROUTES = {"/", "/login", "/me"}


def get_owner_context(user: str | None = None) -> dict:
	user = user or get_session_user()
	if not user or user == "Guest":
		frappe.throw(f"Please sign in to access the {get_owner_portal_brand_name()} owner portal.", frappe.PermissionError)

	if not is_portal_owner_user(user):
		frappe.throw(f"You do not have access to the {get_owner_portal_brand_name()} owner portal.", frappe.PermissionError)

	customers = get_customers_for_user(user)
	if not customers:
		frappe.throw(f"You do not have access to the {get_owner_portal_brand_name()} owner portal.", frappe.PermissionError)

	return {
		"user": user,
		"customers": customers,
		"patients": get_owner_patient_names_for_customers(customers),
	}


def get_customers_for_user(user: str) -> list[str]:
	portal_customers = sorted(set(get_customers_from_customer_portal_users(user)))
	if portal_customers:
		return portal_customers

	contact_user_customers = sorted(set(get_customers_from_contacts(user, include_email_matches=False)))
	if contact_user_customers:
		return contact_user_customers

	email_customers = sorted(set(get_customers_from_contact_email(user)))
	if len(email_customers) == 1:
		return email_customers

	return []


def get_vetedge_website_user_home_page(user: str) -> str | None:
	if not user or user == "Guest":
		return None

	settings = get_portal_settings()
	if not settings.get("enable_owner_portal"):
		return None

	if is_portal_owner_user(user) and get_customers_for_user(user):
		return OWNER_PORTAL_HOME_ROUTE.strip("/")

	return None


@frappe.whitelist()
def ensure_owner_portal_user_for_patient(
	patient: str,
	email: str | None = None,
	full_name: str | None = None,
	send_welcome_email: int = 1,
) -> dict:
	validate_staff_can_manage_owner_portal_users()

	patient_doc = frappe.db.get_value(
		"Veterinary Patient",
		patient,
		["name", "patient_name", "primary_owner"],
		as_dict=True,
	)
	if not patient_doc:
		frappe.throw("Veterinary Patient not found.", frappe.PermissionError)
	if not patient_doc.primary_owner:
		frappe.throw("Select a Primary Owner before creating an owner portal user.", frappe.ValidationError)

	return ensure_owner_portal_user_for_customer(
		customer=patient_doc.primary_owner,
		email=email,
		full_name=full_name,
		send_welcome_email=send_welcome_email,
	)


def ensure_owner_portal_user_for_customer(
	customer: str,
	email: str | None = None,
	full_name: str | None = None,
	send_welcome_email: int = 1,
) -> dict:
	customer_doc = frappe.get_doc("Customer", customer)
	email = validate_owner_portal_email(email or customer_doc.get("email_id"))
	full_name = (full_name or customer_doc.get("customer_name") or customer_doc.name).strip()

	user_created = False
	if frappe.db.exists("User", email):
		user_doc = frappe.get_doc("User", email)
		if not cint(user_doc.enabled):
			frappe.throw("Owner portal user exists but is disabled.", frappe.ValidationError)
	else:
		first_name, last_name = split_full_name(full_name)
		user_doc = frappe.get_doc(
			{
				"doctype": "User",
				"email": email,
				"first_name": first_name,
				"last_name": last_name,
				"user_type": "Website User",
				"send_welcome_email": cint(send_welcome_email),
			}
		)
		user_doc.insert(ignore_permissions=True)
		user_created = True

	user_type_changed = ensure_owner_portal_user_type(user_doc)
	owner_role_added = ensure_owner_portal_role(user_doc)
	role_removed = ensure_owner_portal_roles(user_doc)
	portal_link_added = ensure_customer_portal_user(customer_doc, email)
	post_link_hardening = harden_owner_portal_user(email)

	return {
		"user": email,
		"customer": customer_doc.name,
		"user_created": user_created,
		"user_type_changed": user_type_changed,
		"owner_role_added": owner_role_added,
		"role_removed": role_removed,
		"portal_link_added": portal_link_added,
		"post_link_hardening": post_link_hardening,
		"message": "Owner portal user is ready.",
	}


def validate_staff_can_manage_owner_portal_users() -> None:
	if STAFF_OWNER_PORTAL_ROLES.isdisjoint(set(get_user_roles())):
		frappe.throw("Only authorized staff can manage owner portal users.", frappe.PermissionError)


def validate_owner_portal_email(email: str | None) -> str:
	if not email:
		frappe.throw("Owner email is required to create a portal user.", frappe.ValidationError)

	return validate_email_address(email.strip(), throw=True)


def split_full_name(full_name: str) -> tuple[str, str]:
	parts = (full_name or "").split()
	if not parts:
		return "Owner", ""
	if len(parts) == 1:
		return parts[0], ""
	return parts[0], " ".join(parts[1:])


def ensure_owner_portal_role(user_doc) -> bool:
	current_roles = {row.role for row in user_doc.get("roles") or []}
	if OWNER_PORTAL_ROLE in current_roles:
		return False

	user_doc.add_roles(OWNER_PORTAL_ROLE)
	return True


def ensure_owner_portal_roles(user_doc) -> bool:
	current_roles = {row.role for row in user_doc.get("roles") or []}
	if "Customer" not in current_roles:
		return False

	if hasattr(user_doc, "remove_roles"):
		user_doc.remove_roles("Customer")
	else:
		user_doc.roles = [row for row in (user_doc.get("roles") or []) if row.role != "Customer"]

	if getattr(user_doc, "name", None) and getattr(user_doc, "save", None):
		user_doc.save(ignore_permissions=True)
	return True


def harden_owner_portal_user(user: str):
	if not frappe.db.exists("User", user):
		return {"owner_role_added": False, "role_removed": False, "user_type_changed": False}

	user_doc = frappe.get_doc("User", user)
	owner_role_added = ensure_owner_portal_role(user_doc)
	role_removed = ensure_owner_portal_roles(user_doc)

	if frappe.db.exists("User", user):
		user_doc = frappe.get_doc("User", user)
	user_type_changed = ensure_owner_portal_user_type(user_doc)

	return {
		"owner_role_added": owner_role_added,
		"role_removed": role_removed,
		"user_type_changed": user_type_changed,
	}


def ensure_owner_portal_user_type(user_doc) -> bool:
	roles = {row.role for row in user_doc.get("roles") or []}
	if user_doc.get("user_type") == "Website User":
		return False

	if get_desk_roles_for_roles(roles):
		frappe.throw(
			"Owner portal users must not keep Desk access. Remove internal roles before linking this user to the portal.",
			frappe.ValidationError,
		)

	user_doc.user_type = "Website User"
	if getattr(user_doc, "name", None) and getattr(user_doc, "save", None):
		user_doc.save(ignore_permissions=True)
	return True


def ensure_customer_portal_user(customer_doc, user: str) -> bool:
	for row in customer_doc.get("portal_users") or []:
		if row.user == user:
			return False

	customer_doc.append("portal_users", {"user": user})
	customer_doc.save(ignore_permissions=True)
	return True


def get_customers_from_customer_portal_users(user: str) -> list[str]:
	if not frappe.db.exists("DocType", "Portal User"):
		return []

	return frappe.get_all(
		"Portal User",
		filters={
			"parenttype": "Customer",
			"user": user,
		},
		pluck="parent",
	)


def get_customers_from_contacts(user: str, include_email_matches: bool = True) -> list[str]:
	contact_names = frappe.get_all("Contact", filters={"user": user}, pluck="name")
	if not contact_names and include_email_matches:
		contact_names = frappe.get_all("Contact", filters={"email_id": user}, pluck="name")

	if not contact_names:
		return []

	return frappe.get_all(
		"Dynamic Link",
		filters={
			"parenttype": "Contact",
			"parent": ["in", contact_names],
			"link_doctype": "Customer",
		},
		pluck="link_name",
	)


def get_customers_from_contact_email(user: str) -> list[str]:
	return get_customers_from_contacts(user, include_email_matches=True)


def validate_owner_customer_access(customer: str, owner_context: dict | None = None) -> None:
	owner_context = owner_context or get_owner_context()
	if customer not in owner_context.get("customers", []):
		raise_owner_access_denied()


def get_owner_patient_names(owner_context: dict | None = None) -> list[str]:
	owner_context = owner_context or get_owner_context()
	return list(owner_context.get("patients") or get_owner_patient_names_for_customers(owner_context.get("customers", [])))


def get_owner_patient_names_for_customers(customers: list[str] | tuple[str, ...]) -> list[str]:
	if not customers:
		return []

	return frappe.get_all(
		"Veterinary Patient",
		filters={"primary_owner": ["in", list(customers)]},
		pluck="name",
	)


def validate_owner_patient_access(patient: str, owner_context: dict | None = None) -> None:
	owner_context = owner_context or get_owner_context()
	primary_owner = frappe.db.get_value("Veterinary Patient", patient, "primary_owner")
	if not primary_owner:
		raise_owner_access_denied()

	validate_owner_customer_access(primary_owner, owner_context)


def validate_owner_appointment_access(appointment: str, owner_context: dict | None = None) -> dict:
	owner_context = owner_context or get_owner_context()
	appointment_doc = frappe.db.get_value(
		"Veterinary Appointment",
		appointment,
		["name", "patient", "primary_owner", "branch", "appointment_datetime", "status"],
		as_dict=True,
	)
	if not appointment_doc:
		raise_owner_access_denied()

	if appointment_doc.primary_owner:
		validate_owner_customer_access(appointment_doc.primary_owner, owner_context)
	else:
		validate_owner_patient_access(appointment_doc.patient, owner_context)
	return appointment_doc


def validate_owner_consultation_access(consultation: str, owner_context: dict | None = None) -> dict:
	owner_context = owner_context or get_owner_context()
	consultation_doc = frappe.db.get_value(
		"Veterinary Consultation",
		consultation,
		[
			"name",
			"patient",
			"primary_owner",
			"consultation_datetime",
			"service_branch",
			"consulting_practitioner_name",
			"status",
			"consultation_title",
		],
		as_dict=True,
	)
	if not consultation_doc:
		raise_owner_access_denied()

	if consultation_doc.primary_owner:
		validate_owner_customer_access(consultation_doc.primary_owner, owner_context)
	else:
		validate_owner_patient_access(consultation_doc.patient, owner_context)
	return consultation_doc


def validate_owner_invoice_access(invoice_name: str, owner_context: dict | None = None) -> dict:
	owner_context = owner_context or get_owner_context()
	invoice = frappe.db.get_value(
		"Sales Invoice",
		invoice_name,
		["name", "customer", "posting_date", "status", "outstanding_amount", "grand_total", "currency", "docstatus"],
		as_dict=True,
	)
	if not invoice:
		raise_owner_access_denied()

	validate_owner_customer_access(invoice.customer, owner_context)
	return invoice


def get_owner_invoice_names(owner_context: dict | None = None) -> list[str]:
	owner_context = owner_context or get_owner_context()
	customers = owner_context.get("customers", [])
	if not customers:
		return []

	return frappe.get_all(
		"Sales Invoice",
		filters={"customer": ["in", customers]},
		pluck="name",
	)


def is_portal_owner_user(user: str | None = None) -> bool:
	user = user or get_session_user()
	if not user or user == "Guest":
		return False

	if get_user_type(user) != "Website User":
		return False

	roles = set(get_user_roles(user))
	if has_desk_access(user, roles):
		return False

	return bool(get_customers_for_user(user))


def require_internal_user() -> None:
	user = get_session_user()
	if user is None:
		return
	if not user or user == "Guest":
		frappe.throw(_("Please sign in to continue."), frappe.PermissionError)

	if is_portal_owner_user(user):
		frappe.throw(_("This action is only available to clinic staff."), frappe.PermissionError)


def has_desk_access(user: str, roles: set[str] | None = None) -> bool:
	if get_user_type(user) == "System User":
		return True

	return bool(get_desk_roles_for_roles(roles or set(get_user_roles(user))))


def get_desk_roles_for_roles(roles: set[str] | list[str] | tuple[str, ...]) -> set[str]:
	desk_roles = set()
	for role in set(roles or []):
		if role in {"All", "Guest"}:
			continue
		if cint(frappe.db.get_value("Role", role, "desk_access") or 0):
			desk_roles.add(role)
	return desk_roles


def get_user_type(user: str) -> str | None:
	if not user or user == "Guest":
		return None
	return frappe.db.get_value("User", user, "user_type")


def get_user_roles(user: str | None = None) -> list[str]:
	get_roles = getattr(frappe, "get_roles", None)
	if not get_roles:
		return []
	return list(get_roles(user))


def get_session_user() -> str | None:
	try:
		return getattr(frappe.session, "user", None)
	except RuntimeError:
		return None


def normalize_owner_portal_users() -> None:
	if not frappe.db.exists("DocType", "User"):
		return

	seen_users: set[str] = set()
	for customer in frappe.get_all("Customer", fields=["name"]):
		customer_doc = frappe.get_doc("Customer", customer.name)
		for row in customer_doc.get("portal_users") or []:
			if row.user:
				seen_users.add(row.user)

	for contact in frappe.get_all("Contact", fields=["name", "user", "email_id"]):
		customers = frappe.get_all(
			"Dynamic Link",
			filters={
				"parenttype": "Contact",
				"parent": contact.name,
				"link_doctype": "Customer",
			},
			pluck="link_name",
		)
		if not customers:
			continue

		if contact.user:
			seen_users.add(contact.user)
		elif contact.email_id:
			seen_users.add(contact.email_id)

	for user in seen_users:
		if not frappe.db.exists("User", user):
			continue
		user_doc = frappe.get_doc("User", user)
		roles = {row.role for row in user_doc.get("roles") or []}
		if get_desk_roles_for_roles(roles):
			continue
		if OWNER_PORTAL_ROLE not in roles:
			ensure_owner_portal_role(user_doc)
		if "Customer" in roles:
			ensure_owner_portal_roles(user_doc)
		if user_doc.user_type != "Website User":
			user_doc.user_type = "Website User"
			user_doc.save(ignore_permissions=True)
		harden_owner_portal_user(user)


def block_owner_portal_desk_access() -> None:
	user = get_session_user()
	if not is_portal_owner_user(user):
		return

	path = get_request_path()
	redirect_route = get_owner_portal_redirect_path(path, user=user)
	if not redirect_route:
		return

	frappe.local.response["type"] = "redirect"
	frappe.local.response["location"] = redirect_route
	raise RequestRedirect(redirect_route)


def raise_owner_access_denied() -> None:
	frappe.throw("You do not have access to this record.", frappe.PermissionError)


def get_veterinary_patient_query(user: str | None = None) -> str | None:
	return get_owner_query_condition_for_customer_field("Veterinary Patient", "primary_owner", user=user)


def get_veterinary_appointment_query(user: str | None = None) -> str | None:
	return get_owner_query_condition_for_customer_field("Veterinary Appointment", "primary_owner", user=user)


def get_veterinary_consultation_query(user: str | None = None) -> str | None:
	return get_owner_query_condition_for_customer_field("Veterinary Consultation", "primary_owner", user=user)


def get_sales_invoice_query(user: str | None = None) -> str | None:
	return get_owner_query_condition_for_customer_field("Sales Invoice", "customer", user=user)


def get_veterinary_vital_signs_query(user: str | None = None) -> str | None:
	user = user or get_session_user()
	if not is_portal_owner_user(user):
		return None

	customers = get_customers_for_user(user)
	if not customers:
		return "1=0"

	customer_clause = get_sql_in_clause(customers)
	return (
		"`tabVeterinary Vital Signs`.`patient` in ("
		"select `tabVeterinary Patient`.`name` from `tabVeterinary Patient` "
		f"where `tabVeterinary Patient`.`primary_owner` in ({customer_clause}))"
	)


def has_veterinary_patient_permission(doc, user: str | None = None, permission_type: str | None = None) -> bool | None:
	return has_owner_document_permission(doc, "Veterinary Patient", permission_type, user=user)


def has_veterinary_appointment_permission(doc, user: str | None = None, permission_type: str | None = None) -> bool | None:
	return has_owner_document_permission(doc, "Veterinary Appointment", permission_type, user=user)


def has_veterinary_consultation_permission(doc, user: str | None = None, permission_type: str | None = None) -> bool | None:
	return has_owner_document_permission(doc, "Veterinary Consultation", permission_type, user=user)


def has_veterinary_vital_signs_permission(doc, user: str | None = None, permission_type: str | None = None) -> bool | None:
	return has_owner_document_permission(doc, "Veterinary Vital Signs", permission_type, user=user)


def has_sales_invoice_permission(doc, user: str | None = None, permission_type: str | None = None) -> bool | None:
	return has_owner_document_permission(doc, "Sales Invoice", permission_type, user=user)


def has_owner_document_permission(
	doc,
	doctype: str,
	permission_type: str | None,
	user: str | None = None,
) -> bool | None:
	user = user or get_session_user()
	if not is_portal_owner_user(user):
		return None

	if permission_type and permission_type not in PORTAL_OWNER_ALLOWED_PERMISSIONS:
		return False

	name = doc if isinstance(doc, str) else getattr(doc, "name", None)
	if not name:
		return False

	owner_context = get_owner_context(user=user)
	try:
		if doctype == "Veterinary Patient":
			validate_owner_patient_access(name, owner_context)
		elif doctype == "Veterinary Appointment":
			validate_owner_appointment_access(name, owner_context)
		elif doctype == "Veterinary Consultation":
			validate_owner_consultation_access(name, owner_context)
		elif doctype == "Veterinary Vital Signs":
			patient = frappe.db.get_value("Veterinary Vital Signs", name, "patient")
			if not patient:
				return False
			validate_owner_patient_access(patient, owner_context)
		elif doctype == "Sales Invoice":
			validate_owner_invoice_access(name, owner_context)
		else:
			return None
	except frappe.PermissionError:
		return False

	return True


def get_owner_query_condition_for_customer_field(
	doctype: str,
	fieldname: str,
	user: str | None = None,
) -> str | None:
	user = user or get_session_user()
	if not is_portal_owner_user(user):
		return None

	customers = get_customers_for_user(user)
	if not customers:
		return "1=0"

	return f"`tab{doctype}`.`{fieldname}` in ({get_sql_in_clause(customers)})"


def get_sql_in_clause(values: list[str] | tuple[str, ...]) -> str:
	return ", ".join(frappe.db.escape(value) for value in values)


def get_request_path() -> str:
	request = getattr(frappe.local, "request", None)
	path = getattr(request, "path", None) or getattr(frappe.local, "request_path", None) or ""
	return path or "/"


def get_owner_portal_redirect_path(path: str, user: str | None = None) -> str | None:
	user = user or get_session_user()
	if not is_portal_owner_user(user):
		return None

	path = (path or "/").strip() or "/"
	home_route = get_owner_portal_home_route(user)
	if path == home_route or any(
		path == prefix or path.startswith(f"{prefix}/") for prefix in OWNER_PORTAL_ALLOWED_ROUTE_PREFIXES
	):
		return None

	if path in OWNER_PORTAL_REDIRECT_ENTRY_ROUTES:
		return home_route

	if path.startswith(DESK_ROUTE_PREFIXES):
		return home_route

	return None


def get_owner_portal_home_route(user: str | None = None) -> str:
	route = get_vetedge_website_user_home_page(user) or OWNER_PORTAL_HOME_ROUTE
	return route if route.startswith("/") else f"/{route}"


def get_portal_settings() -> dict:
	if not frappe.db.exists("DocType", "Veterinary Settings"):
		return default_portal_settings()

	settings = frappe.get_single("Veterinary Settings")
	meta = frappe.get_meta("Veterinary Settings")

	def get(fieldname: str, default=None):
		return settings.get(fieldname) if meta.has_field(fieldname) else default

	return {
		"enable_owner_portal": bool(settings.enable_vetedge and settings.enable_owner_portal),
		"enable_guest_booking": bool(settings.enable_vetedge and settings.enable_guest_booking),
		"allow_owner_cancel_appointment": bool(get("allow_owner_cancel_appointment", 0)),
		"allow_owner_reschedule_appointment": bool(get("allow_owner_reschedule_appointment", 0)),
		"enable_portal_payments": bool(settings.enable_vetedge and get("enable_portal_payments", 0)),
		"portal_payment_provider_mode": get("portal_payment_provider_mode", "Stub"),
		"payment_backend_mode": get("payment_backend_mode")
		or LEGACY_PORTAL_PAYMENT_PROVIDER_MAP.get(get("portal_payment_provider_mode", "Stub"), "stub"),
		"portal_show_consultation_summary_only": bool(get("portal_show_consultation_summary_only", 1)),
		"portal_theme": {
			"brand_name": get("portal_brand_name") or "Owner Portal",
			"logo_url": get("portal_logo"),
			"page_background": get("portal_page_background", "#f8fafc"),
			"surface_color": get("portal_surface_color", "#ffffff"),
			"primary_color": get("portal_primary_color", "#0f766e"),
			"primary_text_color": get("portal_primary_text_color", "#ffffff"),
			"accent_color": get("portal_accent_color", "#ecfeff"),
			"nav_background": get("portal_nav_background", "#0f172a"),
			"nav_text_color": get("portal_nav_text_color", "#e2e8f0"),
			"muted_text_color": get("portal_muted_text_color", "#64748b"),
			"heading_color": get("portal_heading_color", "#0f172a"),
			"card_radius": get("portal_card_radius", "16px"),
			"custom_css": get("portal_custom_css", ""),
		},
	}


def default_portal_settings() -> dict:
	return {
		"enable_owner_portal": False,
		"enable_guest_booking": False,
		"allow_owner_cancel_appointment": False,
		"allow_owner_reschedule_appointment": False,
		"enable_portal_payments": False,
		"payment_backend_mode": "stub",
		"portal_payment_provider_mode": "Stub",
		"portal_show_consultation_summary_only": True,
		"portal_theme": {
			"brand_name": "Owner Portal",
			"logo_url": None,
			"page_background": "#f8fafc",
			"surface_color": "#ffffff",
			"primary_color": "#0f766e",
			"primary_text_color": "#ffffff",
			"accent_color": "#ecfeff",
			"nav_background": "#0f172a",
			"nav_text_color": "#e2e8f0",
			"muted_text_color": "#64748b",
			"heading_color": "#0f172a",
			"card_radius": "16px",
			"custom_css": "",
		},
	}
