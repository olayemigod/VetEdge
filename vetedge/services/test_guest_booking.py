from __future__ import annotations

from types import SimpleNamespace
from unittest import TestCase
from unittest.mock import patch

import frappe

from vetedge.services.guest_booking import (
	create_appointment_from_booking_request,
	create_guest_booking_request,
	initiate_guest_registration_payment,
	validate_guest_booking_request,
)


class TestGuestBooking(TestCase):
	def test_guest_booking_validation_requires_contact_path(self):
		doc = frappe._dict(
			status="Registration Requested",
			guest_name="Jane Owner",
			guest_email=None,
			guest_phone=None,
			pet_name="Bingo",
			preferred_branch="Main Branch",
			preferred_datetime="2026-04-20 10:00:00",
			species="Canine",
			breed=None,
			source=None,
		)
		frappe_stub = make_frappe_stub()

		with patch("vetedge.services.guest_booking.frappe", frappe_stub):
			self.assertRaises(frappe.ValidationError, validate_guest_booking_request, doc)

	def test_create_guest_booking_request_inserts_request(self):
		inserted = []

		def get_doc(values):
			doc = frappe._dict(values)
			doc.name = "VGBR-001"
			doc.insert = lambda ignore_permissions=False: inserted.append(doc) or doc
			return doc

		frappe_stub = make_frappe_stub(get_doc=get_doc)

		with (
			patch("vetedge.services.guest_booking.frappe", frappe_stub),
			patch("vetedge.services.guest_booking.get_portal_settings", return_value={"enable_guest_booking": True}),
			patch("vetedge.services.guest_booking.emit_notification_event", return_value={"queued": False}),
		):
			result = create_guest_booking_request(
				guest_name="Jane Owner",
				guest_email="jane@example.com",
				pet_name="Bingo",
				species="Canine",
				preferred_branch="Main Branch",
				reason_for_visit="Annual check",
			)

		self.assertEqual(result["name"], "VGBR-001")
		self.assertEqual(inserted[0].status, "Registration Requested")

	def test_create_appointment_from_booking_request_converts_linked_request(self):
		inserted = []
		saved = []
		request = frappe._dict(
			doctype="Veterinary Guest Booking Request",
			name="VGBR-001",
			status="Registration Confirmed",
			linked_patient="VP-001",
			linked_appointment=None,
			preferred_branch="Main Branch",
			preferred_datetime="2026-04-21 10:30:00",
			source="Guest Portal",
			reason_for_visit="Follow up",
		)
		request.save = lambda: saved.append(request) or request

		def get_doc(*args, **kwargs):
			if args == ("Veterinary Guest Booking Request", "VGBR-001"):
				return request

			doc = frappe._dict(args[0])
			doc.name = "VAPT-001"
			doc.doctype = "Veterinary Appointment"
			doc.appointment_title = "Bingo - 2026-04-21 10:30"
			doc.insert = lambda: inserted.append(doc) or doc
			return doc

		frappe_stub = make_frappe_stub(
			get_doc=get_doc,
			get_roles=lambda *args, **kwargs: ["VetEdge Front Desk"],
		)

		with (
			patch("vetedge.services.guest_booking.frappe", frappe_stub),
			patch("vetedge.services.guest_booking.emit_notification_event", return_value={"queued": False}),
		):
			result = create_appointment_from_booking_request("VGBR-001")

		self.assertEqual(result["name"], "VAPT-001")
		self.assertEqual(inserted[0].patient, "VP-001")
		self.assertEqual(inserted[0].created_from, "Guest")
		self.assertEqual(request.linked_appointment, "VAPT-001")
		self.assertEqual(request.status, "Converted")
		self.assertEqual(saved, [request])

	def test_create_appointment_from_booking_request_blocks_portal_customer_role(self):
		frappe_stub = make_frappe_stub(get_roles=lambda *args, **kwargs: ["Customer"])

		with patch("vetedge.services.guest_booking.frappe", frappe_stub):
			self.assertRaises(
				frappe.PermissionError,
				create_appointment_from_booking_request,
				"VGBR-001",
			)

	def test_create_appointment_from_booking_request_requires_linked_patient(self):
		request = frappe._dict(
			name="VGBR-001",
			status="Registration Requested",
			linked_patient=None,
			linked_appointment=None,
		)

		frappe_stub = make_frappe_stub(
			get_doc=lambda *args, **kwargs: request,
			get_roles=lambda *args, **kwargs: ["VetEdge Front Desk"],
		)

		with patch("vetedge.services.guest_booking.frappe", frappe_stub):
			self.assertRaises(
				frappe.ValidationError,
				create_appointment_from_booking_request,
				"VGBR-001",
			)

	def test_guest_registration_payment_routes_through_payment_service(self):
		request = frappe._dict(
			name="VGBR-001",
			guest_email="jane@example.com",
			guest_phone="2348000000000",
			linked_patient="VP-001",
			registration_invoice="SINV-001",
		)
		invoice = frappe._dict(name="SINV-001", docstatus=1, outstanding_amount=150)
		frappe_stub = make_frappe_stub(
			db=SimpleNamespace(
				exists=lambda *args, **kwargs: True,
				get_value=lambda *args, **kwargs: "SINV-001",
			),
			get_doc=lambda doctype, name=None, *args, **kwargs: invoice if doctype == "Sales Invoice" else request,
		)

		with (
			patch("vetedge.services.guest_booking.frappe", frappe_stub),
			patch("vetedge.services.guest_booking.get_portal_settings", return_value={"enable_portal_payments": True}),
			patch("vetedge.services.guest_booking.validate_guest_registration_payment_access", return_value=request),
			patch("vetedge.services.guest_booking.initiate_payment", return_value={"success": True}) as initiate_payment_mock,
		):
			result = initiate_guest_registration_payment("VGBR-001", guest_email="jane@example.com")

		self.assertEqual(result, {"success": True})
		self.assertEqual(initiate_payment_mock.call_args.kwargs["invoice_name"], "SINV-001")
		self.assertEqual(initiate_payment_mock.call_args.kwargs["access_context"]["mode"], "guest_registration")
		self.assertEqual(initiate_payment_mock.call_args.kwargs["source_context"]["booking_request"], "VGBR-001")


def make_frappe_stub(**overrides):
	def throw(*args, **kwargs):
		exc = args[1] if len(args) > 1 else kwargs.get("exc")
		if isinstance(exc, type) and issubclass(exc, Exception):
			raise exc()
		raise frappe.ValidationError()

	stub = SimpleNamespace(
		db=SimpleNamespace(exists=lambda *args, **kwargs: True),
		get_doc=lambda *args, **kwargs: None,
		get_roles=lambda *args, **kwargs: [],
		throw=throw,
		PermissionError=frappe.PermissionError,
		ValidationError=frappe.ValidationError,
	)
	for key, value in overrides.items():
		setattr(stub, key, value)
	return stub
