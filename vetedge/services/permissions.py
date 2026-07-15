from __future__ import annotations

import frappe
import frappe.permissions
from frappe.utils import cint

from vetedge.services.audit import log_operational_event


ROLE_SYSTEM_MANAGER = "System Manager"
ROLE_VETEDGE_ADMINISTRATOR = "VetEdge Administrator"
ROLE_VETEDGE_DOCTOR = "VetEdge Doctor"
ROLE_VETEDGE_GROOMER = "VetEdge Groomer"
ROLE_VETEDGE_NURSE = "VetEdge Nurse"
ROLE_VETEDGE_FRONT_DESK = "VetEdge Front Desk"
ROLE_VETERINARY_NURSE = "Veterinary Nurse"
ROLE_DISPENSARY_USER = "Dispensary User"
ROLE_LAB_TECHNICIAN = "Lab Technician"
ROLE_BRANCH_MANAGER = "Branch Manager"
ROLE_ACCOUNTS_CASHIER = "Accounts/Cashier"
ROLE_ACCOUNTS_MANAGER = "Accounts Manager"
ROLE_ACCOUNTS_USER = "Accounts User"

ROLE_ALIASES = {
	ROLE_VETEDGE_ADMINISTRATOR: {ROLE_VETEDGE_ADMINISTRATOR},
	ROLE_VETEDGE_DOCTOR: {ROLE_VETEDGE_DOCTOR},
	ROLE_VETEDGE_GROOMER: {ROLE_VETEDGE_GROOMER},
	ROLE_VETEDGE_NURSE: {ROLE_VETEDGE_NURSE, ROLE_VETERINARY_NURSE},
	ROLE_VETEDGE_FRONT_DESK: {ROLE_VETEDGE_FRONT_DESK},
	ROLE_VETERINARY_NURSE: {ROLE_VETERINARY_NURSE, "VetEdge Nurse"},
	ROLE_DISPENSARY_USER: {ROLE_DISPENSARY_USER, "VetEdge Dispensary User"},
	ROLE_LAB_TECHNICIAN: {ROLE_LAB_TECHNICIAN, "VetEdge Lab Technician"},
	ROLE_BRANCH_MANAGER: {ROLE_BRANCH_MANAGER, "VetEdge Branch Manager"},
	ROLE_ACCOUNTS_CASHIER: {ROLE_ACCOUNTS_CASHIER, "VetEdge Accounts/Cashier"},
}


def _role_group(*roles: str) -> set[str]:
	group: set[str] = set()
	for role in roles:
		group |= ROLE_ALIASES.get(role, {role})
	return group


ELEVATED_ROLES = {ROLE_SYSTEM_MANAGER, *_role_group(ROLE_VETEDGE_ADMINISTRATOR)}
DOCTOR_ROLES = {*_role_group(ROLE_VETEDGE_DOCTOR), *ELEVATED_ROLES}
DISPENSARY_ROLES = {*_role_group(ROLE_DISPENSARY_USER), *ELEVATED_ROLES}
LAB_REQUEST_ROLES = DOCTOR_ROLES
LAB_RESULT_ENTRY_ROLES = {*_role_group(ROLE_LAB_TECHNICIAN), *DOCTOR_ROLES}
LAB_REVIEW_ROLES = DOCTOR_ROLES
ROLE_BUNDLE_MANAGER_ROLES = ELEVATED_ROLES
FRONT_DESK_ROLES = {*_role_group(ROLE_VETEDGE_FRONT_DESK), *ELEVATED_ROLES}
GROOMER_ROLES = {*_role_group(ROLE_VETEDGE_GROOMER), *ELEVATED_ROLES}
GROOMING_MANAGER_ROLES = {*_role_group(ROLE_BRANCH_MANAGER), *ELEVATED_ROLES}
GROOMING_APPOINTMENT_ACTION_ROLES = {*FRONT_DESK_ROLES, *GROOMING_MANAGER_ROLES}
GROOMING_SESSION_PROGRESS_ROLES = {*GROOMER_ROLES, *GROOMING_MANAGER_ROLES}
GROOMING_BILLING_ROLES = {*FRONT_DESK_ROLES, *GROOMING_MANAGER_ROLES}
ACCOUNTS_COLLECTION_ROLES = {
	ROLE_ACCOUNTS_MANAGER,
	ROLE_ACCOUNTS_USER,
	*_role_group(ROLE_ACCOUNTS_CASHIER),
	*ELEVATED_ROLES,
}
INTERNAL_ROLES = {
	*ELEVATED_ROLES,
	*_role_group(ROLE_VETEDGE_DOCTOR),
	*_role_group(ROLE_VETEDGE_GROOMER),
	*_role_group(ROLE_VETEDGE_FRONT_DESK),
	*_role_group(ROLE_VETEDGE_NURSE),
	*_role_group(ROLE_VETERINARY_NURSE),
	*_role_group(ROLE_DISPENSARY_USER),
	*_role_group(ROLE_LAB_TECHNICIAN),
	*_role_group(ROLE_BRANCH_MANAGER),
	*_role_group(ROLE_ACCOUNTS_CASHIER),
	ROLE_ACCOUNTS_MANAGER,
	ROLE_ACCOUNTS_USER,
}
PORTAL_ALLOWED_PERMISSION_TYPES = {"read", "print"}
NOTIFICATION_ADMIN_ROLES = {ROLE_SYSTEM_MANAGER, *_role_group(ROLE_VETEDGE_ADMINISTRATOR)}
OWNER_READ_PERMISSION_TYPES = {None, "read", "print", "email", "report"}


def get_current_user() -> str | None:
	try:
		return getattr(frappe.session, "user", None)
	except RuntimeError:
		return None


def get_user_roles(user: str | None = None) -> set[str]:
	user = user or get_current_user()
	get_roles = getattr(frappe, "get_roles", None)
	if not get_roles or not user:
		return set()
	return set(get_roles(user))


def user_has_any_role(user: str | None, roles: set[str]) -> bool:
	return bool(get_user_roles(user) & set(roles))


def get_veterinary_settings_flag(fieldname: str, default: bool = False) -> bool:
	try:
		if not frappe.db.exists("DocType", "Veterinary Settings"):
			return default
		value = frappe.db.get_single_value("Veterinary Settings", fieldname)
	except Exception:
		return default
	return bool(cint(value)) if value is not None else default


def is_notification_admin(user: str | None = None) -> bool:
	user = user or get_current_user()
	if not user or user == "Guest":
		return False
	return user_has_any_role(user, NOTIFICATION_ADMIN_ROLES)


def is_portal_owner_user(user: str | None = None) -> bool:
	from vetedge.services.portal_access import is_portal_owner_user as portal_owner_check

	return portal_owner_check(user)


