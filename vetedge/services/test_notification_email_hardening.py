from __future__ import annotations

import json
from pathlib import Path
from unittest import TestCase

from vetedge.services.notification_events import NOTIFICATION_EVENT_REGISTRY
from vetedge.services.notifications import (
	APPOINTMENT_LIFECYCLE_DELIVERY_EVENTS,
	APPOINTMENT_EVENTS,
	EVENT_SETTING_FIELDS,
	OWNER_EVENTS,
	PORTAL_INTAKE_EVENTS,
	PORTAL_INTAKE_NOTIFICATION_ROLES,
)


ROOT = Path(__file__).resolve().parents[1]


class TestNotificationEmailHardeningContract(TestCase):
	def test_appointment_lifecycle_has_one_controller_emitter(self):
		controller = (
			ROOT
			/ "veterinary"
			/ "doctype"
			/ "veterinary_appointment"
			/ "veterinary_appointment.py"
		).read_text()
		flow = (ROOT / "services" / "appointment_flow.py").read_text()
		owner_portal = (ROOT / "services" / "owner_portal.py").read_text()
		front_desk = (ROOT / "services" / "front_desk_action_center.py").read_text()

		for status, event in {
			"Scheduled": "appointment_scheduled",
			"Confirmed": "appointment_confirmed",
			"Checked In": "appointment_checked_in",
			"In Consultation": "appointment_started",
			"Completed": "appointment_completed",
			"Rescheduled": "appointment_rescheduled",
			"Cancelled": "appointment_cancelled",
			"No Show": "appointment_no_show",
		}.items():
			self.assertIn(f'"{status}": "{event}"', controller)

		self.assertNotIn("emit_appointment_status_notification", flow)
		self.assertNotIn("def emit_appointment_event", flow)
		self.assertNotIn("emit_appointment_status_notification", owner_portal)
		self.assertNotIn("emit_appointment_status_notification", front_desk)

	def test_checked_in_is_supported_and_idempotent_but_not_owner_facing(self):
		self.assertIn("appointment_checked_in", APPOINTMENT_EVENTS)
		self.assertIn("appointment_checked_in", APPOINTMENT_LIFECYCLE_DELIVERY_EVENTS)
		self.assertNotIn("appointment_checked_in", OWNER_EVENTS)
		self.assertEqual(
			NOTIFICATION_EVENT_REGISTRY["appointment_checked_in"].audience,
			"Internal Staff",
		)

	def test_portal_intake_has_one_branch_scoped_action_event(self):
		guest_booking = (ROOT / "services" / "guest_booking.py").read_text()

		self.assertIn(
			'event_key = "guest_appointment_request_received" if doc.appointment_requested else "registration_request_received"',
			guest_booking,
		)
		self.assertNotIn('event_key="appointment_booked"', guest_booking)
		self.assertEqual(guest_booking.count('event_key="guest_appointment_ready_for_approval"'), 2)

		for event_key in (
			"guest_appointment_request_received",
			"guest_appointment_ready_for_approval",
			"owner_appointment_request_received",
			"registration_request_received",
		):
			self.assertIn(event_key, PORTAL_INTAKE_EVENTS)

		self.assertIn("VetEdge Front Desk", PORTAL_INTAKE_NOTIFICATION_ROLES)
		self.assertIn("VetEdge Branch Manager", PORTAL_INTAKE_NOTIFICATION_ROLES)
		self.assertIn("VetEdge Administrator", PORTAL_INTAKE_NOTIFICATION_ROLES)

	def test_semantic_event_setting_mappings_are_explicit(self):
		self.assertEqual(EVENT_SETTING_FIELDS["payment_initiated"], "notify_on_payment_follow_up")
		self.assertEqual(EVENT_SETTING_FIELDS["payment_pending"], "notify_on_payment_follow_up")
		self.assertEqual(EVENT_SETTING_FIELDS["payment_reminder"], "notify_on_payment_follow_up")
		self.assertEqual(
			EVENT_SETTING_FIELDS["consultation_sent_to_dispensary"],
			"notify_on_clinical_workflow_updates",
		)
		self.assertEqual(
			EVENT_SETTING_FIELDS["consultation_ready_for_treatment"],
			"notify_on_clinical_workflow_updates",
		)
		self.assertEqual(
			EVENT_SETTING_FIELDS["dispensary_confirmation_completed"],
			"notify_on_clinical_workflow_updates",
		)

	def test_new_notification_settings_default_off(self):
		settings = json.loads(
			(
				ROOT
				/ "veterinary"
				/ "doctype"
				/ "veterinary_settings"
				/ "veterinary_settings.json"
			).read_text()
		)
		fields = {row.get("fieldname"): row for row in settings.get("fields", [])}
		for fieldname in (
			"notify_on_payment_follow_up",
			"notify_on_clinical_workflow_updates",
		):
			self.assertIn(fieldname, fields)
			self.assertEqual(fields[fieldname].get("default"), "0")

	def test_registered_email_templates_exist_in_fixture(self):
		fixture = json.loads((ROOT.parent / "fixtures" / "vetedge_email_templates.json").read_text())
		templates = {row.get("name"): row for row in fixture}

		for event_key, definition in NOTIFICATION_EVENT_REGISTRY.items():
			if not definition.email_template:
				continue
			self.assertIn(
				definition.email_template,
				templates,
				f"{event_key} maps to missing Email Template {definition.email_template}",
			)

		for event_key, expected_template in {
			"appointment_scheduled": "VetEdge - Appointment Scheduled",
			"appointment_checked_in": "VetEdge - Appointment Checked In",
			"appointment_started": "VetEdge - Appointment Started",
			"appointment_completed": "VetEdge - Appointment Completed",
			"appointment_no_show": "VetEdge - Appointment No Show",
			"invoice_created": "VetEdge - Invoice Created",
			"payment_initiated": "VetEdge - Payment Initiated",
			"payment_reminder": "VetEdge - Payment Reminder",
			"consultation_awaiting_payment": "VetEdge - Consultation Awaiting Payment",
			"registration_confirmed": "VetEdge - Registration Confirmed",
			"grooming_appointment_confirmed": "VetEdge - Grooming Appointment Confirmed",
			"grooming_invoice_created": "VetEdge - Grooming Invoice Created",
		}.items():
			self.assertEqual(
				NOTIFICATION_EVENT_REGISTRY[event_key].email_template,
				expected_template,
			)

	def test_managed_email_templates_do_not_leak_product_brand_footer(self):
		fixture_text = (ROOT.parent / "fixtures" / "vetedge_email_templates.json").read_text()
		self.assertNotIn("Powered by VetEdge", fixture_text)

	def test_notification_log_supports_delivery_reservation(self):
		meta = json.loads(
			(
				ROOT
				/ "veterinary"
				/ "doctype"
				/ "veterinary_notification_log"
				/ "veterinary_notification_log.json"
			).read_text()
		)
		fields = {row.get("fieldname"): row for row in meta.get("fields", [])}
		self.assertEqual(fields["idempotency_key"].get("unique"), 1)
		self.assertIn("Reserved", fields["status"].get("options", ""))
