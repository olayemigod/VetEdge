from __future__ import annotations
import frappe
from unittest import TestCase
from unittest.mock import patch, MagicMock
from vetedge.services.coreedge_sms import send_sms_safe
from vetedge.veterinary.doctype.veterinary_appointment.veterinary_appointment import (
	VeterinaryAppointment,
)

class TestVetEdgeSMSIntegrationV162(TestCase):
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

	def test_appointment_scheduled_status_uses_correct_event_key(self):
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
		def get_val(*args, **kwargs):
			doctype = args[0] if len(args) > 0 else kwargs.get("doctype")
			filters = args[1] if len(args) > 1 else kwargs.get("filters")
			fieldname = args[2] if len(args) > 2 else kwargs.get("fieldname")
			if doctype == "Customer" and filters == "Test Owner":
				if fieldname == "customer_name":
					return "Test Owner"
				return "+2348031234567"
			return orig_get_value(*args, **kwargs)

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
			kwargs = mock_sms.call_args.kwargs
			self.assertEqual(kwargs["event"], "appointment_scheduled")
			self.assertEqual(kwargs["product_app"], "VetEdge")
			self.assertEqual(kwargs["context"]["owner_name"], "Test Owner")

	def test_appointment_cancelled_status_uses_correct_event_key(self):
		appt = frappe._dict({
			"doctype": "Veterinary Appointment",
			"name": "VAPT-TEST-003",
			"status": "Cancelled",
			"primary_owner": "Test Owner",
			"appointment_datetime": "2026-06-28 10:00:00",
			"branch": "Main",
		})
		appt.get_doc_before_save = lambda: frappe._dict({"status": "Scheduled"})

		orig_get_value = frappe.db.get_value
		def get_val(*args, **kwargs):
			doctype = args[0] if len(args) > 0 else kwargs.get("doctype")
			filters = args[1] if len(args) > 1 else kwargs.get("filters")
			fieldname = args[2] if len(args) > 2 else kwargs.get("fieldname")
			if doctype == "Customer" and filters == "Test Owner":
				if fieldname == "customer_name":
					return "Test Owner"
				return "+2348031234567"
			return orig_get_value(*args, **kwargs)

		with (
			patch("vetedge.veterinary.doctype.veterinary_appointment.veterinary_appointment.frappe.db.get_value", side_effect=get_val),
			patch("vetedge.veterinary.doctype.veterinary_appointment.veterinary_appointment.notify_appointment_event"),
			patch("vetedge.veterinary.doctype.veterinary_appointment.veterinary_appointment.sync_missed_appointment_from_source"),
			patch("vetedge.veterinary.doctype.veterinary_appointment.veterinary_appointment.frappe.get_single", return_value=self.mock_settings),
			patch("vetedge.services.coreedge_sms.send_sms_safe") as mock_sms,
		):
			appt.status = "Cancelled"
			VeterinaryAppointment.on_update(appt)

			mock_sms.assert_called_once()
			kwargs = mock_sms.call_args.kwargs
			self.assertEqual(kwargs["event"], "appointment_cancelled")

	def test_disabled_setting_prevents_sms(self):
		appt = frappe._dict({
			"doctype": "Veterinary Appointment",
			"name": "VAPT-TEST-004",
			"status": "Scheduled",
			"primary_owner": "Test Owner",
			"appointment_datetime": "2026-06-28 10:00:00",
			"branch": "Main",
		})
		appt.get_doc_before_save = lambda: frappe._dict({"status": "Owner Requested"})
		self.mock_settings.enable_appointment_sms_notifications = 0

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
			mock_sms.assert_not_called()

	def test_same_status_save_does_not_send_duplicate_sms(self):
		appt = frappe._dict({
			"doctype": "Veterinary Appointment",
			"name": "VAPT-TEST-005",
			"status": "Scheduled",
			"primary_owner": "Test Owner",
			"appointment_datetime": "2026-06-28 10:00:00",
			"branch": "Main",
		})
		appt.get_doc_before_save = lambda: frappe._dict({"status": "Scheduled"})

		with (
			patch("vetedge.veterinary.doctype.veterinary_appointment.veterinary_appointment.notify_appointment_event"),
			patch("vetedge.veterinary.doctype.veterinary_appointment.veterinary_appointment.sync_missed_appointment_from_source"),
			patch("vetedge.services.coreedge_sms.send_sms_safe") as mock_sms,
		):
			appt.status = "Scheduled"
			VeterinaryAppointment.on_update(appt)
			mock_sms.assert_not_called()

	def test_missing_coreedge_does_not_block_save(self):
		appt = frappe._dict({
			"doctype": "Veterinary Appointment",
			"name": "VAPT-TEST-006",
			"status": "Scheduled",
			"primary_owner": "Test Owner",
			"appointment_datetime": "2026-06-28 10:00:00",
			"branch": "Main",
		})
		appt.get_doc_before_save = lambda: frappe._dict({"status": "Owner Requested"})

		orig_get_value = frappe.db.get_value
		def get_val(*args, **kwargs):
			doctype = args[0] if len(args) > 0 else kwargs.get("doctype")
			filters = args[1] if len(args) > 1 else kwargs.get("filters")
			fieldname = args[2] if len(args) > 2 else kwargs.get("fieldname")
			if doctype == "Customer" and filters == "Test Owner":
				if fieldname == "customer_name":
					return "Test Owner"
				return "+2348031234567"
			return orig_get_value(*args, **kwargs)

		with (
			patch("vetedge.veterinary.doctype.veterinary_appointment.veterinary_appointment.frappe.db.get_value", side_effect=get_val),
			patch("vetedge.veterinary.doctype.veterinary_appointment.veterinary_appointment.notify_appointment_event"),
			patch("vetedge.veterinary.doctype.veterinary_appointment.veterinary_appointment.sync_missed_appointment_from_source"),
			patch("vetedge.veterinary.doctype.veterinary_appointment.veterinary_appointment.frappe.get_single", return_value=self.mock_settings),
			patch("vetedge.services.coreedge_sms.send_sms_safe", side_effect=Exception("CoreEdge down")) as mock_sms,
		):
			appt.status = "Scheduled"
			VeterinaryAppointment.on_update(appt)
			mock_sms.assert_called_once()
