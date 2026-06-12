from __future__ import annotations

import json
import sys
from datetime import date, datetime
from pathlib import Path
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
		frappe.db = SimpleNamespace()
		frappe.session = SimpleNamespace(user="test.com")
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

from vetedge.services import notifications
from vetedge.services import permissions


APP_ROOT = Path("/home/olayemigod/frappe-bench/apps/vetedge/vetedge")
ITEM_JSON = APP_ROOT / "veterinary/doctype/veterinary_notification_item/veterinary_notification_item.json"


class TestNotificationItemStructure(TestCase):
	def test_notification_item_doctype_uses_veterinary_label(self):
		doctype_json = json.loads(ITEM_JSON.read_text())

		self.assertEqual(doctype_json["name"], "Veterinary Notification Item")
		labels = {field.get("label") for field in doctype_json["fields"] if field.get("label")}
		self.assertFalse(
			[label for label in labels if "VetEdge" in label],
			msg="Notification Item user-facing field labels must not say VetEdge.",
		)

	def test_notification_item_permission_hooks_are_registered(self):
		hooks_py = (APP_ROOT / "hooks.py").read_text()

		self.assertIn(
			'"Veterinary Notification Item": "vetedge.services.permissions.get_veterinary_notification_item_query"',
			hooks_py,
		)
		self.assertIn(
			'"Veterinary Notification Item": "vetedge.services.permissions.has_veterinary_notification_item_permission"',
			hooks_py,
		)


