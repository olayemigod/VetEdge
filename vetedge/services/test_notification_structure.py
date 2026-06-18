from __future__ import annotations

import json
from pathlib import Path
from unittest import TestCase

from vetedge.services.notification_events import (
	EMAIL_TEMPLATE_MAPPINGS,
	NOTIFICATION_EVENT_REGISTRY,
)


APP_ROOT = Path("/home/olayemigod/frappe-bench/apps/vetedge/vetedge")
EMAIL_TEMPLATE_FIXTURE = Path("/home/olayemigod/frappe-bench/apps/vetedge/fixtures/vetedge_email_templates.json")


class TestNotificationStructure(TestCase):
	ADMIN_ROLES = {"System Manager", "VetEdge Administrator"}

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

	def test_all_seeded_email_templates_are_mapped_to_events(self):
		fixture_rows = json.loads(EMAIL_TEMPLATE_FIXTURE.read_text())
		fixture_event_keys = {row["event_key"] for row in fixture_rows}
		for event_key in fixture_event_keys:
			self.assertIn(event_key, NOTIFICATION_EVENT_REGISTRY)
			self.assertTrue(EMAIL_TEMPLATE_MAPPINGS.get(event_key))

	def test_all_non_empty_registry_email_templates_exist_in_fixture(self):
		fixture_rows = json.loads(EMAIL_TEMPLATE_FIXTURE.read_text())
		fixture_names = {row["name"] for row in fixture_rows}
		for event_key, template_name in EMAIL_TEMPLATE_MAPPINGS.items():
			self.assertIn(
				template_name,
				fixture_names,
				msg=f"{event_key} maps to unseeded template {template_name}",
			)

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

	def test_notification_doctypes_are_admin_only(self):
		for path in (
			APP_ROOT / "veterinary/doctype/vetedge_notification_log/vetedge_notification_log.json",
			APP_ROOT / "veterinary/doctype/vetedge_notification_preference/vetedge_notification_preference.json",
		):
			doctype_json = json.loads(path.read_text())
			roles = {row.get("role") for row in doctype_json.get("permissions", []) if row.get("role")}
			self.assertEqual(roles - self.ADMIN_ROLES, set(), msg=f"Unexpected roles in {path.name}: {roles}")

	def test_notification_log_sensitive_fields_are_admin_permlevel(self):
		doctype_json = json.loads(
			(
				APP_ROOT
				/ "veterinary/doctype/vetedge_notification_log/vetedge_notification_log.json"
			).read_text()
		)
		fields = {field.get("fieldname"): field for field in doctype_json["fields"]}
		for fieldname in ("provider_reference", "error_message", "payload_preview"):
			self.assertEqual(fields[fieldname].get("permlevel"), 1)

	def test_notification_settings_fields_are_admin_permlevel(self):
		settings_json = json.loads(
			(APP_ROOT / "veterinary/doctype/veterinary_settings/veterinary_settings.json").read_text()
		)
		fields = {field.get("fieldname"): field for field in settings_json["fields"]}
		for fieldname in (
			"notifications_tab",
			"notifications_section",
			"enable_notifications",
			"enable_email_notifications",
			"enable_sms_notifications",
			"enable_whatsapp_notifications",
			"notification_backend_mode",
			"processedge_core_notifications_enabled",
			"processedge_core_notification_endpoint",
			"processedge_core_notification_api_key",
			"notify_on_appointment_create",
			"notify_on_appointment_status_change",
			"notify_on_appointment_reminder",
			"notify_on_owner_portal_appointment_request",
			"notify_on_guest_registration_request",
			"notify_on_guest_registration_confirmed",
			"notify_on_guest_appointment_request",
			"notify_on_invoice_created",
			"notify_on_payment_received",
			"notify_on_reschedule",
			"notify_on_cancellation",
			"notify_on_accounts_action_required",
			"notify_on_lab_updates",
			"notification_channels",
			"appointment_reminder_hours",
			"appointment_reminder_hours_before",
			"vaccination_due_reminder_days",
			"payment_reminder_days",
		):
			self.assertEqual(fields[fieldname].get("permlevel"), 1)

	def test_notification_admin_permission_hooks_are_registered(self):
		hooks_py = (APP_ROOT / "hooks.py").read_text()
		self.assertIn('"VetEdge Notification Log": "vetedge.services.permissions.get_notification_admin_only_query"', hooks_py)
		self.assertIn('"VetEdge Notification Preference": "vetedge.services.permissions.get_notification_admin_only_query"', hooks_py)
		self.assertIn('"VetEdge Notification Log": "vetedge.services.permissions.has_notification_admin_permission"', hooks_py)
		self.assertIn('"VetEdge Notification Preference": "vetedge.services.permissions.has_notification_admin_permission"', hooks_py)
		self.assertIn('"Veterinary Settings": "vetedge.services.permissions.has_notification_admin_permission"', hooks_py)

	def test_notification_workspace_links_are_admin_only(self):
		workspace_json = json.loads((APP_ROOT / "workspace_sidebar/vetedge.json").read_text())

		def collect_links(rows):
			links = {}
			for row in rows or []:
				if row.get("type") == "Link" and row.get("label"):
					links[row["label"]] = row
				links.update(collect_links(row.get("items")))
			return links

		links = collect_links(workspace_json.get("items"))
		for label in (
			"Veterinary Settings",
			"Veterinary Notification Item",
			"VetEdge Notification Event Registry",
			"VetEdge Notification Log",
			"VetEdge Notification Preference",
		):
			depends_on = links[label].get("display_depends_on", "")
			self.assertIn("System Manager", depends_on)
			self.assertIn("VetEdge Administrator", depends_on)

	def test_backend_mode_default_is_local(self):
		settings_json = json.loads(
			(APP_ROOT / "veterinary/doctype/veterinary_settings/veterinary_settings.json").read_text()
		)
		backend_field = next(
			field for field in settings_json["fields"] if field.get("fieldname") == "notification_backend_mode"
		)
		self.assertEqual(backend_field.get("default"), "local")
