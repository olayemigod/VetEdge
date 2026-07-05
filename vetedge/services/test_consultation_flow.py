from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace
from unittest import TestCase
from unittest.mock import patch

import frappe

from vetedge.seed.master_data import CONSULTATION_TYPES
from vetedge.services.consultation_flow import (
	apply_linked_appointment_context,
	claim_linked_appointment_for_consultation,
	get_consultation_appointment_summary,
	get_next_daily_consultation_number,
	normalize_consultation_appointment_links,
	sync_service_appointment_status_from_consultation,
	transition_consultation_status,
	validate_consultation,
	validate_consultation_children,
	validate_linked_appointment,
	validate_completion_requirements,
	validate_service_branch_access,
	validate_consultation_status_transition,
)
from vetedge.veterinary.doctype.veterinary_consultation.veterinary_consultation import (
	normalize_consultation_payment_status_fields,
)


class TestConsultationFlow(TestCase):
	def test_consultation_payment_status_normalizer_removes_draft_invoice_pending(self):
		doc = frappe._dict(
			payment_status="Draft Invoice Pending",
			planned_treatments=[
				frappe._dict(payment_status="Draft Invoice Pending"),
				frappe._dict(payment_status="Partially Paid"),
			],
		)

		normalize_consultation_payment_status_fields(doc)

		self.assertEqual(doc.payment_status, "Unpaid")
		self.assertEqual(doc.planned_treatments[0].payment_status, "Unpaid")
		self.assertEqual(doc.planned_treatments[1].payment_status, "Partly Paid")

	def test_consultation_type_master_doctype_is_defined(self):
		doctype_path = (
			Path(__file__).resolve().parents[1]
			/ "veterinary"
			/ "doctype"
			/ "consultation_type"
			/ "consultation_type.json"
		)
		doctype = json.loads(doctype_path.read_text())
		field = next(
			field for field in doctype["fields"] if field.get("fieldname") == "consultation_type"
		)

		self.assertEqual(doctype["name"], "Consultation Type")
		self.assertEqual(doctype["module"], "Veterinary")
		self.assertEqual(doctype["autoname"], "field:consultation_type")
		self.assertEqual(doctype["title_field"], "consultation_type")
		self.assertEqual(field["fieldtype"], "Data")
		self.assertTrue(field["reqd"])
		self.assertTrue(field["unique"])

	def test_default_consultation_types_include_house_call(self):
		default_names = {record["consultation_type"] for record in CONSULTATION_TYPES}

		self.assertIn("General Consultation", default_names)
		self.assertIn("Follow-up Consultation", default_names)
		self.assertIn("Emergency Consultation", default_names)
		self.assertIn("House Call", default_names)
		self.assertIn("Vaccination Consultation", default_names)
		self.assertIn("Surgery Review", default_names)
		self.assertIn("Grooming Consultation", default_names)
		self.assertIn("Boarding Review", default_names)
		self.assertIn("Hospitalisation", default_names)
		house_call = next(record for record in CONSULTATION_TYPES if record["consultation_type"] == "House Call")
		self.assertEqual(house_call["is_house_call"], 1)

	def test_consultation_type_field_is_defined_on_consultation_doctype(self):
		doctype_path = (
			Path(__file__).resolve().parents[1]
			/ "veterinary"
			/ "doctype"
			/ "veterinary_consultation"
			/ "veterinary_consultation.json"
		)
		doctype = json.loads(doctype_path.read_text())
		field = next(
			field for field in doctype["fields"] if field.get("fieldname") == "consultation_type"
		)

		self.assertEqual(field["label"], "Consultation Type")
		self.assertEqual(field["fieldtype"], "Link")
		self.assertEqual(field["options"], "Consultation Type")
		self.assertEqual(field.get("default"), "General Consultation")
		self.assertEqual(field.get("reqd"), 1)
		self.assertIn("consultation_type", doctype["field_order"])

	def test_consultation_feature_flag_blocks_validation(self):
		doc = frappe._dict(patient="VP-001")

		with (
			patch(
				"vetedge.services.consultation_flow.frappe",
				make_frappe_stub(db=SimpleNamespace(exists=lambda *args, **kwargs: True)),
			),
			patch("vetedge.services.consultation_flow.is_enabled", return_value=False),
		):
			self.assertRaises(frappe.ValidationError, validate_consultation, doc)

	def test_consultation_defaults_practitioner_to_current_doctor(self):
		doc = frappe._dict(
			name="VCON-001",
			patient="VP-001",
			primary_owner=None,
			consulting_practitioner=None,
			consulting_practitioner_name=None,
			daily_consultation_number=None,
			service_branch="Branch B",
			consultation_datetime="2026-04-18 10:00:00",
			status="Draft",
			company="Test Company",
			symptoms=[],
			diagnoses=[],
			planned_treatments=[],
			linked_appointment=None,
		)

		def get_value(doctype, name, fields=None, **kwargs):
			if doctype == "User" and fields == "full_name":
				return "Dr Ada Vet"
			if fields == "patient_name":
				return "Buddy"
			return frappe._dict(primary_owner="CUST-001", default_branch="Branch A")

		frappe_stub = make_frappe_stub(
			db=SimpleNamespace(
				get_value=get_value,
				exists=lambda *args, **kwargs: False,
			),
			session=SimpleNamespace(user="doctor@example.com"),
			get_roles=lambda *args, **kwargs: ["VetEdge Doctor"],
		)

		with (
			patch("vetedge.services.consultation_flow.frappe", frappe_stub),
			patch("vetedge.services.consultation_flow.validate_doctor_user"),
			patch("vetedge.services.consultation_flow.can_access_branch_data"),
			patch("vetedge.services.consultation_flow.apply_planned_treatment_defaults"),
			patch("vetedge.services.consultation_flow.validate_registration_payment_before_first_consultation"),
			patch("vetedge.services.consultation_flow.validate_consultation_clinical_permissions"),
			patch("vetedge.services.consultation_flow.validate_consultation_invoice_before_progress"),
			patch("vetedge.services.consultation_flow.validate_consultation_payment_before_treatment"),
			patch("vetedge.services.consultation_flow.sync_consultation_dispensary_state"),
			patch("vetedge.services.consultation_flow.validate_consultation_dispensary_requirements"),
		):
			validate_consultation(doc)

		self.assertEqual(doc.consulting_practitioner, "doctor@example.com")
		self.assertEqual(doc.consulting_practitioner_name, "Dr Ada Vet")

	def test_linked_appointment_practitioner_takes_precedence_over_current_doctor(self):
		doc = frappe._dict(
			patient="VP-001",
			primary_owner=None,
			consulting_practitioner=None,
			consulting_practitioner_name=None,
			daily_consultation_number=None,
			service_branch="Branch B",
			consultation_datetime="2026-04-18 10:00:00",
			status="Draft",
			company="Test Company",
			symptoms=[],
			diagnoses=[],
			planned_treatments=[],
			linked_appointment="VAPT-001",
		)

		def get_value(doctype, name, fields=None, **kwargs):
			if doctype == "User" and fields == "full_name":
				return "Dr Assigned Vet" if name == "assigned.doctor@example.com" else "Dr Current Vet"
			if fields == "patient_name":
				return "Buddy"
			if doctype == "Veterinary Appointment":
				return frappe._dict(
					name="VAPT-001",
					patient="VP-001",
					status="Confirmed",
					branch="Branch B",
					practitioner="assigned.doctor@example.com",
					notes=None,
					linked_consultation=None,
					follow_up_reference=None,
				)
			return frappe._dict(primary_owner="CUST-001", default_branch="Branch A")

		frappe_stub = make_frappe_stub(
			db=SimpleNamespace(
				get_value=get_value,
				exists=lambda *args, **kwargs: False,
			),
			session=SimpleNamespace(user="doctor@example.com"),
			get_roles=lambda *args, **kwargs: ["VetEdge Doctor"],
		)

		with (
			patch("vetedge.services.consultation_flow.frappe", frappe_stub),
			patch("vetedge.services.consultation_flow.validate_doctor_user"),
			patch("vetedge.services.consultation_flow.can_access_branch_data"),
			patch("vetedge.services.consultation_flow.apply_planned_treatment_defaults"),
			patch("vetedge.services.consultation_flow.validate_registration_payment_before_first_consultation"),
			patch("vetedge.services.consultation_flow.validate_consultation_clinical_permissions"),
			patch("vetedge.services.consultation_flow.validate_consultation_invoice_before_progress"),
			patch("vetedge.services.consultation_flow.validate_consultation_payment_before_treatment"),
			patch("vetedge.services.consultation_flow.sync_consultation_dispensary_state"),
			patch("vetedge.services.consultation_flow.validate_consultation_dispensary_requirements"),
		):
			validate_consultation(doc)

		self.assertEqual(doc.consulting_practitioner, "assigned.doctor@example.com")
		self.assertEqual(doc.consulting_practitioner_name, "Dr Assigned Vet")

	def test_linked_appointment_appointment_type_maps_to_consultation_type_when_master_exists(self):
		doc = frappe._dict(
			patient="VP-001",
			primary_owner=None,
			consulting_practitioner=None,
			consulting_practitioner_name=None,
			daily_consultation_number=None,
			service_branch=None,
			consultation_datetime="2026-04-18 10:00:00",
			status="Draft",
			company="Test Company",
			symptoms=[],
			diagnoses=[],
			planned_treatments=[],
			linked_appointment="VAPT-001",
			consultation_type=None,
		)

		def get_value(doctype, name, fields=None, **kwargs):
			if doctype == "User" and fields == "full_name":
				return "Dr Assigned Vet"
			if fields == "patient_name":
				return "Buddy"
			if doctype == "Veterinary Appointment":
				return frappe._dict(
					name="VAPT-001",
					patient="VP-001",
					status="Confirmed",
					branch="Branch B",
					practitioner="assigned.doctor@example.com",
					appointment_type="Consultation",
					notes=None,
					linked_consultation=None,
					follow_up_reference=None,
				)
			return frappe._dict(primary_owner="CUST-001", default_branch="Branch A")

		def exists(doctype, name=None, **kwargs):
			return (doctype, name) == ("Consultation Type", "General Consultation")

		frappe_stub = make_frappe_stub(
			db=SimpleNamespace(
				get_value=get_value,
				exists=exists,
			),
			session=SimpleNamespace(user="doctor@example.com"),
			get_roles=lambda *args, **kwargs: ["VetEdge Doctor"],
		)

		with (
			patch("vetedge.services.consultation_flow.frappe", frappe_stub),
			patch("vetedge.services.consultation_flow.validate_doctor_user"),
			patch("vetedge.services.consultation_flow.can_access_branch_data"),
			patch("vetedge.services.consultation_flow.apply_planned_treatment_defaults"),
			patch("vetedge.services.consultation_flow.validate_registration_payment_before_first_consultation"),
			patch("vetedge.services.consultation_flow.validate_consultation_clinical_permissions"),
			patch("vetedge.services.consultation_flow.validate_consultation_invoice_before_progress"),
			patch("vetedge.services.consultation_flow.validate_consultation_payment_before_treatment"),
			patch("vetedge.services.consultation_flow.sync_consultation_dispensary_state"),
			patch("vetedge.services.consultation_flow.validate_consultation_dispensary_requirements"),
		):
			validate_consultation(doc)

		self.assertEqual(doc.consultation_type, "General Consultation")

	def test_linked_appointment_does_not_overwrite_selected_consultation_type(self):
		doc = frappe._dict(
			linked_appointment="VAPT-001",
			service_branch=None,
			consulting_practitioner=None,
			consultation_type="House Call",
			presenting_complaint=None,
		)
		appointment = frappe._dict(
			branch="Branch B",
			practitioner="doctor@example.com",
			consultation_type="General Consultation",
			appointment_type="Consultation",
			notes="Owner requested a house call.",
		)

		with patch("vetedge.services.consultation_flow.get_linked_appointment_data", return_value=appointment):
			apply_linked_appointment_context(doc)

		self.assertEqual(doc.consultation_type, "House Call")
		self.assertEqual(doc.service_branch, "Branch B")
		self.assertEqual(doc.consulting_practitioner, "doctor@example.com")

	def test_linked_appointment_house_call_maps_to_seeded_consultation_type(self):
		doc = frappe._dict(
			patient="VP-001",
			primary_owner=None,
			consulting_practitioner=None,
			consulting_practitioner_name=None,
			daily_consultation_number=None,
			service_branch=None,
			consultation_datetime="2026-04-18 10:00:00",
			status="Draft",
			company="Test Company",
			symptoms=[],
			diagnoses=[],
			planned_treatments=[],
			linked_appointment="VAPT-001",
			consultation_type=None,
		)

		def get_value(doctype, name, fields=None, **kwargs):
			if doctype == "User" and fields == "full_name":
				return "Dr Assigned Vet"
			if fields == "patient_name":
				return "Buddy"
			if doctype == "Veterinary Appointment":
				return frappe._dict(
					name="VAPT-001",
					patient="VP-001",
					status="Confirmed",
					branch="Branch B",
					practitioner="assigned.doctor@example.com",
					appointment_type="House Call",
					notes=None,
					linked_consultation=None,
					follow_up_reference=None,
				)
			return frappe._dict(primary_owner="CUST-001", default_branch="Branch A")

		def exists(doctype, name=None, **kwargs):
			return (doctype, name) == ("Consultation Type", "House Call")

		frappe_stub = make_frappe_stub(
			db=SimpleNamespace(
				get_value=get_value,
				exists=exists,
			),
			session=SimpleNamespace(user="doctor@example.com"),
			get_roles=lambda *args, **kwargs: ["VetEdge Doctor"],
		)

		with (
			patch("vetedge.services.consultation_flow.frappe", frappe_stub),
			patch("vetedge.services.consultation_flow.validate_doctor_user"),
			patch("vetedge.services.consultation_flow.can_access_branch_data"),
			patch("vetedge.services.consultation_flow.apply_planned_treatment_defaults"),
			patch("vetedge.services.consultation_flow.validate_registration_payment_before_first_consultation"),
			patch("vetedge.services.consultation_flow.validate_consultation_clinical_permissions"),
			patch("vetedge.services.consultation_flow.validate_consultation_invoice_before_progress"),
			patch("vetedge.services.consultation_flow.validate_consultation_payment_before_treatment"),
			patch("vetedge.services.consultation_flow.sync_consultation_dispensary_state"),
			patch("vetedge.services.consultation_flow.validate_consultation_dispensary_requirements"),
		):
			validate_consultation(doc)

		self.assertEqual(doc.consultation_type, "House Call")

	def test_veterinary_consultation_allows_house_call_consultation_type(self):
		doc = frappe._dict(
			patient="VP-001",
			primary_owner=None,
			consulting_practitioner="doctor@example.com",
			consulting_practitioner_name=None,
			daily_consultation_number=None,
			service_branch="Branch B",
			consultation_datetime="2026-04-18 10:00:00",
			status="Draft",
			company="Test Company",
			symptoms=[],
			diagnoses=[],
			planned_treatments=[],
			linked_appointment=None,
			consultation_type="House Call",
		)

		def get_value(doctype, name, fields=None, **kwargs):
			if doctype == "User" and fields == "full_name":
				return "Dr Ada Vet"
			if fields == "patient_name":
				return "Buddy"
			return frappe._dict(primary_owner="CUST-001", default_branch="Branch A")

		frappe_stub = make_frappe_stub(
			db=SimpleNamespace(
				get_value=get_value,
				exists=lambda *args, **kwargs: False,
			)
		)

		with (
			patch("vetedge.services.consultation_flow.frappe", frappe_stub),
			patch("vetedge.services.consultation_flow.validate_doctor_user"),
			patch("vetedge.services.consultation_flow.can_access_branch_data"),
			patch("vetedge.services.consultation_flow.apply_planned_treatment_defaults"),
			patch("vetedge.services.consultation_flow.validate_registration_payment_before_first_consultation"),
			patch("vetedge.services.consultation_flow.validate_consultation_clinical_permissions"),
			patch("vetedge.services.consultation_flow.validate_consultation_invoice_before_progress"),
			patch("vetedge.services.consultation_flow.validate_consultation_payment_before_treatment"),
			patch("vetedge.services.consultation_flow.sync_consultation_dispensary_state"),
			patch("vetedge.services.consultation_flow.validate_consultation_dispensary_requirements"),
		):
			validate_consultation(doc)

		self.assertEqual(doc.consultation_type, "House Call")

	def test_consultation_resolves_owner_and_allows_cross_branch_service(self):
		doc = frappe._dict(
			patient="VP-001",
			primary_owner=None,
			consulting_practitioner=None,
			consulting_practitioner_name=None,
			daily_consultation_number=None,
			service_branch="Branch B",
			consultation_datetime="2026-04-18 10:00:00",
			status="Draft",
			company="Test Company",
			symptoms=[],
			diagnoses=[],
			planned_treatments=[],
		)

		def get_value(doctype, name, fields=None, **kwargs):
			if doctype == "User" and fields == "full_name":
				return None
			if fields == "patient_name":
				return "Buddy"
			return frappe._dict(primary_owner="CUST-001", default_branch="Branch A")

		frappe_stub = make_frappe_stub(
			db=SimpleNamespace(
				get_value=get_value,
				exists=lambda *args, **kwargs: False,
			),
			get_roles=lambda *args, **kwargs: [],
		)

		with (
			patch("vetedge.services.consultation_flow.frappe", frappe_stub),
			patch("vetedge.services.consultation_flow.validate_doctor_user"),
			patch("vetedge.services.consultation_flow.can_access_branch_data"),
			patch("vetedge.services.consultation_flow.apply_planned_treatment_defaults"),
			patch("vetedge.services.consultation_flow.validate_registration_payment_before_first_consultation"),
			patch("vetedge.services.consultation_flow.validate_consultation_clinical_permissions"),
			patch("vetedge.services.consultation_flow.validate_consultation_invoice_before_progress"),
			patch("vetedge.services.consultation_flow.validate_consultation_payment_before_treatment"),
			patch("vetedge.services.consultation_flow.sync_consultation_dispensary_state"),
			patch("vetedge.services.consultation_flow.validate_consultation_dispensary_requirements"),
		):
			validate_consultation(doc)

		self.assertEqual(doc.primary_owner, "CUST-001")
		self.assertEqual(doc.service_branch, "Branch B")
		self.assertEqual(doc.daily_consultation_number, 1)
		self.assertEqual(doc.consultation_title, "Buddy - 2026-04-18 - Consultation 1 - Branch B")

	def test_consultation_title_uses_doctor_full_name(self):
		doc = frappe._dict(
			patient="VP-001",
			primary_owner=None,
			consulting_practitioner="doctor@example.com",
			consulting_practitioner_name=None,
			daily_consultation_number=None,
			service_branch="Branch B",
			consultation_datetime="2026-04-18 10:00:00",
			status="Draft",
			company="Test Company",
			symptoms=[],
			diagnoses=[],
			planned_treatments=[],
		)

		def get_value(doctype, name, fields=None, **kwargs):
			if doctype == "User" and fields == "full_name":
				return "Dr Ada Vet"
			if fields == "patient_name":
				return "Buddy"
			return frappe._dict(primary_owner="CUST-001", default_branch="Branch A")

		frappe_stub = make_frappe_stub(
			db=SimpleNamespace(
				get_value=get_value,
				exists=lambda *args, **kwargs: False,
			)
		)

		with (
			patch("vetedge.services.consultation_flow.frappe", frappe_stub),
			patch("vetedge.services.consultation_flow.validate_doctor_user"),
			patch("vetedge.services.consultation_flow.can_access_branch_data"),
			patch("vetedge.services.consultation_flow.apply_planned_treatment_defaults"),
			patch("vetedge.services.consultation_flow.validate_registration_payment_before_first_consultation"),
			patch("vetedge.services.consultation_flow.validate_consultation_clinical_permissions"),
			patch("vetedge.services.consultation_flow.validate_consultation_invoice_before_progress"),
			patch("vetedge.services.consultation_flow.validate_consultation_payment_before_treatment"),
			patch("vetedge.services.consultation_flow.sync_consultation_dispensary_state"),
			patch("vetedge.services.consultation_flow.validate_consultation_dispensary_requirements"),
		):
			validate_consultation(doc)

		self.assertEqual(doc.consulting_practitioner_name, "Dr Ada Vet")
		self.assertEqual(
			doc.consultation_title,
			"Buddy - 2026-04-18 - Consultation 1 - Dr Ada Vet - Branch B",
		)

	def test_consulting_practitioner_must_be_doctor_user(self):
		doc = frappe._dict(
			patient="VP-001",
			primary_owner=None,
			consulting_practitioner="nurse@example.com",
			consulting_practitioner_name=None,
			daily_consultation_number=None,
			service_branch="Branch B",
			consultation_datetime="2026-04-18 10:00:00",
			status="Draft",
			company="Test Company",
			symptoms=[],
			diagnoses=[],
			planned_treatments=[],
		)

		def get_value(doctype, name, fields=None, **kwargs):
			if doctype == "User" and fields == "full_name":
				return "Nurse User"
			if fields == "patient_name":
				return "Buddy"
			return frappe._dict(primary_owner="CUST-001", default_branch="Branch A")

		frappe_stub = make_frappe_stub(
			db=SimpleNamespace(
				get_value=get_value,
				exists=lambda *args, **kwargs: False,
			)
		)

		with (
			patch("vetedge.services.consultation_flow.frappe", frappe_stub),
			patch("vetedge.services.consultation_flow.validate_doctor_user", side_effect=frappe.ValidationError),
			patch("vetedge.services.consultation_flow.can_access_branch_data"),
			patch("vetedge.services.consultation_flow.apply_planned_treatment_defaults"),
			patch("vetedge.services.consultation_flow.validate_registration_payment_before_first_consultation"),
			patch("vetedge.services.consultation_flow.validate_consultation_clinical_permissions"),
			patch("vetedge.services.consultation_flow.validate_consultation_invoice_before_progress"),
			patch("vetedge.services.consultation_flow.validate_consultation_payment_before_treatment"),
			patch("vetedge.services.consultation_flow.sync_consultation_dispensary_state"),
			patch("vetedge.services.consultation_flow.validate_consultation_dispensary_requirements"),
		):
			self.assertRaises(frappe.ValidationError, validate_consultation, doc)

	def test_daily_consultation_number_increments_per_patient_day(self):
		frappe_stub = make_frappe_stub(
			get_all=lambda *args, **kwargs: [
				frappe._dict(daily_consultation_number=1),
				frappe._dict(daily_consultation_number=2),
			]
		)

		with patch("vetedge.services.consultation_flow.frappe", frappe_stub):
			number = get_next_daily_consultation_number("VP-001", "2026-04-18 15:30:00")

		self.assertEqual(number, 3)

	def test_consultation_defaults_service_branch_from_patient_home_branch(self):
		doc = frappe._dict(
			patient="VP-001",
			primary_owner=None,
			consulting_practitioner=None,
			consulting_practitioner_name=None,
			daily_consultation_number=None,
			service_branch=None,
			consultation_datetime="2026-04-18 10:00:00",
			status="Draft",
			company="Test Company",
			symptoms=[],
			diagnoses=[],
			planned_treatments=[],
		)

		def get_value(doctype, name, fields=None, **kwargs):
			if doctype == "User" and fields == "full_name":
				return None
			if fields == "patient_name":
				return "Buddy"
			return frappe._dict(primary_owner="CUST-001", default_branch="Branch A")

		frappe_stub = make_frappe_stub(
			db=SimpleNamespace(
				get_value=get_value,
				exists=lambda *args, **kwargs: False,
			),
			get_roles=lambda *args, **kwargs: [],
		)

		with (
			patch("vetedge.services.consultation_flow.frappe", frappe_stub),
			patch("vetedge.services.consultation_flow.validate_doctor_user"),
			patch("vetedge.services.consultation_flow.can_access_branch_data"),
			patch("vetedge.services.consultation_flow.apply_planned_treatment_defaults"),
			patch("vetedge.services.consultation_flow.validate_registration_payment_before_first_consultation"),
			patch("vetedge.services.consultation_flow.validate_consultation_clinical_permissions"),
			patch("vetedge.services.consultation_flow.validate_consultation_invoice_before_progress"),
			patch("vetedge.services.consultation_flow.validate_consultation_payment_before_treatment"),
			patch("vetedge.services.consultation_flow.sync_consultation_dispensary_state"),
			patch("vetedge.services.consultation_flow.validate_consultation_dispensary_requirements"),
		):
			validate_consultation(doc)

		self.assertEqual(doc.service_branch, "Branch A")

	def test_consultation_checks_registration_payment_gate(self):
		doc = frappe._dict(
			patient="VP-001",
			primary_owner=None,
			consulting_practitioner=None,
			consulting_practitioner_name=None,
			daily_consultation_number=None,
			service_branch="Branch B",
			consultation_datetime="2026-04-18 10:00:00",
			status="Draft",
			company="Test Company",
			symptoms=[],
			diagnoses=[],
			planned_treatments=[],
		)

		def get_value(doctype, name, fields=None, **kwargs):
			if doctype == "User" and fields == "full_name":
				return "Dr Ada Vet"
			if fields == "patient_name":
				return "Buddy"
			return frappe._dict(primary_owner="CUST-001", default_branch="Branch A")

		frappe_stub = make_frappe_stub(
			db=SimpleNamespace(
				get_value=get_value,
				exists=lambda *args, **kwargs: False,
			)
		)

		with (
			patch("vetedge.services.consultation_flow.frappe", frappe_stub),
			patch("vetedge.services.consultation_flow.validate_doctor_user"),
			patch("vetedge.services.consultation_flow.can_access_branch_data"),
			patch("vetedge.services.consultation_flow.apply_planned_treatment_defaults"),
			patch("vetedge.services.consultation_flow.validate_registration_payment_before_first_consultation") as validate_gate,
			patch("vetedge.services.consultation_flow.validate_consultation_clinical_permissions"),
			patch("vetedge.services.consultation_flow.assert_consultation_can_proceed"),
			patch("vetedge.services.consultation_flow.validate_consultation_invoice_before_progress"),
			patch("vetedge.services.consultation_flow.validate_consultation_payment_before_treatment"),
			patch("vetedge.services.consultation_flow.sync_consultation_dispensary_state"),
			patch("vetedge.services.consultation_flow.validate_consultation_dispensary_requirements"),
		):
			validate_consultation(doc)

		validate_gate.assert_not_called()

	def test_registration_payment_gate_runs_when_consultation_starts(self):
		doc = frappe._dict(
			patient="VP-001",
			primary_owner=None,
			consulting_practitioner="doctor@example.com",
			consulting_practitioner_name=None,
			daily_consultation_number=None,
			service_branch="Branch B",
			consultation_datetime="2026-04-18 10:00:00",
			status="In Progress",
			company="Test Company",
			symptoms=[],
			diagnoses=[],
			planned_treatments=[],
			linked_appointment=None,
		)

		def get_value(doctype, name, fields=None, **kwargs):
			if doctype == "User" and fields == "full_name":
				return "Dr Ada Vet"
			if fields == "patient_name":
				return "Buddy"
			return frappe._dict(primary_owner="CUST-001", default_branch="Branch A")

		frappe_stub = make_frappe_stub(
			db=SimpleNamespace(
				get_value=get_value,
				exists=lambda *args, **kwargs: False,
			)
		)

		with (
			patch("vetedge.services.consultation_flow.frappe", frappe_stub),
			patch("vetedge.services.consultation_flow.validate_doctor_user"),
			patch("vetedge.services.consultation_flow.can_access_branch_data"),
			patch("vetedge.services.consultation_flow.apply_planned_treatment_defaults"),
			patch("vetedge.services.consultation_flow.validate_registration_payment_before_first_consultation") as validate_gate,
			patch("vetedge.services.consultation_flow.validate_consultation_clinical_permissions"),
			patch("vetedge.services.consultation_flow.assert_consultation_can_proceed"),
			patch("vetedge.services.consultation_flow.validate_consultation_invoice_before_progress"),
			patch("vetedge.services.consultation_flow.validate_consultation_payment_before_treatment"),
			patch("vetedge.services.consultation_flow.sync_consultation_dispensary_state"),
			patch("vetedge.services.consultation_flow.validate_consultation_dispensary_requirements"),
		):
			validate_consultation(doc)

		validate_gate.assert_called_once_with("VP-001", current_consultation=None)

	def test_ready_for_treatment_consultation_blocks_new_treatment_items(self):
		doc = frappe._dict(
			patient="VP-001",
			primary_owner=None,
			consulting_practitioner="doctor@example.com",
			consulting_practitioner_name=None,
			daily_consultation_number=None,
			service_branch="Branch A",
			consultation_datetime="2026-04-18 10:00:00",
			status="Ready for Treatment",
			company="Test Company",
			symptoms=[],
			diagnoses=[],
			planned_treatments=[
				frappe._dict(name="ROW-1", item="XRAY", qty=1, uom="Nos", rate=500),
				frappe._dict(name="ROW-2", item="CBC", qty=1, uom="Nos", rate=1000),
			],
		)
		previous = frappe._dict(
			status="Ready for Treatment",
			planned_treatments=[
				frappe._dict(name="ROW-1", item="XRAY", qty=1, uom="Nos", rate=500),
			],
			get=lambda key, default=None: previous[key] if key in previous else default,
		)
		doc.get_doc_before_save = lambda: previous

		def get_value(doctype, name, fields=None, **kwargs):
			if doctype == "User" and fields == "full_name":
				return "Dr Ada Vet"
			if fields == "patient_name":
				return "Buddy"
			return frappe._dict(primary_owner="CUST-001", default_branch="Branch A")

		frappe_stub = make_frappe_stub(
			db=SimpleNamespace(
				get_value=get_value,
				exists=lambda *args, **kwargs: False,
			)
		)

		with (
			patch("vetedge.services.consultation_flow.frappe", frappe_stub),
			patch("vetedge.services.consultation_flow.validate_doctor_user"),
			patch("vetedge.services.consultation_flow.can_access_branch_data"),
			patch("vetedge.services.consultation_flow.apply_planned_treatment_defaults"),
			patch("vetedge.services.consultation_flow.validate_registration_payment_before_first_consultation"),
			patch("vetedge.services.consultation_flow.validate_consultation_clinical_permissions"),
			patch("vetedge.services.consultation_flow.validate_consultation_invoice_before_progress"),
			patch("vetedge.services.consultation_flow.validate_consultation_payment_before_treatment"),
			patch("vetedge.services.consultation_flow.sync_consultation_dispensary_state"),
			patch("vetedge.services.consultation_flow.validate_consultation_dispensary_requirements"),
		):
			with self.assertRaises(frappe.ValidationError):
				validate_consultation(doc)

	def test_consultation_requires_service_branch_when_patient_has_no_default(self):
		doc = frappe._dict(
			patient="VP-001",
			consulting_practitioner=None,
			service_branch=None,
			consultation_datetime="2026-04-18 10:00:00",
			status="Draft",
			company="Test Company",
			symptoms=[],
			diagnoses=[],
			planned_treatments=[],
		)

		frappe_stub = make_frappe_stub(
			db=SimpleNamespace(
				get_value=lambda *args, **kwargs: frappe._dict(
					primary_owner="CUST-001",
					default_branch=None,
				),
				exists=lambda *args, **kwargs: False,
			)
		)

		with (
			patch("vetedge.services.consultation_flow.frappe", frappe_stub),
			patch("vetedge.services.consultation_flow.can_access_branch_data"),
			patch("vetedge.services.consultation_flow.apply_planned_treatment_defaults"),
			patch("vetedge.services.consultation_flow.validate_registration_payment_before_first_consultation"),
			patch("vetedge.services.consultation_flow.validate_consultation_clinical_permissions"),
			patch("vetedge.services.consultation_flow.validate_consultation_invoice_before_progress"),
			patch("vetedge.services.consultation_flow.validate_consultation_payment_before_treatment"),
			patch("vetedge.services.consultation_flow.sync_consultation_dispensary_state"),
			patch("vetedge.services.consultation_flow.validate_consultation_dispensary_requirements"),
		):
			self.assertRaises(frappe.ValidationError, validate_consultation, doc)

	def test_child_rows_validate_links_and_qty(self):
		doc = frappe._dict(
			symptoms=[frappe._dict(symptom="Vomiting")],
			diagnoses=[frappe._dict(diagnosis="Gastroenteritis")],
			planned_treatments=[
				frappe._dict(
					item="CONSULT-ITEM",
					qty=1,
					rate=100,
					service_type="Consultation",
					treatment_type="Medication",
				),
				frappe._dict(
					item="FOLLOWUP-ITEM",
					qty=2,
					rate=250,
					service_type="Consultation",
					treatment_type="Procedure",
				),
			],
		)

		frappe_stub = make_frappe_stub(
			db=SimpleNamespace(
				exists=lambda *args, **kwargs: True,
				get_value=lambda doctype, name, fields=None, **kwargs: frappe._dict(disabled=0)
				if doctype == "Item"
				else 0,
			),
			get_meta=lambda doctype: SimpleNamespace(has_field=lambda fieldname: fieldname == "disabled"),
		)

		with (
			patch("vetedge.services.consultation_flow.frappe", frappe_stub),
			patch("vetedge.services.consultation_flow.apply_planned_treatment_defaults"),
			patch("vetedge.services.consultation_flow.validate_consultation_clinical_permissions"),
		):
			validate_consultation_children(doc)

		self.assertEqual([row.item for row in doc.planned_treatments], ["CONSULT-ITEM", "FOLLOWUP-ITEM"])
		self.assertEqual(doc.planned_treatments[0].amount, 100)
		self.assertEqual(doc.planned_treatments[1].amount, 500)

	def test_ready_for_treatment_lock_is_skipped_during_billing_sync(self):
		from vetedge.services.consultation_flow import validate_consultation_scope_lock

		doc = frappe._dict(
			name="VCON-001",
			status="Ready for Treatment",
			planned_treatments=[frappe._dict(name="ROW-1", item="CONSULT-ITEM", qty=1, rate=250)],
		)
		doc.get_doc_before_save = lambda: frappe._dict(
			status="Ready for Treatment",
			planned_treatments=[frappe._dict(name="ROW-1", item="CONSULT-ITEM", qty=1, rate=100)],
		)

		previous = getattr(frappe.flags, "vetedge_billing_core_syncing", False)
		frappe.flags.vetedge_billing_core_syncing = True
		try:
			validate_consultation_scope_lock(doc)
		finally:
			frappe.flags.vetedge_billing_core_syncing = previous

	def test_completion_requires_vitals_when_setting_is_active(self):
		doc = frappe._dict(name="VCON-001", status="Completed")
		doc.get_doc_before_save = lambda: frappe._dict(status="Ready for Treatment")

		with (
			patch("vetedge.services.consultation_flow.validate_consultation_invoice_before_progress"),
			patch("vetedge.services.consultation_flow.validate_consultation_payment_before_treatment"),
			patch("vetedge.services.consultation_flow.validate_consultation_dispensary_requirements"),
			patch("vetedge.services.consultation_flow.is_vitals_required_before_completion", return_value=True),
			patch("vetedge.services.consultation_flow.has_vitals_for_consultation", return_value=False),
			patch("vetedge.services.consultation_flow.frappe.throw", side_effect=frappe.ValidationError),
		):
			self.assertRaises(frappe.ValidationError, validate_completion_requirements, doc)

	def test_completion_gate_is_skipped_during_billing_core_sync(self):
		doc = frappe._dict(name="VCON-001", status="Completed")
		previous = getattr(frappe.flags, "vetedge_billing_core_syncing", False)
		frappe.flags.vetedge_billing_core_syncing = True
		try:
			with (
				patch("vetedge.services.consultation_flow.assert_consultation_can_proceed", side_effect=frappe.ValidationError) as gate,
				patch("vetedge.services.consultation_flow.validate_consultation_dispensary_requirements") as dispensary_gate,
			):
				validate_completion_requirements(doc)
		finally:
			frappe.flags.vetedge_billing_core_syncing = previous

		gate.assert_not_called()
		dispensary_gate.assert_not_called()

	def test_completion_gate_is_skipped_when_status_did_not_change(self):
		doc = frappe._dict(name="VCON-001", status="Completed")
		doc.get_doc_before_save = lambda: frappe._dict(status="Completed")

		with (
			patch("vetedge.services.consultation_flow.assert_consultation_can_proceed", side_effect=frappe.ValidationError) as gate,
			patch("vetedge.services.consultation_flow.validate_consultation_dispensary_requirements") as dispensary_gate,
		):
			validate_completion_requirements(doc)

		gate.assert_not_called()
		dispensary_gate.assert_not_called()

	def test_completion_gate_is_skipped_on_ordinary_ready_for_treatment_save(self):
		doc = frappe._dict(name="VCON-001", status="Ready for Treatment")
		doc.get_doc_before_save = lambda: frappe._dict(status="Ready for Treatment")

		with (
			patch("vetedge.services.consultation_flow.assert_consultation_can_proceed", side_effect=frappe.ValidationError) as gate,
			patch("vetedge.services.consultation_flow.validate_consultation_dispensary_requirements") as dispensary_gate,
		):
			validate_completion_requirements(doc)

		gate.assert_not_called()
		dispensary_gate.assert_not_called()

	def test_completion_gate_uses_canonical_billing_group_result(self):
		doc = frappe._dict(name="VCON-2026-00069", status="Ready for Treatment")
		doc.get_doc_before_save = lambda: frappe._dict(status="In Progress")

		with (
			patch("vetedge.services.consultation_flow.assert_consultation_can_proceed", return_value=None) as gate,
			patch("vetedge.services.consultation_flow.validate_consultation_dispensary_requirements") as dispensary_gate,
			patch("vetedge.services.consultation_flow.is_vitals_required_before_completion", return_value=False),
		):
			validate_completion_requirements(doc)

		gate.assert_called_once_with(doc, "Ready for Treatment")
		dispensary_gate.assert_called_once_with(doc)

	def test_consultation_status_transition_allows_in_progress_to_billing(self):
		validate_consultation_status_transition("In Progress", "Awaiting Payment")

	def test_consultation_status_transition_allows_pending_dispensary(self):
		validate_consultation_status_transition("In Progress", "Pending Dispensary")

	def test_transition_consultation_status_requires_invoice_before_ready(self):
		doc = frappe._dict(name="VCON-001", status="In Progress", save=lambda: doc)
		frappe_stub = make_frappe_stub(get_doc=lambda doctype, name: doc)

		with (
			patch("vetedge.services.consultation_flow.frappe", frappe_stub),
			patch("vetedge.services.consultation_flow.require_internal_user"),
			patch("vetedge.services.consultation_flow.can_access_consultation"),
			patch("vetedge.services.consultation_flow.assert_consultation_can_proceed", side_effect=frappe.ValidationError),
			patch("vetedge.services.consultation_flow.validate_consultation_payment_before_treatment"),
		):
			self.assertRaises(
				frappe.ValidationError,
				transition_consultation_status,
				"VCON-001",
				"Ready for Treatment",
			)

	def test_transition_consultation_status_requires_payment_before_ready(self):
		doc = frappe._dict(name="VCON-001", status="Awaiting Payment", save=lambda: doc)
		frappe_stub = make_frappe_stub(get_doc=lambda doctype, name: doc)

		with (
			patch("vetedge.services.consultation_flow.frappe", frappe_stub),
			patch("vetedge.services.consultation_flow.require_internal_user"),
			patch("vetedge.services.consultation_flow.can_access_consultation"),
			patch("vetedge.services.consultation_flow.validate_consultation_invoice_before_progress"),
			patch("vetedge.services.consultation_flow.assert_consultation_can_proceed", side_effect=frappe.ValidationError),
		):
			self.assertRaises(
				frappe.ValidationError,
				transition_consultation_status,
				"VCON-001",
				"Ready for Treatment",
			)

	def test_transition_consultation_status_uses_cancellation_preflight(self):
		doc = frappe._dict(
			name="VCON-001",
			status="Ready for Treatment",
			payment_status="Unpaid",
			save=lambda: doc,
		)
		frappe_stub = make_frappe_stub(get_doc=lambda doctype, name: doc)

		with (
			patch("vetedge.services.consultation_flow.frappe", frappe_stub),
			patch("vetedge.services.consultation_flow.require_internal_user"),
			patch("vetedge.services.consultation_flow.can_access_consultation"),
			patch("vetedge.services.consultation_flow.validate_consultation_invoice_before_progress"),
			patch("vetedge.services.consultation_flow.validate_consultation_payment_before_treatment"),
			patch("vetedge.services.consultation_flow.validate_consultation_can_be_cancelled", side_effect=frappe.ValidationError) as preflight,
		):
			self.assertRaises(
				frappe.ValidationError,
				transition_consultation_status,
				"VCON-001",
				"Cancelled",
			)
		preflight.assert_called_once_with("VCON-001")

	def test_consultation_status_transition_rejects_completed_reopen(self):
		frappe_stub = make_frappe_stub()

		with patch("vetedge.services.consultation_flow.frappe", frappe_stub):
			self.assertRaises(
				frappe.ValidationError,
				validate_consultation_status_transition,
				"Completed",
				"In Progress",
			)

	def test_transition_consultation_status_saves_document(self):
		saved = []
		doc = frappe._dict(name="VCON-001", status="In Progress")
		doc.save = lambda: saved.append(doc)
		frappe_stub = make_frappe_stub(get_doc=lambda *args, **kwargs: doc)

		with (
			patch("vetedge.services.consultation_flow.frappe", frappe_stub),
			patch("vetedge.services.consultation_flow.can_access_consultation"),
			patch("vetedge.services.consultation_flow.assert_consultation_can_proceed"),
			patch("vetedge.services.consultation_flow.validate_consultation_invoice_before_progress"),
			patch("vetedge.services.consultation_flow.validate_consultation_payment_before_treatment"),
		):
			result = transition_consultation_status("VCON-001", "Ready for Treatment")

			self.assertEqual(result["status"], "Ready for Treatment")
		self.assertEqual(saved, [doc])

	def test_start_consultation_from_draft_uses_valid_transition_without_gate_block(self):
		saved = []
		doc = frappe._dict(name="VCON-001", status="Draft")
		doc.save = lambda: saved.append(doc)
		frappe_stub = make_frappe_stub(get_doc=lambda *args, **kwargs: doc)

		with (
			patch("vetedge.services.consultation_flow.frappe", frappe_stub),
			patch("vetedge.services.consultation_flow.can_access_consultation"),
			patch("vetedge.services.consultation_flow.assert_consultation_can_proceed") as gate,
		):
			result = transition_consultation_status("VCON-001", "In Progress")

		self.assertEqual(result["status"], "In Progress")
		self.assertEqual(saved, [doc])
		gate.assert_called_once_with(doc, "In Progress")

	def test_transition_consultation_status_blocks_when_feature_disabled(self):
		doc = frappe._dict(name="VCON-001", status="In Progress")
		frappe_stub = make_frappe_stub(get_doc=lambda *args, **kwargs: doc)

		with (
			patch("vetedge.services.consultation_flow.frappe", frappe_stub),
			patch("vetedge.services.consultation_flow.is_enabled", return_value=False),
		):
			self.assertRaises(
				frappe.ValidationError,
				transition_consultation_status,
				"VCON-001",
				"Ready for Treatment",
			)

	def test_validate_consultation_blocks_saving_paid_consultation_as_cancelled(self):
		doc = frappe._dict(
			name="VCON-001",
			patient="VP-001",
			primary_owner="CUST-001",
			consulting_practitioner="doctor@example.com",
			consulting_practitioner_name=None,
			daily_consultation_number=None,
			service_branch="Branch A",
			consultation_datetime="2026-04-18 10:00:00",
			status="Cancelled",
			payment_status="Paid",
			company="Test Company",
			symptoms=[],
			diagnoses=[],
			planned_treatments=[],
		)
		previous = frappe._dict(
			status="Ready for Treatment",
			payment_status="Paid",
			planned_treatments=[],
			get=lambda key, default=None: previous[key] if key in previous else default,
		)
		doc.get_doc_before_save = lambda: previous

		def get_value(doctype, name, fields=None, **kwargs):
			if doctype == "User" and fields == "full_name":
				return "Dr Ada Vet"
			if fields == "patient_name":
				return "Buddy"
			return frappe._dict(primary_owner="CUST-001", default_branch="Branch A")

		frappe_stub = make_frappe_stub(
			db=SimpleNamespace(
				get_value=get_value,
				exists=lambda *args, **kwargs: False,
			)
		)

		with (
			patch("vetedge.services.consultation_flow.frappe", frappe_stub),
			patch("vetedge.services.consultation_flow.validate_doctor_user"),
			patch("vetedge.services.consultation_flow.can_access_branch_data"),
			patch("vetedge.services.consultation_flow.apply_planned_treatment_defaults"),
			patch("vetedge.services.consultation_flow.validate_registration_payment_before_first_consultation"),
			patch("vetedge.services.consultation_flow.validate_consultation_clinical_permissions"),
			patch("vetedge.services.consultation_flow.validate_consultation_invoice_before_progress"),
			patch("vetedge.services.consultation_flow.validate_consultation_payment_before_treatment"),
			patch("vetedge.services.consultation_flow.sync_consultation_dispensary_state"),
			patch("vetedge.services.consultation_flow.validate_consultation_dispensary_requirements"),
			patch("vetedge.services.consultation_flow.validate_consultation_can_be_cancelled", side_effect=frappe.ValidationError) as preflight,
		):
			with self.assertRaises(frappe.ValidationError):
				validate_consultation(doc)
		preflight.assert_called_once_with("VCON-001")

	def test_linked_appointment_must_belong_to_selected_patient(self):
		doc = frappe._dict(
			name="VCON-001",
			patient="VP-001",
			linked_appointment="VAPT-001",
		)
		frappe_stub = make_frappe_stub(
			db=SimpleNamespace(
				get_value=lambda *args, **kwargs: frappe._dict(
					name="VAPT-001",
					patient="VP-002",
					status="Confirmed",
					branch="Main",
					practitioner=None,
					notes=None,
					linked_consultation=None,
				)
			)
		)

		with patch("vetedge.services.consultation_flow.frappe", frappe_stub):
			self.assertRaises(frappe.ValidationError, validate_linked_appointment, doc)

	def test_linked_appointment_allows_ready_status_for_selected_patient(self):
		doc = frappe._dict(
			name="VCON-001",
			patient="VP-001",
			linked_appointment="VAPT-001",
		)
		frappe_stub = make_frappe_stub(
			db=SimpleNamespace(
				get_value=lambda *args, **kwargs: frappe._dict(
					name="VAPT-001",
					patient="VP-001",
					status="Confirmed",
					branch="Main",
					practitioner=None,
					notes=None,
					linked_consultation=None,
				)
			)
		)

		with patch("vetedge.services.consultation_flow.frappe", frappe_stub):
			validate_linked_appointment(doc)

	def test_linked_appointment_rejects_completed_appointment(self):
		doc = frappe._dict(
			name="VCON-001",
			patient="VP-001",
			linked_appointment="VAPT-001",
		)
		frappe_stub = make_frappe_stub(
			db=SimpleNamespace(
				get_value=lambda *args, **kwargs: frappe._dict(
					name="VAPT-001",
					patient="VP-001",
					status="Completed",
					branch="Main",
					practitioner=None,
					notes=None,
					linked_consultation=None,
				)
			)
		)

		with patch("vetedge.services.consultation_flow.frappe", frappe_stub):
			self.assertRaises(frappe.ValidationError, validate_linked_appointment, doc)

	def test_linked_appointment_rejects_existing_consultation_link(self):
		doc = frappe._dict(
			name="VCON-002",
			patient="VP-001",
			linked_appointment="VAPT-001",
		)
		frappe_stub = make_frappe_stub(
			db=SimpleNamespace(
				get_value=lambda *args, **kwargs: frappe._dict(
					name="VAPT-001",
					patient="VP-001",
					status="Confirmed",
					branch="Main",
					practitioner=None,
					notes=None,
					linked_consultation="VCON-001",
				)
			)
		)

		with patch("vetedge.services.consultation_flow.frappe", frappe_stub):
			self.assertRaises(frappe.ValidationError, validate_linked_appointment, doc)

	def test_consultation_appointment_summary_returns_service_appointment(self):
		consultation = frappe._dict(
			doctype="Veterinary Consultation",
			name="VCON-001",
			linked_appointment="VAPT-001",
			follow_up_appointment=None,
		)
		appointment = make_appointment_doc("VAPT-001")

		frappe_stub = make_frappe_stub(
			get_doc=lambda doctype, name: consultation if doctype == "Veterinary Consultation" else appointment,
			has_permission=lambda *args, **kwargs: True,
			get_meta=lambda doctype: SimpleNamespace(
				has_field=lambda fieldname: False,
				get_title_field=lambda: {
					"Veterinary Patient": "patient_name",
					"Customer": "customer_name",
					"User": "full_name",
				}.get(doctype, "name"),
			),
			db=SimpleNamespace(
				exists=lambda doctype, name=None: doctype == "Veterinary Appointment",
				get_value=lambda doctype, name, field=None, **kwargs: {
					("Veterinary Patient", "VP-001", "patient_name"): "Buddy",
					("Customer", "CUST-001", "customer_name"): "Ada Owner",
					("User", "doctor@example.com", "full_name"): "Dr Vet",
				}.get((doctype, name, field), name),
			),
		)

		with (
			patch("vetedge.services.consultation_flow.frappe", frappe_stub),
			patch("vetedge.services.consultation_flow.require_internal_user"),
			patch("vetedge.services.consultation_flow.can_access_consultation"),
			patch("vetedge.services.consultation_flow.can_access_branch_data"),
		):
			result = get_consultation_appointment_summary("VCON-001")

		self.assertEqual(result["service_appointment"]["name"], "VAPT-001")
		self.assertEqual(result["service_appointment"]["patient_name"], "Buddy")
		self.assertEqual(result["service_appointment"]["owner_name"], "Ada Owner")
		self.assertIsNone(result["follow_up_appointment"])

	def test_consultation_appointment_summary_returns_follow_up_appointment(self):
		consultation = frappe._dict(
			doctype="Veterinary Consultation",
			name="VCON-001",
			linked_appointment=None,
			follow_up_appointment="VAPT-FU-001",
		)
		follow_up = make_appointment_doc(
			"VAPT-FU-001",
			appointment_type="Follow Up",
			follow_up_reference="VCON-001",
		)

		frappe_stub = make_frappe_stub(
			get_doc=lambda doctype, name: consultation if doctype == "Veterinary Consultation" else follow_up,
			has_permission=lambda *args, **kwargs: True,
			db=SimpleNamespace(
				exists=lambda doctype, name=None: doctype == "Veterinary Appointment",
				get_value=lambda doctype, name, field=None, **kwargs: name,
			),
		)

		with (
			patch("vetedge.services.consultation_flow.frappe", frappe_stub),
			patch("vetedge.services.consultation_flow.require_internal_user"),
			patch("vetedge.services.consultation_flow.can_access_consultation"),
			patch("vetedge.services.consultation_flow.can_access_branch_data"),
		):
			result = get_consultation_appointment_summary("VCON-001")

		self.assertIsNone(result["service_appointment"])
		self.assertEqual(result["follow_up_appointment"]["name"], "VAPT-FU-001")
		self.assertEqual(result["follow_up_appointment"]["source_consultation"], "VCON-001")

	def test_consultation_appointment_summary_returns_empty_state_without_appointments(self):
		consultation = frappe._dict(
			doctype="Veterinary Consultation",
			name="VCON-001",
			linked_appointment=None,
			follow_up_appointment=None,
		)
		frappe_stub = make_frappe_stub(get_doc=lambda doctype, name: consultation)

		with (
			patch("vetedge.services.consultation_flow.frappe", frappe_stub),
			patch("vetedge.services.consultation_flow.require_internal_user"),
			patch("vetedge.services.consultation_flow.can_access_consultation"),
		):
			result = get_consultation_appointment_summary("VCON-001")

		self.assertIsNone(result["service_appointment"])
		self.assertIsNone(result["follow_up_appointment"])

	def test_consultation_appointment_summary_respects_branch_restrictions(self):
		consultation = frappe._dict(
			doctype="Veterinary Consultation",
			name="VCON-001",
			linked_appointment="VAPT-001",
			follow_up_appointment=None,
		)
		appointment = make_appointment_doc("VAPT-001", branch="Restricted Branch")
		frappe_stub = make_frappe_stub(
			get_doc=lambda doctype, name: consultation if doctype == "Veterinary Consultation" else appointment,
			has_permission=lambda *args, **kwargs: True,
			db=SimpleNamespace(exists=lambda doctype, name=None: doctype == "Veterinary Appointment"),
		)

		with (
			patch("vetedge.services.consultation_flow.frappe", frappe_stub),
			patch("vetedge.services.consultation_flow.require_internal_user"),
			patch("vetedge.services.consultation_flow.can_access_consultation"),
			patch("vetedge.services.consultation_flow.can_access_branch_data", side_effect=frappe.PermissionError),
		):
			self.assertRaises(frappe.PermissionError, get_consultation_appointment_summary, "VCON-001")

	def test_claim_linked_appointment_marks_it_in_consultation(self):
		doc = frappe._dict(
			name="VCON-001",
			linked_appointment="VAPT-001",
		)
		updates = []
		frappe_stub = make_frappe_stub(
			db=SimpleNamespace(
				get_value=lambda *args, **kwargs: frappe._dict(
					name="VAPT-001",
					patient="VP-001",
					status="Checked In",
					branch="Main",
					practitioner=None,
					notes=None,
					linked_consultation=None,
				),
				set_value=lambda *args, **kwargs: updates.append((args, kwargs)),
			)
		)

		with patch("vetedge.services.consultation_flow.frappe", frappe_stub):
			claim_linked_appointment_for_consultation(doc)

		self.assertEqual(updates[0][0][0], "Veterinary Appointment")
		self.assertEqual(updates[0][0][1], "VAPT-001")
		self.assertEqual(updates[0][0][2]["linked_consultation"], "VCON-001")
		self.assertEqual(updates[0][0][2]["status"], "In Consultation")

	def test_normalize_moves_legacy_follow_up_appointment_link(self):
		doc = frappe._dict(
			name="VCON-001",
			linked_appointment="VAPT-001",
			follow_up_appointment=None,
		)
		frappe_stub = make_frappe_stub(
			db=SimpleNamespace(
				get_value=lambda *args, **kwargs: frappe._dict(
					name="VAPT-001",
					patient="VP-001",
					status="Scheduled",
					branch="Main",
					practitioner=None,
					notes=None,
					linked_consultation=None,
					follow_up_reference="VCON-001",
				)
			),
			get_meta=lambda doctype: SimpleNamespace(has_field=lambda fieldname: fieldname == "follow_up_appointment"),
		)

		with patch("vetedge.services.consultation_flow.frappe", frappe_stub):
			normalize_consultation_appointment_links(doc)

		self.assertIsNone(doc.linked_appointment)
		self.assertEqual(doc.follow_up_appointment, "VAPT-001")

	def test_completed_consultation_marks_service_appointment_completed(self):
		doc = frappe._dict(
			name="VCON-001",
			status="Completed",
			linked_appointment="VAPT-001",
		)
		updates = []
		frappe_stub = make_frappe_stub(
			db=SimpleNamespace(
				get_value=lambda *args, **kwargs: frappe._dict(
					name="VAPT-001",
					patient="VP-001",
					status="In Consultation",
					branch="Main",
					practitioner="doctor@example.com",
					notes=None,
					linked_consultation="VCON-001",
					follow_up_reference=None,
				),
				set_value=lambda *args, **kwargs: updates.append((args, kwargs)),
			)
		)

		with (
			patch("vetedge.services.consultation_flow.frappe", frappe_stub),
			patch("vetedge.services.consultation_flow.emit_notification_event", return_value={"queued": False}) as emit,
		):
			sync_service_appointment_status_from_consultation(doc)

		self.assertEqual(updates[0][0], ("Veterinary Appointment", "VAPT-001", "status", "Completed"))
		self.assertEqual(emit.call_args.kwargs["event_key"], "appointment_completed")

	def test_cancelled_consultation_marks_service_appointment_cancelled(self):
		doc = frappe._dict(
			name="VCON-001",
			status="Cancelled",
			linked_appointment="VAPT-001",
		)
		updates = []
		frappe_stub = make_frappe_stub(
			db=SimpleNamespace(
				get_value=lambda *args, **kwargs: frappe._dict(
					name="VAPT-001",
					patient="VP-001",
					status="In Consultation",
					branch="Main",
					practitioner=None,
					notes=None,
					linked_consultation="VCON-001",
					follow_up_reference=None,
				),
				set_value=lambda *args, **kwargs: updates.append((args, kwargs)),
			)
		)

		with (
			patch("vetedge.services.consultation_flow.frappe", frappe_stub),
			patch("vetedge.services.consultation_flow.emit_notification_event", return_value={"queued": False}) as emit,
		):
			sync_service_appointment_status_from_consultation(doc)

		self.assertEqual(updates[0][0], ("Veterinary Appointment", "VAPT-001", "status", "Cancelled"))
		self.assertEqual(emit.call_args.kwargs["event_key"], "appointment_cancelled")

	def test_branch_assignment_is_enforced_when_assignment_doctype_exists(self):
		frappe_stub = make_frappe_stub(
			db=SimpleNamespace(exists=lambda *args, **kwargs: args == ("DocType", "Branch User Assignment")),
			get_all=lambda *args, **kwargs: [],
			get_meta=lambda doctype: SimpleNamespace(has_field=lambda fieldname: False),
		)

		with (
			patch("vetedge.services.consultation_flow.frappe", frappe_stub),
			patch("vetedge.services.consultation_flow.can_access_branch_data", side_effect=frappe.PermissionError),
		):
			self.assertRaises(
				frappe.PermissionError,
				validate_service_branch_access,
				frappe._dict(service_branch="Main", consulting_practitioner=None),
			)

	def test_practitioner_branch_assignment_is_optional_until_assignments_exist(self):
		get_all_calls = []

		def get_all(doctype, filters=None, **kwargs):
			get_all_calls.append((doctype, filters))
			return []

		frappe_stub = make_frappe_stub(
			db=SimpleNamespace(exists=lambda *args, **kwargs: args == ("DocType", "Branch Practitioner Assignment")),
			get_all=get_all,
			get_meta=lambda doctype: SimpleNamespace(has_field=lambda fieldname: False),
		)

		with (
			patch("vetedge.services.consultation_flow.frappe", frappe_stub),
			patch("vetedge.services.consultation_flow.can_access_branch_data"),
		):
			validate_service_branch_access(
				frappe._dict(service_branch="Main", consulting_practitioner="doctor@example.com"),
			)

		self.assertEqual(
			get_all_calls,
			[("Branch Practitioner Assignment", {"practitioner": "doctor@example.com"})],
		)

	def test_practitioner_branch_assignment_is_enforced_when_practitioner_is_scoped(self):
		get_all_calls = []

		def get_all(doctype, filters=None, **kwargs):
			get_all_calls.append((doctype, filters))
			if filters == {"practitioner": "doctor@example.com"}:
				return [frappe._dict(name="BPA-001")]
			return []

		frappe_stub = make_frappe_stub(
			db=SimpleNamespace(exists=lambda *args, **kwargs: args == ("DocType", "Branch Practitioner Assignment")),
			get_all=get_all,
			get_meta=lambda doctype: SimpleNamespace(has_field=lambda fieldname: False),
		)

		with (
			patch("vetedge.services.consultation_flow.frappe", frappe_stub),
			patch("vetedge.services.consultation_flow.can_access_branch_data"),
		):
			self.assertRaises(
				frappe.PermissionError,
				validate_service_branch_access,
				frappe._dict(service_branch="Main", consulting_practitioner="doctor@example.com"),
			)

		self.assertEqual(
			get_all_calls,
			[
				("Branch Practitioner Assignment", {"practitioner": "doctor@example.com"}),
				("Branch Practitioner Assignment", {"practitioner": "doctor@example.com", "branch": "Main"}),
			],
		)


