from __future__ import annotations

import json
import unittest
from unittest.mock import patch

import frappe

from vetedge import platform_client
from vetedge.services.platform_diagnostics import (
	get_remote_platform_diagnostic,
	run_remote_platform_diagnostic,
)


class TestPlatformDiagnostics(unittest.TestCase):
	def setUp(self):
		self.original_conf = dict(frappe.conf)
		frappe.set_user("Administrator")
		for key in (
			"coreedge_authority_mode",
			"coreedge_remote_required",
			"coreedge_service_url",
			"coreedge_api_key",
			"coreedge_api_secret",
			"coreedge_site_identifier",
			"edge_platform_product",
			"coreedge_remote_timeout_seconds",
		):
			frappe.conf.pop(key, None)

	def tearDown(self):
		frappe.conf.clear()
		frappe.conf.update(self.original_conf)
		frappe.set_user("Administrator")

	def _configure_remote(self):
		frappe.conf.coreedge_authority_mode = "legacy_auto"
		frappe.conf.coreedge_service_url = "https://coreedge.example.com"
		frappe.conf.coreedge_api_key = "diagnostic-api-key"
		frappe.conf.coreedge_api_secret = "diagnostic-api-secret"
		frappe.conf.coreedge_site_identifier = "vet.example.com"
		frappe.conf.edge_platform_product = "VetEdge"
		frappe.conf.coreedge_remote_timeout_seconds = 7

	def _gateway_response(self, *, allowed: bool = True) -> dict:
		return {
			"api_version": "v1",
			"service": "CoreEdge Service Gateway",
			"server_time": "2026-07-20 20:00:00",
			"request_id": "diagnostic-request",
			"client": {
				"client_id": "vetedge-reference",
				"tenant": "Reference Tenant",
				"product_app": "VetEdge",
				"site_identifier": "vet.example.com",
				"deployment_mode": "Managed Cloud",
				"environment": "Development",
				"status": "Active",
			},
			"access": {
				"allowed": allowed,
				"enforcement_action": "Allow" if allowed else "Block",
				"primary_reason_code": "ALLOWED" if allowed else "TENANT_SUSPENDED",
				"reason_codes": ["ALLOWED"] if allowed else ["TENANT_SUSPENDED"],
				"reason": "Access is allowed." if allowed else "Tenant is suspended.",
				"tenant": "Reference Tenant",
				"product_app": "VetEdge",
				"tenant_status": "Active" if allowed else "Suspended",
				"product_activation_status": "Active",
				"effective_product_status": "Active",
				"access_scope": "Tenant Product Service",
				"evaluated_on": "2026-07-20 20:00:00",
			},
			"cache_policy": {
				"allowed_ttl_seconds": 60,
				"blocked_ttl_seconds": 15,
				"fail_closed": True,
			},
			"heartbeat_interval_seconds": 300,
		}

	def test_static_diagnostic_is_secret_free_and_does_not_change_authority(self):
		self._configure_remote()
		before = dict(frappe.conf)
		with patch("vetedge.services.platform_diagnostics.frappe.get_roles", return_value=["System Manager"]):
			result = get_remote_platform_diagnostic()

		serialized = json.dumps(result, default=str)
		self.assertTrue(result["configuration"]["configured"])
		self.assertEqual(result["configuration"]["authority_mode"], "legacy_auto")
		self.assertFalse(result["authority_change_performed"])
		self.assertFalse(result["local_coreedge_change_performed"])
		self.assertNotIn("diagnostic-api-key", serialized)
		self.assertNotIn("diagnostic-api-secret", serialized)
		self.assertEqual(dict(frappe.conf), before)

	def test_live_diagnostic_forces_fresh_handshake_without_cache_fallback(self):
		self._configure_remote()
		with (
			patch("vetedge.services.platform_diagnostics.frappe.get_roles", return_value=["VetEdge Administrator"]),
			patch(
				"vetedge.services.platform_diagnostics.platform_client.get_remote_access_response",
				return_value=self._gateway_response(),
			) as remote_call,
		):
			result = run_remote_platform_diagnostic()

		self.assertTrue(result["success"])
		self.assertEqual(result["status"], "Ready")
		self.assertEqual(result["live_response"]["client"]["tenant"], "Reference Tenant")
		remote_call.assert_called_once_with(
			force_refresh=True,
			force_handshake=True,
			allow_cached_on_error=False,
			action="operator_connection_diagnostic",
		)

	def test_live_diagnostic_reports_valid_blocked_decision(self):
		self._configure_remote()
		with (
			patch("vetedge.services.platform_diagnostics.frappe.get_roles", return_value=["System Manager"]),
			patch(
				"vetedge.services.platform_diagnostics.platform_client.get_remote_access_response",
				return_value=self._gateway_response(allowed=False),
			),
		):
			result = run_remote_platform_diagnostic()

		self.assertFalse(result["success"])
		self.assertEqual(result["status"], "Blocked")
		self.assertEqual(
			result["live_response"]["access"]["primary_reason_code"],
			"TENANT_SUSPENDED",
		)

	def test_authentication_failure_is_classified_without_credentials(self):
		self._configure_remote()
		with (
			patch("vetedge.services.platform_diagnostics.frappe.get_roles", return_value=["System Manager"]),
			patch(
				"vetedge.services.platform_diagnostics.platform_client.get_remote_access_response",
				side_effect=platform_client.RemotePlatformAuthenticationError(
					"The product site's platform credentials were rejected."
				),
			),
		):
			result = run_remote_platform_diagnostic()

		serialized = json.dumps(result, default=str)
		self.assertFalse(result["success"])
		self.assertEqual(result["status"], "Authentication Failed")
		self.assertEqual(result["error_code"], "AUTHENTICATION_ERROR")
		self.assertNotIn("diagnostic-api-key", serialized)
		self.assertNotIn("diagnostic-api-secret", serialized)

	def test_incomplete_configuration_does_not_attempt_network_call(self):
		frappe.conf.coreedge_service_url = "https://coreedge.example.com"
		with (
			patch("vetedge.services.platform_diagnostics.frappe.get_roles", return_value=["System Manager"]),
			patch(
				"vetedge.services.platform_diagnostics.platform_client.get_remote_access_response"
			) as remote_call,
		):
			result = run_remote_platform_diagnostic()

		self.assertFalse(result["success"])
		self.assertEqual(result["status"], "Misconfigured")
		self.assertIn("coreedge_api_key", result["configuration"]["missing_configuration"])
		remote_call.assert_not_called()

	def test_non_operator_is_rejected(self):
		self._configure_remote()
		with patch("vetedge.services.platform_diagnostics.frappe.get_roles", return_value=["VetEdge Doctor"]):
			with self.assertRaises(frappe.PermissionError):
				get_remote_platform_diagnostic()

	def test_live_response_does_not_echo_unexpected_secret_fields(self):
		self._configure_remote()
		response = self._gateway_response()
		response["api_key"] = "unexpected-key"
		response["api_secret"] = "unexpected-secret"
		response["client"]["credential"] = "unexpected-credential"
		with (
			patch("vetedge.services.platform_diagnostics.frappe.get_roles", return_value=["System Manager"]),
			patch(
				"vetedge.services.platform_diagnostics.platform_client.get_remote_access_response",
				return_value=response,
			),
		):
			result = run_remote_platform_diagnostic()

		serialized = json.dumps(result, default=str)
		self.assertNotIn("unexpected-key", serialized)
		self.assertNotIn("unexpected-secret", serialized)
		self.assertNotIn("unexpected-credential", serialized)
