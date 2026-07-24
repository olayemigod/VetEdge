from __future__ import annotations

import frappe
from frappe.tests.utils import FrappeTestCase

from vetedge.services.clinical_workspace import (
	create_consultation_vitals,
	get_clinical_link_options,
	get_clinical_summary,
	get_consultation_detail,
	get_consultations,
	save_consultation,
)


class TestVetEdgeClinicalWorkspaceIntegration(FrappeTestCase):
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
		name = self.unique("Edge Clinical Branch")
		return frappe.get_doc({"doctype": "Branch", "branch": name}).insert(ignore_permissions=True).name

	def create_species(self) -> str:
		name = self.unique("Edge Clinical Species")
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
		name = self.unique("Edge Clinical Owner")
		return frappe.get_doc(
			{
				"doctype": "Customer",
				"customer_name": name,
				"customer_type": "Individual",
				"customer_group": customer_group,
				"territory": territory,
			}
		).insert(ignore_permissions=True).name

	def create_doctor(self) -> str:
		marker = frappe.generate_hash(length=8).lower()
		email = f"clinical-doctor-{marker}@example.com"
		doctor = frappe.get_doc(
			{
				"doctype": "User",
				"email": email,
				"first_name": f"Clinical Doctor {marker}",
				"enabled": 1,
				"send_welcome_email": 0,
			}
		).insert(ignore_permissions=True)
		doctor.add_roles("VetEdge Doctor")
		return doctor.name

	def create_patient(self, *, branch: str, customer: str, species: str) -> str:
		return frappe.get_doc(
			{
				"doctype": "Veterinary Patient",
				"patient_name": self.unique("Edge Clinical Patient"),
				"primary_owner": customer,
				"status": "Active",
				"default_branch": branch,
				"species": species,
				"sex": "Unknown",
			}
		).insert(ignore_permissions=True).name

	def ensure_consultation_type(self) -> str:
		name = "General Consultation"
		if not frappe.db.exists("Consultation Type", name):
			frappe.get_doc(
				{
					"doctype": "Consultation Type",
					"consultation_type": name,
					"disabled": 0,
				}
			).insert(ignore_permissions=True)
		return name

	def create_context(self) -> dict:
		branch = self.create_branch()
		species = self.create_species()
		customer = self.create_customer()
		doctor = self.create_doctor()
		patient = self.create_patient(branch=branch, customer=customer, species=species)
		return {
			"branch": branch,
			"customer": customer,
			"doctor": doctor,
			"patient": patient,
			"consultation_type": self.ensure_consultation_type(),
		}

	def test_veterinary_home_page_exists_after_migration(self):
		self.assertTrue(frappe.db.exists("Page", "vetedge"))
		page = frappe.get_doc("Page", "vetedge")
		self.assertEqual(page.page_name, "vetedge")
		self.assertEqual(page.module, "Veterinary")
		self.assertEqual(page.title, "Veterinary Home")

	def test_create_list_detail_update_and_stale_write_contract(self):
		context = self.create_context()
		created = save_consultation(
			{
				"patient": context["patient"],
				"service_branch": context["branch"],
				"consulting_practitioner": context["doctor"],
				"consultation_type": context["consultation_type"],
				"presenting_complaint": "Reduced appetite and lethargy.",
				"symptoms": [],
				"diagnoses": [],
				"planned_treatments": [],
			}
		)
		self.assertTrue(created["name"])
		self.assertEqual(created["status"], "Draft")
		self.assertEqual(created["values"]["patient"], context["patient"])

		listing = get_consultations(
			search=created["name"],
			branch=context["branch"],
			page_length=5,
		)
		self.assertIn(created["name"], {row.name for row in listing["rows"]})
		self.assertEqual(listing["page_length"], 5)

		detail = get_consultation_detail(created["name"])
		updated = save_consultation(
			{
				"name": detail["name"],
				"modified": str(detail["modified"]),
				"patient": detail["values"]["patient"],
				"service_branch": detail["values"]["service_branch"],
				"consulting_practitioner": detail["values"]["consulting_practitioner"],
				"consultation_type": detail["values"]["consultation_type"],
				"presenting_complaint": "Reduced appetite, lethargy and mild dehydration.",
				"symptoms": detail["values"]["symptoms"],
				"diagnoses": detail["values"]["diagnoses"],
				"planned_treatments": detail["values"]["planned_treatments"],
			}
		)
		self.assertIn("mild dehydration", updated["values"]["presenting_complaint"])

		stale_modified = str(updated["modified"])
		doc = frappe.get_doc("Veterinary Consultation", updated["name"])
		doc.presenting_complaint = "Changed by another clinical user."
		doc.save(ignore_permissions=True)
		with self.assertRaises(frappe.TimestampMismatchError):
			save_consultation(
				{
					"name": updated["name"],
					"modified": stale_modified,
					"patient": context["patient"],
					"service_branch": context["branch"],
					"consulting_practitioner": context["doctor"],
					"consultation_type": context["consultation_type"],
					"presenting_complaint": "This must not overwrite the newer value.",
				}
			)

	def test_summary_links_and_vitals_use_live_frappe_services(self):
		context = self.create_context()
		created = save_consultation(
			{
				"patient": context["patient"],
				"service_branch": context["branch"],
				"consulting_practitioner": context["doctor"],
				"consultation_type": context["consultation_type"],
				"presenting_complaint": "Routine clinical review.",
			}
		)

		summary = get_clinical_summary(branch=context["branch"])
		self.assertGreaterEqual(summary["draft"], 1)

		patient_options = get_clinical_link_options("patient", search=context["patient"])
		self.assertIn(context["patient"], {row["value"] for row in patient_options})
		doctor_options = get_clinical_link_options("practitioner", search=context["doctor"])
		self.assertIn(context["doctor"], {row["value"] for row in doctor_options})

		result = create_consultation_vitals(
			created["name"],
			{"temperature": 38.4, "weight": 12.5, "heart_rate": 96, "notes": "Stable."},
			modified=str(created["modified"]),
		)
		self.assertTrue(result["vitals"])
		self.assertEqual(result["detail"]["latest_vitals"]["temperature"], 38.4)
