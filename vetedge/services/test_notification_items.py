from __future__ import annotations

import json
import sys
from datetime import date, datetime
from pathlib import Path
from types import ModuleType, SimpleNamespace
from unittest import TestCase
from unittest.mock import Mock, patch


def _install_frappe_stub() -> None:
	if "frappe" in sys.modules and hasattr(sys.modules["frappe"], "db") and hasattr(sys.modules["frappe"].db, "sql"):
		return

	if "frappe" not in sys.modules:
		frappe = ModuleType("frappe")
		frappe.__path__ = []
		frappe.ValidationError = Exception
		frappe.PermissionError = Exception
		frappe.throw = Mock(side_effect=Exception("blocked"))
		frappe._ = lambda value, *args, **kwargs: value
		frappe.scrub = lambda value: str(value).lower().replace(" ", "_")
		frappe.publish_realtime = Mock()
		frappe.log_error = Mock()
		frappe.get_traceback = lambda: "traceback"
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
		existing = SimpleNamespace(name="VNI-001", frappe_notification_log="NOTIF-001", get=lambda key, default=None: getattr(existing, key, default))
		frappe_stub = SimpleNamespace(
			ValidationError=Exception,
			db=SimpleNamespace(
				exists=Mock(return_value=True),
				get_value=Mock(return_value="VNI-001"),
			),
			get_doc=Mock(return_value=existing),
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
		frappe_stub.get_doc.assert_called_once_with("Veterinary Notification Item", "VNI-001")

	def test_create_notification_item_inserts_when_key_is_new(self):
		inserted = []
		docs = []

		class Doc(SimpleNamespace):
			def get(self, key, default=None):
				return getattr(self, key, default)

			def insert(self, **kwargs):
				inserted.append((self.doctype, kwargs))
				if self.doctype == "Veterinary Notification Item":
					self.name = "VNI-002"
				if self.doctype == "Notification Log":
					self.name = "NOTIF-001"
				docs.append(self)

		frappe_stub = SimpleNamespace(
			ValidationError=Exception,
			session=SimpleNamespace(user="test.com"),
			scrub=lambda value: str(value).lower().replace(" ", "_"),
			publish_realtime=Mock(),
			db=SimpleNamespace(
				exists=Mock(return_value=True),
				get_value=Mock(return_value=None),
				set_value=Mock(),
			),
			get_doc=Mock(side_effect=lambda value, name=None: Doc(**value) if isinstance(value, dict) else docs[0]),
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
		self.assertEqual(result["name"], docs[0].name)
		self.assertEqual(inserted[0], ("Veterinary Notification Item", {"ignore_permissions": True}))
		self.assertEqual(inserted[1], ("Notification Log", {"ignore_permissions": True}))
		self.assertEqual(docs[0].status, "Unread")
		self.assertEqual(docs[1].for_user, "doctor@example.com")
		self.assertEqual(docs[1].subject, "Lab order created")
		self.assertEqual(docs[1].document_type, "Veterinary Lab Order")
		self.assertEqual(docs[1].document_name, "VLAB-001")
		frappe_stub.publish_realtime.assert_not_called()
		frappe_stub.db.set_value.assert_called_once_with(
			"Veterinary Notification Item",
			docs[0].name,
			"frappe_notification_log",
			"NOTIF-001",
			update_modified=False,
		)

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

		class Doc(SimpleNamespace):
			def get(self, key, default=None):
				return getattr(self, key, default)

			def insert(self, **kwargs):
				inserted.append(self.doctype)
				if self.doctype == "Notification Log":
					self.name = "NOTIF-001"

		item = Doc(name="VNI-DB-001", frappe_notification_log="NOTIF-001")

		created_items = {"count": 0}

		def get_value(doctype, filters, fieldname=None, *args, **kwargs):
			if doctype == "Veterinary Notification Item":
				created_items["count"] += 1
				return None if created_items["count"] == 1 else "VNI-DB-001"
			if doctype == "Notification Log":
				return None
			return None

		frappe_stub = SimpleNamespace(
			ValidationError=Exception,
			db=SimpleNamespace(
				exists=Mock(return_value=True),
				get_value=Mock(side_effect=get_value),
				set_value=Mock(),
			),
			get_doc=Mock(side_effect=lambda value, name=None: item if not isinstance(value, dict) else Doc(name="VNI-DB-001", **value)),
			scrub=lambda value: str(value).lower().replace(" ", "_"),
			publish_realtime=Mock(),
			log_error=Mock(),
			get_traceback=lambda: "traceback",
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
		self.assertEqual(inserted.count("Veterinary Notification Item"), 1)
		self.assertEqual(inserted.count("Notification Log"), 1)

	def test_frappe_notification_log_falls_back_to_veterinary_item_reference(self):
		inserted = []

		class Doc(SimpleNamespace):
			def get(self, key, default=None):
				return getattr(self, key, default)

			def insert(self, **kwargs):
				if self.doctype == "Notification Log":
					self.name = "NOTIF-FALLBACK"
				inserted.append(self)

		item = Doc(
			doctype="Veterinary Notification Item",
			name="VNI-003",
			recipient_user="doctor@example.com",
			notification_title="Veterinary reminder",
			message="Reminder",
			reference_doctype=None,
			reference_name=None,
			action_url=None,
			frappe_notification_log=None,
		)
		frappe_stub = SimpleNamespace(
			db=SimpleNamespace(exists=Mock(return_value=True), set_value=Mock()),
			get_doc=Mock(side_effect=lambda value, name=None: item if not isinstance(value, dict) else Doc(**value)),
			scrub=lambda value: str(value).lower().replace(" ", "_"),
			publish_realtime=Mock(),
		)

		with patch.object(notifications, "frappe", frappe_stub):
			name = notifications.ensure_frappe_notification_log("VNI-003")

		self.assertEqual(name, "NOTIF-FALLBACK")
		log = inserted[0]
		self.assertEqual(log.document_type, "Veterinary Notification Item")
		self.assertEqual(log.document_name, "VNI-003")
		self.assertEqual(log.link, "/app/veterinary-notification-item/VNI-003")

	def test_frappe_notification_log_reuses_existing_native_log_when_item_link_is_missing(self):
		inserted = []

		class Doc(SimpleNamespace):
			def get(self, key, default=None):
				return getattr(self, key, default)

			def insert(self, **kwargs):
				inserted.append(self)

		item = Doc(
			doctype="Veterinary Notification Item",
			name="VNI-005",
			recipient_user="doctor@example.com",
			notification_title="Veterinary appointment missed",
			message="Missed",
			reference_doctype="Veterinary Missed Appointment",
			reference_name="VMISS-001",
			action_url="/app/veterinary-missed-appointment/VMISS-001",
			frappe_notification_log=None,
		)
		frappe_stub = SimpleNamespace(
			db=SimpleNamespace(
				exists=Mock(return_value=True),
				get_value=Mock(return_value="NOTIF-EXISTING"),
				set_value=Mock(),
			),
			get_doc=Mock(side_effect=lambda value, name=None: item if not isinstance(value, dict) else Doc(**value)),
			scrub=lambda value: str(value).lower().replace(" ", "_"),
			publish_realtime=Mock(),
		)

		with patch.object(notifications, "frappe", frappe_stub):
			name = notifications.ensure_frappe_notification_log("VNI-005")

		self.assertEqual(name, "NOTIF-EXISTING")
		self.assertEqual(inserted, [])
		frappe_stub.db.set_value.assert_called_once_with(
			"Veterinary Notification Item",
			"VNI-005",
			"frappe_notification_log",
			"NOTIF-EXISTING",
			update_modified=False,
		)

	def test_frappe_notification_log_failure_does_not_block_item_creation(self):
		inserted = []

		class Doc(SimpleNamespace):
			def get(self, key, default=None):
				return getattr(self, key, default)

			def insert(self, **kwargs):
				inserted.append(self.doctype)
				if self.doctype == "Notification Log":
					raise Exception("native bell unavailable")

		frappe_stub = SimpleNamespace(
			ValidationError=Exception,
			db=SimpleNamespace(
				exists=Mock(return_value=True),
				get_value=Mock(return_value=None),
				set_value=Mock(),
			),
			get_doc=Mock(side_effect=lambda value, name=None: Doc(name="VNI-004", **value) if isinstance(value, dict) else None),
			scrub=lambda value: str(value).lower().replace(" ", "_"),
			publish_realtime=Mock(),
			log_error=Mock(),
			get_traceback=lambda: "traceback",
		)

		with patch.object(notifications, "frappe", frappe_stub):
			result = notifications.create_notification_item(
				event_key="lab_order_created",
				recipient_user="doctor@example.com",
				notification_title="Veterinary lab order",
			)

		self.assertTrue(result["created"])
		self.assertEqual(inserted[0], "Veterinary Notification Item")
		self.assertIn("Notification Log", inserted)
		frappe_stub.log_error.assert_called_once()

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
