# -*- coding: utf-8 -*-
from __future__ import annotations

import unittest
from unittest.mock import patch, MagicMock
import frappe
from vetedge.services.branding import (
	get_branding,
	get_brand_name,
	get_company_name,
	get_short_name,
	get_module_label,
	get_app_title,
	hide_source_product_name,
	replace_brand_tokens,
	get_distribution_profile
)

class TestVetEdgeBranding(unittest.TestCase):
	def setUp(self) -> None:
		self.orig_conf = dict(frappe.conf)
		# Clear any custom branding site_config settings
		branding_keys = [
			"vetedge_white_label_enabled",
			"vetedge_brand_name",
			"vetedge_company_name",
			"vetedge_short_name",
			"vetedge_module_label",
			"vetedge_app_title",
			"vetedge_logo",
			"vetedge_favicon",
			"vetedge_primary_color",
			"vetedge_support_email",
			"vetedge_support_phone",
			"vetedge_hide_vetedge_name"
		]
		for key in branding_keys:
			if key in frappe.conf:
				del frappe.conf[key]

		self.orig_web_settings = None
		if frappe.db.exists("DocType", "Website Settings"):
			self.orig_web_settings = frappe.db.get_value("Website Settings", "Website Settings", ["app_name", "footer_powered"], as_dict=True)

	def tearDown(self) -> None:
		frappe.conf.clear()
		frappe.conf.update(self.orig_conf)
		if self.orig_web_settings and frappe.db.exists("DocType", "Website Settings"):
			frappe.db.set_value("Website Settings", "Website Settings", "app_name", self.orig_web_settings.app_name)
			frappe.db.set_value("Website Settings", "Website Settings", "footer_powered", self.orig_web_settings.footer_powered)
			frappe.db.commit()

	def test_branding_fallback_to_defaults(self) -> None:
		# Falls back to safe defaults when no other configurations exist
		res = get_branding()
		self.assertEqual(res["enabled"], 0)
		self.assertEqual(res["brand_name"], "VetEdge")
		self.assertEqual(res["module_label"], "Veterinary")
		self.assertEqual(res["source"], "default")

		# Helper getters
		self.assertEqual(get_brand_name(), "VetEdge")
		self.assertEqual(get_company_name(), "VetEdge")
		self.assertEqual(get_short_name(), "VetEdge")
		self.assertEqual(get_module_label(), "Veterinary")
		self.assertEqual(get_app_title(), "VetEdge")
		self.assertFalse(hide_source_product_name())

	def test_distribution_resolver(self) -> None:
		# Test profile resolution defaults to vetedge upstream
		profile = get_distribution_profile()
		self.assertEqual(profile["app_title"], "VetEdge")
		self.assertEqual(profile["brand_name"], "VetEdge")

		# Test site_config override works
		frappe.conf.edge_distribution = "veterinary"
		profile = get_distribution_profile()
		self.assertEqual(profile["app_title"], "Veterinary")
		self.assertEqual(profile["brand_name"], "Veterinary")

		# Cleanup site config override
		frappe.conf.edge_distribution = None

	def test_branding_site_config_fallback(self) -> None:
		# Falls back to site_config when CoreEdge is missing/disabled
		frappe.conf.vetedge_white_label_enabled = 1
		frappe.conf.vetedge_brand_name = "My Site Config Brand"
		frappe.conf.vetedge_module_label = "Special Vet Care"
		frappe.conf.vetedge_hide_vetedge_name = "1"

		with patch("vetedge.coreedge_adapter.is_coreedge_available", return_value=False):
			res = get_branding()
			self.assertEqual(res["enabled"], 1)
			self.assertEqual(res["brand_name"], "My Site Config Brand")
			self.assertEqual(res["module_label"], "Special Vet Care")
			self.assertEqual(res["hide_source_product_name"], 1)
			self.assertEqual(res["source"], "site_config")

	def test_branding_resolves_coreedge_active(self) -> None:
		# Resolves CoreEdge branding when CoreEdge exists and has active profile
		mock_ce_payload = {
			"enabled": True,
			"brand_name": "CoreEdge Clinic Brand",
			"company_name": "CoreEdge Clinic Company Ltd",
			"short_name": "CE Clinic",
			"module_label": "Pet Health",
			"app_title": "CE Clinic App",
			"logo": "/files/logo.png",
			"favicon": "/files/favicon.ico",
			"primary_color": "#ff0000",
			"support_email": "ce@example.com",
			"support_phone": "123-456",
			"hide_source_product_name": True,
			"source": "coreedge"
		}

		# Setup mocks
		with patch("vetedge.coreedge_adapter.is_coreedge_available", return_value=True), \
			patch("vetedge.coreedge_adapter.is_coreedge_enabled", return_value=True), \
			patch("coreedge.services.branding.get_product_branding", return_value=mock_ce_payload):
			
			res = get_branding()
			self.assertEqual(res["enabled"], 1)
			self.assertEqual(res["brand_name"], "CoreEdge Clinic Brand")
			self.assertEqual(res["company_name"], "CoreEdge Clinic Company Ltd")
			self.assertEqual(res["short_name"], "CE Clinic")
			self.assertEqual(res["module_label"], "Pet Health")
			self.assertEqual(res["hide_source_product_name"], 1)
			self.assertEqual(res["source"], "coreedge")

	def test_branding_coreedge_disabled_falls_back_to_site_config(self) -> None:
		# CoreEdge profile has enabled=False, should fallback to site_config
		mock_ce_payload = {
			"enabled": False,
			"brand_name": "",
			"source": "coreedge"
		}

		frappe.conf.vetedge_white_label_enabled = 1
		frappe.conf.vetedge_brand_name = "Site Config Fallback"

		with patch("vetedge.coreedge_adapter.is_coreedge_available", return_value=True), \
			patch("vetedge.coreedge_adapter.is_coreedge_enabled", return_value=True), \
			patch("coreedge.services.branding.get_product_branding", return_value=mock_ce_payload):
			
			res = get_branding()
			self.assertEqual(res["enabled"], 1)
			self.assertEqual(res["brand_name"], "Site Config Fallback")
			self.assertEqual(res["source"], "site_config")

	def test_branding_failure_does_not_break_vetedge(self) -> None:
		# If CoreEdge service throws an error, fallback to site_config or defaults gracefully
		frappe.conf.vetedge_white_label_enabled = 1
		frappe.conf.vetedge_brand_name = "Safe Fallback"

		with patch("vetedge.coreedge_adapter.is_coreedge_available", return_value=True), \
			patch("vetedge.coreedge_adapter.is_coreedge_enabled", return_value=True), \
			patch("coreedge.services.branding.get_product_branding", side_effect=Exception("Database connection error")):
			
			res = get_branding()
			self.assertEqual(res["enabled"], 1)
			self.assertEqual(res["brand_name"], "Safe Fallback")
			self.assertEqual(res["source"], "site_config")

	def test_replace_brand_tokens(self) -> None:
		# Replace brand tokens "VetEdge" and "VETEDGE", do not replace lowercase technical "vetedge"
		with patch("vetedge.services.branding.get_brand_name", return_value="M&G Vet Home"):
			res1 = replace_brand_tokens("Welcome to VetEdge clinic system.")
			self.assertEqual(res1, "Welcome to M&G Vet Home clinic system.")

			res2 = replace_brand_tokens("This is VETEDGE platform.")
			self.assertEqual(res2, "This is M&G VET HOME platform.")

			res3 = replace_brand_tokens("import vetedge.services.branding; path: /apps/vetedge/api")
			self.assertEqual(res3, "import vetedge.services.branding; path: /apps/vetedge/api")
			
			# Test non-string input
			self.assertEqual(replace_brand_tokens(123), 123)
			self.assertIsNone(replace_brand_tokens(None))

	def test_patch_normalizes_stale_values_when_branding_inactive(self) -> None:
		# Branding is inactive. Website settings with stale "Veterinary" should be normalized back to VetEdge.
		frappe.db.set_value("Website Settings", "Website Settings", "app_name", "Veterinary")
		frappe.db.set_value("Website Settings", "Website Settings", "footer_powered", "Veterinary")
		frappe.db.commit()

		from vetedge.patches.normalize_website_settings_branding import execute as patch_execute
		patch_execute()

		app_name, footer = frappe.db.get_value("Website Settings", "Website Settings", ["app_name", "footer_powered"])
		self.assertEqual(app_name, "VetEdge")
		self.assertEqual(footer, "VetEdge")

	def test_patch_preserves_branding_when_active(self) -> None:
		# Active site_config branding. Patch should not touch website settings.
		frappe.conf.vetedge_white_label_enabled = 1
		frappe.conf.vetedge_brand_name = "Tenant Brand Name"

		frappe.db.set_value("Website Settings", "Website Settings", "app_name", "Tenant Brand Name")
		frappe.db.set_value("Website Settings", "Website Settings", "footer_powered", "Tenant Brand Name")
		frappe.db.commit()

		from vetedge.patches.normalize_website_settings_branding import execute as patch_execute
		patch_execute()

		app_name, footer = frappe.db.get_value("Website Settings", "Website Settings", ["app_name", "footer_powered"])
		self.assertEqual(app_name, "Tenant Brand Name")
		self.assertEqual(footer, "Tenant Brand Name")

	def test_coreedge_draft_profile_ignored(self) -> None:
		# CoreEdge profile exists but has enabled=False (Draft)
		mock_ce_payload = {
			"enabled": False,
			"brand_name": "Draft Brand",
			"source": "coreedge"
		}
		with patch("vetedge.coreedge_adapter.is_coreedge_available", return_value=True), \
			patch("vetedge.coreedge_adapter.is_coreedge_enabled", return_value=True), \
			patch("coreedge.services.branding.get_product_branding", return_value=mock_ce_payload):
			
			res = get_branding()
			# Falls back to default since ce is draft and site_config is empty
			self.assertEqual(res["enabled"], 0)
			self.assertEqual(res["brand_name"], "VetEdge")

	def test_coreedge_profile_ignored_when_disabled(self) -> None:
		# Profile is active, but CoreEdge app/feature is disabled on site
		mock_ce_payload = {
			"enabled": True,
			"brand_name": "Active Brand",
			"source": "coreedge"
		}
		with patch("vetedge.coreedge_adapter.is_coreedge_available", return_value=True), \
			patch("vetedge.coreedge_adapter.is_coreedge_enabled", return_value=False), \
			patch("coreedge.services.branding.get_product_branding", return_value=mock_ce_payload):
			
			res = get_branding()
			self.assertEqual(res["enabled"], 0)
			self.assertEqual(res["brand_name"], "VetEdge")

	def test_branding_never_breaks_workspace_sidebar_identity(self) -> None:
		# Verify that dynamic branding applies to labels but never renames the workspace key
		from vetedge.coreedge_adapter import filter_bootinfo_for_coreedge_platform
		
		# Inactive branding:
		bootinfo = frappe._dict({
			"workspace_sidebar_item": {
				"vetedge": {
					"label": "Old Label",
					"items": []
				}
			}
		})
		filter_bootinfo_for_coreedge_platform(bootinfo)
		self.assertIn("vetedge", bootinfo.workspace_sidebar_item)
		self.assertIn("veterinary", bootinfo.workspace_sidebar_item)
		self.assertEqual(bootinfo.workspace_sidebar_item["vetedge"]["label"], "Veterinary")
		self.assertEqual(bootinfo.workspace_sidebar_item["veterinary"]["label"], "Veterinary")

		# Active site_config branding:
		frappe.conf.vetedge_white_label_enabled = 1
		frappe.conf.vetedge_brand_name = "Tenant App"
		frappe.conf.vetedge_module_label = "Tenant Vet Center"

		bootinfo = frappe._dict({
			"workspace_sidebar_item": {
				"vetedge": {
					"label": "Old Label",
					"items": []
				}
			}
		})
		filter_bootinfo_for_coreedge_platform(bootinfo)
		self.assertIn("vetedge", bootinfo.workspace_sidebar_item)
		self.assertIn("veterinary", bootinfo.workspace_sidebar_item)
		self.assertEqual(bootinfo.workspace_sidebar_item["vetedge"]["label"], "Tenant Vet Center")
		self.assertEqual(bootinfo.workspace_sidebar_item["veterinary"]["label"], "Tenant Vet Center")
