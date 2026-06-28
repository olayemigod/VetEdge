from __future__ import annotations
import frappe
from unittest import TestCase
from unittest.mock import patch, MagicMock
from vetedge.services.coreedge_sms import send_sms_safe
from vetedge.veterinary.doctype.veterinary_appointment.veterinary_appointment import (
	VeterinaryAppointment,
)

class TestVetEdgeSMSWalletIntegrationV163(TestCase):
	def setUp(self):
		super().setUp()
		frappe.set_user("Administrator")
		self.mock_settings = frappe._dict({
			"enable_notifications": 1,
			"enable_appointment_sms_notifications": 1,
			"appointment_sms_on_owner_requested": 0,
			"appointment_sms_on_scheduled": 1,
			"appointment_sms_on_confirmed": 1,
			"appointment_sms_on_rescheduled": 0,
			"appointment_sms_on_cancelled": 0,
			"appointment_sms_on_completed": 0,
			"appointment_sms_on_no_show": 0,
		})

	def test_appointment_sms_succeeds_safely_when_wallet_insufficient(self):
		appt = frappe._dict({
			"doctype": "Veterinary Appointment",
			"name": "VAPT-TEST-301",
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

		# Simulate CoreEdge send_sms returning an INSUFFICIENT_SMS_WALLET error
		insufficient_response = {
			"ok": False,
			"status": "Failed",
			"reason_code": "INSUFFICIENT_SMS_WALLET",
			"message": "SMS wallet has insufficient units."
		}

		with (
			patch("vetedge.veterinary.doctype.veterinary_appointment.veterinary_appointment.frappe.db.get_value", side_effect=get_val),
			patch("vetedge.veterinary.doctype.veterinary_appointment.veterinary_appointment.notify_appointment_event"),
			patch("vetedge.veterinary.doctype.veterinary_appointment.veterinary_appointment.sync_missed_appointment_from_source"),
			patch("vetedge.veterinary.doctype.veterinary_appointment.veterinary_appointment.frappe.get_single", return_value=self.mock_settings),
			patch("vetedge.services.coreedge_sms.send_sms_safe", return_value=insufficient_response) as mock_sms
		):
			appt.status = "Scheduled"
			# Save transition must complete and not raise an error
			VeterinaryAppointment.on_update(appt)
			mock_sms.assert_called_once()

	def test_idempotency_prevents_duplicate_sends(self):
		appt = frappe._dict({
			"doctype": "Veterinary Appointment",
			"name": "VAPT-TEST-302",
			"status": "Scheduled",
			"primary_owner": "Test Owner",
			"appointment_datetime": "2026-06-28 10:00:00",
			"branch": "Main",
		})
		appt.get_doc_before_save = lambda: frappe._dict({"status": "Scheduled"})

		with (
			patch("vetedge.veterinary.doctype.veterinary_appointment.veterinary_appointment.notify_appointment_event"),
			patch("vetedge.veterinary.doctype.veterinary_appointment.veterinary_appointment.sync_missed_appointment_from_source"),
			patch("vetedge.services.coreedge_sms.send_sms_safe") as mock_sms
		):
			appt.status = "Scheduled"
			# This transition has no status changes, so no SMS call should occur
			VeterinaryAppointment.on_update(appt)
			mock_sms.assert_not_called()