def is_internal_staff_user(user: str | None = None) -> bool:
	user = user or get_current_user()
	if not user or user == "Guest":
		return False
	if is_portal_owner_user(user):
		return False
	return bool(get_user_roles(user) & INTERNAL_ROLES or user_has_any_role(user, ELEVATED_ROLES))


def get_assigned_branches(user: str | None = None) -> list[str]:
	user = user or get_current_user()
	if not user or not frappe.db.exists("DocType", "Branch User Assignment"):
		return []

	filters = {"user": user}
	meta = frappe.get_meta("Branch User Assignment")
	if meta.has_field("disabled"):
		filters["disabled"] = ["!=", 1]
	return frappe.get_all("Branch User Assignment", filters=filters, pluck="branch")


def user_has_global_branch_access(user: str | None = None) -> bool:
	return user_has_any_role(user, ELEVATED_ROLES)


def can_access_branch_data(user: str | None, branch: str | None, raise_exception: bool = False) -> bool:
	user = user or get_current_user()
	if not user or user == "Guest" or is_portal_owner_user(user):
		return _deny(
			raise_exception,
			"Not permitted to access branch data.",
			"branch_access_blocked",
			reference_doctype="Branch",
			reference_name=branch,
			details={"branch": branch},
			user=user,
		)

	if not branch or user_has_global_branch_access(user):
		return True

	assigned_branches = get_assigned_branches(user)
	if not assigned_branches:
		return True

	if branch in assigned_branches:
		return True

	return _deny(
		raise_exception,
		f"User {user} is not assigned to Branch {branch}.",
		"branch_access_blocked",
		reference_doctype="Branch",
		reference_name=branch,
		details={"branch": branch, "assigned_branches": assigned_branches},
		user=user,
	)


def can_access_patient(user: str | None, patient: str, raise_exception: bool = False) -> bool:
	user = user or get_current_user()
	if not user or user == "Guest":
		return _deny(
			raise_exception,
			"Not permitted to access this patient.",
			"patient_access_blocked",
			reference_doctype="Veterinary Patient",
			reference_name=patient,
			user=user,
		)

	if is_portal_owner_user(user):
		from vetedge.services.portal_access import validate_owner_patient_access

		try:
			validate_owner_patient_access(patient)
			return True
		except frappe.PermissionError:
			return _deny(
				raise_exception,
				"You do not have access to this patient.",
				"owner_patient_access_blocked",
				reference_doctype="Veterinary Patient",
				reference_name=patient,
				user=user,
			)

	if user_has_global_branch_access(user) or not is_patient_branch_restriction_enabled():
		return True

	assigned_branches = get_assigned_branches(user)
	if not assigned_branches:
		return _deny(
			raise_exception,
			f"User {user} has no branch assignment.",
			"patient_access_blocked",
			reference_doctype="Veterinary Patient",
			reference_name=patient,
			details={"assigned_branches": assigned_branches},
			user=user,
		)

	branch = frappe.db.get_value("Veterinary Patient", patient, "default_branch")
	if not branch or branch in assigned_branches:
		return True

	return _deny(
		raise_exception,
		f"User {user} is not allowed to access Veterinary Patient {patient} for Branch {branch}.",
		"patient_access_blocked",
		reference_doctype="Veterinary Patient",
		reference_name=patient,
		details={"branch": branch, "assigned_branches": assigned_branches},
		user=user,
	)


def validate_patient_branch_access(patient: str, user: str | None = None) -> None:
	if not patient:
		return

	can_access_patient(user or get_current_user(), patient, raise_exception=True)


def is_patient_branch_restriction_enabled() -> bool:
	if not frappe.db.exists("DocType", "Veterinary Settings"):
		return False

	meta = frappe.get_meta("Veterinary Settings")
	if not meta.has_field("patient_branch_restriction_enabled"):
		return False

	return bool(frappe.db.get_single_value("Veterinary Settings", "patient_branch_restriction_enabled"))


def can_access_consultation(user: str | None, consultation: str, raise_exception: bool = False) -> bool:
	user = user or get_current_user()
	if is_portal_owner_user(user):
		from vetedge.services.portal_access import validate_owner_consultation_access

		try:
			validate_owner_consultation_access(consultation)
			return True
		except frappe.PermissionError:
			return _deny(
				raise_exception,
				"You do not have access to this consultation.",
				"owner_consultation_access_blocked",
				reference_doctype="Veterinary Consultation",
				reference_name=consultation,
				user=user,
			)

	branch = frappe.db.get_value("Veterinary Consultation", consultation, "service_branch")
	return can_access_branch_data(user, branch, raise_exception=raise_exception)


def can_access_medical_history(user: str | None, patient: str, raise_exception: bool = False) -> bool:
	user = user or get_current_user()
	if not is_internal_staff_user(user):
		return _deny(
			raise_exception,
			"This action is only available to clinic staff.",
			"medical_history_access_blocked",
			reference_doctype="Veterinary Patient",
			reference_name=patient,
			user=user,
		)
	return can_access_patient(user, patient, raise_exception=raise_exception)


def can_access_lab_order(user: str | None, lab_order: str, raise_exception: bool = False) -> bool:
	user = user or get_current_user()
	if is_portal_owner_user(user):
		return _deny(
			raise_exception,
			"This action is only available to clinic staff.",
			"lab_order_access_blocked",
			reference_doctype="Veterinary Lab Order",
			reference_name=lab_order,
			user=user,
		)

	if not is_internal_staff_user(user):
		return _deny(
			raise_exception,
			"This action is only available to clinic staff.",
			"lab_order_access_blocked",
			reference_doctype="Veterinary Lab Order",
			reference_name=lab_order,
			user=user,
		)

	branch = frappe.db.get_value("Veterinary Lab Order", lab_order, "service_branch")
	return can_access_branch_data(user, branch, raise_exception=raise_exception)


def can_view_invoice(user: str | None, invoice_name: str, raise_exception: bool = False) -> bool:
	user = user or get_current_user()
	if is_portal_owner_user(user):
		from vetedge.services.portal_access import validate_owner_invoice_access

		try:
			validate_owner_invoice_access(invoice_name)
			return True
		except frappe.PermissionError:
			return _deny(
				raise_exception,
				"You do not have access to this invoice.",
				"owner_invoice_access_blocked",
				reference_doctype="Sales Invoice",
				reference_name=invoice_name,
				user=user,
			)

	if not is_internal_staff_user(user):
		return _deny(
			raise_exception,
			"Not permitted to access this invoice.",
			"invoice_access_blocked",
			reference_doctype="Sales Invoice",
			reference_name=invoice_name,
			user=user,
		)

	branch = None
	if frappe.get_meta("Sales Invoice").has_field("branch"):
		branch = frappe.db.get_value("Sales Invoice", invoice_name, "branch")
	return can_access_branch_data(user, branch, raise_exception=raise_exception)


