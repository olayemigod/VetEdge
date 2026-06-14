from __future__ import annotations

from pathlib import Path
from unittest import TestCase


APP_ROOT = Path("/home/olayemigod/frappe-bench/apps/vetedge/vetedge")
HOOKS_PATH = APP_ROOT / "hooks.py"
ITEM_JSON = APP_ROOT / "veterinary/doctype/veterinary_notification_item/veterinary_notification_item.json"


class TestNotificationCenterAssets(TestCase):
	def test_custom_notification_ui_assets_are_not_registered_for_desk(self):
		hooks = HOOKS_PATH.read_text()
		self.assertNotIn("/assets/vetedge/js/veterinary_notification_center.js", hooks)
		self.assertNotIn("/assets/vetedge/css/veterinary_notification_center.css", hooks)

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
