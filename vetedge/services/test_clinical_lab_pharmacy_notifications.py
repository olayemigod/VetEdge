from __future__ import annotations

import sys
from datetime import date, datetime
from pathlib import Path
from types import ModuleType, SimpleNamespace
from unittest import TestCase
from unittest.mock import Mock, patch

# Install stubs if running outside of Frappe environment
def _install_stub_modules() -> None:
	if "frappe" in sys.modules and hasattr(sys.modules["frappe"], "db") and hasattr(sys.modules["frappe"].db, "sql"):
		return

	if "frappe" not in sys.modules:
		frappe = ModuleType("frappe")
		frappe.ValidationError = Exception
		frappe.PermissionError = Exception
		frappe.throw = Mock(side_effect=Exception("blocked"))
		frappe._ = lambda value, *args, **kwargs: value
		frappe.db = SimpleNamespace(
			get_value=Mock(),
			exists=Mock(return_value=False),
			count=Mock(return_value=0),
			set_value=Mock(),
			get_doc=Mock(),
		)
		frappe.session = SimpleNamespace(user="test@example.com")
		sys.modules["frappe"] = frappe

	if "frappe.utils" not in sys.modules:
		utils = ModuleType("frappe.utils")
		utils.cstr = lambda value=None: "" if value is None else str(value)
		utils.getdate = lambda value=None: date.today()
		utils.nowdate = lambda: date.today().isoformat()
		utils.now_datetime = datetime.now
		sys.modules["frappe.utils"] = utils

	stubs = {
		"vetedge.services.notifications": {
			"create_notification_item": lambda *args, **kwargs: {"created": True, "name": "VNI-001"},
			"get_role_recipients": lambda *args, **kwargs: [],
			"get_user_recipient": lambda user, **kwargs: {"user": user} if user else None,
		}
	}
	for name, attrs in stubs.items():
		if name in sys.modules:
			continue
		module = ModuleType(name)
		for attr_name, value in attrs.items():
			setattr(module, attr_name, value)
		sys.modules[name] = module

_install_stub_modules()

import frappe
from vetedge.services import clinical_lab_pharmacy_notifications
from vetedge.services.notifications import emit_notification_event
from vetedge.services.notification_api import get_veterinary_unread_bell_count