def get_invoice_access_diagnostic(user: str | None, invoice_name: str) -> dict:
	user = user or get_current_user()
	if not frappe.db.exists("Sales Invoice", invoice_name):
		return {
			"allowed": False,
			"category": "missing",
			"message": f"Sales Invoice {invoice_name} was not found.",
			"can_open_full_form": False,
		}

	if not is_internal_staff_user(user):
		return {
			"allowed": False,
			"category": "contextual_restriction",
			"message": (
				f"Sales Invoice {invoice_name} is blocked by VetEdge contextual restriction. "
				"This invoice summary is only available to internal clinic staff."
			),
			"can_open_full_form": False,
		}

	branch = frappe.db.get_value("Sales Invoice", invoice_name, "branch") if frappe.get_meta("Sales Invoice").has_field("branch") else None
	assigned_branches = get_assigned_branches(user)
	if not can_view_invoice(user, invoice_name, raise_exception=False):
		if branch and not user_has_global_branch_access(user) and assigned_branches and branch not in assigned_branches:
			return {
				"allowed": False,
				"category": "branch_restriction",
				"message": (
					f"Sales Invoice {invoice_name} is blocked by VetEdge branch restriction. "
					f"User {user} is not assigned to Branch {branch}."
				),
				"can_open_full_form": False,
			}

		return {
			"allowed": False,
			"category": "contextual_restriction",
			"message": (
				f"Sales Invoice {invoice_name} is blocked by VetEdge contextual restriction "
				"for this internal invoice summary request."
			),
			"can_open_full_form": False,
		}

	doctype_allowed, doctype_logs = _evaluate_frappe_permission_debug(
		"Sales Invoice",
		user=user,
		ptype="read",
	)
	if not doctype_allowed:
		return _build_invoice_permission_block(invoice_name, "erpnext_role_permission", doctype_logs)

	doc_allowed, doc_logs = _evaluate_frappe_permission_debug(
		"Sales Invoice",
		user=user,
		ptype="read",
		doc=invoice_name,
	)
	if not doc_allowed:
		category = _classify_invoice_permission_debug_logs(doc_logs)
		return _build_invoice_permission_block(invoice_name, category, doc_logs)

	return {
		"allowed": True,
		"category": "allowed",
		"message": None,
		"can_open_full_form": True,
	}


def can_initiate_payment(
	user: str | None,
	invoice_name: str,
	mode: str = "owner",
	raise_exception: bool = False,
) -> bool:
	user = user or get_current_user()
	if mode == "owner":
		return can_view_invoice(user, invoice_name, raise_exception=raise_exception)

	if not can_view_invoice(user, invoice_name, raise_exception=raise_exception):
		return False

	from vetedge.services.billing import get_consultation_billing_settings

	settings = get_consultation_billing_settings()
	allowed_roles = set(ACCOUNTS_COLLECTION_ROLES)
	if settings.allow_doctor_collect_payment:
		allowed_roles |= DOCTOR_ROLES | FRONT_DESK_ROLES

	if user_has_any_role(user, allowed_roles):
		return True

	return _deny(
		raise_exception,
		"You are not allowed to collect payment for this invoice.",
		"internal_payment_access_blocked",
		reference_doctype="Sales Invoice",
		reference_name=invoice_name,
		user=user,
	)


def can_dispense(user: str | None, consultation, raise_exception: bool = False) -> bool:
	user = user or get_current_user()
	if not is_internal_staff_user(user):
		return _deny(
			raise_exception,
			"This action is only available to clinic staff.",
			"dispensary_access_blocked",
			user=user,
		)

	if not user_has_any_role(user, DISPENSARY_ROLES):
		return _deny(
			raise_exception,
			"Only dispensary staff can confirm stock issue.",
			"dispensary_access_blocked",
			reference_doctype=getattr(consultation, "doctype", "Veterinary Consultation"),
			reference_name=getattr(consultation, "name", consultation if isinstance(consultation, str) else None),
			user=user,
		)

	branch = consultation.service_branch if hasattr(consultation, "service_branch") else frappe.db.get_value(
		"Veterinary Consultation",
		consultation,
		"service_branch",
	)
	return can_access_branch_data(user, branch, raise_exception=raise_exception)


def can_request_lab_tests(user: str | None, context=None, raise_exception: bool = False) -> bool:
	user = user or get_current_user()
	if not is_internal_staff_user(user):
		return _deny(
			raise_exception,
			"This action is only available to clinic staff.",
			"lab_request_blocked",
			reference_doctype=getattr(context, "doctype", None) if context else None,
			reference_name=getattr(context, "name", None) if context else None,
			user=user,
		)

	if user_has_any_role(user, LAB_REQUEST_ROLES):
		return True

	return _deny(
		raise_exception,
		"Only a Veterinary Doctor can request lab tests.",
		"lab_request_blocked",
		reference_doctype=getattr(context, "doctype", None) if context else None,
		reference_name=getattr(context, "name", None) if context else None,
		user=user,
	)


def can_enter_lab_results(user: str | None, context=None, raise_exception: bool = False) -> bool:
	user = user or get_current_user()
	if not is_internal_staff_user(user):
		return _deny(
			raise_exception,
			"This action is only available to clinic staff.",
			"lab_result_entry_blocked",
			reference_doctype=getattr(context, "doctype", None) if context else None,
			reference_name=getattr(context, "name", None) if context else None,
			user=user,
		)

	if user_has_any_role(user, {*_role_group(ROLE_LAB_TECHNICIAN), *ELEVATED_ROLES}):
		return True

	if user_has_any_role(user, _role_group(ROLE_VETEDGE_DOCTOR)) and get_veterinary_settings_flag(
		"allow_doctor_lab_result_entry",
		default=True,
	):
		return True

	return _deny(
		raise_exception,
		"Only lab staff can enter or update lab results.",
		"lab_result_entry_blocked",
		reference_doctype=getattr(context, "doctype", None) if context else None,
		reference_name=getattr(context, "name", None) if context else None,
		user=user,
	)


def can_upload_lab_results(user: str | None, context=None, raise_exception: bool = False) -> bool:
	user = user or get_current_user()
	if not is_internal_staff_user(user):
		return _deny(
			raise_exception,
			"This action is only available to clinic staff.",
			"lab_result_upload_blocked",
			reference_doctype=getattr(context, "doctype", None) if context else None,
			reference_name=getattr(context, "name", None) if context else None,
			user=user,
		)

	if user_has_any_role(user, {*_role_group(ROLE_LAB_TECHNICIAN), *ELEVATED_ROLES}):
		return True

	if user_has_any_role(user, _role_group(ROLE_VETEDGE_DOCTOR)) and get_veterinary_settings_flag(
		"allow_doctor_lab_result_upload",
		default=False,
	):
		return True

	return _deny(
		raise_exception,
		"Only lab staff or permitted doctors can upload lab result files.",
		"lab_result_upload_blocked",
		reference_doctype=getattr(context, "doctype", None) if context else None,
		reference_name=getattr(context, "name", None) if context else None,
		user=user,
	)


