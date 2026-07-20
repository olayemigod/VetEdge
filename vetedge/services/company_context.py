from __future__ import annotations

from typing import Any

import frappe
from frappe import _
from frappe.utils import cstr

from vetedge.coreedge_adapter import get_current_vetedge_company, get_current_vetedge_context


def _clean(value: Any) -> str:
	return cstr(value or "").strip()


def _working_branch_company(user: str | None = None) -> str:
	try:
		from vetedge.services.branch_context import get_working_company

		return _clean(get_working_company(user=user))
	except (ImportError, ModuleNotFoundError, RuntimeError):
		return ""


def get_active_vetedge_company(user: str | None = None) -> str:
	company = _working_branch_company(user)
	if not company:
		company = _clean(get_current_vetedge_company(user))
	if not company:
		company = _clean(frappe.defaults.get_user_default("Company", user=user))
	return company


def get_allowed_vetedge_companies(user: str | None = None) -> list[str]:
	context = get_current_vetedge_context(user)
	allowed = [_clean(value) for value in (context.get("allowed_companies") or []) if _clean(value)]
	active = _clean(context.get("active_company"))
	working = _working_branch_company(user)
	for value in (active, working):
		if value and value not in allowed:
			allowed.append(value)
	if allowed:
		return allowed
	if not frappe.has_permission("Company", "read"):
		return []
	return [row.name for row in frappe.get_list("Company", fields=["name"], order_by="name asc", page_length=500)]


def validate_vetedge_company(company: str | None, user: str | None = None) -> str:
	company = _clean(company) or get_active_vetedge_company(user)
	if not company:
		frappe.throw(_("Select an active Company before continuing."), frappe.ValidationError)
	if not frappe.db.exists("Company", company):
		frappe.throw(_("The selected Company is not valid."), frappe.ValidationError)
	allowed = get_allowed_vetedge_companies(user)
	if allowed and company not in allowed:
		frappe.throw(_("You are not permitted to use Company {0}.").format(company), frappe.PermissionError)
	visible = frappe.get_list("Company", filters={"name": company}, fields=["name"], page_length=1)
	if not visible:
		frappe.throw(_("You are not permitted to read Company {0}.").format(company), frappe.PermissionError)
	return company


def customer_is_allowed_for_company(customer: str | None, company: str | None) -> bool:
	customer = _clean(customer)
	company = _clean(company)
	if not customer or not company:
		return False
	meta = frappe.get_meta("Customer")
	fields = ["name"]
	if meta.has_field("disabled"):
		fields.append("disabled")
	if meta.has_field("restrict_to_companies"):
		fields.append("restrict_to_companies")
	values = frappe.db.get_value("Customer", customer, fields, as_dict=True)
	if not values:
		return False
	if values.get("disabled"):
		return False
	if not meta.has_field("restrict_to_companies") or not values.get("restrict_to_companies"):
		return True
	if not meta.has_field("allowed_companies"):
		return False
	return bool(
		frappe.db.exists(
			"Company Restriction",
			{
				"parenttype": "Customer",
				"parent": customer,
				"parentfield": "allowed_companies",
				"company": company,
			},
		)
	)


def validate_customer_company(customer: str | None, company: str | None) -> str:
	customer = _clean(customer)
	company = validate_vetedge_company(company)
	if not customer_is_allowed_for_company(customer, company):
		frappe.throw(
			_("Pet Owner {0} is not available for Company {1}.").format(customer or _("Unknown"), company),
			frappe.ValidationError,
		)
	return customer


def apply_customer_company_restriction(doc, company: str | None) -> None:
	company = validate_vetedge_company(company)
	meta = frappe.get_meta("Customer")
	if not meta.has_field("restrict_to_companies") or not meta.has_field("allowed_companies"):
		return
	doc.restrict_to_companies = 1
	doc.set("allowed_companies", [])
	doc.append("allowed_companies", {"company": company})
