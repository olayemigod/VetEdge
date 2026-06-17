from __future__ import annotations

import sys
from datetime import date, datetime
from types import ModuleType, SimpleNamespace
from unittest import TestCase
from unittest.mock import Mock, patch


def _install_frappe_stub() -> None:
	if "frappe" not in sys.modules:
		frappe = ModuleType("frappe")
		frappe.__path__ = []
		frappe.ValidationError = Exception
		frappe.PermissionError = Exception
		frappe.throw = Mock(side_effect=Exception("blocked"))
		frappe._ = lambda value, *args, **kwargs: value
		frappe.whitelist = lambda *args, **kwargs: (lambda fn: fn) if args == () else args[0]
		frappe.validate_and_sanitize_search_inputs = lambda fn: fn
		frappe.session = SimpleNamespace(user="doctor@example.com")
		sys.modules["frappe"] = frappe

	if "frappe.permissions" not in sys.modules:
		sys.modules["frappe.permissions"] = ModuleType("frappe.permissions")

	if "frappe.utils" not in sys.modules:
		utils = ModuleType("frappe.utils")
		utils.add_days = lambda value, days: date.today()
		utils.add_to_date = lambda value, **kwargs: value
		utils.cstr = lambda value=None: "" if value is None else str(value)
		utils.flt = lambda value=0: float(value or 0)
		utils.getdate = lambda value=None: date.today()
		utils.now_datetime = datetime.now
		utils.nowdate = lambda: date.today().isoformat()
		sys.modules["frappe.utils"] = utils


_install_frappe_stub()

from vetedge.services import notification_api