def can_review_lab_results(user: str | None, context=None, raise_exception: bool = False) -> bool:
	user = user or get_current_user()
	if not is_internal_staff_user(user):
		return _deny(
			raise_exception,
			"This action is only available to clinic staff.",
			"lab_result_review_blocked",
			reference_doctype=getattr(context, "doctype", None) if context else None,
			reference_name=getattr(context, "name", None) if context else None,
			user=user,
		)

	if user_has_any_role(user, LAB_REVIEW_ROLES):
		return True

	return _deny(
		raise_exception,
		"Only a Veterinary Doctor can review lab results.",
		"lab_result_review_blocked",
		reference_doctype=getattr(context, "doctype", None) if context else None,
		reference_name=getattr(context, "name", None) if context else None,
		user=user,
	)


def _get_grooming_context_values(context, doctype: str | None = None) -> tuple[str | None, str | None, str | None, str | None]:
	if context is None:
		return None, None, None, None
	if isinstance(context, str):
		if not doctype:
			return None, None, doctype, context
		values = frappe.db.get_value(doctype, context, ["service_branch", "groomer"], as_dict=True) or {}
		return values.get("service_branch"), values.get("groomer"), doctype, context
	return (
		getattr(context, "service_branch", None),
		getattr(context, "groomer", None),
		getattr(context, "doctype", doctype),
		getattr(context, "name", None),
	)



def can_manage_grooming_appointments(user: str | None, context=None, raise_exception: bool = False) -> bool:
	user = user or get_current_user()
	branch, groomer, doctype, name = _get_grooming_context_values(context, "Pet Grooming Appointment")
	if not is_internal_staff_user(user):
		return _deny(
			raise_exception,
			"This action is only available to clinic staff.",
			"grooming_appointment_access_blocked",
			reference_doctype=doctype,
			reference_name=name,
			user=user,
		)
	if user_has_any_role(user, GROOMING_APPOINTMENT_ACTION_ROLES):
		return can_access_branch_data(user, branch, raise_exception=raise_exception)
	if user_has_any_role(user, GROOMER_ROLES):
		return can_access_branch_data(user, branch, raise_exception=raise_exception)
	return _deny(
		raise_exception,
		"Only front desk, assigned groomers, or grooming managers can manage grooming appointments.",
		"grooming_appointment_access_blocked",
		reference_doctype=doctype,
		reference_name=name,
		user=user,
	)



def can_create_grooming_session(user: str | None, context=None, raise_exception: bool = False) -> bool:
	user = user or get_current_user()
	branch, groomer, doctype, name = _get_grooming_context_values(context, "Pet Grooming Appointment")
	if not is_internal_staff_user(user):
		return _deny(
			raise_exception,
			"This action is only available to clinic staff.",
			"grooming_session_create_blocked",
			reference_doctype=doctype,
			reference_name=name,
			user=user,
		)
	if user_has_any_role(user, GROOMING_APPOINTMENT_ACTION_ROLES):
		return can_access_branch_data(user, branch, raise_exception=raise_exception)
	if user_has_any_role(user, GROOMER_ROLES):
		return can_access_branch_data(user, branch, raise_exception=raise_exception)
	return _deny(
		raise_exception,
		"Only front desk, assigned groomers, or grooming managers can create grooming sessions.",
		"grooming_session_create_blocked",
		reference_doctype=doctype,
		reference_name=name,
		user=user,
	)



def can_progress_grooming_session(user: str | None, context=None, raise_exception: bool = False) -> bool:
	user = user or get_current_user()
	branch, groomer, doctype, name = _get_grooming_context_values(context, "Pet Grooming Session")
	if not is_internal_staff_user(user):
		return _deny(
			raise_exception,
			"This action is only available to clinic staff.",
			"grooming_session_progress_blocked",
			reference_doctype=doctype,
			reference_name=name,
			user=user,
		)
	if user_has_any_role(user, GROOMING_MANAGER_ROLES):
		return can_access_branch_data(user, branch, raise_exception=raise_exception)
	if user_has_any_role(user, GROOMER_ROLES):
		if groomer != user:
			return _deny(
				raise_exception,
				"Only the assigned groomer can update grooming session progress.",
				"grooming_session_progress_blocked",
				reference_doctype=doctype,
				reference_name=name,
				user=user,
			)
		return can_access_branch_data(user, branch, raise_exception=raise_exception)
	return _deny(
		raise_exception,
		"Only assigned groomers or grooming managers can update grooming sessions.",
		"grooming_session_progress_blocked",
		reference_doctype=doctype,
		reference_name=name,
		user=user,
	)



def can_manage_grooming_billing(user: str | None, context=None, raise_exception: bool = False) -> bool:
	user = user or get_current_user()
	branch, _groomer, doctype, name = _get_grooming_context_values(context, "Pet Grooming Session")
	if not is_internal_staff_user(user):
		return _deny(
			raise_exception,
			"This action is only available to clinic staff.",
			"grooming_billing_blocked",
			reference_doctype=doctype,
			reference_name=name,
			user=user,
		)
	if user_has_any_role(user, GROOMING_BILLING_ROLES | GROOMER_ROLES):
		return can_access_branch_data(user, branch, raise_exception=raise_exception)
	return _deny(
		raise_exception,
		"Only front desk or grooming managers can create or update grooming billing.",
		"grooming_billing_blocked",
		reference_doctype=doctype,
		reference_name=name,
		user=user,
	)


def can_manage_role_bundles(user: str | None = None, raise_exception: bool = False) -> bool:
	user = user or get_current_user()
	if user_has_any_role(user, ROLE_BUNDLE_MANAGER_ROLES):
		return True
	return _deny(
		raise_exception,
		"Only authorized administrators can manage role bundles.",
		"role_bundle_management_blocked",
		user=user,
	)


def can_apply_role_bundle(user: str | None, target_user: str, raise_exception: bool = False) -> bool:
	user = user or get_current_user()
	if can_manage_role_bundles(user, raise_exception=raise_exception):
		return True
	return _deny(
		raise_exception,
		"Only authorized administrators can apply role bundles.",
		"role_bundle_apply_blocked",
		reference_doctype="User",
		reference_name=target_user,
		user=user,
	)


