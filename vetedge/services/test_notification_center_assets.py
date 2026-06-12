from __future__ import annotations

from pathlib import Path
from unittest import TestCase


APP_ROOT = Path("/home/olayemigod/frappe-bench/apps/vetedge/vetedge")
JS_PATH = APP_ROOT / "public/js/veterinary_notification_center.js"
CSS_PATH = APP_ROOT / "public/css/veterinary_notification_center.css"
HOOKS_PATH = APP_ROOT / "hooks.py"


class TestNotificationCenterAssets(TestCase):
	def test_assets_are_registered_for_desk(self):
		hooks = HOOKS_PATH.read_text()
		self.assertIn("/assets/vetedge/js/veterinary_notification_center.js", hooks)
		self.assertIn("/assets/vetedge/css/veterinary_notification_center.css", hooks)

	def test_js_maps_expected_api_methods(self):
		source = JS_PATH.read_text()
		for method in (
			"vetedge.services.notification_api.get_my_notification_count",
			"vetedge.services.notification_api.get_my_notifications",
			"vetedge.services.notification_api.mark_my_notification_read",
			"vetedge.services.notification_api.acknowledge_my_notification",
			"vetedge.services.notification_api.mark_my_notification_done",
			"vetedge.services.notification_api.dismiss_my_notification",
			"vetedge.services.notification_api.archive_my_notification",
			"vetedge.services.notification_api.mark_all_my_notifications_read",
		):
			self.assertIn(method, source)

	def test_js_has_safe_loading_and_duplicate_guard(self):
		source = JS_PATH.read_text()
		self.assertIn('if ($("#" + ROOT_ID).length)', source)
		self.assertIn("if (!target.length)", source)
		self.assertIn(".catch(() => updateBadge(0))", source)

	def test_js_has_badge_and_drawer_behaviour(self):
		source = JS_PATH.read_text()
		self.assertIn('badge.text("0").addClass("hidden")', source)
		self.assertIn("badge.text(unreadCount > 99 ? \"99+\" : String(unreadCount)).removeClass(\"hidden\")", source)
		self.assertIn("new frappe.ui.Dialog", source)
		self.assertIn("call(API.feed, { limit: 50 })", source)
		self.assertIn("veterinary_notification_update", source)

	def test_action_buttons_map_to_status_lifecycle(self):
		source = JS_PATH.read_text()
		for status in ("Unread", "Read", "Acknowledged", "Done", "Dismissed"):
			self.assertIn(status, source)
		for action in ("Mark Read", "Acknowledge", "Done", "Dismiss", "Archive"):
			self.assertIn(action, source)

	def test_new_ui_assets_use_veterinary_label(self):
		for path in (JS_PATH, CSS_PATH):
			legacy_label = "Vet" + "Edge"
			self.assertNotIn(legacy_label, path.read_text())
