from __future__ import annotations

import sys
from datetime import datetime
from types import ModuleType, SimpleNamespace
from unittest import TestCase
from unittest.mock import Mock, patch


class AttrDict(dict):
	def __getattr__(self, key):
		try:
			return self[key]
		except KeyError as exc:
			raise AttributeError(key) from exc

	def __setattr__(self, key, value):
		self[key] = value


class FakeAppointment(AttrDict):
	def __init__(self, **kwargs):
		super().__init__(**kwargs)
		self.insert = Mock(side_effect=self._insert)
		self.save = Mock()
		self.has_permission = Mock(return_value=True)

	def _insert(self, *args, **kwargs):
		self.name = self.get("name") or "VAPT-0001"
		return self


class FakeMissedAppointment(AttrDict):
	def __init__(self, **kwargs):
		super().__init__(**kwargs)
		self.save = Mock()


def _install_stub_modules() -> None:
	if "frappe" in sys.modules and hasattr(sys.modules["frappe"], "db") and hasattr(sys.modules["frappe"].db, "sql"):
		return

	if "frappe" not in sys.modules:
		frappe = ModuleType("frappe")
		frappe._ = lambda value: value
		frappe.ValidationError = Exception
		frappe.PermissionError = Exception
		frappe.throw = Mock(side_effect=Exception("blocked"))
		frappe.whitelist = lambda *args, **kwargs: (lambda fn: fn)
		frappe.session = SimpleNamespace(user="tester@example.com")
		frappe.db = SimpleNamespace(exists=Mock(return_value=False), set_value=Mock())
		frappe.get_all = Mock(return_value=[])
		frappe.get_doc = Mock()
		frappe.get_meta = Mock(return_value=SimpleNamespace(has_field=lambda fieldname: True))
		frappe.get_roles = Mock(return_value=[])
		sys.modules["frappe"] = frappe

	if "frappe.utils" not in sys.modules:
		utils = ModuleType("frappe.utils")
		utils.add_days = lambda value, days: value
		utils.cstr = lambda value="": "" if value is None else str(value)
		utils.get_datetime = lambda value=None: datetime.fromisoformat(str(value).replace(" ", "T")) if value else datetime(2026, 5, 1, 12, 0, 0)
		utils.getdate = lambda value=None: str(value).split(" ")[0] if value else "2026-05-01"
		utils.now = lambda: "2026-05-01 12:00:00"
		utils.now_datetime = lambda: datetime(2026, 5, 1, 12, 0, 0)
		sys.modules["frappe.utils"] = utils

	stubs = {
		"vetedge.services.consultation_flow": {
			"get_document_title": lambda *args, **kwargs: "Patient",
			"get_user_full_name": lambda user=None: "Doctor User" if user else None,
			"validate_practitioner_branch_access": lambda *args, **kwargs: None,
			"validate_user_branch_access": lambda *args, **kwargs: None,
		},
		"vetedge.services.feature_flags": {"is_enabled": lambda feature: True},
		"vetedge.services.notifications": {"emit_notification_event": lambda *args, **kwargs: None},
		"vetedge.services.permissions": {
			"ELEVATED_ROLES": {"System Manager", "VetEdge Administrator"},
			"FRONT_DESK_ROLES": {"VetEdge Front Desk", "System Manager", "VetEdge Administrator"},
			"ROLE_BRANCH_MANAGER": "Branch Manager",
			"can_access_consultation": lambda *args, **kwargs: True,
			"user_has_any_role": lambda user, roles: bool(set(sys.modules["frappe"].get_roles(user)) & set(roles)),
			"validate_doctor_user": lambda user=None, label="Practitioner": None if user != "nurse@example.com" else (_ for _ in ()).throw(Exception("not doctor")),
		},
		"vetedge.services.portal_access": {"require_internal_user": lambda: None},
		"vetedge.services.registration_billing": {"validate_registration_payment_before_first_consultation": lambda *args, **kwargs: None},
	}
	for module_name, attrs in stubs.items():
		if module_name in sys.modules:
			continue
		module = ModuleType(module_name)
		for key, value in attrs.items():
			setattr(module, key, value)
		sys.modules[module_name] = module


_install_stub_modules()

from vetedge.services import appointment_flow