def validate_consultation_clinical_permissions(doc, user: str | None = None) -> None:
	user = user or get_current_user()
	if not user or user == "Guest":
		return
	if is_portal_owner_user(user):
		frappe.throw("This action is only available to clinic staff.", frappe.PermissionError)

	has_diagnosis = bool(doc.get("diagnoses"))
	has_treatment_plan = bool(doc.get("planned_treatments"))
	if not (has_diagnosis or has_treatment_plan):
		return

	if user_has_any_role(user, DOCTOR_ROLES):
		return

	log_operational_event(
		"consultation_clinical_entry",
		"blocked",
		user=user,
		reference_doctype=getattr(doc, "doctype", "Veterinary Consultation"),
		reference_name=getattr(doc, "name", None),
		details={"has_diagnosis": has_diagnosis, "has_treatment_plan": has_treatment_plan},
	)
	frappe.throw(
		"Only a Veterinary Doctor can capture diagnoses or prescribe treatment items.",
		frappe.PermissionError,
	)


def validate_role_bundle(doc) -> None:
	if not doc.bundle_name:
		frappe.throw("Bundle Name is required.", frappe.ValidationError)

	seen_roles: set[str] = set()
	for row in doc.get("roles") or []:
		if not row.role:
			frappe.throw("Each role bundle row must reference a Role.", frappe.ValidationError)
		if row.role in seen_roles:
			frappe.throw(f"Role {row.role} appears more than once in this bundle.", frappe.ValidationError)
		if not frappe.db.exists("Role", row.role):
			frappe.throw(f"Role {row.role} is not a valid ERPNext Role.", frappe.ValidationError)
		seen_roles.add(row.role)


def validate_branch_user_assignment(doc) -> None:
	user_type = frappe.db.get_value("User", doc.user, "user_type")
	if user_type != "System User":
		frappe.throw(
			f"User {doc.user} must be a System User before branch access can be assigned.",
			frappe.ValidationError,
		)
	_validate_branch_assignment_duplicate(
		doctype="Branch User Assignment",
		current_name=getattr(doc, "name", None),
		filters={"user": doc.user, "branch": doc.branch},
		label=f"User {doc.user} is already assigned to Branch {doc.branch}.",
	)


def validate_branch_practitioner_assignment(doc) -> None:
	validate_doctor_user(doc.practitioner, label="Practitioner")
	_validate_branch_assignment_duplicate(
		doctype="Branch Practitioner Assignment",
		current_name=getattr(doc, "name", None),
		filters={"practitioner": doc.practitioner, "branch": doc.branch},
		label=f"Practitioner {doc.practitioner} is already assigned to Branch {doc.branch}.",
	)


def validate_doctor_user(user: str | None, label: str = "Practitioner") -> None:
	if not user:
		return

	if user_has_any_role(user, DOCTOR_ROLES):
		return

	frappe.throw(
		f"{label} {user} must have the VetEdge Doctor role.",
		frappe.ValidationError,
	)


@frappe.whitelist()
@frappe.validate_and_sanitize_search_inputs
def get_veterinary_doctor_users(doctype, txt, searchfield, start, page_len, filters):
	search = f"%{txt}%"
	return frappe.db.sql(
		"""
		SELECT DISTINCT
			user.name,
			COALESCE(NULLIF(user.full_name, ''), user.email, user.name)
		FROM `tabUser` user
		INNER JOIN `tabHas Role` has_role
			ON has_role.parent = user.name
			AND has_role.parenttype = 'User'
		WHERE user.enabled = 1
			AND has_role.role = 'VetEdge Doctor'
			AND (
				user.name LIKE %(search)s
				OR user.full_name LIKE %(search)s
				OR user.email LIKE %(search)s
			)
		ORDER BY COALESCE(NULLIF(user.full_name, ''), user.email, user.name) ASC
		LIMIT %(start)s, %(page_len)s
		""",
		{
			"search": search,
			"start": start,
			"page_len": page_len,
		},
	)


@frappe.whitelist()
@frappe.validate_and_sanitize_search_inputs
def get_system_users(doctype, txt, searchfield, start, page_len, filters):
	search = f"%{txt}%"
	return frappe.db.sql(
		"""
		SELECT
			user.name,
			COALESCE(NULLIF(user.full_name, ''), user.email, user.name)
		FROM `tabUser` user
		WHERE user.enabled = 1
			AND user.user_type = 'System User'
			AND (
				user.name LIKE %(search)s
				OR user.full_name LIKE %(search)s
				OR user.email LIKE %(search)s
			)
		ORDER BY COALESCE(NULLIF(user.full_name, ''), user.email, user.name) ASC
		LIMIT %(start)s, %(page_len)s
		""",
		{
			"search": search,
			"start": start,
			"page_len": page_len,
		},
	)


@frappe.whitelist()
@frappe.validate_and_sanitize_search_inputs
def get_grooming_staff_users(doctype, txt, searchfield, start, page_len, filters):
	search = f"%{txt}%"
	roles = (
		ROLE_SYSTEM_MANAGER,
		ROLE_VETEDGE_ADMINISTRATOR,
		ROLE_VETEDGE_GROOMER,
		ROLE_BRANCH_MANAGER,
		"VetEdge Branch Manager",
	)
	placeholders = ", ".join(["%s"] * len(roles))
	return frappe.db.sql(
		f"""
		SELECT DISTINCT
			user.name,
			COALESCE(NULLIF(user.full_name, ''), user.email, user.name)
		FROM `tabUser` user
		INNER JOIN `tabHas Role` has_role
			ON has_role.parent = user.name
			AND has_role.parenttype = 'User'
		WHERE user.enabled = 1
			AND user.user_type = 'System User'
			AND has_role.role IN ({placeholders})
			AND (
				user.name LIKE %s
				OR user.full_name LIKE %s
				OR user.email LIKE %s
			)
		ORDER BY COALESCE(NULLIF(user.full_name, ''), user.email, user.name) ASC
		LIMIT %s, %s
		""",
		(*roles, search, search, search, start, page_len),
	)


@frappe.whitelist()
@frappe.validate_and_sanitize_search_inputs
def get_vaccination_staff_users(doctype, txt, searchfield, start, page_len, filters):
	search = f"%{txt}%"
	roles = (
		ROLE_SYSTEM_MANAGER,
		ROLE_VETEDGE_ADMINISTRATOR,
		ROLE_VETEDGE_DOCTOR,
		ROLE_VETEDGE_NURSE,
		ROLE_VETERINARY_NURSE,
	)
	placeholders = ", ".join(["%s"] * len(roles))
	return frappe.db.sql(
		f"""
		SELECT DISTINCT
			user.name,
			COALESCE(NULLIF(user.full_name, ''), user.email, user.name)
		FROM `tabUser` user
		INNER JOIN `tabHas Role` has_role
			ON has_role.parent = user.name
			AND has_role.parenttype = 'User'
		WHERE user.enabled = 1
			AND user.user_type = 'System User'
			AND has_role.role IN ({placeholders})
			AND (
				user.name LIKE %s
				OR user.full_name LIKE %s
				OR user.email LIKE %s
			)
		ORDER BY COALESCE(NULLIF(user.full_name, ''), user.email, user.name) ASC
		LIMIT %s, %s
		""",
		(*roles, search, search, search, start, page_len),
	)


