from __future__ import annotations

from types import SimpleNamespace
from unittest import TestCase
from unittest.mock import patch

import frappe

from vetedge.services.notification_backends.local_backend import LocalNotificationBackend
from vetedge.services.notification_backends.processedge_core_backend import (
	ProcessEdgeCoreNotificationBackend,
)
from vetedge.services.notifications import (
	dispatch_notification_event,
	emit_notification_event,
	parse_notification_channels,
	query_due_vaccination_notifications,
	resolve_notification_recipients,
	send_due_vaccination_notifications,
	send_due_appointment_reminders,
	send_payment_pending_reminders,
)


class TestNotifications(TestCase):
	def test_transaction_routing_does_not_broadcast_to_doctor_role(self):
		def exists(doctype, name=None):
			if doctype == "User":
				return name in {"doctor.a@example.com", "owner@example.com"}
			if doctype == "DocType" and name == "Portal User":
				return True
			return False

		def get_value(doctype, name, fieldname=None, **kwargs):
			if doctype == "Customer" and name == "CUST-001" and fieldname == "email_id":
				return "owner@example.com"
			if doctype == "User" and fieldname == "enabled":
				return 1
			if doctype == "User" and fieldname == "email":
				return name
			return None

		def get_all(doctype, **kwargs):
			if doctype == "Has Role":
				raise AssertionError("Ordinary transaction notifications must not expand Doctor roles.")
			if doctype == "Portal User":
				return ["owner@example.com"]
			return []

		frappe_stub = SimpleNamespace(
			db=SimpleNamespace(exists=exists, get_value=get_value),
			get_all=get_all,
		)

		with patch("vetedge.services.notifications.frappe", frappe_stub):
			recipients = resolve_notification_recipients(
				"appointment_created",
				{
					"primary_owner": "CUST-001",
					"document_owner": "doctor.a@example.com",
					"branch": "Main",
				},
			)

		addresses = {recipient["address"] for recipient in recipients}
		self.assertIn("doctor.a@example.com", addresses)
		self.assertIn("owner@example.com", addresses)
		self.assertNotIn("doctor.b@example.com", addresses)

	def test_assigned_practitioner_is_notified_only_when_present(self):
		def exists(doctype, name=None):
			return doctype == "User" and name in {"creator@example.com", "practitioner@example.com"}

		def get_value(doctype, name, fieldname=None, **kwargs):
			if doctype == "User" and fieldname == "enabled":
				return 1
			if doctype == "User" and fieldname == "email":
				return name
			return None

		frappe_stub = SimpleNamespace(
			db=SimpleNamespace(exists=exists, get_value=get_value),
			get_all=lambda *args, **kwargs: [],
		)

		with patch("vetedge.services.notifications.frappe", frappe_stub):
			without_practitioner = resolve_notification_recipients(
				"consultation_ready_for_treatment",
				{"document_owner": "creator@example.com"},
			)
			with_practitioner = resolve_notification_recipients(
				"consultation_ready_for_treatment",
				{
					"document_owner": "creator@example.com",
					"practitioner_user": "practitioner@example.com",
				},
			)

		self.assertEqual({recipient["address"] for recipient in without_practitioner}, {"creator@example.com"})
		self.assertEqual(
			{recipient["address"] for recipient in with_practitioner},
			{"creator@example.com", "practitioner@example.com"},
		)

	def test_duplicate_and_disabled_connected_users_are_filtered(self):
		def exists(doctype, name=None):
			if doctype == "User":
				return name in {"creator@example.com", "disabled@example.com"}
			if doctype == "DocType" and name == "Portal User":
				return True
			return False

		def get_value(doctype, name, fieldname=None, **kwargs):
			if doctype == "Customer" and name == "CUST-001" and fieldname == "email_id":
				return "owner@example.com"
			if doctype == "User" and fieldname == "enabled":
				return 0 if name == "disabled@example.com" else 1
			if doctype == "User" and fieldname == "email":
				return name
			return None

		frappe_stub = SimpleNamespace(
			db=SimpleNamespace(exists=exists, get_value=get_value),
			get_all=lambda doctype, **kwargs: ["owner@example.com"] if doctype == "Portal User" else [],
		)

		with patch("vetedge.services.notifications.frappe", frappe_stub):
			recipients = resolve_notification_recipients(
				"appointment_rescheduled",
				{
					"primary_owner": "CUST-001",
					"document_owner": "creator@example.com",
					"practitioner_user": "creator@example.com",
					"assigned_to": "disabled@example.com",
				},
			)

		addresses = [recipient["address"] for recipient in recipients]
		self.assertEqual(addresses.count("creator@example.com"), 1)
		self.assertEqual(addresses.count("owner@example.com"), 1)
		self.assertNotIn("disabled@example.com", addresses)

	def test_admin_escalation_intentionally_uses_manager_role_routing_with_branch_scope(self):
		def get_all(doctype, **kwargs):
			if doctype == "Has Role":
				return ["manager.main@example.com", "manager.other@example.com"]
			return []

		def get_value(doctype, name, fieldname=None, **kwargs):
			if doctype == "User" and fieldname == "enabled":
				return 1
			if doctype == "User" and fieldname == "email":
				return name
			return None

		frappe_stub = SimpleNamespace(
			db=SimpleNamespace(
				exists=lambda doctype, name=None: doctype == "User" or (doctype == "DocType" and name == "Branch User Assignment"),
				get_value=get_value,
			),
			get_all=get_all,
		)

		with (
			patch("vetedge.services.notifications.frappe", frappe_stub),
			patch("vetedge.services.notifications.get_assigned_branches", side_effect=lambda user: ["Main"] if user == "manager.main@example.com" else ["Other"]),
		):
			recipients = resolve_notification_recipients(
				"unauthorized_action_blocked",
				{"branch": "Main", "document_owner": "doctor.a@example.com"},
			)

		self.assertEqual({recipient["address"] for recipient in recipients}, {"manager.main@example.com"})

	def test_parse_notification_channels_filters_supported_channels(self):
		self.assertEqual(
			parse_notification_channels("Email\nSMS\nSignal\nWhatsApp"),
			["Email", "SMS", "WhatsApp"],
		)

	def test_notification_event_returns_stubbed_queue_payload(self):
		backend = SimpleNamespace(
			dispatch=lambda **kwargs: [
				{
					"channel": "Email",
					"recipient": "owner@example.com",
					"audience_type": "Owner",
					"status": "Queued",
					"backend_mode": "local",
					"provider_reference": "VetEdge - Appointment Created",
					"error_message": None,
				}
			]
		)
		with (
			patch(
				"vetedge.services.notifications.get_notification_settings",
				return_value={
					"enabled": True,
					"channels": ["Email"],
					"notify_on_appointment_create": True,
					"notification_backend_mode": "local",
				},
			),
			patch(
				"vetedge.services.notifications.resolve_notification_recipients",
				return_value=[
					{
						"identifier": "CUST-001",
						"address": "owner@example.com",
						"audience_type": "Owner",
						"preference_key": "CUST-001",
					}
				],
			),
			patch("vetedge.services.notifications.get_notification_backend", return_value=backend),
			patch("vetedge.services.notifications.frappe.logger", return_value=SimpleNamespace(info=lambda payload: None)),
		):
			result = emit_notification_event(
				event_key="appointment_created",
				reference_doctype="Veterinary Appointment",
				reference_name="VAPT-001",
				context={"patient": "VP-001"},
			)

		self.assertTrue(result["queued"])
		self.assertEqual(result["channels"], ["Email"])
		self.assertEqual(result["delivery"]["attempts"][0]["status"], "Queued")

	def test_invalid_event_key_raises_validation_error(self):
		with self.assertRaises(frappe.ValidationError):
			emit_notification_event("not_a_real_event")

	def test_disabled_event_does_not_queue(self):
		with patch(
			"vetedge.services.notifications.get_notification_settings",
			return_value={
				"enabled": True,
				"channels": ["Email"],
				"notify_on_appointment_create": False,
			},
		):
			result = emit_notification_event("appointment_created", "Veterinary Appointment", "VAPT-001")

		self.assertFalse(result["queued"])
		self.assertEqual(result["reason"], "event_disabled")

	def test_disabled_global_notifications_skip(self):
		with patch(
			"vetedge.services.notifications.get_notification_settings",
			return_value={"enabled": False, "channels": ["Email"]},
		):
			result = emit_notification_event("appointment_created", "Veterinary Appointment", "VAPT-001")

		self.assertFalse(result["queued"])
		self.assertEqual(result["reason"], "notifications_disabled")

	def test_disabled_email_channel_skips_email(self):
		with patch(
			"vetedge.services.notifications.get_notification_settings",
			return_value={"enabled": True, "channels": ["SMS"], "notify_on_appointment_create": True},
		):
			result = emit_notification_event("appointment_created", "Veterinary Appointment", "VAPT-001")

		self.assertFalse(result["queued"])
		self.assertEqual(result["reason"], "no_channels_configured")

	def test_preference_disables_channel(self):
		backend = SimpleNamespace(dispatch=lambda **kwargs: [])
		with (
			patch(
				"vetedge.services.notifications.resolve_notification_recipients",
				return_value=[
					{
						"identifier": "CUST-001",
						"address": "owner@example.com",
						"audience_type": "Owner",
						"preference_key": "CUST-001",
					}
				],
			),
			patch(
				"vetedge.services.notifications.get_notification_settings",
				return_value={
					"enabled": True,
					"channels": ["Email"],
					"notify_on_appointment_create": True,
					"notification_backend_mode": "local",
				},
			),
			patch(
				"vetedge.services.notifications.get_notification_preference",
				return_value={"email_enabled": 0, "sms_enabled": 0, "whatsapp_enabled": 0},
			),
			patch("vetedge.services.notifications.get_notification_backend", return_value=backend),
		):
			result = emit_notification_event("appointment_created", "Veterinary Appointment", "VAPT-001")

		self.assertFalse(result["queued"])
		self.assertEqual(result["delivery"]["attempts"][0]["status"], "Skipped")

	def test_local_backend_uses_email_template_mapping(self):
		sent = []
		backend = LocalNotificationBackend()
		event_definition = SimpleNamespace(event_key="payment_received", event_label="Payment Received", email_template="VetEdge - Payment Received")
		with (
			patch("vetedge.services.notification_backends.local_backend.frappe.db.exists", return_value=True),
			patch(
				"vetedge.services.notification_backends.local_backend.frappe.get_doc",
				return_value=SimpleNamespace(
					get_formatted_subject=lambda context: "Payment Received",
					get_formatted_response=lambda context: "<p>Paid</p>",
				),
			),
			patch(
				"vetedge.services.notification_backends.local_backend.frappe.sendmail",
				side_effect=lambda **kwargs: sent.append(kwargs),
			),
		):
			result = backend.dispatch(
				event_definition=event_definition,
				recipient={"identifier": "CUST-001", "address": "owner@example.com", "audience_type": "Owner"},
				channels=["Email"],
				context={"clinic_name": "VetEdge"},
				settings={},
				reference_doctype="Sales Invoice",
				reference_name="SINV-001",
			)

		self.assertEqual(result[0]["provider_reference"], "VetEdge - Payment Received")
		self.assertEqual(sent[0]["subject"], "Payment Received")
		self.assertTrue(sent[0]["raw_html"])

	def test_missing_template_fallback_works(self):
		sent = []
		backend = LocalNotificationBackend()
		event_definition = SimpleNamespace(event_key="payment_received", event_label="Payment Received", email_template="VetEdge - Payment Received")
		with (
			patch("vetedge.services.notification_backends.local_backend.frappe.db.exists", return_value=False),
			patch(
				"vetedge.services.notification_backends.local_backend.frappe.sendmail",
				side_effect=lambda **kwargs: sent.append(kwargs),
			),
		):
			result = backend.dispatch(
				event_definition=event_definition,
				recipient={"identifier": "CUST-001", "address": "owner@example.com", "audience_type": "Owner"},
				channels=["Email"],
				context={"clinic_name": "VetEdge", "notes": "sensitive"},
				settings={},
				reference_doctype="Sales Invoice",
				reference_name="SINV-001",
			)

		self.assertIsNone(result[0]["provider_reference"])
		self.assertIn("VetEdge: Payment Received", sent[0]["subject"])

	def test_blank_rendered_template_falls_back_to_generated_email(self):
		sent = []
		backend = LocalNotificationBackend()
		event_definition = SimpleNamespace(event_key="payment_received", event_label="Payment Received", email_template="VetEdge - Payment Received")
		with (
			patch("vetedge.services.notification_backends.local_backend.frappe.db.exists", return_value=True),
			patch(
				"vetedge.services.notification_backends.local_backend.frappe.get_doc",
				return_value=SimpleNamespace(
					get_formatted_subject=lambda context: "",
					get_formatted_response=lambda context: "",
				),
			),
			patch(
				"vetedge.services.notification_backends.local_backend.frappe.sendmail",
				side_effect=lambda **kwargs: sent.append(kwargs),
			),
		):
			result = backend.dispatch(
				event_definition=event_definition,
				recipient={"identifier": "CUST-001", "address": "owner@example.com", "audience_type": "Owner"},
				channels=["Email"],
				context={"clinic_name": "VetEdge", "invoice": "SINV-001"},
				settings={},
				reference_doctype="Sales Invoice",
				reference_name="SINV-001",
			)

		self.assertIsNone(result[0]["provider_reference"])
		self.assertIn("VetEdge: Payment Received", sent[0]["subject"])
		self.assertIn("SINV-001", sent[0]["message"])

	def test_processedge_core_mode_returns_pending_safely(self):
		backend = ProcessEdgeCoreNotificationBackend()
		event_definition = SimpleNamespace(event_key="payment_received", event_label="Payment Received", email_template="VetEdge - Payment Received")
		result = backend.dispatch(
			event_definition=event_definition,
			recipient={"identifier": "CUST-001", "address": "owner@example.com", "audience_type": "Owner"},
			channels=["Email"],
			context={"clinic_name": "VetEdge"},
			settings={"processedge_core_notification_endpoint": None, "processedge_core_notification_api_key": None},
			reference_doctype="Sales Invoice",
			reference_name="SINV-001",
		)
		self.assertEqual(result[0]["backend_mode"], "processedge_core")
		self.assertEqual(result[0]["status"], "Skipped")

	def test_due_reminders_emit_stub_and_mark_sent(self):
		set_values = []

		appointment = frappe._dict(
			name="VAPT-001",
			patient="VP-001",
			primary_owner="CUST-001",
			branch="Branch A",
			practitioner="doctor@example.com",
			appointment_datetime="2026-04-19 09:00:00",
			status="Scheduled",
		)

		frappe_stub = SimpleNamespace(
			get_all=lambda *args, **kwargs: [frappe._dict(name="VAPT-001")],
			get_doc=lambda *args, **kwargs: appointment,
			db=SimpleNamespace(set_value=lambda *args, **kwargs: set_values.append((args, kwargs))),
		)

		with (
			patch("vetedge.services.notifications.frappe", frappe_stub),
			patch("vetedge.services.notifications.now_datetime", return_value="2026-04-19 08:00:00"),
			patch("vetedge.services.notifications.add_to_date", return_value="2026-04-20 08:00:00"),
			patch(
				"vetedge.services.notifications.get_notification_settings",
				return_value={
					"enabled": True,
					"channels": ["Email"],
					"notify_on_appointment_reminder": True,
					"appointment_reminder_hours_before": 24,
				},
			),
			patch(
				"vetedge.services.notifications.notify_appointment_event",
				return_value={"queued": True},
			),
		):
			results = send_due_appointment_reminders()

		self.assertEqual(results, [{"queued": True}])
		self.assertEqual(set_values[0][0][0], "Veterinary Appointment")

	def test_vaccination_due_window_logic(self):
		rows = [
			frappe._dict(name="VACC-1", next_due_date="2026-04-20", patient="VP-1", primary_owner="CUST-1", vaccine="Rabies", service_branch="Main"),
			frappe._dict(name="VACC-2", next_due_date="2026-04-18", patient="VP-2", primary_owner="CUST-2", vaccine="Booster", service_branch="Main"),
			frappe._dict(name="VACC-3", next_due_date="2026-05-10", patient="VP-3", primary_owner="CUST-3", vaccine="Booster", service_branch="Main"),
		]
		with (
			patch("vetedge.services.notifications.frappe.get_all", return_value=rows),
			patch("vetedge.services.notifications.getdate", side_effect=lambda value=None: frappe.utils.getdate("2026-04-19" if value is None else value)),
			patch("vetedge.services.notifications.add_days", side_effect=lambda date_obj, days: frappe.utils.add_days(date_obj, days)),
		):
			result = query_due_vaccination_notifications(due_soon_days=7)

		self.assertEqual(len(result), 2)
		self.assertEqual(result[0]["due_state"], "Due Soon")
		self.assertEqual(result[1]["due_state"], "Overdue")

	def test_payment_reminder_outstanding_invoice_logic(self):
		with (
			patch(
				"vetedge.services.notifications.get_notification_settings",
				return_value={"enabled": True, "payment_reminder_days": 3, "channels": ["Email"], "notify_on_payment_received": True},
			),
			patch(
				"vetedge.services.notifications.frappe.get_all",
				return_value=[
					frappe._dict(name="SINV-1", customer="CUST-1", outstanding_amount=500, due_date="2026-04-19", branch="Main"),
					frappe._dict(name="SINV-2", customer="CUST-2", outstanding_amount=300, due_date="2026-05-30", branch="Main"),
				],
			),
			patch("vetedge.services.notifications.frappe.get_meta", return_value=SimpleNamespace(has_field=lambda fieldname: fieldname == "branch")),
			patch("vetedge.services.notifications.already_notified_recently", return_value=False),
			patch("vetedge.services.notifications.emit_notification_event", side_effect=lambda **kwargs: {"queued": True, "reference_name": kwargs["reference_name"]}),
			patch("vetedge.services.notifications.getdate", side_effect=lambda value=None: frappe.utils.getdate("2026-04-19" if value is None else value)),
			patch("vetedge.services.notifications.add_days", side_effect=lambda date_obj, days: frappe.utils.add_days(date_obj, days)),
		):
			result = send_payment_pending_reminders()

		self.assertEqual(len(result), 1)
