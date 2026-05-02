from __future__ import annotations

from dataclasses import dataclass

import frappe
from frappe import _
from frappe.utils import cint, flt, nowdate

from vetedge.install.custom_fields import BRANCH_COST_CENTER_FIELD
from vetedge.services.permissions import can_access_patient
from vetedge.services.portal_access import require_internal_user


SETTINGS_DOCTYPE = "Veterinary Settings"
PAID_STATUS = "Registration Paid"
REGISTERED_STATUS = "Registered"
AWAITING_PAYMENT_STATUS = "Awaiting Registration Payment"


@dataclass(frozen=True)
class RegistrationBillingRule:
	enabled: bool
	branch: str | None
	registration_item: str | None
	registration_fee: float
	auto_create_invoice: bool
	require_payment_before_first_consultation: bool
	enforce_cost_center: bool = False


def validate_registration_settings(settings) -> None:
	if settings.default_registration_fee not in (None, "") and flt(settings.default_registration_fee) < 0:
		frappe.throw("Default Registration Fee cannot be negative.", frappe.ValidationError)

	validate_registration_item(settings.default_registration_item, "Default Registration Item")

	active_branches = set()
	for rule in settings.get("branch_registration_rules") or []:
		if rule.registration_fee not in (None, "") and flt(rule.registration_fee) < 0:
			frappe.throw("Branch Registration Fee cannot be negative.", frappe.ValidationError)

		validate_registration_item(rule.registration_item, "Branch Registration Item")

		if not rule.is_active:
			continue

		if rule.branch in active_branches:
			frappe.throw(
				f"Only one active registration rule is allowed per branch: {rule.branch}",
				frappe.ValidationError,
			)
		active_branches.add(rule.branch)


def validate_registration_item(item_code: str | None, label: str) -> None:
	if not item_code:
		return

	item = frappe.db.get_value("Item", item_code, ["disabled", "is_sales_item", "is_stock_item"], as_dict=True)
	if not item:
		frappe.throw(f"{label} must be a valid Item.", frappe.ValidationError)

	if item.disabled:
		frappe.throw(f"{label} cannot be a disabled Item.", frappe.ValidationError)

	if not item.is_sales_item:
		frappe.throw(f"{label} must be a sales Item.", frappe.ValidationError)

	if item.is_stock_item:
		frappe.throw(f"{label} must be a non-stock service Item.", frappe.ValidationError)


def validate_patient_registration(doc) -> None:
	rule = get_registration_rule(doc.default_branch)
	if not rule.enabled:
		doc.registration_status = REGISTERED_STATUS
		return

	if not doc.default_branch:
		frappe.throw("Default Branch is required when registration billing is enabled.", frappe.ValidationError)

	if not doc.primary_owner:
		frappe.throw("Primary Owner is required when registration billing is enabled.", frappe.ValidationError)

	if not rule.registration_item:
		frappe.throw("Registration Item is required when registration billing is enabled.", frappe.ValidationError)

	if flt(rule.registration_fee) < 0:
		frappe.throw("Registration Fee cannot be negative.", frappe.ValidationError)

	doc.registration_fee_amount = flt(rule.registration_fee)
	if not doc.registration_status:
		doc.registration_status = REGISTERED_STATUS


def handle_patient_registration_insert(doc) -> None:
	rule = get_registration_rule(doc.default_branch)
	if not rule.enabled:
		set_patient_registration_fields(doc.name, registration_status=REGISTERED_STATUS)
		return

	validate_patient_registration(doc)
	if not rule.auto_create_invoice:
		set_patient_registration_fields(
			doc.name,
			registration_status=REGISTERED_STATUS,
			registration_fee_amount=rule.registration_fee,
		)
		return

	if doc.registration_invoice:
		update_patient_registration_payment_status(doc.name, doc.registration_invoice)
		return

	existing_invoice = get_existing_registration_invoice(doc.name)
	if existing_invoice:
		update_patient_registration_payment_status(doc.name, existing_invoice)
		return

	invoice = create_registration_invoice(doc, rule)
	set_patient_registration_fields(
		doc.name,
		registration_invoice=invoice.name,
		registration_status=AWAITING_PAYMENT_STATUS,
		registration_billed=1,
		registration_fee_amount=rule.registration_fee,
	)


