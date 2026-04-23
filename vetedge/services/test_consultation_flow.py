from __future__ import annotations

from types import SimpleNamespace
from unittest import TestCase
from unittest.mock import patch

import frappe

from vetedge.services.consultation_flow import (
	claim_linked_appointment_for_consultation,
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


class TestConsultationFlow(TestCase):
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
			)
		)

		with (
			patch("vetedge.services.consultation_flow.frappe", frappe_stub),
			patch("vetedge.services.consultation_flow.can_access_branch_data"),
			patch("vetedge.services.consultation_flow.apply_planned_treatment_defaults"),
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
			patch("vetedge.services.consultation_flow.can_access_branch_data"),
			patch("vetedge.services.consultation_flow.apply_planned_treatment_defaults"),
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
			)
		)

		with (
			patch("vetedge.services.consultation_flow.frappe", frappe_stub),
			patch("vetedge.services.consultation_flow.can_access_branch_data"),
			patch("vetedge.services.consultation_flow.apply_planned_treatment_defaults"),
			patch("vetedge.services.consultation_flow.validate_consultation_clinical_permissions"),
			patch("vetedge.services.consultation_flow.validate_consultation_invoice_before_progress"),
			patch("vetedge.services.consultation_flow.validate_consultation_payment_before_treatment"),
			patch("vetedge.services.consultation_flow.sync_consultation_dispensary_state"),
			patch("vetedge.services.consultation_flow.validate_consultation_dispensary_requirements"),
		):
			validate_consultation(doc)

		self.assertEqual(doc.service_branch, "Branch A")

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
					service_type="Consultation",
					treatment_type="Medication",
				)
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

	def test_completion_requires_vitals_when_setting_is_active(self):
		doc = frappe._dict(name="VCON-001", status="Completed")

		with (
			patch("vetedge.services.consultation_flow.validate_consultation_invoice_before_progress"),
			patch("vetedge.services.consultation_flow.validate_consultation_payment_before_treatment"),
			patch("vetedge.services.consultation_flow.validate_consultation_dispensary_requirements"),
			patch("vetedge.services.consultation_flow.is_vitals_required_before_completion", return_value=True),
			patch("vetedge.services.consultation_flow.has_vitals_for_consultation", return_value=False),
			patch("vetedge.services.consultation_flow.frappe.throw", side_effect=frappe.ValidationError),
		):
			self.assertRaises(frappe.ValidationError, validate_completion_requirements, doc)

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
			patch("vetedge.services.consultation_flow.validate_consultation_invoice_before_progress", side_effect=frappe.ValidationError),
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
			patch("vetedge.services.consultation_flow.validate_consultation_payment_before_treatment", side_effect=frappe.ValidationError),
		):
			self.assertRaises(
				frappe.ValidationError,
				transition_consultation_status,
				"VCON-001",
				"Ready for Treatment",
			)

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
			patch("vetedge.services.consultation_flow.validate_consultation_invoice_before_progress"),
			patch("vetedge.services.consultation_flow.validate_consultation_payment_before_treatment"),
		):
			result = transition_consultation_status("VCON-001", "Ready for Treatment")

		self.assertEqual(result["status"], "Ready for Treatment")
		self.assertEqual(saved, [doc])

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
		self.assertEqual(emit.call_args.kwargs["event"], "appointment_completed")

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
		self.assertEqual(emit.call_args.kwargs["event"], "appointment_cancelled")

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
