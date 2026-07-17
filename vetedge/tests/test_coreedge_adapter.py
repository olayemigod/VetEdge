# -*- coding: utf-8 -*-
from __future__ import annotations

import unittest
from unittest.mock import patch, MagicMock
import frappe
from vetedge.coreedge_adapter import (
	is_coreedge_available,
	is_coreedge_enabled,
	should_show_coreedge_controls,
	should_fail_closed_when_coreedge_missing,
	get_vetedge_product_app,
	get_current_vetedge_context,
	get_current_vetedge_branch,
	get_current_vetedge_company,
	has_vetedge_access,
	require_vetedge_access,
	get_vetedge_access_context,
	get_visible_vetedge_sidebar_items,
	get_visible_vetedge_settings_items,
	filter_bootinfo_for_coreedge_platform,
	get_canonical_vetedge_sidebar_for_boot,
	_parse_config_bool,
	get_edge_platform_mode
)

class TestCoreEdgeAdapter(unittest.TestCase):
	def setUp(self):
		# Back up original frappe.conf keys
		self.orig_conf = dict(frappe.conf)
		# Clear any coreedge settings from active test conf to start with clean state
		for key in ("coreedge_required", "edge_platform_mode", "edge_platform_product"):
			if key in frappe.conf:
				del frappe.conf[key]

	def tearDown(self):
		# Restore original frappe.conf keys
		frappe.conf.clear()
		frappe.conf.update(self.orig_conf)

	def test_config_truthiness_parsing(self):
		# 10. Config truthiness is parsed correctly for values like "0", "false", "1", "true", 0, 1, None, and blank strings.
		self.assertTrue(_parse_config_bool(1))
		self.assertTrue(_parse_config_bool("1"))
		self.assertTrue(_parse_config_bool(True))
		self.assertTrue(_parse_config_bool("true"))
		self.assertTrue(_parse_config_bool("True"))
		self.assertTrue(_parse_config_bool("yes"))
		self.assertTrue(_parse_config_bool("on"))
		
		self.assertFalse(_parse_config_bool(0))
		self.assertFalse(_parse_config_bool("0"))
		self.assertFalse(_parse_config_bool(False))
		self.assertFalse(_parse_config_bool("false"))
		self.assertFalse(_parse_config_bool("no"))
		self.assertFalse(_parse_config_bool("off"))
		self.assertFalse(_parse_config_bool(""))
		self.assertFalse(_parse_config_bool(None))

	def test_standalone_with_coreedge_missing_uses_local_fallback(self):
		# 1. edge_platform_mode = standalone with CoreEdge missing uses local fallback.
		frappe.conf.edge_platform_mode = "standalone"
		with patch("vetedge.coreedge_adapter.is_coreedge_available", return_value=False):
			self.assertFalse(is_coreedge_enabled())
			self.assertFalse(should_show_coreedge_controls())
			
			# Fallback context check
			context = get_current_vetedge_context()
			self.assertIsNone(context.get("tenant"))
			self.assertEqual(context.get("active_product_app"), "VetEdge")
			self.assertTrue(has_vetedge_access())
			# require_vetedge_access should succeed (not fail closed)
			require_vetedge_access()

	def test_coreedge_required_and_missing_fails_closed(self):
		# 2. coreedge_required = 1 with CoreEdge missing fails closed with controlled PermissionError.
		frappe.conf.coreedge_required = 1
		with patch("vetedge.coreedge_adapter.is_coreedge_available", return_value=False):
			self.assertTrue(is_coreedge_enabled())
			with self.assertRaises(frappe.PermissionError):
				require_vetedge_access()

	def test_shared_hosted_forces_coreedge_required_and_fails_closed(self):
		# 3. edge_platform_mode = shared_hosted forces CoreEdge required and fails closed if CoreEdge is missing.
		frappe.conf.edge_platform_mode = "shared_hosted"
		with patch("vetedge.coreedge_adapter.is_coreedge_available", return_value=False):
			self.assertTrue(is_coreedge_enabled())
			with self.assertRaises(frappe.PermissionError):
				require_vetedge_access()

	def test_white_label_forces_coreedge_required_and_fails_closed(self):
		# 4. edge_platform_mode = white_label forces CoreEdge required and fails closed if CoreEdge is missing.
		frappe.conf.edge_platform_mode = "white_label"
		with patch("vetedge.coreedge_adapter.is_coreedge_available", return_value=False):
			self.assertTrue(is_coreedge_enabled())
			with self.assertRaises(frappe.PermissionError):
				require_vetedge_access()

	def test_edge_platform_product_configuration_and_default(self):
		# 5. edge_platform_product configures the active product app name and defaults to "VetEdge" when unset/blank.
		self.assertEqual(get_vetedge_product_app(), "VetEdge")
		
		frappe.conf.edge_platform_product = "CustomApp"
		self.assertEqual(get_vetedge_product_app(), "CustomApp")
		
		frappe.conf.edge_platform_product = ""
		self.assertEqual(get_vetedge_product_app(), "VetEdge")

	def test_veterinary_settings_ignored_for_authority(self):
		# 6. Veterinary Settings database fields are no longer used for deployment authority.
		frappe.conf.edge_platform_mode = "standalone"
		
		def mock_get_single_value(doctype, field):
			if doctype == "Veterinary Settings":
				return {
					"deployment_mode": "Hosted Platform",
					"enable_coreedge_platform": 1,
					"fail_closed_when_coreedge_missing": 1,
					"coreedge_product_app": "PlatformApp"
				}.get(field)
			return None

		with patch("frappe.db.get_single_value", side_effect=mock_get_single_value):
			with patch("vetedge.coreedge_adapter.is_coreedge_available", return_value=False):
				self.assertFalse(is_coreedge_enabled())
				self.assertEqual(get_vetedge_product_app(), "VetEdge")  # Defaults to VetEdge, ignoring the DB PlatformApp
				require_vetedge_access()  # Should not raise exception because authority is read from frappe.conf

	def test_sidebar_links_hidden_in_standalone_mode(self):
		# 7. CoreEdge Platform sidebar/workspace links are hidden in standalone mode.
		frappe.conf.edge_platform_mode = "standalone"
		with patch("vetedge.coreedge_adapter.is_coreedge_available", return_value=True):
			self.assertFalse(should_show_coreedge_controls())
			
			sidebar_items = [
				{"label": "Veterinary Patient", "link_to": "Veterinary Patient", "type": "Link"},
				{"label": "Platform Settings", "link_to": "CoreEdge Settings", "type": "Link"},
				{"label": "Product Activation", "link_to": "CoreEdge Product Activation", "type": "Link"}
			]
			visible_items = get_visible_vetedge_sidebar_items(sidebar_items)
			labels = [item["label"] for item in visible_items]
			self.assertIn("Veterinary Patient", labels)
			self.assertNotIn("Platform Settings", labels)
			self.assertNotIn("Product Activation", labels)

	def test_sidebar_links_visible_when_required_and_installed(self):
		# 8. CoreEdge Platform links are visible when CoreEdge is installed and required.
		frappe.conf.edge_platform_mode = "shared_hosted"
		with patch("vetedge.coreedge_adapter.is_coreedge_available", return_value=True):
			self.assertTrue(should_show_coreedge_controls())
			
			sidebar_items = [
				{"label": "Veterinary Patient", "link_to": "Veterinary Patient", "type": "Link"},
				{"label": "Platform Settings", "link_to": "CoreEdge Settings", "type": "Link"},
				{"label": "Product Activation", "link_to": "CoreEdge Product Activation", "type": "Link"}
			]
			visible_items = get_visible_vetedge_sidebar_items(sidebar_items)
			labels = [item["label"] for item in visible_items]
			self.assertIn("Veterinary Patient", labels)
			self.assertIn("Platform Settings", labels)
			self.assertIn("Product Activation", labels)

	def test_no_workflow_gating_introduced(self):
		# 9. No clinical or operational workflow gating is introduced by this phase.
		frappe.conf.edge_platform_mode = "standalone"
		with patch("vetedge.coreedge_adapter.is_coreedge_available", return_value=False):
			self.assertTrue(has_vetedge_access())
			require_vetedge_access()

	def test_lazy_imports_and_filtering_no_side_effects(self):
		self.assertTrue(callable(is_coreedge_available))
		self.assertTrue(callable(get_current_vetedge_context))

		settings_items = [
			{"label": "Veterinary Settings", "name": "Veterinary Settings"},
			{"label": "Cost Center", "name": "Cost Center"}
		]
		visible_settings = get_visible_vetedge_settings_items(settings_items)
		self.assertEqual(len(visible_settings), 2)

	def test_unsupported_edge_platform_mode_fails_safe_to_required(self):
		frappe.conf.edge_platform_mode = "unsupported_mode_value"
		with patch("vetedge.coreedge_adapter.is_coreedge_available", return_value=False):
			self.assertTrue(is_coreedge_enabled())
			self.assertTrue(should_fail_closed_when_coreedge_missing())
			with self.assertRaises(frappe.PermissionError):
				require_vetedge_access()

	def test_filter_bootinfo_branding_overrides(self):
		# Setup bootinfo
		bootinfo = frappe._dict({
			"workspace_sidebar_item": {
				"vetedge": {
					"label": "VetEdge",
					"items": []
				}
			},
			"desktop_icons": [
				{
					"app": "vetedge",
					"name": "VetEdge",
					"label": "VetEdge",
					"link_type": "Workspace Sidebar",
					"link_to": "VetEdge"
				}
			],
			"app_data": [
				{
					"app_name": "vetedge",
					"app_title": "VetEdge",
					"app_logo_url": "/old-logo.png"
				}
			],
			"navbar_settings": frappe._dict({
				"app_logo": "/old-logo.png"
			})
		})

		mock_branding = {
			"enabled": 1,
			"brand_name": "Branded Clinic",
			"app_title": "Branded Desk App",
			"module_label": "Branded Veterinary",
			"logo": "/branded-logo.png"
		}

		with patch("vetedge.services.branding.get_branding", return_value=mock_branding):
			filter_bootinfo_for_coreedge_platform(bootinfo)

		# 1. Sidebar label overridden
		self.assertEqual(bootinfo.workspace_sidebar_item["vetedge"]["label"], "Branded Veterinary")

		# 2. Top-level bootinfo app_title and logo overridden
		self.assertEqual(bootinfo.app_title, "Branded Desk App")
		self.assertEqual(bootinfo.app_logo_url, "/branded-logo.png")

		# 3. Navbar settings logo overridden
		self.assertEqual(bootinfo.navbar_settings.app_logo, "/branded-logo.png")

		# 4. App data title and logo overridden
		self.assertEqual(bootinfo.app_data[0]["app_title"], "Branded Desk App")
		self.assertEqual(bootinfo.app_data[0]["app_logo_url"], "/branded-logo.png")

		# 5. Desktop icon link overridden to supported Desk route
		self.assertEqual(bootinfo.desktop_icons[0]["link_type"], "Workspace Sidebar")
		self.assertEqual(bootinfo.desktop_icons[0]["link"], "")
		self.assertEqual(bootinfo.desktop_icons[0]["link_to"], "VetEdge")
		self.assertNotEqual(bootinfo.desktop_icons[0]["link"], "/desk/veterinary-patient")
		self.assertEqual(bootinfo.app_data[0]["route"], "/app/vetedge")

	def test_filter_bootinfo_replaces_stale_autogenerated_sidebar_keys(self):
		stale_sidebar = {
			"label": "Veterinary",
			"items": [
				{"label": "Veterinary Patient", "link_to": "Veterinary Patient", "link_type": "DocType", "type": "Link"}
			],
		}
		canonical_sidebar = {
			"label": "Veterinary",
			"items": [
				{"label": "Executive Dashboard", "link_to": "vetedge-executive-dashboard", "link_type": "Page", "type": "Link"}
			],
			"app": "vetedge",
			"module": "Veterinary",
		}
		bootinfo = frappe._dict({
			"workspace_sidebar_item": {
				"vetedge": stale_sidebar.copy(),
				"veterinary": stale_sidebar.copy(),
			},
			"desktop_icons": [],
			"app_data": [],
		})

		with patch("vetedge.coreedge_adapter.get_canonical_vetedge_sidebar_for_boot", return_value=canonical_sidebar):
			filter_bootinfo_for_coreedge_platform(bootinfo)

		for key in ("vetedge", "veterinary"):
			first = bootinfo.workspace_sidebar_item[key]["items"][0]
			self.assertEqual(first["label"], "Executive Dashboard")
			self.assertEqual(first["link_to"], "vetedge-executive-dashboard")
			self.assertNotEqual(first["link_to"], "Veterinary Patient")
