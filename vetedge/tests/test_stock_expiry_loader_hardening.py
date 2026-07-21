import os
import re

import frappe
from frappe.tests.utils import FrappeTestCase


class TestStockExpiryLoaderHardening(FrappeTestCase):
	def _controller(self):
		path = os.path.join(
			frappe.get_app_path("vetedge"),
			"veterinary",
			"page",
			"stock_expiry_monitor",
			"stock_expiry_monitor.js",
		)
		with open(path) as controller:
			return controller.read()

	def test_controller_boot_and_registration_guards(self):
		content = self._controller()
		self.assertIn("[BOOT]", content)
		self.assertLess(
			content.find("try {"),
			content.find("frappe.pages['stock-expiry-monitor']"),
		)
		self.assertTrue("if (!page)" in content or "if (!wrapper.page)" in content)

	def test_failure_rendering_uses_wrapper(self):
		content = self._controller()
		self.assertIn("wrapper.appendChild", content)
		self.assertIn("appendStockExpiryFailure", content)

	def test_catch_blocks_do_not_depend_on_asset_loader(self):
		content = self._controller()
		active_content = re.sub(r"/\*.*?\*/", "", content, flags=re.DOTALL)
		active_content = re.sub(r"//.*?\n", "\n", active_content)
		catch_bodies = re.findall(
			r"catch\s*\([^)]*\)\s*\{(.*?)\n\s*\}",
			active_content,
			flags=re.DOTALL,
		)
		self.assertTrue(catch_bodies, "No catch blocks found")
		for body in catch_bodies:
			self.assertNotIn("frappe.require", body)
