from __future__ import annotations

import json
import unittest
from pathlib import Path
from unittest.mock import patch

import frappe
from edgesuite_ui.api.product_context import get_product_context, switch_product

from vetedge.api.product_context import get_product_availability


class TestVetEdgeProductAppContext(unittest.TestCase):
	def app_path(self, *parts: str) -> Path:
		return Path(frappe.get_app_path("vetedge", *parts))

	def test_administrator_receives_veterinary_descriptor_when_available(self):
		original_user = frappe.session.user
		try:
			frappe.session.user = "Administrator"
			with patch("vetedge.api.product_context.has_vetedge_access", return_value=True):
				product = get_product_availability()
		finally:
			frappe.session.user = original_user

		self.assertEqual(product["key"], "vetedge")
		self.assertEqual(product["label"], "Veterinary")
		self.assertEqual(product["home_route"], "/app/vetedge")
		self.assertIn("/app/veterinary-*", product["route_patterns"])

	def test_stable_veterinary_home_page_is_source_controlled(self):
		page_root = self.app_path("veterinary", "page", "vetedge")
		page = json.loads((page_root / "vetedge.json").read_text(encoding="utf-8"))
		script = (page_root / "vetedge.js").read_text(encoding="utf-8")

		self.assertEqual(page["name"], "vetedge")
		self.assertEqual(page["module"], "Veterinary")
		self.assertEqual(page["title"], "Veterinary Home")
		self.assertIn('frappe.pages["vetedge"]', script)
		self.assertIn('const target = "vetedge-document-workspace"', script)
		self.assertIn("frappe.set_route(target)", script)

	def test_guest_and_website_users_are_not_available_products(self):
		original_user = frappe.session.user
		try:
			frappe.session.user = "Guest"
			self.assertIsNone(get_product_availability())

			frappe.session.user = "owner@example.com"
			with patch("frappe.db.get_value", return_value="Website User"):
				self.assertIsNone(get_product_availability())
		finally:
			frappe.session.user = original_user

	def test_platform_access_decision_controls_availability(self):
		original_user = frappe.session.user
		try:
			frappe.session.user = "doctor@example.com"
			with (
				patch("frappe.db.get_value", return_value="System User"),
				patch("vetedge.api.product_context.has_vetedge_access", return_value=False),
			):
				self.assertIsNone(get_product_availability())
		finally:
			frappe.session.user = original_user

	def test_shared_context_aggregates_only_currently_available_veterinary(self):
		original_user = frappe.session.user
		try:
			frappe.session.user = "Administrator"
			with patch("vetedge.api.product_context.has_vetedge_access", return_value=True):
				context = get_product_context()
			self.assertIn(
				"vetedge",
				{product["key"] for product in context["available_products"]},
			)

			with patch("vetedge.api.product_context.has_vetedge_access", return_value=False):
				context = get_product_context()
				self.assertNotIn(
					"vetedge",
					{product["key"] for product in context["available_products"]},
				)
				with self.assertRaises(frappe.PermissionError):
					switch_product("vetedge")
		finally:
			frappe.session.user = original_user

	def test_provider_does_not_mutate_clinical_or_accounting_documents(self):
		source = self.app_path("api", "product_context.py").read_text().lower()
		for forbidden in (
			"doc.save(",
			"doc.submit(",
			"frappe.db.set_value",
			"sales invoice",
			"payment entry",
			"stock entry",
		):
			self.assertNotIn(forbidden, source)
