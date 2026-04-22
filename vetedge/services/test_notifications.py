from __future__ import annotations

from types import SimpleNamespace
from unittest import TestCase
from unittest.mock import patch

import frappe

from vetedge.services.notifications import (
	dispatch_notification_event,
	emit_notification_event,
	parse_notification_channels,
	send_due_appointment_reminders,
)


class TestNotifications(TestCase):
	def test_parse_notification_channels_filters_supported_channels(self):
		self.assertEqual(
			parse_notification_channels("Email\nSMS\nSignal\nWhatsApp"),
			["Email", "SMS", "WhatsApp"],
		)

	def test_notification_event_returns_stubbed_queue_payload(self):
		with (
			patch(
				"vetedge.services.notifications.get_notification_settings",
				return_value={
					"enabled": True,
					"channels": ["Email"],
					"notify_on_appointment_create": True,
				},
			),
			patch("vetedge.services.notifications.frappe.logger", return_value=SimpleNamespace(info=lambda payload: None)),
			patch(
				"vetedge.services.notifications.dispatch_notification_event",
				return_value={"Email": {"queued": True, "recipients": ["owner@example.com"]}},
			),
		):
			result = emit_notification_event(
				"appointment_created",
				"Veterinary Appointment",
				"VAPT-001",
				{"patient": "VP-001"},
			)

		self.assertTrue(result["queued"])
		self.assertEqual(result["channels"], ["Email"])
		self.assertTrue(result["delivery"]["Email"]["queued"])

	def test_email_dispatch_queues_frappe_email(self):
		sent = []
		event_payload = {
			"event": "invoice_created",
			"reference_doctype": "Sales Invoice",
			"reference_name": "SINV-001",
			"payload": {"customer": "CUST-001", "invoice": "SINV-001"},
		}

		with (
			patch("vetedge.services.notifications.get_email_recipients", return_value=["owner@example.com"]),
			patch("vetedge.services.notifications.frappe.sendmail", side_effect=lambda **kwargs: sent.append(kwargs)),
		):
			result = dispatch_notification_event(event_payload, {"channels": ["Email"]})

		self.assertTrue(result["Email"]["queued"])
		self.assertEqual(sent[0]["recipients"], ["owner@example.com"])
		self.assertEqual(sent[0]["reference_doctype"], "Sales Invoice")

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