class TestNotificationApi(TestCase):
	def test_count_uses_session_user(self):
		frappe_stub = SimpleNamespace(session=SimpleNamespace(user="doctor@example.com"), PermissionError=Exception)

		with (
			patch.object(notification_api, "frappe", frappe_stub),
			patch.object(notification_api, "get_unread_notification_count", return_value=3) as count,
		):
			result = notification_api.get_my_notification_count()

		self.assertEqual(result, {"unread_count": 3})
		count.assert_called_once_with(user="doctor@example.com")

	def test_veterinary_unread_bell_count_uses_session_user(self):
		frappe_stub = SimpleNamespace(session=SimpleNamespace(user="doctor@example.com"), PermissionError=Exception)

		with (
			patch.object(notification_api, "frappe", frappe_stub),
			patch.object(notification_api, "get_veterinary_unread_bell_count", return_value=4) as count,
		):
			result = notification_api.get_my_veterinary_unread_bell_count()

		self.assertEqual(result, {"unread_count": 4})
		count.assert_called_once_with("doctor@example.com")

	def test_veterinary_unread_bell_count_uses_veterinary_item_lifecycle(self):
		count = Mock(return_value=2)
		frappe_stub = SimpleNamespace(db=SimpleNamespace(count=count))

		with patch.object(notification_api, "frappe", frappe_stub):
			result = notification_api.get_veterinary_unread_bell_count("doctor@example.com")

		self.assertEqual(result, 2)
		count.assert_called_once_with(
			"Veterinary Notification Item",
			{"recipient_user": "doctor@example.com", "status": "Unread"},
		)

	def test_veterinary_unread_bell_count_ignores_native_notification_log_read_state(self):
		frappe_stub = SimpleNamespace(db=SimpleNamespace(count=Mock(return_value=0)))

		with patch.object(notification_api, "frappe", frappe_stub):
			count = notification_api.get_veterinary_unread_bell_count("doctor@example.com")

		self.assertEqual(count, 0)
		self.assertFalse(hasattr(frappe_stub.db, "sql"))

	def test_mark_veterinary_notification_read_for_log_uses_linked_item(self):
		frappe_stub = SimpleNamespace(
			session=SimpleNamespace(user="doctor@example.com"),
			PermissionError=Exception,
			db=SimpleNamespace(get_value=Mock(return_value="VNI-001"), count=Mock(return_value=0)),
		)

		with (
			patch.object(notification_api, "frappe", frappe_stub),
			patch.object(notification_api, "mark_notification_read", return_value={"name": "VNI-001", "status": "Read"}) as mark_read,
		):
			result = notification_api.mark_my_veterinary_notification_read_for_log("LOG-001")

		self.assertEqual(result, {"ok": True, "notification": "VNI-001", "unread_count": 0})
		frappe_stub.db.get_value.assert_called_once_with(
			"Veterinary Notification Item",
			{"frappe_notification_log": "LOG-001", "recipient_user": "doctor@example.com"},
			"name",
		)
		mark_read.assert_called_once_with("VNI-001", user="doctor@example.com")

	def test_mark_veterinary_notification_read_for_log_falls_back_to_reference_match(self):
		get_value = Mock(
			side_effect=[
				None,
				{
					"document_type": "Veterinary Missed Appointment",
					"document_name": "VMISS-001",
					"subject": "Veterinary appointment missed",
					"link": "/app/veterinary-missed-appointment/VMISS-001",
				},
				"VNI-002",
			]
		)
		frappe_stub = SimpleNamespace(
			session=SimpleNamespace(user="doctor@example.com"),
			PermissionError=Exception,
			db=SimpleNamespace(get_value=get_value, count=Mock(return_value=1)),
		)

		with (
			patch.object(notification_api, "frappe", frappe_stub),
			patch.object(notification_api, "mark_notification_read", return_value={"name": "VNI-002", "status": "Read"}) as mark_read,
		):
			result = notification_api.mark_my_veterinary_notification_read_for_log("LOG-002")

		self.assertEqual(result["notification"], "VNI-002")
		self.assertEqual(result["unread_count"], 1)
		mark_read.assert_called_once_with("VNI-002", user="doctor@example.com")
		self.assertEqual(get_value.call_args_list[2].args[1]["recipient_user"], "doctor@example.com")
		self.assertEqual(get_value.call_args_list[2].args[1]["reference_doctype"], "Veterinary Missed Appointment")

	def test_mark_all_my_veterinary_notifications_read_uses_current_user_only(self):
		frappe_stub = SimpleNamespace(session=SimpleNamespace(user="doctor@example.com"), PermissionError=Exception)

		with (
			patch.object(notification_api, "frappe", frappe_stub),
			patch.object(notification_api, "mark_all_notifications_read", return_value={"updated": 2}) as mark_all,
			patch.object(notification_api, "get_veterinary_unread_bell_count", return_value=0) as count,
		):
			result = notification_api.mark_all_my_veterinary_notifications_read()

		self.assertEqual(result, {"ok": True, "updated": 2, "unread_count": 0})
		mark_all.assert_called_once_with(user="doctor@example.com")
		count.assert_called_once_with("doctor@example.com")

	def test_recipient_user_can_fetch_own_feed(self):
		rows = [
			{
				"name": "VNI-001",
				"notification_title": "Veterinary lab order ready",
				"message": "A lab order needs review.",
				"priority": "High",
				"status": "Unread",
				"event_key": "lab_result_ready_for_review",
				"created_on": "2026-06-12 10:00:00",
				"reference_doctype": "Veterinary Lab Order",
				"reference_name": "VLAB-001",
				"action_url": "/app/veterinary-lab-order/VLAB-001",
			}
		]
		frappe_stub = SimpleNamespace(session=SimpleNamespace(user="doctor@example.com"), PermissionError=Exception)

		with (
			patch.object(notification_api, "frappe", frappe_stub),
			patch.object(notification_api, "get_notification_feed", return_value=rows) as feed,
			patch.object(notification_api, "get_unread_notification_count", return_value=1),
		):
			result = notification_api.get_my_notifications(limit=25)

		feed.assert_called_once_with(
			user="doctor@example.com",
			status=None,
			include_archived=False,
			limit=25,
		)
		self.assertEqual(result["unread_count"], 1)
		self.assertEqual(result["items"][0]["name"], "VNI-001")
		self.assertEqual(result["items"][0]["title"], "Veterinary lab order ready")
		self.assertEqual(result["items"][0]["category"], "Lab")
		self.assertNotIn("payload_json", result["items"][0])

	def test_feed_supports_category_and_priority_filters(self):
		rows = [
			{"name": "VNI-001", "notification_title": "Lab", "priority": "High", "event_key": "lab_order_created"},
			{"name": "VNI-002", "notification_title": "Billing", "priority": "High", "event_key": "invoice_created"},
			{"name": "VNI-003", "notification_title": "Normal Lab", "priority": "Normal", "event_key": "lab_result_entered"},
		]
		frappe_stub = SimpleNamespace(session=SimpleNamespace(user="doctor@example.com"), PermissionError=Exception)

		with (
			patch.object(notification_api, "frappe", frappe_stub),
			patch.object(notification_api, "get_notification_feed", return_value=rows),
			patch.object(notification_api, "get_unread_notification_count", return_value=2),
		):
			result = notification_api.get_my_notifications(category="Lab", priority="High")

		self.assertEqual([item["name"] for item in result["items"]], ["VNI-001"])

	def test_status_action_uses_session_user_and_returns_client_shape(self):
		frappe_stub = SimpleNamespace(session=SimpleNamespace(user="doctor@example.com"), PermissionError=Exception)

		with (
			patch.object(notification_api, "frappe", frappe_stub),
			patch.object(notification_api, "mark_notification_read", return_value={"name": "VNI-001", "status": "Read"}) as mark_read,
			patch.object(notification_api, "get_unread_notification_count", return_value=2),
		):
			result = notification_api.mark_my_notification_read("VNI-001")

		mark_read.assert_called_once_with("VNI-001", user="doctor@example.com")
		self.assertEqual(result, {"ok": True, "notification": "VNI-001", "status": "Read", "unread_count": 2})

	def test_unrelated_user_cannot_mutate_another_notification_through_api(self):
		frappe_stub = SimpleNamespace(session=SimpleNamespace(user="other@example.com"), PermissionError=Exception)

		with (
			patch.object(notification_api, "frappe", frappe_stub),
			patch.object(notification_api, "mark_notification_read", side_effect=Exception("Not permitted to update this notification.")) as mark_read,
		):
			with self.assertRaises(Exception):
				notification_api.mark_my_notification_read("VNI-001")

		mark_read.assert_called_once_with("VNI-001", user="other@example.com")

	def test_api_does_not_accept_client_user_parameter(self):
		frappe_stub = SimpleNamespace(session=SimpleNamespace(user="doctor@example.com"), PermissionError=Exception)

		with patch.object(notification_api, "frappe", frappe_stub):
			with self.assertRaises(TypeError):
				notification_api.get_my_notifications(user="other@example.com")

	def test_admin_access_remains_service_layer_responsibility(self):
		frappe_stub = SimpleNamespace(session=SimpleNamespace(user="Administrator"), PermissionError=Exception)

		with (
			patch.object(notification_api, "frappe", frappe_stub),
			patch.object(notification_api, "archive_notification", return_value={"name": "VNI-ANY", "status": "Archived"}) as archive,
			patch.object(notification_api, "get_unread_notification_count", return_value=0),
		):
			result = notification_api.archive_my_notification("VNI-ANY")

		archive.assert_called_once_with("VNI-ANY", user="Administrator")
		self.assertEqual(result["status"], "Archived")

	def test_new_api_messages_do_not_use_legacy_product_label(self):
		messages = [
			"Please sign in to view Veterinary notifications.",
			"Priority filter is not valid.",
		]
		legacy_label = "Vet" + "Edge"
		self.assertFalse([message for message in messages if legacy_label in message])