class AppointmentAutomationTests(TestCase):
	def setUp(self):
		self._original_db_exists = appointment_flow.frappe.db.exists
		self._original_db_set_value = appointment_flow.frappe.db.set_value
		self._original_get_meta = appointment_flow.frappe.get_meta
		self._original_get_all = appointment_flow.frappe.get_all
		self._original_get_doc = appointment_flow.frappe.get_doc
		self._original_get_roles = appointment_flow.frappe.get_roles
		self._original_require_internal_user = appointment_flow.require_internal_user
		self._original_validate_user_branch_access = appointment_flow.validate_user_branch_access
		self._original_validate_practitioner_branch_access = appointment_flow.validate_practitioner_branch_access
		self._original_validate_doctor_user = appointment_flow.validate_doctor_user
		self._original_user_has_any_role = appointment_flow.user_has_any_role
		self._original_now = appointment_flow.now
		self._original_now_datetime = appointment_flow.now_datetime
		self._original_session_user = appointment_flow.frappe.session.user
		appointment_flow.frappe.db.exists = Mock(side_effect=lambda doctype, name=None: doctype == "DocType" and name == "Veterinary Appointment")
		appointment_flow.frappe.db.set_value = Mock()
		appointment_flow.frappe.get_meta = Mock(return_value=SimpleNamespace(has_field=lambda fieldname: True))
		appointment_flow.frappe.get_all = Mock(return_value=[])
		appointment_flow.frappe.get_roles = Mock(return_value=["System Manager"])
		appointment_flow.require_internal_user = Mock()
		appointment_flow.validate_user_branch_access = Mock()
		appointment_flow.validate_practitioner_branch_access = Mock()
		appointment_flow.validate_doctor_user = Mock(
			side_effect=lambda user=None, label="Practitioner": None
			if user != "nurse@example.com"
			else (_ for _ in ()).throw(Exception("not doctor"))
		)
		appointment_flow.user_has_any_role = lambda user, roles: bool(set(appointment_flow.frappe.get_roles(user)) & set(roles))
		appointment_flow.now = lambda: "2026-05-01 12:00:00"
		appointment_flow.now_datetime = lambda: datetime(2026, 5, 1, 12, 0, 0)
		appointment_flow.frappe.session.user = "tester@example.com"

	def tearDown(self):
		appointment_flow.frappe.db.exists = self._original_db_exists
		appointment_flow.frappe.db.set_value = self._original_db_set_value
		appointment_flow.frappe.get_meta = self._original_get_meta
		appointment_flow.frappe.get_all = self._original_get_all
		appointment_flow.frappe.get_doc = self._original_get_doc
		appointment_flow.frappe.get_roles = self._original_get_roles
		appointment_flow.require_internal_user = self._original_require_internal_user
		appointment_flow.validate_user_branch_access = self._original_validate_user_branch_access
		appointment_flow.validate_practitioner_branch_access = self._original_validate_practitioner_branch_access
		appointment_flow.validate_doctor_user = self._original_validate_doctor_user
		appointment_flow.user_has_any_role = self._original_user_has_any_role
		appointment_flow.now = self._original_now
		appointment_flow.now_datetime = self._original_now_datetime
		appointment_flow.frappe.session.user = self._original_session_user

	def test_consultation_follow_up_creates_generated_appointment(self):
		created = FakeAppointment()
		appointment_flow.frappe.get_doc = Mock(side_effect=lambda value, name=None: (created.update(value) or created) if isinstance(value, dict) else None)
		consultation = AttrDict(
			doctype="Veterinary Consultation",
			name="VCON-001",
			patient="PAT-001",
			primary_owner="CUST-001",
			service_branch="Main Branch",
			consulting_practitioner="doctor@example.com",
			follow_up_date="2026-05-10",
			follow_up_appointment=None,
		)

		result = appointment_flow.sync_follow_up_appointment_from_consultation(consultation)

		self.assertEqual(result, "VAPT-0001")
		created.insert.assert_called_once()
		self.assertEqual(created.source_doctype, "Veterinary Consultation")
		self.assertEqual(created.source_name, "VCON-001")
		self.assertEqual(created.source_field, "follow_up_date")
		self.assertEqual(created.appointment_datetime, "2026-05-10 09:00:00")

	def test_repeated_consultation_save_updates_existing_generated_appointment(self):
		existing = FakeAppointment(name="VAPT-0001", status="Scheduled", appointment_datetime="2026-05-10 09:00:00")
		appointment_flow.frappe.get_all = Mock(return_value=["VAPT-0001"])
		appointment_flow.frappe.get_doc = Mock(return_value=existing)
		consultation = AttrDict(
			doctype="Veterinary Consultation",
			name="VCON-001",
			patient="PAT-001",
			primary_owner="CUST-001",
			service_branch="Main Branch",
			consulting_practitioner="doctor@example.com",
			follow_up_date="2026-05-11",
			follow_up_appointment=None,
		)

		result = appointment_flow.sync_follow_up_appointment_from_consultation(consultation)

		self.assertEqual(result, "VAPT-0001")
		existing.save.assert_called_once()
		self.assertEqual(existing.appointment_datetime, "2026-05-11 09:00:00")

	def test_vaccination_next_due_creates_appointment_without_nurse_as_practitioner(self):
		created = FakeAppointment()
		appointment_flow.frappe.get_doc = Mock(side_effect=lambda value, name=None: (created.update(value) or created) if isinstance(value, dict) else None)
		record = AttrDict(
			doctype="Veterinary Vaccination Record",
			name="VVAC-001",
			patient="PAT-001",
			primary_owner="CUST-001",
			service_branch="Main Branch",
			administered_by="nurse@example.com",
			vaccine="Rabies",
			next_due_date="2026-06-01",
			next_vaccination_appointment=None,
		)

		result = appointment_flow.sync_next_vaccination_appointment_from_record(record)

		self.assertEqual(result, "VAPT-0001")
		self.assertIsNone(created.practitioner)
		self.assertEqual(created.appointment_type, "Vaccination")
		self.assertEqual(created.notes, "Vaccination - Rabies")

	def test_missed_status_detection(self):
		for status in ["Awaiting Registration", "Owner Requested", "Scheduled"]:
			self.assertTrue(
				appointment_flow.is_missed_appointment_row(
					{"status": status, "appointment_datetime": "2026-05-01 09:00:00"},
					reference_datetime="2026-05-01 12:00:00",
				)
			)

		for status in ["Completed", "Cancelled", "In Consultation", "Checked In", "Confirmed", "No Show"]:
			self.assertFalse(
				appointment_flow.is_missed_appointment_row(
					{"status": status, "appointment_datetime": "2026-05-01 09:00:00"},
					reference_datetime="2026-05-01 12:00:00",
				)
			)

	def test_future_scheduled_appointment_is_not_missed(self):
		self.assertFalse(
			appointment_flow.is_missed_appointment_row(
				{"status": "Scheduled", "appointment_datetime": "2026-05-01 14:00:00"},
				reference_datetime="2026-05-01 12:00:00",
			)
		)

	def test_mark_missed_appointment_contacted_updates_missed_record_only(self):
		missed, appointment = self._mock_missed_action_docs()

		result = appointment_flow.mark_missed_appointment_contacted("VMISS-001", note="Owner called")

		self.assertEqual(result["status"], "Contacted")
		self.assertEqual(missed.status, "Contacted")
		self.assertEqual(missed.contacted, 1)
		self.assertEqual(missed.contact_note, "Owner called")
		self.assertEqual(missed.contacted_by, "tester@example.com")
		missed.save.assert_called_once()
		appointment.save.assert_not_called()

	def test_reschedule_missed_appointment_updates_linked_appointment_and_resolves(self):
		missed, appointment = self._mock_missed_action_docs()
		missed.save.side_effect = Exception("modified timestamp conflict")

		result = appointment_flow.reschedule_missed_appointment(
			"VMISS-001",
			new_date="2026-05-02",
			new_time="10:30:00",
			note="Booked new slot",
		)

		self.assertEqual(result["status"], "Rescheduled")
		self.assertEqual(appointment.status, "Scheduled")
		self.assertEqual(str(appointment.appointment_datetime), "2026-05-02 10:30:00")
		self.assertEqual(missed.resolved, 1)
		self.assertEqual(missed.resolution_status, "Rescheduled")
		self.assertEqual(missed.resolution_note, "Booked new slot")
		appointment.save.assert_called_once()
		missed.save.assert_not_called()
		appointment_flow.frappe.db.set_value.assert_any_call(
			"Veterinary Missed Appointment",
			"VMISS-001",
			{
				"status": "Rescheduled",
				"resolved": 1,
				"resolution_status": "Rescheduled",
				"resolution_note": "Booked new slot",
				"resolved_on": "2026-05-01 12:00:00",
				"resolved_by": "tester@example.com",
			},
		)

	def test_cancel_missed_appointment_updates_linked_appointment_and_resolves(self):
		missed, appointment = self._mock_missed_action_docs()
		missed.save.side_effect = Exception("modified timestamp conflict")

		result = appointment_flow.cancel_missed_appointment("VMISS-001", note="Owner cancelled")

		self.assertEqual(result["appointment_status"], "Cancelled")
		self.assertEqual(appointment.status, "Cancelled")
		self.assertEqual(missed.status, "Cancelled")
		self.assertEqual(missed.resolved, 1)
		self.assertEqual(missed.resolution_note, "Owner cancelled")
		appointment.save.assert_called_once()
		missed.save.assert_not_called()
		appointment_flow.frappe.db.set_value.assert_any_call(
			"Veterinary Missed Appointment",
			"VMISS-001",
			{
				"status": "Cancelled",
				"resolved": 1,
				"resolution_status": "Cancelled",
				"resolution_note": "Owner cancelled",
				"resolved_on": "2026-05-01 12:00:00",
				"resolved_by": "tester@example.com",
			},
		)

	def test_repeated_reschedule_missed_appointment_is_idempotent(self):
		missed, appointment = self._mock_missed_action_docs(resolved=1, status="Rescheduled", resolution_status="Rescheduled")

		result = appointment_flow.reschedule_missed_appointment(
			"VMISS-001",
			new_date="2026-05-02",
			new_time="10:30:00",
			note="Already rescheduled",
		)

		self.assertEqual(result["status"], "Rescheduled")
		appointment.save.assert_not_called()
		missed.save.assert_not_called()
		appointment_flow.frappe.db.set_value.assert_not_called()

	def test_repeated_cancel_missed_appointment_is_idempotent(self):
		missed, appointment = self._mock_missed_action_docs(resolved=1, status="Cancelled", resolution_status="Cancelled")

		result = appointment_flow.cancel_missed_appointment("VMISS-001", note="Already cancelled")

		self.assertEqual(result["status"], "Cancelled")
		self.assertEqual(result["appointment_status"], "Scheduled")
		appointment.save.assert_not_called()
		missed.save.assert_not_called()
		appointment_flow.frappe.db.set_value.assert_not_called()

	def test_sync_after_reschedule_does_not_reopen_resolved_missed_record(self):
		missed, appointment = self._mock_missed_action_docs(resolved=1, status="Rescheduled", resolution_status="Rescheduled")
		appointment.appointment_datetime = "2026-05-02 10:30:00"
		appointment.status = "Scheduled"
		appointment_flow.frappe.db.exists = Mock(
			side_effect=lambda doctype, filters=None: True
			if doctype == "DocType" and filters == "Veterinary Missed Appointment"
			else ("VMISS-001" if doctype == "Veterinary Missed Appointment" else False)
		)

		result = appointment_flow.sync_missed_appointment_from_source(appointment)

		self.assertIsNone(result)
		missed.save.assert_not_called()
		appointment_flow.frappe.db.set_value.assert_not_called()

	def test_sync_after_cancel_does_not_reopen_resolved_missed_record(self):
		missed, appointment = self._mock_missed_action_docs(resolved=1, status="Cancelled", resolution_status="Cancelled")
		appointment.status = "Cancelled"
		appointment_flow.frappe.db.exists = Mock(
			side_effect=lambda doctype, filters=None: True
			if doctype == "DocType" and filters == "Veterinary Missed Appointment"
			else ("VMISS-001" if doctype == "Veterinary Missed Appointment" else False)
		)

		result = appointment_flow.sync_missed_appointment_from_source(appointment)

		self.assertIsNone(result)
		missed.save.assert_not_called()
		appointment_flow.frappe.db.set_value.assert_not_called()

	def test_resolve_missed_appointment_requires_note_when_still_missed_eligible_for_non_manager(self):
		self._mock_missed_action_docs()
		appointment_flow.frappe.get_roles = Mock(return_value=["VetEdge Front Desk"])

		with self.assertRaises(Exception):
			appointment_flow.resolve_missed_appointment("VMISS-001")

	def test_resolve_missed_appointment_marks_record_resolved_with_note(self):
		missed, appointment = self._mock_missed_action_docs()
		appointment_flow.frappe.get_roles = Mock(return_value=["VetEdge Front Desk"])

		result = appointment_flow.resolve_missed_appointment("VMISS-001", resolution_note="Owner unreachable")

		self.assertEqual(result["status"], "Resolved")
		self.assertEqual(missed.resolved, 1)
		self.assertEqual(missed.resolution_status, "Resolved")
		self.assertEqual(missed.resolution_note, "Owner unreachable")
		appointment.save.assert_not_called()
		missed.save.assert_called_once()

	def test_reopen_missed_appointment_returns_record_to_open_state_for_manager(self):
		missed, _appointment = self._mock_missed_action_docs(resolved=1, status="Resolved")
		appointment_flow.frappe.get_roles = Mock(return_value=["Branch Manager"])

		result = appointment_flow.reopen_missed_appointment("VMISS-001", note="Resolved by mistake")

		self.assertEqual(result["status"], "Reopened")
		self.assertEqual(missed.resolved, 0)
		self.assertIsNone(missed.resolved_on)
		self.assertIsNone(missed.resolved_by)
		self.assertEqual(missed.resolution_status, "Reopened")
		self.assertEqual(missed.resolution_note, "Resolved by mistake")
		missed.save.assert_called_once()

	def test_unauthorized_user_cannot_act_on_missed_appointment(self):
		self._mock_missed_action_docs()
		appointment_flow.frappe.get_roles = Mock(return_value=["VetEdge Nurse"])

		with self.assertRaises(Exception):
			appointment_flow.mark_missed_appointment_contacted("VMISS-001")

	def test_system_manager_can_resolve_still_missed_eligible_without_note(self):
		missed, _appointment = self._mock_missed_action_docs()

		result = appointment_flow.resolve_missed_appointment("VMISS-001")

		self.assertEqual(result["status"], "Resolved")
		self.assertEqual(missed.resolved, 1)
		missed.save.assert_called_once()

	def test_upsert_does_not_reopen_existing_resolved_missed_record(self):
		missed = FakeMissedAppointment(name="VMISS-001", appointment="VAPT-001", resolved=1, status="Resolved")
		appointment_flow.frappe.db.exists = Mock(return_value="VMISS-001")
		appointment_flow.frappe.get_doc = Mock(return_value=missed)

		result = appointment_flow.upsert_missed_appointment(
			{
				"name": "VAPT-001",
				"appointment_datetime": "2026-05-01 09:00:00",
				"patient": "PAT-001",
				"primary_owner": "CUST-001",
				"branch": "Main Branch",
				"practitioner": "doctor@example.com",
				"status": "Scheduled",
			}
		)

		self.assertEqual(result, "unchanged")
		self.assertEqual(missed.status, "Resolved")
		missed.save.assert_not_called()

	def _mock_missed_action_docs(self, **missed_overrides):
		missed_values = {
			"name": "VMISS-001",
			"appointment": "VAPT-001",
			"appointment_datetime": "2026-05-01 09:00:00",
			"patient": "PAT-001",
			"primary_owner": "CUST-001",
			"branch": "Main Branch",
			"practitioner": "doctor@example.com",
			"original_status": "Scheduled",
			"status": "Open",
			"resolved": 0,
		}
		missed_values.update(missed_overrides)
		missed = FakeMissedAppointment(**missed_values)
		appointment = FakeAppointment(
			name="VAPT-001",
			appointment_datetime="2026-05-01 09:00:00",
			patient="PAT-001",
			primary_owner="CUST-001",
			branch="Main Branch",
			practitioner="doctor@example.com",
			status="Scheduled",
		)
		appointment_flow.frappe.get_doc = Mock(
			side_effect=lambda doctype, name=None: missed
			if doctype == "Veterinary Missed Appointment"
			else appointment
		)
		appointment_flow.frappe.get_all = Mock(return_value=[])
		def set_value(doctype, name, values, *args, **kwargs):
			if doctype == "Veterinary Missed Appointment" and name == missed.name and isinstance(values, dict):
				missed.update(values)

		appointment_flow.frappe.db.set_value = Mock(side_effect=set_value)
		return missed, appointment
