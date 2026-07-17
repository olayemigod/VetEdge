from __future__ import annotations

import sys
import unittest
from unittest.mock import MagicMock, patch

import frappe

from vetedge.coreedge_adapter import (
	check_vetedge_feature_access,
	get_distribution,
	get_product_family,
	get_supported_feature_keys,
	get_vetedge_access_context,
	has_vetedge_access,
	require_vetedge_access,
	resolve_product_identity,
)


class TestVetEdgePlatformDistributionContext(unittest.TestCase):
	def setUp(self):
		self.orig_conf = dict(frappe.conf)
		for key in ("coreedge_required", "edge_platform_mode", "edge_platform_product"):
			if key in frappe.conf:
				del frappe.conf[key]

	def tearDown(self):
		frappe.conf.clear()
		frappe.conf.update(self.orig_conf)

	def test_vetedge_product_identity_is_distribution_aware(self):
		identity = resolve_product_identity(feature_key="Stock Expiry")

		self.assertEqual(get_product_family(), "veterinary_practice")
		self.assertEqual(get_distribution(), "vetedge")
		self.assertEqual(identity["product_family"], "veterinary_practice")
		self.assertEqual(identity["distribution"], "vetedge")
		self.assertEqual(identity["legacy_product_key"], "vetedge")
		self.assertEqual(identity["display_label"], "VetEdge")
		self.assertEqual(identity["feature_key"], "stock_expiry")

	def test_required_feature_keys_are_supported(self):
		keys = get_supported_feature_keys()

		self.assertIn("stock_expiry", keys)
		self.assertIn("financial_dashboard", keys)
		self.assertIn("hospitalisation_dashboard", keys)
		self.assertIn("appointment", keys)
		self.assertIn("consultation", keys)
		self.assertIn("billing", keys)
		self.assertIn("lab", keys)
		self.assertIn("vaccination", keys)
		self.assertIn("grooming", keys)
		self.assertIn("boarding", keys)

	def test_coreedge_access_request_includes_distribution_context_when_supported(self):
		frappe.conf.edge_platform_mode = "shared_hosted"
		mock_has_access = MagicMock(return_value=True)
		old_modules = self._install_mock_access_module(has_product_access=mock_has_access)
		try:
			with patch("vetedge.coreedge_adapter.is_coreedge_available", return_value=True):
				self.assertTrue(has_vetedge_access(tenant="Tenant A", user="test@example.com"))
		finally:
			self._restore_modules(old_modules)

		mock_has_access.assert_called_once()
		kwargs = mock_has_access.call_args.kwargs
		self.assertEqual(kwargs["product_family"], "veterinary_practice")
		self.assertEqual(kwargs["distribution"], "vetedge")
		self.assertEqual(kwargs["product_code"], "VetEdge")

	def test_legacy_coreedge_access_signature_still_falls_back(self):
		frappe.conf.edge_platform_mode = "shared_hosted"
		mock_has_access = MagicMock(side_effect=[TypeError("old signature"), True])
		old_modules = self._install_mock_access_module(has_product_access=mock_has_access)
		try:
			with patch("vetedge.coreedge_adapter.is_coreedge_available", return_value=True):
				self.assertTrue(has_vetedge_access(tenant="Tenant A", user="test@example.com"))
		finally:
			self._restore_modules(old_modules)

		self.assertEqual(mock_has_access.call_count, 2)
		self.assertIn("product_family", mock_has_access.call_args_list[0].kwargs)
		self.assertNotIn("product_family", mock_has_access.call_args_list[1].kwargs)

	def test_require_access_passes_distribution_context_when_supported(self):
		frappe.conf.edge_platform_mode = "shared_hosted"
		mock_require = MagicMock(return_value=True)
		old_modules = self._install_mock_access_module(require_product_access=mock_require)
		try:
			with patch("vetedge.coreedge_adapter.is_coreedge_available", return_value=True):
				require_vetedge_access(
					tenant="Tenant A",
					user="test@example.com",
					action="test_action",
					reference_doctype="Veterinary Patient",
					reference_name="VP-001",
				)
		finally:
			self._restore_modules(old_modules)

		kwargs = mock_require.call_args.kwargs
		self.assertEqual(kwargs["product_family"], "veterinary_practice")
		self.assertEqual(kwargs["distribution"], "vetedge")
		self.assertEqual(kwargs["source_doctype"], "Veterinary Patient")

	def test_access_context_fallback_includes_distribution_context(self):
		frappe.conf.edge_platform_mode = "standalone"
		with patch("vetedge.coreedge_adapter.is_coreedge_available", return_value=False):
			context = get_vetedge_access_context()

		self.assertTrue(context["allowed"])
		self.assertEqual(context["distribution_context"]["product_family"], "veterinary_practice")
		self.assertEqual(context["distribution_context"]["distribution"], "vetedge")

	def test_missing_coreedge_respects_fail_open_and_fail_closed_for_feature_access(self):
		frappe.conf.edge_platform_mode = "standalone"
		with patch("vetedge.coreedge_adapter.is_coreedge_available", return_value=False):
			result = check_vetedge_feature_access("stock_expiry")
		self.assertTrue(result["allowed"])
		self.assertEqual(result["distribution"], "vetedge")

		frappe.conf.edge_platform_mode = "shared_hosted"
		with patch("vetedge.coreedge_adapter.is_coreedge_available", return_value=False):
			result = check_vetedge_feature_access("stock_expiry")
		self.assertFalse(result["allowed"])
		self.assertEqual(result["primary_reason_code"], "PLATFORM_MISSING")

	def test_distribution_aware_feature_access_uses_coreedge_runtime_when_available(self):
		frappe.conf.edge_platform_mode = "shared_hosted"
		mock_check = MagicMock(
			return_value={
				"allowed": True,
				"access_result": "Allowed",
			}
		)
		old_modules = self._install_mock_runtime_module(check_feature_access=mock_check)
		try:
			with patch("vetedge.coreedge_adapter.is_coreedge_available", return_value=True):
				result = check_vetedge_feature_access("financial-dashboard", tenant="Tenant A", user="test@example.com")
		finally:
			self._restore_modules(old_modules)

		self.assertTrue(result["allowed"])
		self.assertEqual(result["feature_key"], "financial_dashboard")
		self.assertEqual(result["product_family"], "veterinary_practice")
		self.assertEqual(result["distribution"], "vetedge")
		kwargs = mock_check.call_args.kwargs
		self.assertEqual(kwargs["product_family"], "veterinary_practice")
		self.assertEqual(kwargs["distribution"], "vetedge")
		self.assertEqual(kwargs["feature_key"], "financial_dashboard")

	def test_dashboard_and_stock_feature_keys_can_be_requested(self):
		frappe.conf.edge_platform_mode = "standalone"
		with patch("vetedge.coreedge_adapter.is_coreedge_available", return_value=False):
			for feature_key in ("stock_expiry", "financial_dashboard", "hospitalisation_dashboard"):
				result = check_vetedge_feature_access(feature_key)
				self.assertTrue(result["allowed"])
				self.assertEqual(result["feature_key"], feature_key)
				self.assertEqual(result["product_family"], "veterinary_practice")
				self.assertEqual(result["distribution"], "vetedge")

	def _install_mock_access_module(self, **attrs):
		old_modules = self._remove_coreedge_modules()
		mock_access = MagicMock()
		for key, value in attrs.items():
			setattr(mock_access, key, value)
		sys.modules["coreedge"] = MagicMock()
		sys.modules["coreedge.adapters"] = MagicMock()
		sys.modules["coreedge.adapters.access"] = mock_access
		return old_modules

	def _install_mock_runtime_module(self, **attrs):
		old_modules = self._remove_coreedge_modules()
		mock_runtime = MagicMock()
		for key, value in attrs.items():
			setattr(mock_runtime, key, value)
		sys.modules["coreedge"] = MagicMock()
		sys.modules["coreedge.coreedge"] = MagicMock()
		sys.modules["coreedge.coreedge.runtime"] = mock_runtime
		return old_modules

	def _remove_coreedge_modules(self):
		old_modules = {}
		for key in list(sys.modules.keys()):
			if key.startswith("coreedge"):
				old_modules[key] = sys.modules[key]
				del sys.modules[key]
		return old_modules

	def _restore_modules(self, old_modules):
		for key in list(sys.modules.keys()):
			if key.startswith("coreedge"):
				del sys.modules[key]
		sys.modules.update(old_modules)


if __name__ == "__main__":
	unittest.main()