class TestNotificationItemService(TestCase):
	def test_create_notification_item_reuses_existing_idempotency_key(self):
		frappe_stub = SimpleNamespace(
			ValidationError=Exception,
			db=SimpleNamespace(
				exists=Mock(return_value=True),
				get_value=Mock(return_value="VNI-001"),
			),
		)

		with patch.object(notifications, "frappe", frappe_stub):
			result = notifications.create_notification_item(
				event_key="lab_order_created",
				recipient_user="doctor@example.com",
				notification_title="Lab order created",
				reference_doctype="Veterinary Lab Order",
				reference_name="VLAB-001",
			)

		self.assertFalse(result["created"])
		self.assertEqual(result["name"], "VNI-001")

	def test_create_notification_item_inserts_when_key_is_new(self):
		inserted = []
		doc = SimpleNamespace(name="VNI-002", insert=lambda **kwargs: inserted.append(kwargs))
		frappe_stub = SimpleNamespace(
			ValidationError=Exception,
			db=SimpleNamespace(
				exists=Mock(return_value=True),
				get_value=Mock(return_value=None),
			),
			get_doc=Mock(return_value=doc),
		)

		with patch.object(notifications, "frappe", frappe_stub):
			result = notifications.create_notification_item(
				event_key="lab_order_created",
				recipient_user="doctor@example.com",
				notification_title="Lab order created",
				message="A lab order needs attention.",
				reference_doctype="Veterinary Lab Order",
				reference_name="VLAB-001",
				payload={"lab_order": "VLAB-001"},
			)

		self.assertTrue(result["created"])
		self.assertEqual(result["name"], "VNI-002")
		self.assertEqual(inserted, [{"ignore_permissions": True}])
		frappe_stub.get_doc.assert_called_once()
		self.assertEqual(frappe_stub.get_doc.call_args.args[0]["status"], "Unread")

	def test_unread_count_is_scoped_to_current_user(self):
		frappe_stub = SimpleNamespace(
			session=SimpleNamespace(user="doctor@example.com"),
			db=SimpleNamespace(count=Mock(return_value=3)),
		)

		with patch.object(notifications, "frappe", frappe_stub):
			count = notifications.get_unread_notification_count()

		self.assertEqual(count, 3)
		frappe_stub.db.count.assert_called_once_with(
			"Veterinary Notification Item",
			{"recipient_user": "doctor@example.com", "status": "Unread"},
		)

	def test_mark_read_updates_status_when_user_can_update_item(self):
		set_value = Mock()
		frappe_stub = SimpleNamespace(
			ValidationError=Exception,
			PermissionError=Exception,
			db=SimpleNamespace(set_value=set_value),
		)

		with (
			patch.object(notifications, "frappe", frappe_stub),
			patch.object(notifications, "can_update_notification_item", return_value=True),
		):
			result = notifications.mark_notification_read("VNI-001", user="doctor@example.com")

		self.assertEqual(result, {"name": "VNI-001", "status": "Read"})
		set_value.assert_called_once()
		self.assertEqual(set_value.call_args.args[0], "Veterinary Notification Item")
		self.assertEqual(set_value.call_args.args[1], "VNI-001")
		self.assertEqual(set_value.call_args.args[2]["status"], "Read")

	def test_status_model_includes_operational_lifecycle_fields(self):
		doctype_json = json.loads(ITEM_JSON.read_text())
		fields = {field.get("fieldname"): field for field in doctype_json["fields"]}
		self.assertEqual(
			fields["status"]["options"],
			"Unread\nRead\nAcknowledged\nDone\nDismissed\nArchived",
		)
		for fieldname in ("read_on", "acknowledged_on", "completed_on", "dismissed_on", "archived_on"):
			self.assertIn(fieldname, fields)
			self.assertEqual(fields[fieldname].get("read_only"), 1)

	def test_duplicate_idempotency_key_skips_second_db_insert(self):
		inserted = []
		doc = SimpleNamespace(name="VNI-DB-001", insert=lambda **kwargs: inserted.append(kwargs))
		frappe_stub = SimpleNamespace(
			ValidationError=Exception,
			db=SimpleNamespace(
				exists=Mock(return_value=True),
				get_value=Mock(side_effect=[None, "VNI-DB-001"]),
			),
			get_doc=Mock(return_value=doc),
		)

		with patch.object(notifications, "frappe", frappe_stub):
			first = notifications.create_notification_item(
				event_key="lab_order_created",
				recipient_user="doctor.com",
				notification_title="Lab order created",
				idempotency_key="same-key",
			)
			second = notifications.create_notification_item(
				event_key="lab_order_created",
				recipient_user="doctor.com",
				notification_title="Lab order created",
				idempotency_key="same-key",
			)

		self.assertTrue(first["created"])
		self.assertFalse(second["created"])
		self.assertEqual(second["name"], "VNI-DB-001")
		frappe_stub.get_doc.assert_called_once()
		self.assertEqual(len(inserted), 1)

	def test_operational_status_actions_set_matching_timestamp_only(self):
		set_value = Mock()
		frappe_stub = SimpleNamespace(
			ValidationError=Exception,
			PermissionError=Exception,
			db=SimpleNamespace(set_value=set_value),
		)

		with (
			patch.object(notifications, "frappe", frappe_stub),
			patch.object(notifications, "can_update_notification_item", return_value=True),
		):
			notifications.acknowledge_notification("VNI-001", user="doctor.com")
			notifications.mark_notification_done("VNI-001", user="doctor.com")
			notifications.dismiss_notification("VNI-001", user="doctor.com")

		ack_values = set_value.call_args_list[0].args[2]
		done_values = set_value.call_args_list[1].args[2]
		dismissed_values = set_value.call_args_list[2].args[2]
		self.assertEqual(ack_values["status"], "Acknowledged")
		self.assertIn("acknowledged_on", ack_values)
		self.assertNotIn("completed_on", ack_values)
		self.assertEqual(done_values["status"], "Done")
		self.assertIn("completed_on", done_values)
		self.assertEqual(dismissed_values["status"], "Dismissed")
		self.assertIn("dismissed_on", dismissed_values)

	def test_feed_excludes_archived_by_default(self):
		get_all = Mock(return_value=[])
		frappe_stub = SimpleNamespace(
			ValidationError=Exception,
			session=SimpleNamespace(user="doctor.com"),
			get_all=get_all,
		)

		with patch.object(notifications, "frappe", frappe_stub):
			feed = notifications.get_notification_feed(limit=25)

		self.assertEqual(feed, [])
		self.assertEqual(get_all.call_args.kwargs["filters"], {"recipient_user": "doctor.com", "status": ["!=", "Archived"]})
		self.assertEqual(get_all.call_args.kwargs["limit_page_length"], 25)

	def test_recipient_and_admin_notification_permissions(self):
		doc = SimpleNamespace(recipient_user="doctor.com")

		with patch.object(permissions, "is_notification_admin", return_value=False):
			self.assertTrue(
				permissions.has_veterinary_notification_item_permission(
					doc,
					user="doctor.com",
					permission_type="read",
				)
			)
			self.assertTrue(
				permissions.has_veterinary_notification_item_permission(
					doc,
					user="doctor.com",
					permission_type="write",
				)
			)
			self.assertFalse(
				permissions.has_veterinary_notification_item_permission(
					doc,
					user="other.com",
					permission_type="read",
				)
			)
			self.assertFalse(
				permissions.has_veterinary_notification_item_permission(
					doc,
					user="other.com",
					permission_type="write",
				)
			)

		with patch.object(permissions, "is_notification_admin", return_value=True):
			self.assertTrue(
				permissions.has_veterinary_notification_item_permission(
					doc,
					user="admin.com",
					permission_type="read",
				)
			)
			self.assertTrue(
				permissions.has_veterinary_notification_item_permission(
					doc,
					user="admin.com",
					permission_type="write",
				)
			)

	def test_notification_query_scopes_non_admin_to_recipient(self):
		frappe_stub = SimpleNamespace(db=SimpleNamespace(escape=lambda value: "'%s'" % value))

		with (
			patch.object(permissions, "frappe", frappe_stub),
			patch.object(permissions, "is_notification_admin", return_value=False),
		):
			query = permissions.get_veterinary_notification_item_query(user="doctor.com")

		self.assertEqual(
			query,
			"`tabVeterinary Notification Item`.`recipient_user` = 'doctor.com'",
		)
