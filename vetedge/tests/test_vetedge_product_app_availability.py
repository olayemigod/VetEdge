from __future__ import annotations

import unittest
from unittest.mock import patch

import frappe

from vetedge.api.product_context import PRODUCT_DESCRIPTOR, get_product_availability


class TestVetEdgeProductAppAvailability(unittest.TestCase):
	def test_descriptor_is_stable_and_current(self):
		self.assertEqual(PRODUCT_DESCRIPTOR["key"], "vetedge")
		self.assertEqual(PRODUCT_DESCRIPTOR["product_key"], "vetedge")
		self.assertEqual(PRODUCT_DESCRIPTOR["label"], "Veterinary")
		self.assertEqual(PRODUCT_DESCRIPTOR["home_route"], "/desk/vetedge")
		self.assertIn("/desk/veterinary-*", PRODUCT_DESCRIPTOR["route_patterns"])
		self.assertTrue(all(not pattern.startswith("/app/") for pattern in PRODUCT_DESCRIPTOR["route_patterns"]))

	def test_guest_is_not_available(self):
		original_user = frappe.session.user
		try:
			frappe.session.user = "Guest"
			self.assertIsNone(get_product_availability())
		finally:
			frappe.session.user = original_user

	def test_website_user_is_not_available(self):
		original_user = frappe.session.user
		try:
			frappe.session.user = "owner@example.com"
			with patch("vetedge.api.product_context.frappe.db.get_value", return_value="Website User"):
				self.assertIsNone(get_product_availability())
		finally:
			frappe.session.user = original_user

	def test_platform_access_controls_system_user_availability(self):
		original_user = frappe.session.user
		try:
			frappe.session.user = "doctor@example.com"
			with (
				patch("vetedge.api.product_context.frappe.db.get_value", return_value="System User"),
				patch("vetedge.api.product_context.has_vetedge_access", return_value=False),
			):
				self.assertIsNone(get_product_availability())
			with (
				patch("vetedge.api.product_context.frappe.db.get_value", return_value="System User"),
				patch("vetedge.api.product_context.has_vetedge_access", return_value=True),
			):
				self.assertEqual(get_product_availability()["key"], "vetedge")
		finally:
			frappe.session.user = original_user

	def test_provider_is_read_only(self):
		from pathlib import Path

		source = Path(frappe.get_app_path("vetedge", "api", "product_context.py")).read_text().lower()
		for forbidden in ("doc.save(", "doc.submit(", "frappe.db.set_value", "sales invoice", "payment entry", "stock entry"):
			self.assertNotIn(forbidden, source)


if __name__ == "__main__":
	unittest.main()
