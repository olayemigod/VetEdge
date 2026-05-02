from __future__ import annotations

import json
from pathlib import Path
from unittest import TestCase

from vetedge.services.notification_events import (
	EMAIL_TEMPLATE_MAPPINGS,
	NOTIFICATION_EVENT_REGISTRY,
)


APP_ROOT = Path("/home/olayemigod/frappe-bench/apps/vetedge/vetedge")


class TestNotificationStructure(TestCase):
	def test_registry_contains_known_events(self):
		for key in (
			"appointment_created",
			"payment_received",
			"lab_order_created",
			"vaccination_administered",
			"boarding_checked_in",
			"grooming_completed",
			"role_bundle_applied",
			"unauthorized_action_blocked",
		):
			self.assertIn(key, NOTIFICATION_EVENT_REGISTRY)

	def test_template_mappings_exist_for_key_email_events(self):
		for key in (
			"appointment_created",
			"payment_received",
			"lab_order_created",
			"vaccination_administered",
			"boarding_checked_in",
			"grooming_completed",
		):
			self.assertTrue(EMAIL_TEMPLATE_MAPPINGS.get(key))

	def test_settings_fields_exist(self):
		settings_json = json.loads(
			(APP_ROOT / "veterinary/doctype/veterinary_settings/veterinary_settings.json").read_text()
		)
		fieldnames = {field.get("fieldname") for field in settings_json["fields"]}
		for fieldname in (
			"enable_email_notifications",
			"enable_sms_notifications",
			"enable_whatsapp_notifications",
			"notification_backend_mode",
			"appointment_reminder_hours",
			"vaccination_due_reminder_days",
			"payment_reminder_days",
			"processedge_core_notifications_enabled",
			"processedge_core_notification_endpoint",
			"processedge_core_notification_api_key",
		):
			self.assertIn(fieldname, fieldnames)

	def test_notification_log_doctype_json_is_valid(self):
		doctype_json = json.loads(
			(
				APP_ROOT
				/ "veterinary/doctype/vetedge_notification_log/vetedge_notification_log.json"
			).read_text()
		)
		self.assertEqual(doctype_json["name"], "VetEdge Notification Log")

	def test_backend_mode_default_is_local(self):
		settings_json = json.loads(
			(APP_ROOT / "veterinary/doctype/veterinary_settings/veterinary_settings.json").read_text()
		)
		backend_field = next(
			field for field in settings_json["fields"] if field.get("fieldname") == "notification_backend_mode"
		)
		self.assertEqual(backend_field.get("default"), "local")
