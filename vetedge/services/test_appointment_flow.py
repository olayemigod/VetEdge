from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace
from unittest import TestCase
from unittest.mock import patch

import frappe

from vetedge.services.appointment_flow import (
	create_consultation_from_appointment,
	get_appointment_queue,
	normalize_consultation_links,
	transition_appointment_status,
	validate_appointment,
	validate_branch_access,
	validate_duplicate_practitioner_slot,
	validate_linked_consultation,
	validate_start_consultation_from_appointment,
	validate_status,
)


class TestAppointmentFlow(TestCase):
	def test_appointment_feature_flag_blocks_validation(self):
		doc = make_appointment_doc()

		with (
			patch("vetedge.services.appointment_flow.frappe", make_frappe_stub()),
			patch("vetedge.services.appointment_flow.is_enabled", return_value=False),
		):
			self.assertRaises(frappe.ValidationError, validate_appointment, doc)

	def test_appointment_resolves_owner_and_allows_cross_branch_patient(self):
		doc = make_appointment_doc(branch="Branch B")

		frappe_stub = make_frappe_stub(
			db=SimpleNamespace(
				get_value=get_value_for_patient_and_user,
				exists=lambda *args, **kwargs: False,
			)
		)

		with (
			patch("vetedge.services.appointment_flow.frappe", frappe_stub),
			patch("vetedge.services.appointment_flow.get_user_full_name", return_value="Dr Ada Vet"),
			patch("vetedge.services.appointment_flow.get_document_title", return_value="Buddy"),
			patch("vetedge.services.appointment_flow.validate_doctor_user"),
			patch("vetedge.services.appointment_flow.validate_user_branch_access"),
			patch("vetedge.services.appointment_flow.validate_practitioner_branch_access"),
		):
			validate_appointment(doc)

		self.assertEqual(doc.primary_owner, "CUST-001")
		self.assertEqual(doc.branch, "Branch B")
		self.assertIn("Dr Ada Vet", doc.appointment_title)

	def test_appointment_defaults_branch_from_patient_home_branch(self):
		doc = make_appointment_doc(branch=None)
		frappe_stub = make_frappe_stub(
			db=SimpleNamespace(
				get_value=get_value_for_patient_and_user,
				exists=lambda *args, **kwargs: False,
			)
		)

		with (
			patch("vetedge.services.appointment_flow.frappe", frappe_stub),
			patch("vetedge.services.appointment_flow.get_user_full_name", return_value="Dr Ada Vet"),
			patch("vetedge.services.appointment_flow.get_document_title", return_value="Buddy"),
			patch("vetedge.services.appointment_flow.validate_doctor_user"),
			patch("vetedge.services.appointment_flow.validate_user_branch_access"),
			patch("vetedge.services.appointment_flow.validate_practitioner_branch_access"),
		):
			validate_appointment(doc)

		self.assertEqual(doc.branch, "Branch A")

	def test_invalid_status_transition_is_rejected(self):
		doc = make_appointment_doc(status="Completed")
		doc.get_doc_before_save = lambda: frappe._dict(status="Scheduled")

		frappe_stub = make_frappe_stub()
		with patch("vetedge.services.appointment_flow.frappe", frappe_stub):
			self.assertRaises(frappe.ValidationError, validate_status, doc)

	def test_final_statuses_are_terminal_and_preserve_existing_links(self):
		for final_status in ("Completed", "Cancelled", "No Show"):
			with self.subTest(final_status=final_status):
				doc = make_appointment_doc(
					status="Confirmed",
					primary_owner="CUST-001",
					linked_consultation="VCON-001",
					source_doctype="Veterinary Grooming",
					source_name="VGRM-001",
					notes="Existing appointment notes",
				)
				previous = make_appointment_doc(
					status=final_status,
					primary_owner="CUST-001",
					linked_consultation="VCON-001",
					source_doctype="Veterinary Grooming",
					source_name="VGRM-001",
					notes="Existing appointment notes",
				)
				doc.get_doc_before_save = lambda previous=previous: previous

				frappe_stub = make_frappe_stub()
				with patch("vetedge.services.appointment_flow.frappe", frappe_stub):
					self.assertRaises(frappe.ValidationError, validate_status, doc)

				self.assertEqual(doc.patient, "VP-001")
				self.assertEqual(doc.primary_owner, "CUST-001")
				self.assertEqual(doc.linked_consultation, "VCON-001")
				self.assertEqual(doc.source_doctype, "Veterinary Grooming")
				self.assertEqual(doc.source_name, "VGRM-001")
				self.assertEqual(doc.notes, "Existing appointment notes")

	def test_appointment_metadata_and_ui_preserve_final_status_history_links(self):
		meta_path = Path(__file__).resolve().parents[1] / "veterinary" / "doctype" / "veterinary_appointment" / "veterinary_appointment.json"
		js_path = Path(__file__).resolve().parents[1] / "veterinary" / "doctype" / "veterinary_appointment" / "veterinary_appointment.js"
		meta = json.loads(meta_path.read_text())
		fields = {field["fieldname"]: field for field in meta["fields"]}
		script = js_path.read_text()

		self.assertIn("Completed", fields["status"]["options"])
		self.assertIn("Cancelled", fields["status"]["options"])
		self.assertIn("No Show", fields["status"]["options"])
		self.assertEqual(fields["linked_consultation"]["read_only"], 1)
		self.assertEqual(fields["source_name"]["read_only"], 1)
		self.assertIn("add_consultation_link_actions(frm)", script)
		self.assertIn('__("Open Service Consultation")', script)
		self.assertIn('__("Open Originating Consultation")', script)

	def test_confirmed_appointment_can_move_to_in_consultation(self):
		doc = make_appointment_doc(status="In Consultation")
		doc.get_doc_before_save = lambda: frappe._dict(status="Confirmed")

		frappe_stub = make_frappe_stub()
		with patch("vetedge.services.appointment_flow.frappe", frappe_stub):
			validate_status(doc)

	def test_owner_requested_appointment_can_be_approved_to_scheduled(self):
		doc = make_appointment_doc(status="Scheduled", created_from="Portal")
		doc.get_doc_before_save = lambda: frappe._dict(status="Owner Requested")

		frappe_stub = make_frappe_stub()
		with patch("vetedge.services.appointment_flow.frappe", frappe_stub):
			validate_status(doc)

	def test_owner_requested_portal_appointment_skips_staff_branch_access(self):
		doc = make_appointment_doc(status="Owner Requested", created_from="Portal", branch="Branch B")

		with (
			patch("vetedge.services.appointment_flow.validate_user_branch_access") as user_validator,
			patch("vetedge.services.appointment_flow.validate_practitioner_branch_access") as practitioner_validator,
		):
			validate_branch_access(doc)

		user_validator.assert_not_called()
		practitioner_validator.assert_not_called()

	def test_duplicate_practitioner_exact_slot_is_rejected(self):
		doc = make_appointment_doc(name="VAPT-001")
		frappe_stub = make_frappe_stub(get_all=lambda *args, **kwargs: ["VAPT-002"])

		with patch("vetedge.services.appointment_flow.frappe", frappe_stub):
			self.assertRaises(frappe.ValidationError, validate_duplicate_practitioner_slot, doc)

	def test_branch_validation_delegates_to_assignment_rules(self):
		doc = make_appointment_doc(branch="Branch B")

		with (
			patch("vetedge.services.appointment_flow.validate_user_branch_access") as user_validator,
			patch("vetedge.services.appointment_flow.validate_practitioner_branch_access") as practitioner_validator,
		):
			validate_branch_access(doc)

		user_validator.assert_called_once_with("Branch B")
		practitioner_validator.assert_called_once_with("doctor@example.com", "Branch B")

	def test_appointment_practitioner_must_be_doctor_user(self):
		doc = make_appointment_doc(practitioner="nurse@example.com")

		with (
			patch("vetedge.services.appointment_flow.frappe", make_frappe_stub()),
			patch("vetedge.services.appointment_flow.validate_doctor_user", side_effect=frappe.ValidationError),
			patch("vetedge.services.appointment_flow.get_user_full_name", return_value="Nurse User"),
			patch("vetedge.services.appointment_flow.get_document_title", return_value="Buddy"),
			patch("vetedge.services.appointment_flow.validate_user_branch_access"),
			patch("vetedge.services.appointment_flow.validate_practitioner_branch_access"),
		):
			self.assertRaises(frappe.ValidationError, validate_appointment, doc)

	def test_queue_segments_today_tomorrow_and_future(self):
		calls = []

		def get_all(doctype, filters=None, **kwargs):
			calls.append(filters)
			return [frappe._dict(name="VAPT-001", appointment_datetime="2026-04-19 09:00:00")]

		frappe_stub = make_frappe_stub(get_all=get_all)
		with patch("vetedge.services.appointment_flow.frappe", frappe_stub):
			queue = get_appointment_queue(reference_date="2026-04-19")

		self.assertIn("today", queue)
		self.assertIn("tomorrow", queue)
		self.assertIn("future", queue)
		self.assertEqual(len(calls), 3)
		self.assertTrue(any("appointment_datetime" in filters for filters in calls))

	def test_queue_status_filter_limits_status(self):
		calls = []

		def get_all(doctype, filters=None, **kwargs):
			calls.append(filters)
			return []

		frappe_stub = make_frappe_stub(get_all=get_all)
		with patch("vetedge.services.appointment_flow.frappe", frappe_stub):
			get_appointment_queue(status="Owner Requested", reference_date="2026-04-19")

		self.assertEqual(len(calls), 3)
		self.assertTrue(all(filters["status"] == "Owner Requested" for filters in calls))

	def test_queue_rejects_invalid_status_filter(self):
		frappe_stub = make_frappe_stub()

		with patch("vetedge.services.appointment_flow.frappe", frappe_stub):
			self.assertRaises(
				frappe.ValidationError,
				get_appointment_queue,
				status="Bad Status",
				reference_date="2026-04-19",
			)

	def test_queue_blocks_when_appointments_disabled(self):
		with (
			patch("vetedge.services.appointment_flow.frappe", make_frappe_stub()),
			patch("vetedge.services.appointment_flow.is_enabled", return_value=False),
		):
			self.assertRaises(frappe.ValidationError, get_appointment_queue, reference_date="2026-04-19")

	def test_follow_up_creation_from_consultation_links_consultation(self):
		inserted = []
		set_values = []

		def get_doc(*args, **kwargs):
			if args and args[0] == "Veterinary Consultation":
				return frappe._dict(
					name="VCON-001",
					patient="VP-001",
					primary_owner="CUST-001",
					service_branch="Branch B",
					consulting_practitioner="doctor@example.com",
					planned_treatments=[frappe._dict(name="PT-1", item="ITEM-1", qty=1)],
				)
			doc = frappe._dict(args[0])
			doc.name = "VAPT-001"
			doc.appointment_title = "Buddy - Follow Up"
			doc.insert = lambda ignore_permissions=True: inserted.append(doc)
			return doc

		frappe_stub = make_frappe_stub(
			get_doc=get_doc,
			get_meta=lambda doctype: SimpleNamespace(has_field=lambda fieldname: fieldname == "follow_up_appointment"),
			db=SimpleNamespace(
				exists=lambda *args, **kwargs: False,
				set_value=lambda *args, **kwargs: set_values.append(args),
			),
		)

		with (
			patch("vetedge.services.appointment_flow.frappe", frappe_stub),
			patch("vetedge.services.appointment_flow.can_access_consultation"),
			patch("vetedge.services.appointment_flow.emit_notification_event", return_value={"queued": False}) as emit,
		):
			from vetedge.services.appointment_flow import create_follow_up_from_consultation

			result = create_follow_up_from_consultation("VCON-001", "2026-04-25 09:00:00")

		self.assertEqual(result["name"], "VAPT-001")
		self.assertEqual(inserted[0].follow_up_reference, "VCON-001")
		self.assertIsNone(inserted[0].get("linked_consultation"))
		self.assertEqual(set_values[0][2], "follow_up_appointment")
		self.assertNotIn("planned_treatments", {args[2] for args in set_values})
		self.assertEqual(emit.call_args.kwargs["event_key"], "appointment_created")

	def test_normalize_clears_old_follow_up_link_bug(self):
		doc = make_appointment_doc(
			is_follow_up=1,
			follow_up_reference="VCON-001",
			linked_consultation="VCON-001",
		)

		normalize_consultation_links(doc)

		self.assertIsNone(doc.linked_consultation)

	def test_linked_consultation_cannot_match_originating_consultation(self):
		doc = make_appointment_doc(
			is_follow_up=1,
			follow_up_reference="VCON-001",
			linked_consultation="VCON-001",
		)
		frappe_stub = make_frappe_stub(
			db=SimpleNamespace(exists=lambda *args, **kwargs: True)
		)

		with patch("vetedge.services.appointment_flow.frappe", frappe_stub):
			self.assertRaises(frappe.ValidationError, validate_linked_consultation, doc)

	def test_consultation_creation_from_appointment_links_both_records(self):
		inserted = []
		saved = []

		appointment = make_appointment_doc(
			name="VAPT-001",
			status="Checked In",
			linked_consultation=None,
			notes="Follow-up limp check",
		)
		appointment.save = lambda: saved.append(appointment)

		def get_doc(*args, **kwargs):
			if args and args[0] == "Veterinary Appointment":
				return appointment
			doc = frappe._dict(args[0])
			doc.name = "VCON-001"
			doc.consultation_title = "Buddy - 2026-04-20 - Consultation 1"
			doc.insert = lambda: inserted.append(doc)
			return doc

		frappe_stub = make_frappe_stub(get_doc=get_doc)

		with (
			patch("vetedge.services.appointment_flow.frappe", frappe_stub),
			patch("vetedge.services.appointment_flow.now_datetime", return_value="2026-04-20 10:00:00"),
			patch("vetedge.services.appointment_flow.validate_registration_payment_before_first_consultation"),
			patch("vetedge.services.appointment_flow.assert_consultation_can_proceed") as payment_gate,
			patch("vetedge.services.appointment_flow.emit_notification_event", return_value={"queued": False}) as emit,
		):
			result = create_consultation_from_appointment("VAPT-001")

		self.assertEqual(result["name"], "VCON-001")
		self.assertEqual(inserted[0].linked_appointment, "VAPT-001")
		self.assertEqual(inserted[0].service_branch, "Branch B")
		self.assertEqual(appointment.linked_consultation, "VCON-001")
		self.assertEqual(appointment.status, "In Consultation")
		self.assertEqual(saved, [appointment])
		payment_gate.assert_called_once_with(inserted[0], "In Progress")
		self.assertEqual(emit.call_args.kwargs["event_key"], "appointment_started")

	def test_consultation_creation_from_appointment_rejects_duplicate_link(self):
		appointment = make_appointment_doc(
			name="VAPT-001",
			status="Checked In",
			linked_consultation="VCON-001",
		)
		frappe_stub = make_frappe_stub()

		with patch("vetedge.services.appointment_flow.frappe", frappe_stub):
			self.assertRaises(
				frappe.ValidationError,
				validate_start_consultation_from_appointment,
				appointment,
			)

	def test_start_consultation_from_appointment_runs_registration_payment_gate(self):
		appointment = make_appointment_doc(
			name="VAPT-001",
			status="Checked In",
			linked_consultation=None,
			patient="VP-001",
			branch="Branch B",
		)
		frappe_stub = make_frappe_stub()

		with (
			patch("vetedge.services.appointment_flow.frappe", frappe_stub),
			patch("vetedge.services.appointment_flow.validate_registration_payment_before_first_consultation") as validate_gate,
		):
			validate_start_consultation_from_appointment(appointment)

		validate_gate.assert_called_once_with("VP-001")

	def test_transition_appointment_status_uses_server_validation(self):
		saved = []
		appointment = make_appointment_doc(name="VAPT-001", status="Scheduled")
		appointment.save = lambda: saved.append(appointment)

		frappe_stub = make_frappe_stub(get_doc=lambda *args, **kwargs: appointment)

		with (
			patch("vetedge.services.appointment_flow.frappe", frappe_stub),
			patch("vetedge.services.appointment_flow.emit_notification_event", return_value={"queued": False}) as emit,
		):
			result = transition_appointment_status("VAPT-001", "Confirmed")

		self.assertEqual(result["status"], "Confirmed")
		self.assertEqual(saved, [appointment])
		self.assertEqual(emit.call_args.kwargs.get("event_key") or emit.call_args.kwargs.get("event"), "appointment_confirmed")