def _combine_query_conditions(*conditions: str | None) -> str | None:
	parts = [f"({condition})" for condition in conditions if condition]
	if not parts:
		return None
	return " and ".join(parts)



def get_grooming_query_condition(doctype: str, user: str | None = None, *, allow_front_desk: bool = False) -> str | None:
	user = user or get_current_user()
	if is_portal_owner_user(user):
		return "1=0"
	if not user or user == "Guest":
		return "1=0"
	if user_has_global_branch_access(user):
		return None
	branch_condition = get_branch_scoped_query_condition(doctype, "service_branch", user=user)
	if user_has_any_role(user, GROOMING_MANAGER_ROLES):
		return branch_condition
	if allow_front_desk and user_has_any_role(user, FRONT_DESK_ROLES):
		return branch_condition
	if user_has_any_role(user, GROOMER_ROLES):
		return branch_condition
	return "1=0"



def has_grooming_document_permission(doc, doctype: str, permission_type: str | None = None, user: str | None = None, *, allow_front_desk: bool = False) -> bool:
	user = user or get_current_user()
	if is_portal_owner_user(user):
		return False
	if permission_type == "create":
		return True
	name = doc if isinstance(doc, str) else getattr(doc, "name", None)
	if _is_unsaved_document(doc, doctype, name):
		return True
	if permission_type in {None, "write"} and not name:
		return True
	if not user or user == "Guest":
		return False
	if user_has_global_branch_access(user):
		return True
	branch_allowed = has_document_permission(doc, doctype, "service_branch", permission_type=permission_type, user=user)
	if branch_allowed is False:
		return False
	if user_has_any_role(user, GROOMING_MANAGER_ROLES):
		return True
	if allow_front_desk and user_has_any_role(user, FRONT_DESK_ROLES):
		return True
	if user_has_any_role(user, GROOMER_ROLES):
		return True
	return False


def get_branch_scoped_query_condition(doctype: str, branch_field: str, user: str | None = None) -> str | None:
	user = user or get_current_user()
	if is_portal_owner_user(user):
		from vetedge.services import portal_access

		owner_query_map = {
			"Veterinary Patient": portal_access.get_veterinary_patient_query,
			"Veterinary Appointment": portal_access.get_veterinary_appointment_query,
			"Veterinary Consultation": portal_access.get_veterinary_consultation_query,
			"Veterinary Vital Signs": portal_access.get_veterinary_vital_signs_query,
			"Sales Invoice": portal_access.get_sales_invoice_query,
		}
		return owner_query_map.get(doctype, lambda user=None: None)(user=user)

	if not user or user == "Guest" or user_has_global_branch_access(user):
		return None

	branches = get_assigned_branches(user)
	if not branches:
		return None

	quoted = ", ".join(frappe.db.escape(branch) for branch in branches)
	return (
		f"(IFNULL(`tab{doctype}`.`{branch_field}`, '') = '' "
		f"OR `tab{doctype}`.`{branch_field}` in ({quoted}))"
	)


def has_document_permission(doc, doctype: str, branch_field: str, permission_type: str | None = None, user: str | None = None) -> bool | None:
	user = user or get_current_user()
	if is_portal_owner_user(user):
		if permission_type and permission_type not in PORTAL_ALLOWED_PERMISSION_TYPES:
			return False
		from vetedge.services import portal_access

		owner_permission_map = {
			"Veterinary Patient": portal_access.has_veterinary_patient_permission,
			"Veterinary Appointment": portal_access.has_veterinary_appointment_permission,
			"Veterinary Consultation": portal_access.has_veterinary_consultation_permission,
			"Veterinary Vital Signs": portal_access.has_veterinary_vital_signs_permission,
			"Sales Invoice": portal_access.has_sales_invoice_permission,
		}
		return owner_permission_map.get(doctype, lambda *args, **kwargs: None)(doc, user=user, permission_type=permission_type)

	if permission_type == "create":
		return None

	if not user or user == "Guest" or user_has_global_branch_access(user):
		return None

	branches = get_assigned_branches(user)
	if not branches:
		return None

	name = doc if isinstance(doc, str) else getattr(doc, "name", None)
	if _is_unsaved_document(doc, doctype, name):
		return None
	if not name:
		return None
	branch = (
		getattr(doc, branch_field, None)
		if not isinstance(doc, str)
		else frappe.db.get_value(doctype, name, branch_field)
	)
	if not branch:
		return True
	return branch in branches


def is_document_owner(doc, doctype: str, user: str | None = None) -> bool:
	user = user or get_current_user()
	if not user or user == "Guest":
		return False

	if not isinstance(doc, str):
		owner = getattr(doc, "owner", None)
		if owner:
			return owner == user
		name = getattr(doc, "name", None)
	else:
		name = doc

	if not name:
		return False

	return frappe.db.get_value(doctype, name, "owner") == user


def get_veterinary_patient_query(user: str | None = None) -> str | None:
	user = user or get_current_user()
	if is_portal_owner_user(user):
		from vetedge.services import portal_access

		return portal_access.get_veterinary_patient_query(user=user)

	if not is_patient_branch_restriction_enabled():
		return None

	if not user or user == "Guest" or user_has_global_branch_access(user):
		return None

	branches = get_assigned_branches(user)
	if not branches:
		return "1=0"

	quoted = ", ".join(frappe.db.escape(branch) for branch in branches)
	return (
		"(IFNULL(`tabVeterinary Patient`.`default_branch`, '') = '' "
		f"OR `tabVeterinary Patient`.`default_branch` in ({quoted}))"
	)


def get_veterinary_appointment_query(user: str | None = None) -> str | None:
	return get_branch_scoped_query_condition("Veterinary Appointment", "branch", user=user)


def get_veterinary_missed_appointment_query(user: str | None = None) -> str | None:
	return get_branch_scoped_query_condition("Veterinary Missed Appointment", "branch", user=user)


def get_veterinary_consultation_query(user: str | None = None) -> str | None:
	return get_branch_scoped_query_condition("Veterinary Consultation", "service_branch", user=user)


def get_veterinary_vital_signs_query(user: str | None = None) -> str | None:
	return get_branch_scoped_query_condition("Veterinary Vital Signs", "service_branch", user=user)


