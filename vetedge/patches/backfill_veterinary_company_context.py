from __future__ import annotations

import frappe


def _single_allowed_customer_company(customer: str | None) -> str | None:
	if not customer or not frappe.db.exists("Customer", customer):
		return None
	meta = frappe.get_meta("Customer")
	if not meta.has_field("restrict_to_companies") or not meta.has_field("allowed_companies"):
		return None
	if not frappe.db.get_value("Customer", customer, "restrict_to_companies"):
		return None
	companies = frappe.get_all(
		"Company Restriction",
		filters={
			"parenttype": "Customer",
			"parent": customer,
			"parentfield": "allowed_companies",
		},
		pluck="company",
	)
	companies = list(dict.fromkeys(company for company in companies if company))
	return companies[0] if len(companies) == 1 else None


def execute():
	if not frappe.db.exists("DocType", "Veterinary Patient"):
		return
	if not frappe.get_meta("Veterinary Patient").has_field("company"):
		return

	companies = frappe.get_all("Company", pluck="name")
	single_site_company = companies[0] if len(companies) == 1 else None
	patients = frappe.get_all(
		"Veterinary Patient",
		filters={"company": ["in", ["", None]]},
		fields=["name", "primary_owner"],
	)
	for patient in patients:
		company = _single_allowed_customer_company(patient.primary_owner) or single_site_company
		if company:
			frappe.db.set_value("Veterinary Patient", patient.name, "company", company, update_modified=False)

	if not frappe.db.exists("DocType", "Veterinary Appointment"):
		return
	if not frappe.get_meta("Veterinary Appointment").has_field("company"):
		return

	frappe.db.sql(
		"""
		UPDATE `tabVeterinary Appointment` a
		INNER JOIN `tabVeterinary Patient` p ON p.name = a.patient
		SET a.company = p.company
		WHERE (a.company IS NULL OR a.company = '')
			AND p.company IS NOT NULL
			AND p.company != ''
		"""
	)
