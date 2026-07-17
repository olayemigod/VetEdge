from __future__ import annotations

import frappe
from frappe import _
from frappe.utils import add_days, cint, cstr, flt, getdate, nowdate


def build_financial_dataset(filters=None) -> list[dict]:
	"""
	Returns a unified, normalized dataset of financial records (Sales Invoices)
	acting as the single source of truth for the Veterinary Financial Dashboard,
	Revenue Summary, Unpaid Invoice Report, and other financial analytics.
	
	Branch resolution uses a prioritized checklist:
	1. Service branch/branch of linked clinical documents.
	2. Branch on the Sales Invoice itself.
	3. Branch on Payment Entries.
	4. Mapped cost center -> Branch.
	
	This delegates to the existing reporting_structure helper functions
	to preserve backward compatibility and unit test mock integrations.
	"""
	filters = frappe._dict(filters or {})
	
	from vetedge.services.reporting_structure import (
		_get_sales_invoice_rows,
		_build_invoice_context_map,
		_resolve_invoice_report_branch,
		_get_invoice_payment_branch_map,
		_invoice_status_from_row,
		_existing_field
	)

	invoices = _get_sales_invoice_rows(filters)
	if not invoices:
		return []

	invoice_names = [inv.get("name") for inv in invoices]
	invoice_context = _build_invoice_context_map(invoice_names)
	payment_branch_map = _get_invoice_payment_branch_map(invoice_names)

	consultation_map = {}
	vaccination_map = {}
	lab_map = {}
	boarding_map = {}
	grooming_map = {}
	hospitalisation_map = {}
	billing_session_map = {}

	# Helper function to dynamically query a linked doctype and populate its map
	def populate_link_map(target_doctype, invoice_fields, target_map):
		if not frappe.db.exists("DocType", target_doctype):
			return
		inv_field = _existing_field(target_doctype, invoice_fields)
		if not inv_field:
			return
		branch_field = _existing_field(target_doctype, ["service_branch", "branch"])
		patient_field = _existing_field(target_doctype, ["patient"])
		cost_center_field = _existing_field(target_doctype, ["cost_center"])
		
		fields_to_get = ["name", inv_field]
		if branch_field:
			fields_to_get.append(branch_field)
		if patient_field:
			fields_to_get.append(patient_field)
		if cost_center_field:
			fields_to_get.append(cost_center_field)
			
		rows = frappe.get_all(
			target_doctype,
			filters={inv_field: ("in", invoice_names)},
			fields=fields_to_get
		)
		for row in rows:
			inv_name = row.get(inv_field)
			if inv_name:
				target_map[inv_name] = frappe._dict({
					"name": row.get("name"),
					"sales_invoice": inv_name,
					"patient": row.get(patient_field) if patient_field else None,
					"service_branch": row.get(branch_field) if branch_field else None,
					"branch": row.get(branch_field) if branch_field else None,
					"cost_center": row.get(cost_center_field) if cost_center_field else None,
				})

	# 1. Fetch direct Consultation links
	populate_link_map("Veterinary Consultation", ["sales_invoice", "linked_invoice", "invoice"], consultation_map)

	# Fetch child table Consultation links if Consultation has child tables
	if frappe.db.exists("DocType", "Consultation Invoice Reference"):
		child_rows = frappe.get_all(
			"Consultation Invoice Reference",
			filters={"sales_invoice": ("in", invoice_names), "parenttype": "Veterinary Consultation"},
			fields=["parent", "sales_invoice"]
		)
		child_parent_names = [r.parent for r in child_rows if r.parent]
		if child_parent_names:
			branch_field = _existing_field("Veterinary Consultation", ["service_branch", "branch"])
			patient_field = _existing_field("Veterinary Consultation", ["patient"])
			cost_center_field = _existing_field("Veterinary Consultation", ["cost_center"])
			
			fields_to_get = ["name"]
			if branch_field:
				fields_to_get.append(branch_field)
			if patient_field:
				fields_to_get.append(patient_field)
			if cost_center_field:
				fields_to_get.append(cost_center_field)
				
			consultations = frappe.get_all(
				"Veterinary Consultation",
				filters={"name": ("in", child_parent_names)},
				fields=fields_to_get
			)
			consultation_by_name = {c.name: c for c in consultations}
			for row in child_rows:
				c_doc = consultation_by_name.get(row.parent)
				if c_doc and row.sales_invoice not in consultation_map:
					consultation_map[row.sales_invoice] = frappe._dict({
						"name": c_doc.get("name"),
						"sales_invoice": row.sales_invoice,
						"patient": c_doc.get(patient_field) if patient_field else None,
						"service_branch": c_doc.get(branch_field) if branch_field else None,
						"branch": c_doc.get(branch_field) if branch_field else None,
						"cost_center": c_doc.get(cost_center_field) if cost_center_field else None,
					})

	# 2. Fetch Vaccination links
	populate_link_map("Veterinary Vaccination Record", ["linked_invoice"], vaccination_map)

	# 3. Fetch Lab Order links
	populate_link_map("Veterinary Lab Order", ["linked_invoice", "invoice"], lab_map)

	# 4. Fetch Boarding links
	populate_link_map("Pet Boarding Booking", ["linked_invoice"], boarding_map)

	# 5. Fetch Grooming links
	populate_link_map("Pet Grooming Session", ["linked_invoice"], grooming_map)

	# 6. Fetch Hospitalisation links
	populate_link_map("Veterinary Hospitalisation", ["sales_invoice"], hospitalisation_map)

	# 7. Fetch Billing Session links
	if frappe.db.exists("DocType", "Veterinary Billing Session Charge"):
		rows = frappe.get_all(
			"Veterinary Billing Session Charge",
			filters={"invoice": ("in", invoice_names)},
			fields=["parent", "invoice"]
		)
		for row in rows:
			billing_session_map[row.invoice] = row.parent

	dataset = []
	for inv in invoices:
		name = inv.get("name")
		context = invoice_context.get(name, {})

		c_doc = consultation_map.get(name)
		v_doc = vaccination_map.get(name)
		l_doc = lab_map.get(name)
		b_doc = boarding_map.get(name)
		g_doc = grooming_map.get(name)
		h_doc = hospitalisation_map.get(name)
		bs_ref = billing_session_map.get(name)

		# Resolve patient
		patient = context.get("patient")
		if not patient:
			for doc in (c_doc, v_doc, l_doc, b_doc, g_doc, h_doc):
				if doc and doc.get("patient"):
					patient = doc.get("patient")
					break

		# Resolve branch
		resolved_branch = _resolve_invoice_report_branch(inv, context)

		# Filter by branch in Python since branch requires dynamic resolution from linked docs
		if filters.get("branch") and resolved_branch != cstr(filters.get("branch")).strip():
			continue

		grand_total = flt(inv.get("grand_total"))
		outstanding = flt(inv.get("outstanding_amount"))
		paid_amount = grand_total - outstanding

		if cint(inv.get("docstatus")) == 0:
			outstanding = grand_total
			paid_amount = 0.0

		status_val = inv.get("status") or _invoice_status_from_row(inv)
		service_source = context.get("service_category") or "General"

		dataset.append({
			"sales_invoice": name,
			"posting_date": inv.get("posting_date"),
			"due_date": inv.get("due_date"),
			"company": inv.get("company"),
			"branch": resolved_branch,
			"customer": inv.get("customer"),
			"patient": patient,
			"service_source": service_source,
			"consultation_reference": c_doc.get("name") if c_doc else None,
			"lab_reference": l_doc.get("name") if l_doc else None,
			"vaccination_reference": v_doc.get("name") if v_doc else None,
			"grooming_reference": g_doc.get("name") if g_doc else None,
			"boarding_reference": b_doc.get("name") if b_doc else None,
			"hospitalisation_reference": h_doc.get("name") if h_doc else None,
			"billing_session_reference": bs_ref,
			"payment_status": status_val,
			"outstanding_amount": outstanding,
			"paid_amount": paid_amount,
			"grand_total": grand_total,
			"docstatus": cint(inv.get("docstatus")),
		})

	return dataset
