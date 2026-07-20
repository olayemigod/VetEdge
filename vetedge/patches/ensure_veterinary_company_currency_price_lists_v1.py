from __future__ import annotations

import frappe

from vetedge.services.appointment_quick_create_safety import get_compatible_selling_price_list


def execute() -> None:
	if not frappe.db.exists("DocType", "Company") or not frappe.db.exists("DocType", "Price List"):
		return
	for company in frappe.get_all("Company", fields=["name", "abbr", "default_currency"]):
		currency = (company.default_currency or "").strip()
		if not currency or get_compatible_selling_price_list(currency):
			continue
		base_name = f"Veterinary Selling - {currency}"
		name = base_name
		if frappe.db.exists("Price List", name):
			name = f"{base_name} - {company.abbr or company.name}"
		if frappe.db.exists("Price List", name):
			continue
		doc = frappe.get_doc(
			{
				"doctype": "Price List",
				"price_list_name": name,
				"currency": currency,
				"selling": 1,
				"buying": 0,
				"enabled": 1,
			}
		)
		doc.insert()