def get_veterinary_lab_order_query(user: str | None = None) -> str | None:
	user = user or get_current_user()
	if is_portal_owner_user(user):
		return "1=0"
	return get_branch_scoped_query_condition("Veterinary Lab Order", "service_branch", user=user)


def get_veterinary_vaccination_record_query(user: str | None = None) -> str | None:
	user = user or get_current_user()
	if is_portal_owner_user(user):
		return "1=0"
	return get_branch_scoped_query_condition("Veterinary Vaccination Record", "service_branch", user=user)



def get_pet_grooming_appointment_query(user: str | None = None) -> str | None:
	return get_grooming_query_condition("Pet Grooming Appointment", user=user, allow_front_desk=True)



def get_pet_grooming_session_query(user: str | None = None) -> str | None:
	return get_grooming_query_condition("Pet Grooming Session", user=user, allow_front_desk=True)


def get_veterinary_guest_booking_request_query(user: str | None = None) -> str | None:
	return get_branch_scoped_query_condition("Veterinary Guest Booking Request", "preferred_branch", user=user)


def get_sales_invoice_query(user: str | None = None) -> str | None:
	if frappe.get_meta("Sales Invoice").has_field("branch"):
		return get_branch_scoped_query_condition("Sales Invoice", "branch", user=user)
	return None


def get_notification_admin_only_query(user: str | None = None) -> str | None:
	return None if is_notification_admin(user) else "1=0"


def has_veterinary_patient_permission(doc, user: str | None = None, permission_type: str | None = None) -> bool:
	user = user or get_current_user()
	if is_portal_owner_user(user):
		from vetedge.services import portal_access

		return bool(portal_access.has_veterinary_patient_permission(doc, user=user, permission_type=permission_type))

	if permission_type == "create" or not is_patient_branch_restriction_enabled():
		return True

	if not user or user == "Guest":
		return False

	if user_has_global_branch_access(user):
		return True

	branches = get_assigned_branches(user)
	if not branches:
		return False

	name = doc if isinstance(doc, str) else getattr(doc, "name", None)
	if _is_unsaved_document(doc, "Veterinary Patient", name):
		return True
	if not name:
		return True

	branch = (
		getattr(doc, "default_branch", None)
		if not isinstance(doc, str)
		else frappe.db.get_value("Veterinary Patient", name, "default_branch")
	)
	return bool(not branch or branch in branches)


def has_veterinary_appointment_permission(doc, user: str | None = None, permission_type: str | None = None) -> bool:
	user = user or get_current_user()
	if is_portal_owner_user(user):
		return False
	if user_has_global_branch_access(user):
		return True

	name = doc if isinstance(doc, str) else getattr(doc, "name", None)
	if permission_type == "create":
		return True
	if _is_unsaved_document(doc, "Veterinary Appointment", name):
		return True
	if permission_type in {None, "write"} and not name:
		return True
	if permission_type in OWNER_READ_PERMISSION_TYPES and is_document_owner(doc, "Veterinary Appointment", user=user):
		return True

	result = has_document_permission(doc, "Veterinary Appointment", "branch", permission_type=permission_type, user=user)
	return True if result is None else result


def has_veterinary_missed_appointment_permission(doc, user: str | None = None, permission_type: str | None = None) -> bool:
	user = user or get_current_user()
	if is_portal_owner_user(user):
		return False
	if user_has_global_branch_access(user):
		return True

	name = doc if isinstance(doc, str) else getattr(doc, "name", None)
	if permission_type == "create":
		return True
	if _is_unsaved_document(doc, "Veterinary Missed Appointment", name):
		return True
	if permission_type in {None, "write"} and not name:
		return True
	if permission_type in OWNER_READ_PERMISSION_TYPES and is_document_owner(doc, "Veterinary Missed Appointment", user=user):
		return True

	result = has_document_permission(doc, "Veterinary Missed Appointment", "branch", permission_type=permission_type, user=user)
	return True if result is None else result


def has_veterinary_consultation_permission(doc, user: str | None = None, permission_type: str | None = None) -> bool:
	user = user or get_current_user()
	if is_portal_owner_user(user):
		return False
	if user_has_global_branch_access(user):
		return True

	name = doc if isinstance(doc, str) else getattr(doc, "name", None)
	if permission_type == "create":
		return True
	if _is_unsaved_document(doc, "Veterinary Consultation", name):
		return True
	if permission_type in {None, "write"} and not name:
		return True
	if permission_type in OWNER_READ_PERMISSION_TYPES and is_document_owner(doc, "Veterinary Consultation", user=user):
		return True

	result = has_document_permission(doc, "Veterinary Consultation", "service_branch", permission_type=permission_type, user=user)
	return True if result is None else result


def has_veterinary_vital_signs_permission(doc, user: str | None = None, permission_type: str | None = None) -> bool:
	user = user or get_current_user()
	if is_portal_owner_user(user):
		return False
	if user_has_global_branch_access(user):
		return True

	name = doc if isinstance(doc, str) else getattr(doc, "name", None)
	if permission_type == "create":
		return True
	if _is_unsaved_document(doc, "Veterinary Vital Signs", name):
		return True
	if permission_type in {None, "write"} and not name:
		return True
	if permission_type in OWNER_READ_PERMISSION_TYPES and is_document_owner(doc, "Veterinary Vital Signs", user=user):
		return True

	result = has_document_permission(doc, "Veterinary Vital Signs", "service_branch", permission_type=permission_type, user=user)
	return True if result is None else result


def has_veterinary_lab_order_permission(doc, user: str | None = None, permission_type: str | None = None) -> bool:
	user = user or get_current_user()
	if is_portal_owner_user(user):
		return False
	if user_has_global_branch_access(user):
		return True

	name = doc if isinstance(doc, str) else getattr(doc, "name", None)
	if permission_type == "create":
		return True
	if _is_unsaved_document(doc, "Veterinary Lab Order", name):
		return True
	if permission_type in {None, "write"} and not name:
		return True
	if permission_type in OWNER_READ_PERMISSION_TYPES and is_document_owner(doc, "Veterinary Lab Order", user=user):
		return True

	result = has_document_permission(doc, "Veterinary Lab Order", "service_branch", permission_type=permission_type, user=user)
	return True if result is None else result


def has_veterinary_vaccination_record_permission(doc, user: str | None = None, permission_type: str | None = None) -> bool:
	user = user or get_current_user()
	if is_portal_owner_user(user):
		return False
	if user_has_global_branch_access(user):
		return True

	name = doc if isinstance(doc, str) else getattr(doc, "name", None)
	if permission_type == "create":
		return True
	if _is_unsaved_document(doc, "Veterinary Vaccination Record", name):
		return True
	if permission_type in {None, "write"} and not name:
		return True
	if permission_type in OWNER_READ_PERMISSION_TYPES and is_document_owner(doc, "Veterinary Vaccination Record", user=user):
		return True

	result = has_document_permission(doc, "Veterinary Vaccination Record", "service_branch", permission_type=permission_type, user=user)
	return True if result is None else result



