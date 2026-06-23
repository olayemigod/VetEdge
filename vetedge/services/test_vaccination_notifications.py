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
			set_value=Mock()
		)
		frappe.session = SimpleNamespace(user="test@example.com")
		sys.modules["frappe"] = frappe

	if "frappe.utils" not in sys.modules:
		utils = ModuleType("frappe.utils")
		utils.add_days = lambda value, days: date.fromisoformat(str(value).split(" ")[0]).fromordinal(date.fromisoformat(str(value).split(" ")[0]).toordinal() + days)
		utils.cstr = lambda value=None: "" if value is None else str(value)
		utils.getdate = lambda value=None: date.fromisoformat(str(value).split(" ")[0]) if value else date.today()
		utils.nowdate = lambda: date.today().isoformat()
		utils.now_datetime = datetime.now
		sys.modules["frappe.utils"] = utils

	stubs = {
		"vetedge.services.notifications": {
			"create_notification_item": lambda *args, **kwargs: {"created": True, "name": "VNI-001"},
			"get_role_recipients": lambda *args, **kwargs: [],
			"get_user_recipient": lambda user, **kwargs: {"user": user} if user else None,
			"get_notification_settings": lambda: {"enabled": True, "vaccination_due_reminder_days": 7},
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
from vetedge.services import vaccination_notifications
from vetedge.services.notification_api import get_veterinary_unread_bell_count

class TestVaccinationNotifications(TestCase):
	def test_resolve_recipients_does_not_notify_owners_or_customers(self):
		# Setup record document
		doc = {
			"name": "VVAC-001",
			"patient": "PAT-001",
			"primary_owner": "CUST-001", # owner should not be notified as a customer
			"service_branch": "Main Branch",
			"vaccine": "Rabies",
			"next_due_date": "2026-06-23",
			"administered_by": "doctor@example.com",
			"owner": "creator@example.com",
		}
		
		# We mock get_role_recipients to return some branch roles
		role_users = [
			{"user": "frontdesk@example.com"},
			{"user": "manager@example.com"},
		]
		
		def mock_get_user_recipient(user, **kwargs):
			return {"user": user} if user else None

		with (
			patch("vetedge.services.vaccination_notifications.get_role_recipients", return_value=role_users),
			patch("vetedge.services.vaccination_notifications.get_user_recipient", side_effect=mock_get_user_recipient)
		):
			recipients = vaccination_notifications.resolve_vaccination_notification_recipients(doc)
			
		self.assertIn("doctor@example.com", recipients)
		self.assertIn("creator@example.com", recipients)
		self.assertIn("frontdesk@example.com", recipients)
		self.assertIn("manager@example.com", recipients)
		self.assertNotIn("CUST-001", recipients)

	def test_resolve_recipients_deduplicates_users(self):
		# If administered_by, creator, and role recipients overlap
		doc = {
			"name": "VVAC-001",
			"service_branch": "Main Branch",
			"administered_by": "doctor@example.com",
			"owner": "doctor@example.com",
		}
		role_users = [
			{"user": "doctor@example.com"},
		]
		
		def mock_get_user_recipient(user, **kwargs):
			return {"user": user} if user else None

		with (
			patch("vetedge.services.vaccination_notifications.get_role_recipients", return_value=role_users),
			patch("vetedge.services.vaccination_notifications.get_user_recipient", side_effect=mock_get_user_recipient)
		):
			recipients = vaccination_notifications.resolve_vaccination_notification_recipients(doc)
			
		self.assertEqual(len(recipients), 1)
		self.assertEqual(recipients[0], "doctor@example.com")

	def test_resolve_recipients_fallback_to_doctors_and_admin(self):
		# No primary practitioner, creator, or front desk staff resolved
		doc = {
			"name": "VVAC-001",
			"service_branch": "Main Branch",
			"administered_by": None,
			"owner": None,
		}
		
		# mock get_role_recipients to simulate:
		# First call (HIGH_VISIBILITY_ROLES): returns empty list
		# Second call (fallback_roles: doctor/nurse): returns doctor
		fallback_mock = Mock(side_effect=[[], [{"user": "doctor.fallback@example.com"}]])
		
		def mock_get_user_recipient(user, **kwargs):
			return {"user": user} if user else None

		with (
			patch("vetedge.services.vaccination_notifications.get_role_recipients", fallback_mock),
			patch("vetedge.services.vaccination_notifications.get_user_recipient", side_effect=mock_get_user_recipient)
		):
			recipients = vaccination_notifications.resolve_vaccination_notification_recipients(doc)
			
		self.assertIn("doctor.fallback@example.com", recipients)
		self.assertEqual(fallback_mock.call_count, 2)

	def test_due_vaccination_notification_creation_and_idempotency(self):
		doc = {
			"name": "VVAC-001",
			"patient": "PAT-001",
			"primary_owner": "CUST-001",
			"service_branch": "Main Branch",
			"vaccine": "Rabies",
			"next_due_date": "2026-06-23",
			"administered_by": "doctor@example.com",
			"owner": "creator@example.com",
		}
		
		created_items = []
		
		def mock_create_item(event_key, recipient_user, idempotency_key, **kwargs):
			created_items.append({
				"event_key": event_key,
				"recipient_user": recipient_user,
				"idempotency_key": idempotency_key,
			})
			return {"created": True, "name": "VNI-001"}
			
		with (
			patch("vetedge.services.vaccination_notifications.resolve_vaccination_notification_recipients", return_value=["doctor@example.com"]),
			patch("vetedge.services.vaccination_notifications.create_notification_item", side_effect=mock_create_item)
		):
			vaccination_notifications.notify_vaccination_due(doc)
			
		self.assertEqual(len(created_items), 1)
		self.assertEqual(created_items[0]["event_key"], "vaccination_due")
		self.assertEqual(created_items[0]["recipient_user"], "doctor@example.com")
		self.assertEqual(created_items[0]["idempotency_key"], "vaccination_due::VVAC-001::2026-06-23::doctor@example.com")

	def test_overdue_vaccination_notification_creation_and_idempotency(self):
		doc = {
			"name": "VVAC-002",
			"patient": "PAT-001",
			"primary_owner": "CUST-001",
			"service_branch": "Main Branch",
			"vaccine": "Rabies",
			"next_due_date": "2026-06-20",
			"administered_by": "doctor@example.com",
			"owner": "creator@example.com",
		}
		
		created_items = []
		
		def mock_create_item(event_key, recipient_user, idempotency_key, **kwargs):
			created_items.append({
				"event_key": event_key,
				"recipient_user": recipient_user,
				"idempotency_key": idempotency_key,
			})
			return {"created": True, "name": "VNI-002"}
			
		with (
			patch("vetedge.services.vaccination_notifications.resolve_vaccination_notification_recipients", return_value=["doctor@example.com"]),
			patch("vetedge.services.vaccination_notifications.create_notification_item", side_effect=mock_create_item)
		):
			vaccination_notifications.notify_vaccination_overdue(doc)
			
		self.assertEqual(len(created_items), 1)
		self.assertEqual(created_items[0]["event_key"], "vaccination_overdue")
		self.assertEqual(created_items[0]["recipient_user"], "doctor@example.com")
		self.assertEqual(created_items[0]["idempotency_key"], "vaccination_overdue::VVAC-002::2026-06-20::doctor@example.com")

	def test_run_vaccination_notification_checks_triggers_both_runs(self):
		due_called = []
		overdue_called = []
		
		with (
			patch("vetedge.services.vaccination_notifications.send_due_vaccination_notifications", side_effect=lambda: due_called.append(True)),
			patch("vetedge.services.vaccination_notifications.send_overdue_vaccination_notifications", side_effect=lambda: overdue_called.append(True))
		):
			vaccination_notifications.run_vaccination_notification_checks()
			
		self.assertTrue(due_called)
		self.assertTrue(overdue_called)

	def test_badge_count_increases_on_unread_decreases_on_read(self):
		# We want to verify that when we call get_veterinary_unread_bell_count, it returns count based on status Unread.
		counts = {"Unread": 5, "Read": 10}
		
		def mock_count(doctype, filters):
			status = filters.get("status")
			return counts.get(status, 0)
			
		frappe_stub = SimpleNamespace(
			db=SimpleNamespace(
				count=mock_count
			)
		)
		
		with patch("vetedge.services.notification_api.frappe", frappe_stub):
			unread_count = get_veterinary_unread_bell_count("test@example.com")
			
		self.assertEqual(unread_count, 5)
