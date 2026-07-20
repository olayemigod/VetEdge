from __future__ import annotations

import time

import frappe
from frappe import _

from vetedge import platform_client

_OPERATOR_ROLES = {"System Manager", "VetEdge Administrator"}


@frappe.whitelist()
def get_remote_platform_diagnostic() -> dict:
	"""Return a secret-free configuration and cache diagnostic without external I/O."""
	_assert_operator()
	return _build_static_diagnostic()


@frappe.whitelist(methods=["POST"])
def run_remote_platform_diagnostic() -> dict:
	"""Perform a fresh CoreEdge handshake without changing platform authority or deployment."""
	_assert_operator()
	result = _build_static_diagnostic()
	result["live_check_requested"] = True

	if not result["configuration"]["configured"]:
		result.update(
			{
				"status": "Misconfigured",
				"success": False,
				"message": _("Remote platform connection settings are incomplete or invalid."),
			}
		)
		return result

	started = time.perf_counter()
	try:
		response = platform_client.get_remote_access_response(
			force_refresh=True,
			force_handshake=True,
			allow_cached_on_error=False,
			action="operator_connection_diagnostic",
		)
	except platform_client.RemotePlatformConfigurationError as exc:
		_update_failure(result, "Misconfigured", "CONFIGURATION_ERROR", exc)
	except platform_client.RemotePlatformAuthenticationError as exc:
		_update_failure(result, "Authentication Failed", "AUTHENTICATION_ERROR", exc)
	except platform_client.RemotePlatformUnavailableError as exc:
		_update_failure(result, "Unavailable", "SERVICE_UNAVAILABLE", exc)
	except platform_client.RemotePlatformProtocolError as exc:
		_update_failure(result, "Contract Error", "PROTOCOL_ERROR", exc)
	except platform_client.RemotePlatformError as exc:
		_update_failure(result, "Failed", "REMOTE_PLATFORM_ERROR", exc)
	finally:
		result["duration_ms"] = round((time.perf_counter() - started) * 1000, 2)

	if not result.get("success"):
		return result

	live_response = _sanitize_gateway_response(response)
	allowed = bool((live_response.get("access") or {}).get("allowed"))
	result.update(
		{
			"status": "Ready" if allowed else "Blocked",
			"success": allowed,
			"message": (
				_("CoreEdge authenticated this VetEdge site and currently allows access.")
				if allowed
				else _("CoreEdge authenticated this VetEdge site but currently blocks access.")
			),
			"live_response": live_response,
		}
	)
	return result


def _build_static_diagnostic() -> dict:
	status = platform_client.get_remote_platform_status()
	try:
		config = platform_client.get_remote_platform_config(validate=False)
	except platform_client.RemotePlatformError:
		config = {}

	configured = bool(status.get("configured"))
	checks = [
		_check("service_url", bool(config.get("service_url")), _("CoreEdge service URL is valid.")),
		_check("api_key", bool(config.get("api_key")), _("CoreEdge API key is configured.")),
		_check("api_secret", bool(config.get("api_secret")), _("CoreEdge API secret is configured.")),
		_check(
			"site_identifier",
			bool(config.get("site_identifier")),
			_("Product-site identifier is configured."),
		),
		_check("product_app", bool(config.get("product_app")), _("Product app identity is configured.")),
	]
	return {
		"status": "Configured" if configured else "Misconfigured",
		"success": configured,
		"message": (
			_("Remote platform settings are ready for a live diagnostic.")
			if configured
			else _("Remote platform settings are incomplete or invalid.")
		),
		"live_check_requested": False,
		"authority_change_performed": False,
		"local_coreedge_change_performed": False,
		"configuration": {
			"authority_mode": status.get("authority_mode"),
			"remote_required": platform_client._conf_bool("coreedge_remote_required"),
			"remote_requested": bool(status.get("remote_requested")),
			"configured": configured,
			"service_host": status.get("service_host"),
			"site_identifier": status.get("site_identifier"),
			"product_app": status.get("product_app"),
			"timeout_seconds": config.get("timeout_seconds"),
			"missing_configuration": list(status.get("missing_configuration") or []),
			"configuration_error": status.get("configuration_error") or "",
		},
		"cache": {
			"available": bool(status.get("cached")),
			"allowed": status.get("allowed"),
			"primary_reason_code": status.get("primary_reason_code"),
			"expires_on": status.get("cache_expires_on"),
		},
		"checks": checks,
		"live_response": None,
		"duration_ms": None,
	}


def _sanitize_gateway_response(response: dict) -> dict:
	client = response.get("client") or {}
	access = response.get("access") or {}
	cache_policy = response.get("cache_policy") or {}
	return {
		"api_version": response.get("api_version"),
		"service": response.get("service"),
		"server_time": response.get("server_time"),
		"request_id": response.get("request_id"),
		"client": {
			"client_id": client.get("client_id"),
			"tenant": client.get("tenant"),
			"product_app": client.get("product_app"),
			"site_identifier": client.get("site_identifier"),
			"deployment_mode": client.get("deployment_mode"),
			"environment": client.get("environment"),
			"status": client.get("status"),
		},
		"access": {
			"allowed": bool(access.get("allowed")),
			"enforcement_action": access.get("enforcement_action"),
			"primary_reason_code": access.get("primary_reason_code"),
			"reason_codes": list(access.get("reason_codes") or []),
			"reason": access.get("reason"),
			"tenant_status": access.get("tenant_status"),
			"product_activation_status": access.get("product_activation_status"),
			"effective_product_status": access.get("effective_product_status"),
			"access_scope": access.get("access_scope"),
			"evaluated_on": access.get("evaluated_on"),
		},
		"cache_policy": {
			"allowed_ttl_seconds": cache_policy.get("allowed_ttl_seconds"),
			"blocked_ttl_seconds": cache_policy.get("blocked_ttl_seconds"),
			"fail_closed": bool(cache_policy.get("fail_closed")),
		},
		"heartbeat_interval_seconds": response.get("heartbeat_interval_seconds"),
	}


def _update_failure(result: dict, status: str, code: str, exc: Exception) -> None:
	result.update(
		{
			"status": status,
			"success": False,
			"message": str(exc),
			"error_code": code,
			"live_response": None,
		}
	)


def _check(key: str, passed: bool, message: str) -> dict:
	return {"key": key, "passed": bool(passed), "message": message}


def _assert_operator() -> None:
	user = frappe.session.user
	if not user or user == "Guest" or not _OPERATOR_ROLES.intersection(set(frappe.get_roles(user))):
		frappe.throw(
			_("Only authorised VetEdge operators may run platform connection diagnostics."),
			frappe.PermissionError,
		)
