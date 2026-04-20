from __future__ import annotations

from types import SimpleNamespace
from unittest import TestCase
from unittest.mock import patch

import frappe

from vetedge.services.owner_portal import create_owner_appointment_request


class TestOwnerPortal(TestCase):
	def test_owner_can_create_appointment_request_for_own_pet(self):
		inserted = []

		def get_value(doctype, name, fields=None, **kwargs):
			if doctype == "Veterinary Patient":
				return frappe._dict(
					name="VP-001",
					primary_owner="CUST-001",
					default_branch="Main Branch",
				)
			return None

		def get_doc(values):
			doc = frappe._dict(values)
			doc.name = "VAPT-001"
			doc.appointment_title = "Bingo - 2026-04-21 10:30"
			doc.insert = lambda ignore_permissions=False: inserted.append(doc) or doc
			return doc

		frappe_stub = make_frappe_stub(
			db=SimpleNamespace(
				exists=lambda doctype, name=None, **kwargs: True,
				get_value=get_value,
			),
			get_doc=get_doc,
		)

		with (
			patch("vetedge.services.owner_portal.frappe", frappe_stub),
			patch(
				"vetedge.services.owner_portal.get_owner_context",
				return_value={"user": "jane@example.com", "customers": ["CUST-001"]},
			),
			patch(
				"vetedge.services.owner_portal.get_portal_settings",
				return_value={"enable_owner_portal": True},
			),
			patch("vetedge.services.owner_portal.validate_owner_patient_access"),
			patch("vetedge.services.owner_portal.emit_notification_event", return_value={"queued": False}),
		):
			result = create_owner_appointment_request(
				patient="VP-001",
				preferred_datetime="2026-04-21T10:30",
				reason_for_visit="Follow up",
			)

		self.assertEqual(result["name"], "VAPT-001")
		self.assertEqual(result["status"], "Owner Requested")
		self.assertEqual(inserted[0].doctype, "Veterinary Appointment")
		self.assertEqual(inserted[0].patient, "VP-001")
		self.assertEqual(inserted[0].created_from, "Portal")
		self.assertEqual(inserted[0].status, "Owner Requested")

	def test_owner_appointment_request_requires_enabled_portal(self):
		frappe_stub = make_frappe_stub()

		with (
			patch("vetedge.services.owner_portal.frappe", frappe_stub),
			patch(
				"vetedge.services.owner_portal.get_owner_context",
				return_value={"user": "jane@example.com", "customers": ["CUST-001"]},
			),
			patch(
				"vetedge.services.owner_portal.get_portal_settings",
				return_value={"enable_owner_portal": False},
			),
		):
			self.assertRaises(
				frappe.PermissionError,
				create_owner_appointment_request,
				patient="VP-001",
				preferred_datetime="2026-04-21 10:30",
			)


def make_frappe_stub(**overrides):
	def throw(*args, **kwargs):
		exc = args[1] if len(args) > 1 else kwargs.get("exc")
		if isinstance(exc, type) and issubclass(exc, Exception):
			raise exc()
		raise frappe.ValidationError()

	stub = SimpleNamespace(
		db=SimpleNamespace(exists=lambda *args, **kwargs: True, get_value=lambda *args, **kwargs: None),
		get_doc=lambda *args, **kwargs: None,
		throw=throw,
		PermissionError=frappe.PermissionError,
		ValidationError=frappe.ValidationError,
	)
	for key, value in overrides.items():
		setattr(stub, key, value)
	return stub
