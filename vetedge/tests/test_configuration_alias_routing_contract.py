from __future__ import annotations

import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
PAGE_ROOT = ROOT / "vetedge" / "veterinary" / "page"


class TestConfigurationAliasRoutingContract(unittest.TestCase):
	def test_configuration_aliases_defer_router_redirect_until_page_show_returns(self):
		aliases = {
			"vetedge_branch_user_access/vetedge_branch_user_access.js": "user-assignments",
			"vetedge_practitioner_coverage/vetedge_practitioner_coverage.js": "practitioner-assignments",
			"vetedge_notification_preferences/vetedge_notification_preferences.js": "notification-preferences",
			"vetedge_notification_delivery_log/vetedge_notification_delivery_log.js": "notification-logs",
			"vetedge_notification_items/vetedge_notification_items.js": "notification-items",
			"vetedge_role_bundles/vetedge_role_bundles.js": "role-bundles",
			"vetedge_license_profile/vetedge_license_profile.js": "license-profile",
		}

		for relative_path, resource in aliases.items():
			with self.subTest(path=relative_path):
				text = (PAGE_ROOT / relative_path).read_text(encoding="utf-8")
				self.assertIn(f"resource={resource}", text)
				self.assertIn("window.setTimeout(() => {", text)
				self.assertIn("history.replaceState", text)
				self.assertIn("frappe.router.route", text)
				self.assertLess(text.index("window.setTimeout"), text.index("history.replaceState"))
				self.assertIn("}, 0);", text)


if __name__ == "__main__":
	unittest.main()
