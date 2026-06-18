from __future__ import annotations

from pathlib import Path
from unittest import TestCase


APP_ROOT = Path("/home/olayemigod/frappe-bench/apps/vetedge/vetedge")
HOOKS_PATH = APP_ROOT / "hooks.py"
ITEM_JSON = APP_ROOT / "veterinary/doctype/veterinary_notification_item/veterinary_notification_item.json"
BADGE_JS = APP_ROOT / "public/js/veterinary_unread_badge.js"
BADGE_CSS = APP_ROOT / "public/css/veterinary_unread_badge.css"


class TestNotificationCenterAssets(TestCase):
	def test_custom_notification_ui_assets_are_not_registered_for_desk(self):
		hooks = HOOKS_PATH.read_text()
		self.assertNotIn("/assets/vetedge/js/veterinary_notification_center.js", hooks)
		self.assertNotIn("/assets/vetedge/css/veterinary_notification_center.css", hooks)

	def test_veterinary_unread_badge_assets_are_registered_for_desk(self):
		hooks = HOOKS_PATH.read_text()
		self.assertIn("/assets/vetedge/js/veterinary_unread_badge.js", hooks)
		self.assertIn("/assets/vetedge/css/veterinary_unread_badge.css", hooks)

	def test_veterinary_unread_badge_js_is_lightweight_native_bell_badge(self):
		source = BADGE_JS.read_text()
		self.assertIn("veterinary-unread-bell-badge", source)
		self.assertIn("veterinary-unread-badge-drawer", source)
		self.assertIn("get_my_veterinary_unread_bell_count", source)
		self.assertIn("get_my_notifications", source)
		self.assertIn("mark_my_veterinary_notification_read_for_log", source)
		self.assertIn("mark_my_notification_read", source)
		self.assertIn("acknowledge_my_notification", source)
		self.assertIn("mark_my_notification_done", source)
		self.assertIn("dismiss_my_notification", source)
		self.assertIn("archive_my_notification", source)
		self.assertIn("mark_all_my_veterinary_notifications_read", source)
		self.assertIn('frappe.realtime.on("notification"', source)
		self.assertIn('.notification-item[data-name]', source)
		self.assertIn("Veterinary", source)
		self.assertIn(".sidebar-notification", source)
		self.assertIn(".notifications-icon", source)
		self.assertIn(".dropdown-notifications", source)
		self.assertNotIn("VetEdge Notifications", source)
		self.assertNotIn("openDrawer", source)
		self.assertNotIn("new frappe.ui.Dialog", source)
		self.assertNotIn("veterinary_notification_center", source)
		self.assertNotIn("veterinary-sidebar-notification-center", source)
		self.assertNotIn("veterinary-workspace-notification-center", source)
		self.assertNotIn("veterinary-patient", source)
		self.assertNotIn("veterinary-appointment", source)
		self.assertNotIn("window.location", source)

	def test_veterinary_unread_badge_css_is_scoped(self):
		source = BADGE_CSS.read_text()
		self.assertIn("#veterinary-unread-bell-badge", source)
		self.assertIn("#veterinary-unread-badge-drawer", source)
		self.assertNotIn(".veterinary-notification-dialog", source)

	def test_native_bell_backend_files_remain_available(self):
		self.assertTrue((APP_ROOT / "services/notifications.py").exists())
		self.assertTrue((APP_ROOT / "services/notification_api.py").exists())
		self.assertTrue(ITEM_JSON.exists())

	def test_notification_item_tracks_native_frappe_notification_log(self):
		source = ITEM_JSON.read_text()
		self.assertIn('"fieldname": "frappe_notification_log"', source)
		self.assertIn('"options": "Notification Log"', source)

	def test_no_user_facing_legacy_product_notification_label_in_hooks_or_schema(self):
		legacy_label = "Vet" + "Edge Notifications"
		self.assertNotIn(legacy_label, HOOKS_PATH.read_text())
		self.assertNotIn(legacy_label, ITEM_JSON.read_text())