def make_appointment_doc(**overrides):
	doc = frappe._dict(
		name=overrides.pop("name", None),
		patient="VP-001",
		primary_owner=None,
		branch="Branch B",
		practitioner="doctor@example.com",
		practitioner_name=None,
		appointment_datetime="2026-04-19 09:00:00",
		status="Scheduled",
		created_from="Manual",
		source_doctype=None,
		source_name=None,
		is_follow_up=0,
		follow_up_reference=None,
		linked_consultation=None,
		notes=None,
	)
	doc.update(overrides)
	doc.get_doc_before_save = lambda: None
	return doc


def make_frappe_stub(**overrides):
	def throw(*args, **kwargs):
		exc = args[1] if len(args) > 1 else kwargs.get("exc")
		if isinstance(exc, type) and issubclass(exc, Exception):
			raise exc()
		raise frappe.ValidationError()

	stub = SimpleNamespace(
		db=SimpleNamespace(
			exists=lambda dt, name=None: True if (dt == "Veterinary Settings" or name == "Veterinary Settings" or (dt == "DocType" and name == "Veterinary Settings")) else False,
			get_value=get_value_for_patient_and_user,
		),
		get_all=lambda *args, **kwargs: [],
		get_roles=lambda *args, **kwargs: ["VetEdge Front Desk"],
		get_meta=lambda doctype: SimpleNamespace(
			has_field=lambda fieldname: False,
			get_title_field=lambda: "patient_name" if doctype == "Veterinary Patient" else "name",
		),
		session=SimpleNamespace(user="staff@example.com"),
		throw=throw,
		ValidationError=frappe.ValidationError,
		PermissionError=frappe.PermissionError,
	)
	for key, value in overrides.items():
		setattr(stub, key, value)
	return stub


def get_value_for_patient_and_user(doctype, name, fields=None, **kwargs):
	if doctype == "User" and fields == "full_name":
		return "Dr Ada Vet"
	if fields == "patient_name":
		return "Buddy"
	return frappe._dict(primary_owner="CUST-001", default_branch="Branch A")