def make_frappe_stub(**overrides):
	def throw(*args, **kwargs):
		exc = args[1] if len(args) > 1 else kwargs.get("exc")
		if isinstance(exc, type) and issubclass(exc, Exception):
			raise exc()
		raise frappe.ValidationError()

	stub = SimpleNamespace(
		db=SimpleNamespace(exists=lambda *args, **kwargs: False),
		get_all=lambda *args, **kwargs: [],
		get_roles=lambda *args, **kwargs: ["VetEdge Doctor"],
		get_meta=lambda doctype: SimpleNamespace(
			has_field=lambda fieldname: False,
			get_title_field=lambda: "patient_name" if doctype == "Veterinary Patient" else "name",
		),
		session=SimpleNamespace(user="test@example.com"),
		throw=throw,
		utils=SimpleNamespace(now_datetime=lambda: "2026-04-18 10:00:00"),
		ValidationError=frappe.ValidationError,
		PermissionError=frappe.PermissionError,
	)
	for key, value in overrides.items():
		setattr(stub, key, value)
	return stub


def make_appointment_doc(name: str, **overrides):
	values = {
		"doctype": "Veterinary Appointment",
		"name": name,
		"appointment_datetime": "2026-04-18 10:00:00",
		"status": "Confirmed",
		"patient": "VP-001",
		"primary_owner": "CUST-001",
		"branch": "Main Branch",
		"practitioner": "doctor@example.com",
		"practitioner_name": "Dr Vet",
		"appointment_type": "Consultation",
		"notes": "Annual check",
		"linked_consultation": None,
		"follow_up_reference": None,
	}
	values.update(overrides)
	return frappe._dict(values)
