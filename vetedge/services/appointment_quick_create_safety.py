from __future__ import annotations

from contextlib import contextmanager
from typing import Any

import frappe
from frappe import _
from frappe.utils import cstr

from vetedge.services.company_context_compat import get_branch_company
from vetedge.services.guest_booking import get_default_customer_group, get_default_territory


def _clean(value: Any) -> str:
	return cstr(value or "").strip()


def get_company_currency(company: str) -> str:
	company = _clean(company)
	if not company or not frappe.db.exists("Company", company):
		frappe.throw(_("Select a valid Veterinary Company."), frappe.ValidationError)
	currency = _clean(frappe.db.get_value("Company", company, "default_currency"))
	if not currency:
		frappe.throw(
			_("Configure a default currency for Company {0} before registering a Veterinary Patient.").format(company),
			frappe.ValidationError,
		)
	return currency


def get_compatible_selling_price_list(currency: str, branch: str | None = None) -> str:
	currency = _clean(currency)
	branch = _clean(branch)
	candidates: list[str] = []
	if branch and frappe.db.exists("Branch", branch):
		meta = frappe.get_meta("Branch")
		for fieldname in ("vetedge_price_list", "default_selling_price_list", "selling_price_list"):
			if meta.has_field(fieldname):
				value = _clean(frappe.db.get_value("Branch", branch, fieldname))
				if value:
					candidates.append(value)
	if frappe.db.exists("DocType", "Selling Settings"):
		value = _clean(frappe.db.get_single_value("Selling Settings", "selling_price_list"))
		if value:
			candidates.append(value)
	for price_list in candidates:
		if frappe.db.get_value("Price List", price_list, "currency") == currency:
			return price_list
	rows = frappe.get_all(
		"Price List",
		filters={"selling": 1, "enabled": 1, "currency": currency},
		pluck="name",
		order_by="modified desc",
		limit=1,
	)
	return rows[0] if rows else ""


def get_applicable_loyalty_programs(customer_group: str, territory: str) -> list[str]:
	if not frappe.db.exists("DocType", "Loyalty Program"):
		return []
	from erpnext.selling.doctype.customer.customer import get_loyalty_programs

	customer = frappe.get_doc(
		{
			"doctype": "Customer",
			"customer_name": "VetEdge Quick Create Preview",
			"customer_type": "Individual",
			"customer_group": customer_group,
			"territory": territory,
		}
	)
	return list(get_loyalty_programs(customer) or [])


def get_owner_quick_create_context(company: str, branch: str | None = None) -> dict[str, Any]:
	company = _clean(company)
	customer_group = get_default_customer_group()
	territory = get_default_territory()
	if not customer_group or not territory:
		return {
			"ready": False,
			"warning": _("Configure a default Customer Group and Territory before creating Pet Owners."),
			"customer_group": customer_group or "",
			"territory": territory or "",
			"company_currency": "",
			"default_price_list": "",
			"loyalty_programs": [],
			"requires_loyalty_program": False,
			"default_loyalty_program": "",
		}
	currency = get_company_currency(company)
	programs = get_applicable_loyalty_programs(customer_group, territory)
	return {
		"ready": True,
		"warning": "",
		"customer_group": customer_group,
		"territory": territory,
		"company_currency": currency,
		"default_price_list": get_compatible_selling_price_list(currency, branch),
		"loyalty_programs": [{"value": name, "label": name} for name in programs],
		"requires_loyalty_program": len(programs) > 1,
		"default_loyalty_program": programs[0] if len(programs) == 1 else "",
	}


def resolve_owner_loyalty_program(context: dict[str, Any], selected: str | None) -> str:
	selected = _clean(selected)
	programs = [row.get("value") if isinstance(row, dict) else row for row in context.get("loyalty_programs") or []]
	programs = [_clean(name) for name in programs if _clean(name)]
	if selected and selected not in programs:
		frappe.throw(_("The selected Loyalty Program is not applicable to this Pet Owner."), frappe.ValidationError)
	if len(programs) == 1:
		return programs[0]
	if len(programs) > 1 and not selected:
		frappe.throw(_("Select a Loyalty Program for this Pet Owner."), frappe.ValidationError)
	return selected


def validate_patient_quick_create_context(company: str, branch: str | None = None) -> dict[str, str]:
	company = _clean(company)
	branch = _clean(branch)
	currency = get_company_currency(company)
	if branch:
		branch_company = get_branch_company(branch)
		if branch_company and branch_company != company:
			frappe.throw(
				_("Default Branch {0} belongs to Company {1}, not Company {2}.").format(
					branch,
					branch_company,
					company,
				),
				frappe.ValidationError,
			)
	return {
		"company": company,
		"company_currency": currency,
		"selling_price_list": get_compatible_selling_price_list(currency, branch),
	}


@contextmanager
def registration_invoice_context(patient_doc):
	flags = getattr(frappe, "flags", None)
	if flags is None:
		yield
		return
	previous = getattr(flags, "vetedge_registration_invoice_context", None)
	flags.vetedge_registration_invoice_context = {
		"patient": patient_doc.get("name"),
		"customer": patient_doc.get("primary_owner"),
		"company": patient_doc.get("company"),
		"branch": patient_doc.get("default_branch"),
	}
	try:
		yield
	finally:
		flags.vetedge_registration_invoice_context = previous


def align_registration_invoice_company_currency(doc, method: str | None = None) -> None:
	context = getattr(getattr(frappe, "flags", None), "vetedge_registration_invoice_context", None)
	if not context or doc.get("doctype") != "Sales Invoice" or int(doc.get("docstatus") or 0) != 0:
		return
	customer = _clean(context.get("customer"))
	if customer and doc.get("customer") and doc.get("customer") != customer:
		return
	company = _clean(context.get("company"))
	branch = _clean(context.get("branch"))
	currency = get_company_currency(company)
	price_list = get_compatible_selling_price_list(currency, branch)

	doc.company = company
	doc.currency = currency
	doc.conversion_rate = 1
	if doc.meta.has_field("price_list_currency"):
		doc.price_list_currency = currency
	if doc.meta.has_field("plc_conversion_rate"):
		doc.plc_conversion_rate = 1
	if doc.meta.has_field("selling_price_list"):
		doc.selling_price_list = price_list or None
	if branch and doc.meta.has_field("branch"):
		doc.branch = branch
