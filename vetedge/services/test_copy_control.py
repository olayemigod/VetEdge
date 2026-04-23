from __future__ import annotations

from types import SimpleNamespace
from unittest import TestCase
from unittest.mock import patch

import frappe

from vetedge.services.copy_control import reset_vetedge_copy_state


class TestCopyControl(TestCase):
	def test_consultation_copy_resets_workflow_state(self):
		doc = frappe._dict(
			doctype="Veterinary Consultation",
			flags=SimpleNamespace(in_copy=True),
			status="Completed",
			consultation_datetime="2026-04-23 09:00:00",
			daily_consultation_number=3,
			consultation_title="Old",
			linked_appointment="VAPT-0001",
			follow_up_appointment="VAPT-0002",
			dispensary_status="Dispensary Confirmed",
			dispensed_treatments=[frappe._dict(item="MED-001")],
			dispensary_confirmed_on="2026-04-23 09:30:00",
			dispensary_confirmed_by="user@example.com",
			dispensary_stock_entry="STE-0001",
			linked_invoice="SINV-0001",
			payment_status="Paid",
		)
		doc.set = lambda key, value: doc.__setitem__(key, value)

		reset_vetedge_copy_state(doc)

		self.assertEqual(doc.status, "Draft")
		self.assertIsNone(doc.consultation_datetime)
		self.assertIsNone(doc.linked_appointment)
		self.assertEqual(doc.dispensary_status, "Not Required")
		self.assertEqual(doc.dispensed_treatments, [])
		self.assertEqual(doc.payment_status, "Not Billed")

	def test_appointment_copy_resets_operational_state(self):
		doc = frappe._dict(
			doctype="Veterinary Appointment",
			flags=SimpleNamespace(in_copy=True),
			status="Completed",
			appointment_title="Old Appointment",
			guest_booking_request="VGBR-0001",
			created_from="Portal",
			linked_consultation="VCON-0001",
			reminder_sent=1,
			reminder_sent_on="2026-04-23 08:00:00",
		)

		reset_vetedge_copy_state(doc)

		self.assertEqual(doc.status, "Scheduled")
		self.assertEqual(doc.created_from, "Manual")
		self.assertIsNone(doc.linked_consultation)
		self.assertEqual(doc.reminder_sent, 0)

	def test_guest_booking_copy_resets_conversion_links(self):
		doc = frappe._dict(
			doctype="Veterinary Guest Booking Request",
			flags=SimpleNamespace(in_copy=True),
			status="Converted",
			linked_customer="CUST-0001",
			linked_patient="VP-0001",
			linked_appointment="VAPT-0001",
			registration_invoice="SINV-0001",
		)

		reset_vetedge_copy_state(doc)

		self.assertEqual(doc.status, "Registration Requested")
		self.assertIsNone(doc.linked_customer)
		self.assertIsNone(doc.registration_invoice)

	def test_patient_copy_resets_registration_and_deceased_state(self):
		doc = frappe._dict(
			doctype="Veterinary Patient",
			flags=SimpleNamespace(in_copy=True),
			status="Deceased",
			is_deceased=1,
			registration_status="Billed",
			registration_invoice="SINV-0001",
			registration_billed=1,
			registration_fee_amount=2500,
		)

		reset_vetedge_copy_state(doc)

		self.assertEqual(doc.status, "Active")
		self.assertEqual(doc.is_deceased, 0)
		self.assertEqual(doc.registration_status, "Registered")
		self.assertEqual(doc.registration_billed, 0)

	def test_vitals_copy_refreshes_capture_timestamps(self):
		doc = frappe._dict(
			doctype="Veterinary Vital Signs",
			flags=SimpleNamespace(in_copy=True),
			vitals_title="Old Vitals",
			recorded_on="2026-04-20 10:00:00",
			recorded_by="nurse@example.com",
		)

		with patch("vetedge.services.copy_control.now_datetime", return_value="2026-04-23 11:00:00"):
			reset_vetedge_copy_state(doc)

		self.assertIsNone(doc.recorded_by)
		self.assertEqual(doc.recorded_on, "2026-04-23 11:00:00")

	def test_non_copy_documents_are_untouched(self):
		doc = frappe._dict(doctype="Veterinary Consultation", flags=SimpleNamespace(in_copy=False), status="Completed")

		reset_vetedge_copy_state(doc)

		self.assertEqual(doc.status, "Completed")