def get_registration_rule(branch: str | None) -> RegistrationBillingRule:
	settings = get_registration_settings()
	branch_rule = get_branch_registration_rule(settings, branch)

	return RegistrationBillingRule(
		enabled=bool(cint(settings.get("enable_registration_billing"))),
		branch=branch,
		registration_item=get_rule_value(branch_rule, "registration_item", settings.get("default_registration_item")),
		registration_fee=flt(get_rule_value(branch_rule, "registration_fee", settings.get("default_registration_fee"))),
		auto_create_invoice=bool(
			cint(
				get_rule_value(
					branch_rule,
					"auto_create_invoice_on_registration",
					settings.get("auto_create_invoice_on_registration"),
				)
			)
		),
		require_payment_before_first_consultation=bool(
			cint(
				get_rule_value(
					branch_rule,
					"require_payment_before_first_consultation",
					settings.get("require_payment_before_first_consultation"),
				)
			)
		),
		enforce_cost_center=bool(cint(settings.get("enforce_cost_center_on_billing"))),
	)


def get_registration_settings():
	if not frappe.db.exists("DocType", SETTINGS_DOCTYPE):
		return frappe._dict()

	return frappe.get_single(SETTINGS_DOCTYPE)


def get_branch_registration_rule(settings, branch: str | None):
	if not branch:
		return None

	for rule in settings.get("branch_registration_rules") or []:
		if rule.branch == branch and rule.is_active:
			return rule

	return None


def get_rule_value(rule, fieldname: str, fallback):
	if not rule:
		return fallback

	value = rule.get(fieldname)
	if value in (None, ""):
		return fallback

	return value


def create_registration_invoice(doc, rule: RegistrationBillingRule):
	cost_center = get_billing_cost_center(doc.default_branch, required=rule.enforce_cost_center)
	invoice = frappe.get_doc(
		{
			"doctype": "Sales Invoice",
			"customer": doc.primary_owner,
			"company": get_default_company(),
			"posting_date": nowdate(),
			"due_date": nowdate(),
			"items": [
				{
					"item_code": rule.registration_item,
					"cost_center": cost_center,
					"qty": 1,
					"rate": rule.registration_fee,
				}
			],
		}
	)

	if doc.default_branch and frappe.get_meta("Sales Invoice").has_field("branch"):
		invoice.branch = doc.default_branch

	if cost_center and frappe.get_meta("Sales Invoice").has_field("cost_center"):
		invoice.cost_center = cost_center

	invoice.insert(ignore_permissions=True)
	return invoice


def validate_registration_payment_before_first_consultation(
	patient: str,
	current_consultation: str | None = None,
) -> None:
	if not patient:
		return

	patient_doc = frappe.db.get_value(
		"Veterinary Patient",
		patient,
		["name", "default_branch", "registration_status", "registration_invoice"],
		as_dict=True,
	)
	if not patient_doc:
		return

	rule = get_registration_rule(patient_doc.default_branch)
	if not rule.enabled or not rule.require_payment_before_first_consultation:
		return

	if not is_first_consultation_for_patient(patient, current_consultation=current_consultation):
		return

	active_invoice_name = get_active_registration_invoice_name(patient_doc.name)
	if active_invoice_name:
		invoice = frappe.get_doc("Sales Invoice", active_invoice_name)
		update_patient_registration_payment_status(patient_doc.name, invoice)
		if is_invoice_paid(invoice):
			return

		frappe.throw(
			_("Registration invoice {0} must be paid before the first consultation can proceed.").format(
				active_invoice_name
			),
			frappe.ValidationError,
		)

	if patient_doc.registration_invoice:
		frappe.throw(
			_("Registration invoice {0} must be created again and paid before the first consultation can proceed.").format(
				patient_doc.registration_invoice
			),
			frappe.ValidationError,
		)

	frappe.throw(
		_("A registration invoice must be created and paid before the first consultation can proceed."),
		frappe.ValidationError,
	)


def is_first_consultation_for_patient(patient: str, current_consultation: str | None = None) -> bool:
	filters = {
		"patient": patient,
		"status": ["!=", "Cancelled"],
	}
	if current_consultation:
		filters["name"] = ["!=", current_consultation]

	return not bool(
		frappe.get_all(
			"Veterinary Consultation",
			filters=filters,
			fields=["name"],
			limit=1,
		)
	)


def get_billing_cost_center(branch: str | None, required: bool = True) -> str | None:
	if not branch:
		return None

	cost_center = get_branch_cost_center(branch)
	if cost_center:
		return cost_center

	if required:
		frappe.throw(
			f"Cost Center is required for Branch {branch} before billing documents can be created.",
			frappe.ValidationError,
		)

	return None