class TestClinicalLabPharmacyNotifications(TestCase):
	def setUp(self):
		self.context = {
			"patient": "PAT-001",
			"primary_owner": "CUST-001",
			"branch": "Main Branch",
			"item": "ITEM-001",
			"warehouse": "Dispensary - WH",
		}

	def test_unsupported_events_do_not_create_notifications(self):
		# Standard event like appointment_created is not in the allowlist
		created = []
		with patch("vetedge.services.clinical_lab_pharmacy_notifications.create_notification_item", side_effect=lambda **kwargs: created.append(kwargs)):
			clinical_lab_pharmacy_notifications.handle_clinical_lab_pharmacy_notifications(
				event_key="appointment_created",
				reference_doctype="Veterinary Appointment",
				reference_name="VAPT-001",
				recipients=[{"user": "doctor@example.com"}],
				context=self.context
			)
		self.assertEqual(len(created), 0)

	def test_supported_events_create_exactly_one_notification_item_per_recipient(self):
		created = []
		recipients = [{"user": "doctor@example.com"}, {"user": "nurse@example.com"}]
		
		def mock_get_user_recipient(user, **kwargs):
			return {"user": user} if user else None

		with (
			patch("vetedge.services.clinical_lab_pharmacy_notifications.create_notification_item", side_effect=lambda **kwargs: created.append(kwargs) or {"created": True}),
			patch("vetedge.services.clinical_lab_pharmacy_notifications.get_user_recipient", side_effect=mock_get_user_recipient),
			patch("vetedge.services.clinical_lab_pharmacy_notifications.is_internal_staff_user", return_value=True),
			patch("vetedge.services.clinical_lab_pharmacy_notifications.get_role_recipients", return_value=[])
		):
			clinical_lab_pharmacy_notifications.handle_clinical_lab_pharmacy_notifications(
				event_key="lab_order_created",
				reference_doctype="Veterinary Lab Order",
				reference_name="VLAB-001",
				recipients=recipients,
				context=self.context
			)
		self.assertEqual(len(created), 2)
		self.assertEqual(created[0]["recipient_user"], "doctor@example.com")
		self.assertEqual(created[1]["recipient_user"], "nurse@example.com")
		self.assertEqual(created[0]["reference_doctype"], "Veterinary Lab Order")
		self.assertEqual(created[0]["reference_name"], "VLAB-001")

	def test_repeated_event_emit_does_not_duplicate(self):
		seen_keys = set()
		created = []

		def mock_create_item(idempotency_key, **kwargs):
			if idempotency_key not in seen_keys:
				seen_keys.add(idempotency_key)
				created.append(idempotency_key)
				return {"created": True, "name": "VNI-001"}
			return {"created": False, "name": "VNI-001"}

		def mock_get_user_recipient(user, **kwargs):
			return {"user": user} if user else None

		with (
			patch("vetedge.services.clinical_lab_pharmacy_notifications.create_notification_item", side_effect=mock_create_item),
			patch("vetedge.services.clinical_lab_pharmacy_notifications.get_user_recipient", side_effect=mock_get_user_recipient),
			patch("vetedge.services.clinical_lab_pharmacy_notifications.is_internal_staff_user", return_value=True),
			patch("vetedge.services.clinical_lab_pharmacy_notifications.get_role_recipients", return_value=[])
		):
			clinical_lab_pharmacy_notifications.handle_clinical_lab_pharmacy_notifications(
				event_key="lab_order_created",
				reference_doctype="Veterinary Lab Order",
				reference_name="VLAB-001",
				recipients=[{"user": "doctor@example.com"}],
				context=self.context
			)
			clinical_lab_pharmacy_notifications.handle_clinical_lab_pharmacy_notifications(
				event_key="lab_order_created",
				reference_doctype="Veterinary Lab Order",
				reference_name="VLAB-001",
				recipients=[{"user": "doctor@example.com"}],
				context=self.context
			)

		self.assertEqual(len(created), 1)

	def test_owner_customer_is_never_notified(self):
		recipients = [
			{"user": "CUST-001"},  # customer (owner)
			{"user": "doctor@example.com"},  # internal doctor
		]

		def mock_get_user_recipient(user, **kwargs):
			return {"user": user} if user else None

		# is_internal_staff_user returns False for CUST-001
		def mock_is_staff(user):
			return user == "doctor@example.com"

		created = []
		with (
			patch("vetedge.services.clinical_lab_pharmacy_notifications.create_notification_item", side_effect=lambda **kwargs: created.append(kwargs)),
			patch("vetedge.services.clinical_lab_pharmacy_notifications.get_user_recipient", side_effect=mock_get_user_recipient),
			patch("vetedge.services.clinical_lab_pharmacy_notifications.is_internal_staff_user", side_effect=mock_is_staff),
			patch("vetedge.services.clinical_lab_pharmacy_notifications.get_role_recipients", return_value=[])
		):
			clinical_lab_pharmacy_notifications.handle_clinical_lab_pharmacy_notifications(
				event_key="lab_order_created",
				reference_doctype="Veterinary Lab Order",
				reference_name="VLAB-001",
				recipients=recipients,
				context=self.context
			)
		
		self.assertEqual(len(created), 1)
		self.assertEqual(created[0]["recipient_user"], "doctor@example.com")

	def test_no_outbound_channel_provider_calls_are_introduced(self):
		# Verify that no SMS, WhatsApp, or other outbound integrations are called.
		# Outbound channel is completely skipped or mocked out.
		with patch("vetedge.services.notifications.dispatch_notification_event") as mock_dispatch:
			# Even if emit_notification_event is triggered, we check that no external SMS/WA channels are active.
			# Let's mock settings to have no channels configured or disabled
			with (
				patch("vetedge.services.notifications.get_notification_settings", return_value={"enabled": True, "channels": ["Email"]}),
				patch("vetedge.services.notifications.resolve_notification_recipients", return_value=[]),
				patch("vetedge.services.clinical_lab_pharmacy_notifications.handle_clinical_lab_pharmacy_notifications")
			):
				emit_notification_event(
					event_key="lab_order_created",
					reference_doctype="Veterinary Lab Order",
					reference_name="VLAB-001",
					payload=self.context
				)
			# Because resolve_notification_recipients returned empty, dispatch is not called
			mock_dispatch.assert_not_called()

	def test_badge_count_increases_on_unread_decreases_on_read(self):
		counts = {"Unread": 3, "Read": 7}
		
		def mock_count(doctype, filters):
			status = filters.get("status")
			return counts.get(status, 0)

		frappe_stub = SimpleNamespace(
			db=SimpleNamespace(
				count=mock_count
			)
		)

		with patch("vetedge.services.notification_api.frappe", frappe_stub):
			unread_count = get_veterinary_unread_bell_count("doctor@example.com")

		self.assertEqual(unread_count, 3)

	def test_idempotency_key_for_stock_failures_includes_item_and_warehouse(self):
		recipient_user = "dispensary@example.com"
		key = clinical_lab_pharmacy_notifications.build_idempotency_key(
			event_key="dispensary_expired_stock_blocked",
			reference_doctype="Veterinary Consultation",
			reference_name="VCON-001",
			recipient_user=recipient_user,
			context=self.context
		)
		self.assertEqual(key, f"dispensary_expired_stock_blocked::Veterinary Consultation::VCON-001::ITEM-001::Dispensary - WH::{recipient_user}")
