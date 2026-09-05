from __future__ import annotations

import frappe
from frappe.utils import now_datetime
from frappe.utils.password import update_password

from vetedge.services.guest_booking import create_awaiting_registration_appointment
from vetedge.services.permissions import ROLE_VETEDGE_DOCTOR
from vetedge.services.role_bundles import STARTER_ROLE_BUNDLES

BRANCH_A = "VHOME QA Branch A"
BRANCH_B = "VHOME QA Branch B"
SPECIES = "VHOME QA Species"

PERSONA_USERS = {
	"doctor": ("vhome-browser-doctor@example.com", "Veterinary Doctor"),
	"front-desk": ("vhome-browser-frontdesk@example.com", "Front Desk"),
	"nurse": ("vhome-browser-nurse@example.com", "Veterinary Nurse"),
	"lab": ("vhome-browser-lab@example.com", "Lab Technician"),
	"groomer": ("vhome-browser-groomer@example.com", "Grooming Staff"),
	"dispensary": ("vhome-browser-dispensary@example.com", "Dispensary User"),
	"accounts": ("vhome-browser-accounts@example.com", "Accounts/Cashier"),
	"branch-manager": ("vhome-browser-manager@example.com", "Branch Manager"),
	"manager-doctor": ("vhome-browser-manager-doctor@example.com", "Branch Manager"),
	"branch-multi": ("vhome-browser-frontdesk-multi@example.com", "Front Desk"),
	"plain-desk": ("vhome-browser-desk-only@example.com", None),
}


def _ensure_branch(name: str) -> None:
	if frappe.db.exists("Branch", name):
		return
	frappe.get_doc({"doctype": "Branch", "branch": name}).insert(ignore_permissions=True)


def _ensure_species() -> None:
	if frappe.db.exists("Veterinary Species", SPECIES):
		return
	frappe.get_doc({"doctype": "Veterinary Species", "species_name": SPECIES}).insert(ignore_permissions=True)


def _ensure_user(email: str, roles: list[str], password: str) -> None:
	if not frappe.db.exists("User", email):
		frappe.get_doc(
			{
				"doctype": "User",
				"email": email,
				"first_name": "VHOME Browser QA",
				"enabled": 1,
				"user_type": "System User",
				"send_welcome_email": 0,
			}
		).insert(ignore_permissions=True)

	user = frappe.get_doc("User", email)
	changed = False
	if not user.enabled:
		user.enabled = 1
		changed = True
	if user.user_type != "System User":
		user.user_type = "System User"
		changed = True
	if changed:
		user.save(ignore_permissions=True)

	existing_roles = {row.role for row in user.get("roles") or []}
	for role in roles:
		if role and role not in existing_roles and frappe.db.exists("Role", role):
			user.add_roles(role)
			existing_roles.add(role)

	update_password(user=email, pwd=password, logout_all_sessions=True)
	frappe.clear_cache(user=email)


def _replace_branch_assignments(user: str, branches: list[str]) -> None:
	if not frappe.db.exists("DocType", "Branch User Assignment"):
		return
	for name in frappe.get_all("Branch User Assignment", filters={"user": user}, pluck="name"):
		frappe.delete_doc("Branch User Assignment", name, ignore_permissions=True, force=1)
	for branch in branches:
		frappe.get_doc(
			{
				"doctype": "Branch User Assignment",
				"user": user,
				"branch": branch,
				"disabled": 0,
			}
		).insert(ignore_permissions=True)


def _ensure_branch_appointment(branch: str, marker: str) -> str:
	email = f"vhome-browser-{marker}@example.com"
	request_name = frappe.db.get_value(
		"Veterinary Guest Booking Request",
		{"guest_email": email, "preferred_branch": branch},
		"name",
	)
	if request_name:
		request = frappe.get_doc("Veterinary Guest Booking Request", request_name)
	else:
		request = frappe.get_doc(
			{
				"doctype": "Veterinary Guest Booking Request",
				"status": "Registration Requested",
				"preferred_branch": branch,
				"appointment_requested": 1,
				"preferred_datetime": now_datetime(),
				"guest_name": f"VHOME Browser {marker}",
				"guest_email": email,
				"pet_name": f"VHOME Pet {marker}",
				"species": SPECIES,
				"reason_for_visit": "VHOME browser branch-scope fixture",
			}
		).insert(ignore_permissions=True)

	if request.linked_appointment and frappe.db.exists("Veterinary Appointment", request.linked_appointment):
		return request.linked_appointment

	appointment = create_awaiting_registration_appointment(request)
	request.db_set("linked_appointment", appointment.name, update_modified=False)
	return appointment.name


def prepare_browser_fixture(password: str) -> dict:
	if not password:
		frappe.throw("VHOME browser fixture password is required.")

	frappe.set_user("Administrator")
	_ensure_branch(BRANCH_A)
	_ensure_branch(BRANCH_B)
	_ensure_species()

	users: dict[str, str] = {}
	for key, (email, bundle_name) in PERSONA_USERS.items():
		if bundle_name:
			roles = list(STARTER_ROLE_BUNDLES[bundle_name])
		else:
			roles = ["Desk User"]
		if key == "manager-doctor" and ROLE_VETEDGE_DOCTOR not in roles:
			roles.append(ROLE_VETEDGE_DOCTOR)
		_ensure_user(email, roles, password)
		users[key] = email

	single_branch_keys = {
		"doctor",
		"front-desk",
		"nurse",
		"lab",
		"groomer",
		"dispensary",
		"accounts",
		"branch-manager",
	}
	for key in single_branch_keys:
		_replace_branch_assignments(users[key], [BRANCH_A])
	_replace_branch_assignments(users["manager-doctor"], [BRANCH_A, BRANCH_B])
	_replace_branch_assignments(users["branch-multi"], [BRANCH_A, BRANCH_B])

	appointments = {
		BRANCH_A: _ensure_branch_appointment(BRANCH_A, "branch-a"),
		BRANCH_B: _ensure_branch_appointment(BRANCH_B, "branch-b"),
	}

	frappe.db.commit()
	return {
		"users": users,
		"branches": [BRANCH_A, BRANCH_B],
		"appointments": appointments,
	}