def get_branch_cost_center(branch: str) -> str | None:
	branch_meta = frappe.get_meta("Branch")
	for fieldname in ("cost_center", BRANCH_COST_CENTER_FIELD):
		if branch_meta.has_field(fieldname):
			cost_center = frappe.db.get_value("Branch", branch, fieldname)
			if cost_center:
				return cost_center

	return None


def get_existing_registration_invoice(patient: str) -> str | None:
	return frappe.db.get_value("Veterinary Patient", patient, "registration_invoice")


def get_active_registration_invoice_name(patient: str) -> str | None:
	invoice_name = get_existing_registration_invoice(patient)
	if not invoice_name:
		return None

	docstatus = frappe.db.get_value("Sales Invoice", invoice_name, "docstatus")
	if cint(docstatus) == 2:
		return None

	return invoice_name


def get_default_company() -> str | None:
	try:
		from erpnext import get_default_company as erpnext_get_default_company

		return erpnext_get_default_company() or get_first_company()
	except Exception:
		return get_first_company()


def get_first_company() -> str | None:
	companies = frappe.get_all("Company", pluck="name", limit=1)
	return companies[0] if companies else None


def set_patient_registration_fields(patient: str, **values) -> None:
	if not values:
		return

	frappe.db.set_value("Veterinary Patient", patient, values, update_modified=False)


@frappe.whitelist()
def is_registration_billing_enabled_for_ui() -> bool:
	require_internal_user()
	return bool(get_registration_rule(None).enabled)


@frappe.whitelist()
def create_manual_registration_invoice(patient: str) -> dict:
	require_internal_user()
	can_access_patient(frappe.session.user, patient, raise_exception=True)

	patient_doc = frappe.get_doc("Veterinary Patient", patient)
	rule = get_registration_rule(patient_doc.default_branch)
	if not rule.enabled:
		frappe.throw(_("Registration billing is not enabled."), frappe.ValidationError)

	validate_patient_registration(patient_doc)
	active_invoice_name = get_active_registration_invoice_name(patient_doc.name)
	if active_invoice_name:
		update_patient_registration_payment_status(patient_doc.name, active_invoice_name)
		return {
			"patient": patient_doc.name,
			"invoice": active_invoice_name,
			"created": False,
			"status": frappe.db.get_value("Veterinary Patient", patient_doc.name, "registration_status"),
		}

	invoice = create_registration_invoice(patient_doc, rule)
	set_patient_registration_fields(
		patient_doc.name,
		registration_invoice=invoice.name,
		registration_status=AWAITING_PAYMENT_STATUS,
		registration_billed=1,
		registration_fee_amount=rule.registration_fee,
	)
	return {
		"patient": patient_doc.name,
		"invoice": invoice.name,
		"created": True,
		"status": AWAITING_PAYMENT_STATUS,
	}


def update_registration_status_from_invoice(doc, method: str | None = None) -> None:
	patients = frappe.get_all(
		"Veterinary Patient",
		filters={"registration_invoice": doc.name},
		pluck="name",
	)

	for patient in patients:
		update_patient_registration_payment_status(patient, doc)


def update_registration_status_from_payment_entry(doc, method: str | None = None) -> None:
	for reference in doc.get("references") or []:
		if reference.reference_doctype != "Sales Invoice" or not reference.reference_name:
			continue

		invoice = frappe.get_doc("Sales Invoice", reference.reference_name)
		update_registration_status_from_invoice(invoice, method)


def update_patient_registration_payment_status(patient: str, invoice) -> None:
	if isinstance(invoice, str):
		invoice = frappe.get_doc("Sales Invoice", invoice)

	if is_invoice_paid(invoice):
		set_patient_registration_fields(
			patient,
			registration_invoice=invoice.name,
			registration_status=PAID_STATUS,
			registration_billed=1,
		)
		return

	if cint(invoice.docstatus) == 2:
		set_patient_registration_fields(
			patient,
			registration_invoice=None,
			registration_status=REGISTERED_STATUS,
			registration_billed=0,
		)
		return

	set_patient_registration_fields(
		patient,
		registration_invoice=invoice.name,
		registration_status=AWAITING_PAYMENT_STATUS,
		registration_billed=1,
	)


def is_invoice_paid(invoice) -> bool:
	return invoice.docstatus == 1 and (invoice.status == "Paid" or flt(invoice.outstanding_amount) <= 0)
