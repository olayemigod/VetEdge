from __future__ import annotations
import frappe
from unittest import TestCase
from unittest.mock import patch, MagicMock
from vetedge.services.coreedge_sms import send_sms_safe
from vetedge.veterinary.doctype.veterinary_appointment.veterinary_appointment import (
	VeterinaryAppointment,
)

class TestVetEdgeSMSIntegrationV161(TestCase):
	def setUp(self):
		super().setUp()
		frappe.set_user("Administrator")
		self.mock_settings = frappe._dict({
			"enable_notifications": 1,
			"enable_appointment_sms_notifications": 1,
			"appointment_sms_on_owner_requested": 0,
			"appointment_sms_on_scheduled": 1,
			"appointment_sms_on_confirmed": 1,
			"appointment_sms_on_rescheduled": 1,
			"appointment_sms_on_cancelled": 1,
			"appointment_sms_on_completed": 0,
			"appointment_sms_on_no_show": 0,
		})

	def test_send_sms_safe_returns_unavailable_when_coreedge_import_fails(self):
		with patch.dict("sys.modules", {"coreedge.coreedge.sms_engine": None}):
			res = send_sms_safe(
				to="08031234567",
				message="Hello",
				event="test",
				product_app="VetEdge"
			)
			self.assertFalse(res["ok"])
			self.assertEqual(res["status"], "CoreEdge Unavailable")
			self.assertEqual(res["reason_code"], "COREDGE_NOT_INSTALLED")

	def test_send_sms_safe_handles_unexpected_exception(self):
		with patch("coreedge.coreedge.sms_engine.send_sms", side_effect=Exception("Unexpected DB lock error")):
			res = send_sms_safe(
				to="08031234567",
				message="Hello",
				event="test",
				product_app="VetEdge"
			)
			self.assertFalse(res["ok"])
			self.assertEqual(res["status"], "Failed")
			self.assertEqual(res["reason_code"], "COREDGE_SMS_ERROR")
			self.assertIn("Unexpected DB lock error", res["message"])

	def test_appointment_confirmation_does_not_fail_if_sms_fails(self):
		appt = frappe._dict({
			"doctype": "Veterinary Appointment",
			"name": "VAPT-TEST-001",
			"status": "Scheduled",
			"primary_owner": "Test Owner",
			"appointment_datetime": "2026-06-28 10:00:00",
			"branch": "Main",
		})
		appt.get_doc_before_save = lambda: frappe._dict({"status": "Scheduled"})

		orig_get_value = frappe.db.get_value
		def get_val(doctype, name, fieldname=None, *args, **kwargs):
			if doctype == "Customer" and name == "Test Owner":
				return "+2348031234567"
			return orig_get_value(doctype, name, fieldname, *args, **kwargs)

		with (
			patch("vetedge.veterinary.doctype.veterinary_appointment.veterinary_appointment.frappe.db.get_value", side_effect=get_val),
			patch("vetedge.veterinary.doctype.veterinary_appointment.veterinary_appointment.notify_appointment_event"),
			patch("vetedge.veterinary.doctype.veterinary_appointment.veterinary_appointment.sync_missed_appointment_from_source"),
			patch("vetedge.veterinary.doctype.veterinary_appointment.veterinary_appointment.frappe.get_single", return_value=self.mock_settings),
			patch("vetedge.services.coreedge_sms.send_sms_safe", side_effect=Exception("SMS gateway down")) as mock_sms,
		):
			appt.status = "Confirmed"
			VeterinaryAppointment.on_update(appt)
			mock_sms.assert_called_once()

	def test_appointment_sms_settings_driven_triggers(self):
		appt = frappe._dict({
			"doctype": "Veterinary Appointment",
			"name": "VAPT-TEST-002",
			"status": "Scheduled",
			"primary_owner": "Test Owner",
			"appointment_datetime": "2026-06-28 10:00:00",
			"branch": "Main",
		})

		appt.get_doc_before_save = lambda: frappe._dict({"status": "Owner Requested"})
		orig_get_value = frappe.db.get_value
		def get_val(doctype, name, fieldname=None, *args, **kwargs):
			if doctype == "Customer" and name == "Test Owner":
				return "+2348031234567"
			return orig_get_value(doctype, name, fieldname, *args, **kwargs)

		with (
			patch("vetedge.veterinary.doctype.veterinary_appointment.veterinary_appointment.frappe.db.get_value", side_effect=get_val),
			patch("vetedge.veterinary.doctype.veterinary_appointment.veterinary_appointment.notify_appointment_event"),
			patch("vetedge.veterinary.doctype.veterinary_appointment.veterinary_appointment.sync_missed_appointment_from_source"),
			patch("vetedge.veterinary.doctype.veterinary_appointment.veterinary_appointment.frappe.get_single", return_value=self.mock_settings),
			patch("vetedge.services.coreedge_sms.send_sms_safe") as mock_sms,
		):
			appt.status = "Scheduled"
			VeterinaryAppointment.on_update(appt)
			mock_sms.assert_called_once()

			mock_sms.reset_mock()

			self.mock_settings.enable_appointment_sms_notifications = 0
			appt.get_doc_before_save = lambda: frappe._dict({"status": "Owner Requested"})
			appt.status = "Scheduled"
			VeterinaryAppointment.on_update(appt)
			mock_sms.assert_not_called()

			self.mock_settings.enable_appointment_sms_notifications = 1

			self.mock_settings.appointment_sms_on_scheduled = 0
			appt.get_doc_before_save = lambda: frappe._dict({"status": "Owner Requested"})
			appt.status = "Scheduled"
			VeterinaryAppointment.on_update(appt)
			mock_sms.assert_not_called()
