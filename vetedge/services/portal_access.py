from __future__ import annotations

import frappe
from frappe.utils import cint, validate_email_address


STAFF_OWNER_PORTAL_ROLES = {
	"System Manager",
	"VetEdge Administrator",
	"VetEdge Front Desk",
}


def get_owner_context(user: str | None = None) -> dict:
	user = user or frappe.session.user
	if not user or user == "Guest":
		frappe.throw("Please sign in to access the VetEdge owner portal.", frappe.PermissionError)

	customers = get_customers_for_user(user)
	return {"user": user, "customers": customers}


def get_customers_for_user(user: str) -> list[str]:
	customers = set(get_customers_from_customer_portal_users(user))
	customers.update(get_customers_from_contacts(user))
	return sorted(customers)


def get_vetedge_website_user_home_page(user: str) -> str | None:
	if not user or user == "Guest":
		return None

	settings = get_portal_settings()
	if not settings.get("enable_owner_portal"):
		return None

	if "Customer" in frappe.get_roles(user) and get_customers_for_user(user):
		return "vetedge_portal"

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

	role_added = ensure_customer_role(user_doc)
	portal_link_added = ensure_customer_portal_user(customer_doc, email)

	return {
		"user": email,
		"customer": customer_doc.name,
		"user_created": user_created,
		"role_added": role_added,
		"portal_link_added": portal_link_added,
		"message": "Owner portal user is ready.",
	}


def validate_staff_can_manage_owner_portal_users() -> None:
	if STAFF_OWNER_PORTAL_ROLES.isdisjoint(set(frappe.get_roles())):
		frappe.throw("Only authorized VetEdge staff can manage owner portal users.", frappe.PermissionError)


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


def ensure_customer_role(user_doc) -> bool:
	current_roles = {row.role for row in user_doc.get("roles") or []}
	if "Customer" in current_roles:
		return False

	user_doc.add_roles("Customer")
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


def get_customers_from_contacts(user: str) -> list[str]:
	contact_names = frappe.get_all(
		"Contact",
		filters={"user": user},
		pluck="name",
	)
	if not contact_names:
		contact_names = frappe.get_all(
			"Contact",
			filters={"email_id": user},
			pluck="name",
		)

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


def validate_owner_customer_access(customer: str, owner_context: dict | None = None) -> None:
	owner_context = owner_context or get_owner_context()
	if customer not in owner_context.get("customers", []):
		frappe.throw("You do not have access to this customer record.", frappe.PermissionError)


def get_owner_patient_names(owner_context: dict | None = None) -> list[str]:
	owner_context = owner_context or get_owner_context()
	customers = owner_context.get("customers", [])
	if not customers:
		return []

	return frappe.get_all(
		"Veterinary Patient",
		filters={"primary_owner": ["in", customers]},
		pluck="name",
	)


def validate_owner_patient_access(patient: str, owner_context: dict | None = None) -> None:
	owner_context = owner_context or get_owner_context()
	primary_owner = frappe.db.get_value("Veterinary Patient", patient, "primary_owner")
	if not primary_owner:
		frappe.throw("Veterinary Patient not found.", frappe.PermissionError)

	validate_owner_customer_access(primary_owner, owner_context)


def validate_owner_invoice_access(invoice_name: str, owner_context: dict | None = None) -> dict:
	owner_context = owner_context or get_owner_context()
	invoice = frappe.db.get_value(
		"Sales Invoice",
		invoice_name,
		["name", "customer", "posting_date", "status", "outstanding_amount", "grand_total", "currency", "docstatus"],
		as_dict=True,
	)
	if not invoice:
		frappe.throw("Sales Invoice not found.", frappe.PermissionError)

	validate_owner_customer_access(invoice.customer, owner_context)
	return invoice


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
		"portal_show_consultation_summary_only": bool(get("portal_show_consultation_summary_only", 1)),
	}


def default_portal_settings() -> dict:
	return {
		"enable_owner_portal": False,
		"enable_guest_booking": False,
		"allow_owner_cancel_appointment": False,
		"allow_owner_reschedule_appointment": False,
		"enable_portal_payments": False,
		"portal_payment_provider_mode": "Stub",
		"portal_show_consultation_summary_only": True,
	}
