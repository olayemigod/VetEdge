from __future__ import annotations

from types import SimpleNamespace
from unittest import TestCase
from unittest.mock import Mock, patch

import frappe

from vetedge.services import appointment_notifications
from vetedge.services import notifications
from vetedge.veterinary.doctype.veterinary_appointment.veterinary_appointment import (
	VeterinaryAppointment,
)


def _appointment(**overrides):
	values = {
		"name": "VAPT-2026-00001",
		"owner": "creator@example.com",
		"patient": "VP-001",
		"primary_owner": "CUST-001",
		"branch": "Main",
		"practitioner": "doctor.a@example.com",
		"appointment_datetime": "2026-06-14 10:00:00",
		"status": "Scheduled",
		"appointment_type": "Consultation",
	}
	values.update(overrides)
	return frappe._dict(values)


def _user_recipient(user, audience_type="Appointment", **kwargs):
	if not user:
		return None
	return {
		"user": user,
		"identifier": user,
		"address": user,
		"audience_type": audience_type,
		"preference_key": user,
	}


class TestAppointmentNotificationsPhase1C(TestCase):
	def test_due_soon_creates_notification_once_by_idempotency_key(self):
		seen_keys = set()
		created = []

		def create_item(**kwargs):
			created.append(kwargs)
			created_now = kwargs["idempotency_key"] not in seen_keys
			seen_keys.add(kwargs["idempotency_key"])
			return {"created": created_now, "name": "VNI-001"}

		with (
			patch("vetedge.services.appointment_notifications.get_user_recipient", side_effect=_user_recipient),
			patch("vetedge.services.appointment_notifications.get_role_recipients", return_value=[]),
			patch("vetedge.services.appointment_notifications.create_notification_item", side_effect=create_item),
		):
			first = appointment_notifications.notify_appointment_due_soon(_appointment(), window_minutes=60)
			second = appointment_notifications.notify_appointment_due_soon(_appointment(), window_minutes=60)

		self.assertTrue(first[0]["created"])
		self.assertFalse(second[0]["created"])
		self.assertEqual(created[0]["idempotency_key"], "appointment_due_soon::VAPT-2026-00001::60::doctor.a@example.com")
		self.assertEqual(created[0]["reference_doctype"], "Veterinary Appointment")
		self.assertEqual(created[0]["reference_name"], "VAPT-2026-00001")
		self.assertEqual(created[0]["action_url"], "/app/veterinary-appointment/VAPT-2026-00001")
		self.assertEqual(created[0]["payload"]["category"], "Appointment")

	def test_missed_appointment_is_high_priority_and_does_not_notify_customer_owner(self):
		created = []

		def create_item(**kwargs):
			created.append(kwargs)
			return {"created": True, "name": kwargs["recipient_user"]}

		def role_recipients(roles, **kwargs):
			self.assertNotIn("VetEdge Doctor", roles)
			return [_user_recipient("frontdesk@example.com", audience_type="Appointment Escalation")]

		def exists(doctype, filters=None):
			if doctype == "DocType" and filters == "Veterinary Missed Appointment":
				return True
			if doctype == "Veterinary Missed Appointment":
				return "VMISS-001"
			return None

		with (
			patch("vetedge.services.appointment_notifications.frappe.db.exists", side_effect=exists),
			patch("vetedge.services.appointment_flow.upsert_missed_appointment", return_value="created") as upsert,
			patch("vetedge.services.appointment_notifications.get_user_recipient", side_effect=_user_recipient),
			patch("vetedge.services.appointment_notifications.get_role_recipients", side_effect=role_recipients),
			patch("vetedge.services.appointment_notifications.create_notification_item", side_effect=create_item),
		):
			appointment_notifications.notify_missed_appointment(_appointment())

		upsert.assert_called_once()
		recipients = {row["recipient_user"] for row in created}
		self.assertEqual(recipients, {"doctor.a@example.com", "creator@example.com", "frontdesk@example.com"})
		self.assertNotIn("CUST-001", recipients)
		self.assertTrue(all(row["priority"] == "High" for row in created))
		self.assertTrue(all(row["reference_doctype"] == "Veterinary Missed Appointment" for row in created))
		self.assertTrue(all(row["reference_name"] == "VMISS-001" for row in created))
		self.assertTrue(all(row["action_url"] == "/app/veterinary-missed-appointment/VMISS-001" for row in created))
		self.assertTrue(all(row["payload"]["appointment"] == "VAPT-2026-00001" for row in created))
		self.assertTrue(all(row["payload"]["missed_appointment"] == "VMISS-001" for row in created))

	def test_duplicate_missed_scheduler_runs_reuse_record_and_notification_idempotency(self):
		seen_keys = set()
		created = []

		def create_item(**kwargs):
			created.append(kwargs)
			created_now = kwargs["idempotency_key"] not in seen_keys
			seen_keys.add(kwargs["idempotency_key"])
			return {"created": created_now, "name": kwargs["idempotency_key"]}

		def exists(doctype, filters=None):
			if doctype == "DocType":
				return filters in {"Veterinary Appointment", "Veterinary Notification Item", "Veterinary Missed Appointment"}
			if doctype == "Veterinary Missed Appointment":
				return "VMISS-001"
			return None

		with (
			patch("vetedge.services.appointment_notifications._appointment_notifications_available", return_value=True),
			patch("vetedge.services.appointment_notifications.now_datetime", return_value="2026-06-14 11:00:00"),
			patch("vetedge.services.appointment_notifications.frappe.get_all", return_value=[_appointment()]),
			patch("vetedge.services.appointment_notifications.frappe.db.exists", side_effect=exists),
			patch("vetedge.services.appointment_flow.upsert_missed_appointment", return_value="unchanged") as upsert,
			patch("vetedge.services.appointment_notifications.get_user_recipient", side_effect=_user_recipient),
			patch("vetedge.services.appointment_notifications.get_role_recipients", return_value=[]),
			patch("vetedge.services.appointment_notifications.create_notification_item", side_effect=create_item),
		):
			first = appointment_notifications.send_missed_appointment_notifications()
			second = appointment_notifications.send_missed_appointment_notifications()

		self.assertEqual(len(first), 2)
		self.assertEqual(len(second), 2)
		self.assertEqual(upsert.call_count, 2)
		self.assertEqual(created[0]["idempotency_key"], "missed_appointment::VAPT-2026-00001::doctor.a@example.com")
		self.assertTrue(first[0]["created"])
		self.assertFalse(second[0]["created"])
		self.assertEqual({row["reference_name"] for row in created}, {"VMISS-001"})

	def test_duplicate_missed_recipients_create_one_notification_per_user(self):
		created = []

		def create_item(**kwargs):
			created.append(kwargs)
			return {"created": True, "name": kwargs["idempotency_key"]}

		def exists(doctype, filters=None):
			if doctype == "DocType" and filters == "Veterinary Missed Appointment":
				return True
			if doctype == "Veterinary Missed Appointment":
				return "VMISS-001"
			return None

		with (
			patch("vetedge.services.appointment_notifications.frappe.db.exists", side_effect=exists),
			patch("vetedge.services.appointment_flow.upsert_missed_appointment", return_value="unchanged"),
			patch("vetedge.services.appointment_notifications.get_user_recipient", side_effect=_user_recipient),
			patch(
				"vetedge.services.appointment_notifications.get_role_recipients",
				return_value=[_user_recipient("doctor.a@example.com", audience_type="Appointment Escalation")],
			),
			patch("vetedge.services.appointment_notifications.create_notification_item", side_effect=create_item),
		):
			appointment_notifications.notify_missed_appointment(
				_appointment(owner="doctor.a@example.com", created_by="doctor.a@example.com")
			)

		self.assertEqual([row["recipient_user"] for row in created], ["doctor.a@example.com"])
		self.assertEqual(
			created[0]["idempotency_key"],
			"missed_appointment::VAPT-2026-00001::doctor.a@example.com",
		)

	def test_checked_in_event_creates_notification_only_on_actual_status_change(self):
		changed_doc = _appointment(status="Checked In")
		changed_doc.get_doc_before_save = lambda: SimpleNamespace(status="Confirmed")
		unchanged_doc = _appointment(status="Checked In")
		unchanged_doc.get_doc_before_save = lambda: SimpleNamespace(status="Checked In")

		with (
			patch("vetedge.veterinary.doctype.veterinary_appointment.veterinary_appointment.sync_missed_appointment_from_source"),
			patch("vetedge.veterinary.doctype.veterinary_appointment.veterinary_appointment.notify_appointment_checked_in") as checked_in,
		):
			VeterinaryAppointment.on_update(unchanged_doc)
			VeterinaryAppointment.on_update(changed_doc)

		checked_in.assert_called_once_with(changed_doc)

	def test_completed_event_creates_notification_only_on_actual_status_change(self):
		changed_doc = _appointment(status="Completed")
		changed_doc.get_doc_before_save = lambda: SimpleNamespace(status="In Consultation")
		unchanged_doc = _appointment(status="Completed")
		unchanged_doc.get_doc_before_save = lambda: SimpleNamespace(status="Completed")

		with (
			patch("vetedge.veterinary.doctype.veterinary_appointment.veterinary_appointment.sync_missed_appointment_from_source"),
			patch("vetedge.veterinary.doctype.veterinary_appointment.veterinary_appointment.notify_appointment_completed") as completed,
		):
			VeterinaryAppointment.on_update(unchanged_doc)
			VeterinaryAppointment.on_update(changed_doc)

		completed.assert_called_once_with(changed_doc)

	def test_reminder_sent_and_failed_create_single_operational_notification(self):
		appointment = _appointment()
		with (
			patch("vetedge.services.notifications.get_notification_settings", return_value={"enabled": True, "notify_on_appointment_reminder": True, "appointment_reminder_hours": 24}),
			patch("vetedge.services.notifications.add_to_date", return_value="2026-06-15 10:00:00"),
			patch("vetedge.services.notifications.now_datetime", return_value="2026-06-14 09:00:00"),
			patch("vetedge.services.notifications.frappe.get_all", return_value=[frappe._dict(name=appointment.name)]),
			patch("vetedge.services.notifications.frappe.get_doc", return_value=appointment),
			patch("vetedge.services.notifications.frappe.db.set_value"),
			patch("vetedge.services.notifications.notify_appointment_event", return_value={"queued": True}),
			patch("vetedge.services.appointment_notifications.notify_appointment_reminder_sent") as sent,
			patch("vetedge.services.appointment_notifications.notify_appointment_reminder_failed") as failed,
		):
			results = notifications.send_due_appointment_reminders()

		self.assertTrue(results[0]["queued"])
		sent.assert_called_once_with(appointment)
		failed.assert_not_called()

		with (
			patch("vetedge.services.notifications.get_notification_settings", return_value={"enabled": True, "notify_on_appointment_reminder": True, "appointment_reminder_hours": 24}),
			patch("vetedge.services.notifications.add_to_date", return_value="2026-06-15 10:00:00"),
			patch("vetedge.services.notifications.now_datetime", return_value="2026-06-14 09:00:00"),
			patch("vetedge.services.notifications.frappe.get_all", return_value=[frappe._dict(name=appointment.name)]),
			patch("vetedge.services.notifications.frappe.get_doc", return_value=appointment),
			patch("vetedge.services.notifications.notify_appointment_event", side_effect=Exception("SMTP unavailable")),
			patch("vetedge.services.appointment_notifications.notify_appointment_reminder_failed") as failed_again,
		):
			results = notifications.send_due_appointment_reminders()

		self.assertFalse(results[0]["queued"])
		failed_again.assert_called_once_with(appointment, reason="SMTP unavailable")

	def test_scheduler_due_soon_and_missed_skip_terminal_statuses(self):
		rows = [
			_appointment(name="VAPT-DUE", status="Scheduled"),
			_appointment(name="VAPT-DONE", status="Completed"),
		]
		with (
			patch("vetedge.services.appointment_notifications._appointment_notifications_available", return_value=True),
			patch("vetedge.services.appointment_notifications.add_to_date", return_value="2026-06-14 11:00:00"),
			patch("vetedge.services.appointment_notifications.now_datetime", return_value="2026-06-14 10:00:00"),
			patch("vetedge.services.appointment_notifications.frappe.get_all", return_value=rows),
			patch("vetedge.services.appointment_notifications.notify_appointment_due_soon", return_value=[{"created": True}]) as due_soon,
		):
			result = appointment_notifications.send_due_soon_appointment_notifications()

		self.assertEqual(result, [{"created": True}])
		due_soon.assert_called_once()

	def test_appointment_notifications_do_not_call_outbound_channel_engine(self):
		with (
			patch("vetedge.services.appointment_notifications.get_user_recipient", side_effect=_user_recipient),
			patch("vetedge.services.appointment_notifications.get_role_recipients", return_value=[]),
			patch("vetedge.services.appointment_notifications.create_notification_item", return_value={"created": True}),
			patch("vetedge.services.notifications.emit_notification_event") as emit,
		):
			appointment_notifications.notify_appointment_completed(_appointment())

		emit.assert_not_called()
