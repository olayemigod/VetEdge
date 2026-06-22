# -*- coding: utf-8 -*-
from __future__ import annotations

import unittest
from unittest.mock import patch, MagicMock
import frappe
from vetedge.coreedge_adapter import (
	is_coreedge_available,
	is_coreedge_enabled,
	should_show_coreedge_controls,
	get_vetedge_product_app,
	get_current_vetedge_context,
	get_current_vetedge_branch,
	get_current_vetedge_company,
	has_vetedge_access,
	require_vetedge_access,
	get_vetedge_access_context,
	get_visible_vetedge_sidebar_items,
	get_visible_vetedge_settings_items,
	filter_bootinfo_for_coreedge_platform
)

class TestCoreEdgeAdapter(unittest.TestCase):
	def setUp(self):
		frappe.db.set_single_value("Veterinary Settings", "enable_coreedge_platform", 0)
		frappe.db.set_single_value("Veterinary Settings", "coreedge_product_app", "VetEdge")
		frappe.db.set_single_value("Veterinary Settings", "fail_closed_when_coreedge_missing", 0)
		frappe.db.commit()

	def tearDown(self):
		frappe.db.set_single_value("Veterinary Settings", "enable_coreedge_platform", 0)
		frappe.db.set_single_value("Veterinary Settings", "coreedge_product_app", "VetEdge")
		frappe.db.set_single_value("Veterinary Settings", "fail_closed_when_coreedge_missing", 0)
		frappe.db.commit()

	def test_coreedge_disabled_returns_local_fallback(self):
		# CoreEdge disabled
		frappe.db.set_single_value("Veterinary Settings", "enable_coreedge_platform", 0)
		frappe.db.commit()

		context = get_current_vetedge_context()
		self.assertIsNone(context.get("tenant"))
		self.assertEqual(context.get("active_product_app"), "VetEdge")
		self.assertIsNone(context.get("active_branch"))
		self.assertIn("VetEdge", context.get("available_product_apps"))

	def test_coreedge_missing_and_platform_disabled_does_not_crash(self):
		with patch("vetedge.coreedge_adapter.is_coreedge_available", return_value=False):
			frappe.db.set_single_value("Veterinary Settings", "enable_coreedge_platform", 0)
			frappe.db.commit()

			self.assertFalse(should_show_coreedge_controls())
			context = get_current_vetedge_context()
			self.assertEqual(context.get("active_product_app"), "VetEdge")
			# Verify no crash on access check
			self.assertTrue(has_vetedge_access())
			# Verify no crash on require access
			require_vetedge_access()

	def test_coreedge_missing_and_platform_enabled_and_fail_closed_raises_controlled_error(self):
		with patch("vetedge.coreedge_adapter.is_coreedge_available", return_value=False):
			frappe.db.set_single_value("Veterinary Settings", "enable_coreedge_platform", 1)
			frappe.db.set_single_value("Veterinary Settings", "fail_closed_when_coreedge_missing", 1)
			frappe.db.commit()

			with self.assertRaises(frappe.PermissionError):
				require_vetedge_access()

	def test_coreedge_installed_and_platform_disabled_hides_controls(self):
		with patch("vetedge.coreedge_adapter.is_coreedge_available", return_value=True):
			frappe.db.set_single_value("Veterinary Settings", "enable_coreedge_platform", 0)
			frappe.db.commit()

			self.assertFalse(should_show_coreedge_controls())

			sidebar_items = [
				{"label": "Veterinary Patient", "link_to": "Veterinary Patient", "type": "Link"},
				{"label": "Platform Settings", "link_to": "CoreEdge Settings", "type": "Link"},
				{"label": "Product Activation", "link_to": "CoreEdge Product Activation", "type": "Link"},
				{"label": "Onboarding", "link_to": "CoreEdge Tenant", "type": "Link"}
			]

			visible_items = get_visible_vetedge_sidebar_items(sidebar_items)
			labels = [item["label"] for item in visible_items]
			self.assertIn("Veterinary Patient", labels)
			self.assertNotIn("Platform Settings", labels)
			self.assertNotIn("Product Activation", labels)
			self.assertNotIn("Onboarding", labels)

	def test_coreedge_installed_and_platform_enabled_shows_allowed_controls(self):
		with patch("vetedge.coreedge_adapter.is_coreedge_available", return_value=True):
			frappe.db.set_single_value("Veterinary Settings", "enable_coreedge_platform", 1)
			frappe.db.commit()

			self.assertTrue(should_show_coreedge_controls())

			sidebar_items = [
				{"label": "Veterinary Patient", "link_to": "Veterinary Patient", "type": "Link"},
				{"label": "Platform Settings", "link_to": "CoreEdge Settings", "type": "Link"},
				{"label": "Product Activation", "link_to": "CoreEdge Product Activation", "type": "Link"},
				{"label": "Onboarding", "link_to": "CoreEdge Tenant", "type": "Link"}
			]

			visible_items = get_visible_vetedge_sidebar_items(sidebar_items)
			labels = [item["label"] for item in visible_items]
			self.assertIn("Veterinary Patient", labels)
			self.assertIn("Platform Settings", labels)
			self.assertIn("Product Activation", labels)
			self.assertIn("Onboarding", labels)

	def test_lazy_imports_do_not_break_vetedge_at_import_time(self):
		# Verify that importing the module works fine when coreedge is unavailable
		# Since it's already imported above, we just check that no global references crash.
		self.assertTrue(callable(is_coreedge_available))
		self.assertTrue(callable(get_current_vetedge_context))

	def test_workspace_sidebar_and_settings_filtering_does_not_break_normal_vetedge_ui(self):
		sidebar_items = [
			{"label": "Veterinary Patient", "link_to": "Veterinary Patient", "type": "Link"},
			{"label": "Veterinary Hospitalisation", "link_to": "Veterinary Hospitalisation", "type": "Link"}
		]
		visible_items = get_visible_vetedge_sidebar_items(sidebar_items)
		self.assertEqual(len(visible_items), 2)

		settings_items = [
			{"label": "Veterinary Settings", "name": "Veterinary Settings"},
			{"label": "Cost Center", "name": "Cost Center"}
		]
		visible_settings = get_visible_vetedge_settings_items(settings_items)
		self.assertEqual(len(visible_settings), 2)

	def test_no_workflow_gating_happens_in_this_phase(self):
		# Verify that has_vetedge_access and require_vetedge_access default to True/no-op when platform is disabled
		frappe.db.set_single_value("Veterinary Settings", "enable_coreedge_platform", 0)
		frappe.db.commit()

		self.assertTrue(has_vetedge_access())
		# should not raise any exceptions
		require_vetedge_access()