def has_pet_grooming_appointment_permission(doc, user: str | None = None, permission_type: str | None = None) -> bool | None:
	return has_grooming_document_permission(doc, "Pet Grooming Appointment", permission_type=permission_type, user=user, allow_front_desk=True)



def has_pet_grooming_session_permission(doc, user: str | None = None, permission_type: str | None = None) -> bool | None:
	return has_grooming_document_permission(doc, "Pet Grooming Session", permission_type=permission_type, user=user, allow_front_desk=True)


def has_sales_invoice_permission(doc, user: str | None = None, permission_type: str | None = None) -> bool | None:
	user = user or get_current_user()
	if is_portal_owner_user(user):
		return has_document_permission(doc, "Sales Invoice", "branch", permission_type=permission_type, user=user)

	if permission_type in {"create", "read", "write"}:
		return True

	if not frappe.get_meta("Sales Invoice").has_field("branch"):
		return True

	result = has_document_permission(doc, "Sales Invoice", "branch", permission_type=permission_type, user=user)
	return True if result is None else result


def get_veterinary_notification_item_query(user: str | None = None) -> str | None:
	user = user or get_current_user()
	if is_notification_admin(user):
		return None
	if not user or user == "Guest":
		return "1=0"
	return f"`tabVeterinary Notification Item`.`recipient_user` = {frappe.db.escape(user)}"


def has_veterinary_notification_item_permission(doc, user: str | None = None, permission_type: str | None = None) -> bool | None:
	user = user or get_current_user()
	if is_notification_admin(user):
		return True
	if not user or user == "Guest":
		return False
	if permission_type == "create":
		return False
	if permission_type == "delete":
		return False
	recipient_user = getattr(doc, "recipient_user", None)
	if isinstance(doc, str):
		recipient_user = frappe.db.get_value("Veterinary Notification Item", doc, "recipient_user")
	return recipient_user == user


def has_notification_admin_permission(doc, user: str | None = None, permission_type: str | None = None) -> bool:
	if permission_type == "create":
		return is_notification_admin(user)
	return is_notification_admin(user)


def _validate_branch_assignment_duplicate(doctype: str, current_name: str | None, filters: dict, label: str) -> None:
	if not all(filters.values()):
		frappe.throw("Branch assignments must include both user/practitioner and branch.", frappe.ValidationError)
	duplicates = frappe.get_all(doctype, filters=filters, pluck="name", limit=1)
	if duplicates and duplicates[0] != current_name:
		frappe.throw(label, frappe.ValidationError)


def _is_unsaved_document(doc, doctype: str, name: str | None) -> bool:
	if not name:
		return True

	if isinstance(doc, str):
		return name.startswith("new-") or not _document_exists(doctype, name)

	if getattr(doc, "__islocal", False):
		return True

	flags = getattr(doc, "flags", None)
	if getattr(flags, "in_insert", False):
		return True

	return name.startswith("new-") or not _document_exists(doctype, name)


def _document_exists(doctype: str, name: str) -> bool:
	try:
		return bool(frappe.db.exists(doctype, name))
	except RuntimeError:
		return False


def _deny(
	raise_exception: bool,
	message: str,
	action: str,
	reference_doctype: str | None = None,
	reference_name: str | None = None,
	details: dict | None = None,
	user: str | None = None,
) -> bool:
	log_operational_event(
		action,
		"blocked",
		user=user,
		reference_doctype=reference_doctype,
		reference_name=reference_name,
		details=details,
	)
	if raise_exception:
		frappe.throw(message, frappe.PermissionError)
	return False


def _evaluate_frappe_permission_debug(
	doctype: str,
	user: str | None = None,
	ptype: str = "read",
	doc=None,
) -> tuple[bool, list[str]]:
	allowed = frappe.permissions.has_permission(
		doctype,
		ptype=ptype,
		doc=doc,
		user=user,
		print_logs=False,
		debug=True,
	)
	return bool(allowed), list(frappe.permissions._pop_debug_log())


def _classify_invoice_permission_debug_logs(logs: list[str]) -> str:
	text = " ".join(logs or [])
	if (
		"User doesn't have access to this document because of User Permissions" in text
		or "User has no permissions because of User Permissions" in text
		or "because of User Permissions" in text
		or "Not allowed for" in text
	):
		return "user_permission"
	if "linked to" in text:
		return "user_permission"
	if "doctype access via role permission" in text:
		return "erpnext_role_permission"
	if "Permission check failed from role permission system" in text:
		return "erpnext_role_permission"
	if "Not allowed via controller permission check" in text:
		return "contextual_restriction"
	return "erpnext_permission"


def _build_invoice_permission_block(invoice_name: str, category: str, logs: list[str]) -> dict:
	if category == "user_permission":
		message = (
			f"Sales Invoice {invoice_name} is blocked by ERPNext User Permission rules. "
			"Review User Permission records affecting Sales Invoice or linked doctypes such as "
			"Customer, Company, Branch, Cost Center, or Territory."
		)
	elif category == "erpnext_role_permission":
		runtime_roles = sorted(get_user_roles())
		configured_read_roles = get_sales_invoice_read_roles()
		matching_roles = sorted(set(runtime_roles) & set(configured_read_roles))
		message = (
			f"Sales Invoice {invoice_name} failed the ERPNext DocType read check. "
			f"Runtime user roles: {', '.join(runtime_roles) or 'none'}. "
			f"Sales Invoice read roles configured on this site: {', '.join(configured_read_roles) or 'none'}. "
			f"Matching read roles on the current user: {', '.join(matching_roles) or 'none'}."
		)
	elif category == "contextual_restriction":
		message = (
			f"Sales Invoice {invoice_name} is blocked by a scripted permission check. "
			"Review VetEdge or ERPNext controller-level permission hooks for this invoice."
		)
	else:
		message = (
			f"Sales Invoice {invoice_name} is blocked by ERPNext document access rules."
		)

	if logs:
		message = f"{message} Diagnostic: {logs[-1]}"

	return {
		"allowed": False,
		"category": category,
		"message": message,
		"can_open_full_form": False,
	}


def get_sales_invoice_read_roles() -> list[str]:
	meta = frappe.get_meta("Sales Invoice")
	return sorted(
		{
			row.role
			for row in getattr(meta, "permissions", [])
			if getattr(row, "role", None) and frappe.utils.cint(getattr(row, "read", 0)) and not frappe.utils.cint(getattr(row, "permlevel", 0))
		}
	)
