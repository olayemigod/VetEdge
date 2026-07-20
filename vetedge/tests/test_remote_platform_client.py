from __future__ import annotations

import time
import unittest
from unittest.mock import patch

import frappe
import requests

import vetedge.platform_client as client
from vetedge.services.platform_access import require_vetedge_platform_access


class _Response:
	def __init__(self, status_code=200, body=None):
		self.status_code = status_code
		self._body = body or {}

	def json(self):
		return self._body


class TestRemotePlatformClient(unittest.TestCase):
	def setUp(self):
		self.original_conf = dict(frappe.conf)
		for key in (
			"coreedge_authority_mode",
			"coreedge_remote_required",
			"coreedge_service_url",
			"coreedge_api_key",
			"coreedge_api_secret",
			"coreedge_site_identifier",
			"coreedge_remote_timeout_seconds",
			"coreedge_allow_insecure_http",
			"edge_platform_product",
			"host_name",
			"developer_mode",
		):
			frappe.conf.pop(key, None)

	def tearDown(self):
		frappe.conf.clear()
		frappe.conf.update(self.original_conf)

	def _configure_remote(self):
		frappe.conf.coreedge_authority_mode = "remote"
		frappe.conf.coreedge_service_url = "https://platform.example.com"
		frappe.conf.coreedge_api_key = "api-key"
		frappe.conf.coreedge_api_secret = "api-secret"
		frappe.conf.coreedge_site_identifier = "vet.example.com"
		frappe.conf.edge_platform_product = "VetEdge"

	def _gateway_response(self, *, allowed=True, site="vet.example.com", product="VetEdge"):
		return {
			"api_version": "v1",
			"service": "CoreEdge Service Gateway",
			"server_time": "2026-07-20 12:00:00",
			"request_id": "request-001",
			"client": {
				"client_id": "vet-example",
				"client_name": "Vet Example",
				"tenant": "Tenant A",
				"product_app": product,
				"site_identifier": site,
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
				"tenant": "Tenant A",
				"product_app": product,
				"tenant_status": "Active" if allowed else "Suspended",
				"product_activation_status": "Active",
				"effective_product_status": "Active",
				"compliance_status": "Not Evaluated",
				"user_compliance_evaluated": False,
			},
			"cache_policy": {
				"allowed_ttl_seconds": 60,
				"blocked_ttl_seconds": 15,
				"fail_closed": True,
			},
			"heartbeat_interval_seconds": 300,
		}

	def test_default_authority_remains_legacy_for_migration(self):
		self.assertEqual(client.get_platform_authority_mode(), "legacy_auto")
		self.assertFalse(client.is_remote_platform_requested())

	def test_remote_configuration_selects_remote_authority(self):
		frappe.conf.coreedge_service_url = "https://platform.example.com"
		self.assertEqual(client.get_platform_authority_mode(), "remote")

	def test_unknown_explicit_authority_fails_safe_to_remote(self):
		frappe.conf.coreedge_authority_mode = "disabled"
		self.assertEqual(client.get_platform_authority_mode(), "remote")

	def test_http_requires_explicit_developer_override(self):
		self._configure_remote()
		frappe.conf.coreedge_service_url = "http://coreedge.local:8000"
		with self.assertRaises(client.RemotePlatformConfigurationError):
			client.get_remote_platform_config()
		frappe.conf.developer_mode = 1
		frappe.conf.coreedge_allow_insecure_http = 1
		config = client.get_remote_platform_config()
		self.assertEqual(config["service_url"], "http://coreedge.local:8000")

	def test_first_call_uses_handshake_and_never_sends_tenant_or_product(self):
		self._configure_remote()
		response = _Response(body={"message": self._gateway_response()})
		cache_writes = []
		with (
			patch("vetedge.platform_client.requests.post", return_value=response) as post,
			patch("vetedge.platform_client._cache_get", return_value=None),
			patch("vetedge.platform_client._cache_set", side_effect=lambda *args: cache_writes.append(args)),
			patch("vetedge.platform_client._cache_delete"),
		):
			result = client.get_remote_access_response(
				action="create_consultation",
				reference_doctype="Veterinary Consultation",
				reference_name="CONS-001",
			)
		self.assertTrue(result["access"]["allowed"])
		url = post.call_args.args[0]
		kwargs = post.call_args.kwargs
		self.assertTrue(url.endswith("/api/method/coreedge.api.v1.service_gateway.handshake"))
		self.assertEqual(kwargs["headers"]["Authorization"], "token api-key:api-secret")
		self.assertFalse(kwargs["allow_redirects"])
		self.assertNotIn("tenant", kwargs["json"])
		self.assertNotIn("product_app", kwargs["json"])
		self.assertEqual(kwargs["json"]["site_identifier"], "vet.example.com")
		self.assertGreaterEqual(len(cache_writes), 2)

	def test_valid_cached_decision_avoids_network_call(self):
		self._configure_remote()
		entry = {
			"response": self._gateway_response(),
			"expires_at_epoch": time.time() + 30,
		}
		with (
			patch("vetedge.platform_client._cache_get", return_value=entry),
			patch("vetedge.platform_client.requests.post") as post,
		):
			result = client.get_remote_access_response()
		self.assertTrue(result["access"]["allowed"])
		post.assert_not_called()

	def test_force_refresh_can_use_still_valid_allowed_cache_on_network_failure(self):
		self._configure_remote()
		entry = {
			"response": self._gateway_response(),
			"expires_at_epoch": time.time() + 30,
		}
		with (
			patch("vetedge.platform_client._cache_get", side_effect=[entry, None]),
			patch(
				"vetedge.platform_client.requests.post",
				side_effect=requests.ConnectionError("offline"),
			),
		):
			result = client.get_remote_access_response(force_refresh=True)
		self.assertTrue(result["access"]["allowed"])

	def test_no_cache_network_failure_fails_closed(self):
		self._configure_remote()
		with (
			patch("vetedge.platform_client._cache_get", return_value=None),
			patch(
				"vetedge.platform_client.requests.post",
				side_effect=requests.ConnectionError("offline"),
			),
		):
			with self.assertRaises(client.RemotePlatformUnavailableError):
				client.get_remote_access_response()

	def test_redirect_is_rejected_without_following_it(self):
		self._configure_remote()
		with (
			patch("vetedge.platform_client._cache_get", return_value=None),
			patch("vetedge.platform_client.requests.post", return_value=_Response(status_code=302)),
		):
			with self.assertRaises(client.RemotePlatformProtocolError):
				client.get_remote_access_response()

	def test_response_site_and_product_binding_are_validated(self):
		self._configure_remote()
		for body in (
			self._gateway_response(site="other.example.com"),
			self._gateway_response(product="RetailEdge"),
		):
			with (
				patch("vetedge.platform_client._cache_get", return_value=None),
				patch(
					"vetedge.platform_client.requests.post",
					return_value=_Response(body={"message": body}),
				),
			):
				with self.assertRaises(client.RemotePlatformProtocolError):
					client.get_remote_access_response()

	def test_blocked_decision_raises_controlled_access_error(self):
		self._configure_remote()
		with patch(
			"vetedge.platform_client.get_remote_access_response",
			return_value=self._gateway_response(allowed=False),
		):
			with self.assertRaises(client.RemotePlatformAccessDenied) as context:
				client.require_remote_platform_access()
		self.assertEqual(context.exception.decision["primary_reason_code"], "TENANT_SUSPENDED")

	def test_cache_ttl_is_capped_at_five_minutes(self):
		body = self._gateway_response()
		body["cache_policy"]["allowed_ttl_seconds"] = 3600
		self.assertEqual(client._response_ttl(body), 300)

	def test_status_never_exposes_api_credentials(self):
		self._configure_remote()
		with patch("vetedge.platform_client._cache_get", return_value=None):
			status = client.get_remote_platform_status()
		serialized = str(status)
		self.assertNotIn("api-key", serialized)
		self.assertNotIn("api-secret", serialized)
		self.assertNotIn("api_key", status)
		self.assertNotIn("api_secret", status)

	def test_bootinfo_hides_local_coreedge_controls_in_remote_mode(self):
		self._configure_remote()
		bootinfo = frappe._dict(
			{
				"edgesuite_product_menu": {"show_coreedge_controls": True},
				"workspace_sidebar_item": {
					"vetedge": {
						"items": [
							{"label": "Platform Settings", "link_to": "CoreEdge Settings"},
							{"label": "Veterinary Patient", "link_to": "Veterinary Patient"},
						]
					}
				},
				"workspaces": {
					"pages": [
						{"name": "CoreEdge"},
						{"name": "Veterinary"},
					]
				},
			}
		)
		with patch("vetedge.platform_client._cache_get", return_value=None):
			client.extend_bootinfo_with_remote_platform(bootinfo)
		self.assertFalse(bootinfo.should_show_coreedge_controls)
		self.assertEqual(
			[item["label"] for item in bootinfo.workspace_sidebar_item["vetedge"]["items"]],
			["Veterinary Patient"],
		)
		self.assertEqual([page["name"] for page in bootinfo.workspaces["pages"]], ["Veterinary"])

	def test_platform_gate_routes_remote_without_local_fallback(self):
		self._configure_remote()
		with (
			patch("vetedge.platform_client.require_remote_platform_access") as remote_gate,
			patch("vetedge.coreedge_adapter.require_vetedge_access") as local_gate,
		):
			require_vetedge_platform_access(action="create_consultation")
		remote_gate.assert_called_once()
		local_gate.assert_not_called()

	def test_incomplete_remote_config_is_translated_to_permission_error(self):
		frappe.conf.coreedge_authority_mode = "remote"
		with self.assertRaises(frappe.PermissionError):
			require_vetedge_platform_access(action="create_consultation")

	def test_heartbeat_is_noop_in_legacy_mode(self):
		with patch("vetedge.platform_client.get_remote_access_response") as request:
			client.refresh_remote_platform_heartbeat()
		request.assert_not_called()
