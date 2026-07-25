from __future__ import annotations

import frappe
from frappe.tests.utils import FrappeTestCase

from vetedge.services.clinical_workspace import create_consultation_vitals
from vetedge.services.clinical_workspace_context import (
	get_clinical_context_options,
	get_patient_owner_context,
)
from vetedge.services.clinical_workspace_stage3 import (
	_treatment_row_edit_is_protected,
	_treatment_row_removal_is_protected,
	save_consultation,
)
from vetedge.services.consultation_billing_plan import DEFAULT_CONSULTATION_SOURCE_DETAIL


class TestVetEdgeClinicalWorkspaceQAFollowup(FrappeTestCase):
	def setUp(self):
		frappe.set_user("Administrator")
		settings = frappe.get_single("Veterinary Settings")
		for fieldname, value in (
			("enable_vetedge", 1),
			("enable_consultations", 1),
			("enable_vitals", 1),
			("enable_registration_billing", 0),
			("enable_notifications", 0),
			("auto_add_default_consultation_billing_item", 0),
		):
			if settings.meta.has_field(fieldname):
				settings.set(fieldname, value)
		settings.save(ignore_permissions=True)

	def unique(self, prefix: str) -> str:
		return f"{prefix}-{frappe.generate_hash(length=8)}"

	def create_branch(self) -> str:
		name = self.unique("Edge Clinical QA Branch")
		return frappe.get_doc({"doctype": "Branch", "branch": name}).insert(ignore_permissions=True).name

	def create_species(self) -> str:
		name = self.unique("Edge Clinical QA Species")
		return frappe.get_doc(
			{
				"doctype": "Veterinary Species",
				"species_name": name,
				"disabled": 0,
			}
		).insert(ignore_permissions=True).name

	def create_customer(self) -> str:
		customer_group = frappe.db.get_value("Customer Group", {"is_group": 0}, "name")
		territory = frappe.db.get_value("Territory", {"is_group": 0}, "name")
		self.assertTrue(customer_group)
		self.assertTrue(territory)
		name = self.unique("Edge Clinical QA Owner")
		values = {
			"doctype": "Customer",
			"customer_name": name,
			"customer_type": "Individual",
			"customer_group": customer_group,
			"territory": territory,
		}
		meta = frappe.get_meta("Customer")
		if meta.has_field("mobile_no"):
			values["mobile_no"] = "+2348012345678"
		if meta.has_field("email_id"):
			values["email_id"] = f"{frappe.generate_hash(length=8).lower()}@example.com"
		return frappe.get_doc(values).insert(ignore_permissions=True).name

	def create_doctor(self) -> str:
		marker = frappe.generate_hash(length=8).lower()
		doctor = frappe.get_doc(
			{
				"doctype": "User",
				"email": f"clinical-qa-doctor-{marker}@example.com",
				"first_name": f"Clinical QA Doctor {marker}",
				"enabled": 1,
				"send_welcome_email": 0,
			}
		).insert(ignore_permissions=True)
		doctor.add_roles("VetEdge Doctor")
		return doctor.name

	def ensure_consultation_type(self, name: str = "General Consultation", sort_order: int = 1) -> str:
		if not frappe.db.exists("Consultation Type", name):
			frappe.get_doc(
				{
					"doctype": "Consultation Type",
					"consultation_type": name,
					"sort_order": sort_order,
					"disabled": 0,
				}
			).insert(ignore_permissions=True)
		return name

	def create_context(self) -> dict:
		branch = self.create_branch()
		species = self.create_species()
		customer = self.create_customer()
		doctor = self.create_doctor()
		patient = frappe.get_doc(
			{
				"doctype": "Veterinary Patient",
				"patient_name": self.unique("Edge Clinical QA Patient"),
				"primary_owner": customer,
				"status": "Active",
				"default_branch": branch,
				"species": species,
				"sex": "Unknown",
				"emergency_contact": "+2348098765432",
			}
		).insert(ignore_permissions=True).name
		return {
			"branch": branch,
			"customer": customer,
			"doctor": doctor,
			"patient": patient,
			"consultation_type": self.ensure_consultation_type(),
		}

	def test_restricted_doctor_cannot_write_or_record_vitals_for_another_doctor(self):
		context = self.create_context()
		other_doctor = self.create_doctor()
		created = save_consultation(
			{
				"patient": context["patient"],
				"service_branch": context["branch"],
				"consulting_practitioner": context["doctor"],
				"consultation_type": context["consultation_type"],
				"presenting_complaint": "Ownership test.",
			}
		)

		frappe.set_user(other_doctor)
		try:
			options = get_clinical_context_options("practitioner")
			self.assertEqual([row["value"] for row in options], [other_doctor])

			with self.assertRaises(frappe.PermissionError):
				save_consultation(
					{
						"name": created["name"],
						"modified": str(created["modified"]),
						"patient": context["patient"],
						"service_branch": context["branch"],
						"consulting_practitioner": other_doctor,
						"consultation_type": context["consultation_type"],
						"presenting_complaint": "Attempted reassignment.",
					}
				)

			with self.assertRaises(frappe.PermissionError):
				create_consultation_vitals(
					created["name"],
					{"temperature": 38.1},
					modified=str(created["modified"]),
				)

			owned = save_consultation(
				{
					"patient": context["patient"],
					"service_branch": context["branch"],
					"consultation_type": context["consultation_type"],
					"presenting_complaint": "Doctor-owned consultation.",
				}
			)
			self.assertEqual(owned["values"]["consulting_practitioner"], other_doctor)
		finally:
			frappe.set_user("Administrator")

	def test_patient_owner_context_and_full_enabled_consultation_type_list(self):
		context = self.create_context()
		additional_types = [
			self.ensure_consultation_type("Follow-up Consultation", 2),
			self.ensure_consultation_type("House Call", 3),
		]

		options = get_clinical_context_options("consultation_type", search="", limit=50)
		values = {row["value"] for row in options}
		self.assertIn(context["consultation_type"], values)
		for label in additional_types:
			self.assertIn(label, values)

		patient_context = get_patient_owner_context(context["patient"])
		self.assertEqual(patient_context["patient"]["default_branch"], context["branch"])
		self.assertEqual(patient_context["patient"]["emergency_contact"], "+2348098765432")
		self.assertEqual(patient_context["owner"]["name"], context["customer"])
		self.assertTrue(patient_context["owner"]["label"])

	def test_default_consultation_fee_can_be_edited_but_not_removed_while_pending(self):
		settings = frappe._dict(
			enabled=True,
			auto_add_default_consultation_billing_item=True,
			allow_editing_consultation_billing_item=True,
		)
		row = frappe._dict(
			source_type="Consultation",
			source_doctype="Veterinary Consultation",
			source_document="VET-CONS-QA",
			source_detail_name=DEFAULT_CONSULTATION_SOURCE_DETAIL,
			billing_status="Pending",
			payment_status="Not Billed",
		)

		self.assertFalse(_treatment_row_edit_is_protected(row, settings))
		self.assertTrue(_treatment_row_removal_is_protected(row))

		settings.allow_editing_consultation_billing_item = False
		self.assertTrue(_treatment_row_edit_is_protected(row, settings))

		settings.allow_editing_consultation_billing_item = True
		row.billing_status = "Draft Invoiced"
		self.assertTrue(_treatment_row_edit_is_protected(row, settings))

	def test_lab_vaccination_and_paid_rows_remain_protected(self):
		settings = frappe._dict(
			enabled=True,
			auto_add_default_consultation_billing_item=True,
			allow_editing_consultation_billing_item=True,
		)
		for source_type in ("Lab Order", "Vaccination"):
			row = frappe._dict(
				source_type=source_type,
				source_document=f"{source_type}-QA",
				source_detail_name="QA Source Row",
				billing_status="Pending",
				payment_status="Not Billed",
			)
			self.assertTrue(_treatment_row_edit_is_protected(row, settings))
			self.assertTrue(_treatment_row_removal_is_protected(row))

		paid = frappe._dict(
			source_type="Treatment",
			billing_status="Submitted Invoiced",
			payment_status="Paid",
		)
		self.assertTrue(_treatment_row_edit_is_protected(paid, settings))
		self.assertTrue(_treatment_row_removal_is_protected(paid))
