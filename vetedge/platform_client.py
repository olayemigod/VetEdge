# -*- coding: utf-8 -*-
from __future__ import annotations

import hashlib
import json
import time
import uuid
from urllib.parse import urlsplit

import frappe
import requests
from frappe import _

from vetedge import __version__ as VETEDGE_VERSION

COREEDGE_GATEWAY_API_VERSION = "v1"
COREEDGE_GATEWAY_SERVICE = "CoreEdge Service Gateway"
COREEDGE_HANDSHAKE_METHOD = "coreedge.api.v1.service_gateway.handshake"
COREEDGE_ACCESS_METHOD = "coreedge.api.v1.service_gateway.check_runtime_access"

DEFAULT_TIMEOUT_SECONDS = 5
MAX_TIMEOUT_SECONDS = 30
MAX_CACHE_TTL_SECONDS = 300
DEFAULT_HEARTBEAT_SECONDS = 300

REMOTE_AUTHORITY_MODE = "remote"
LEGACY_AUTHORITY_MODE = "legacy_auto"
_ALLOWED_AUTHORITY_MODES = {REMOTE_AUTHORITY_MODE, LEGACY_AUTHORITY_MODE}
_REMOTE_CONFIG_KEYS = (
	"coreedge_service_url",
	"coreedge_api_key",
	"coreedge_api_secret",
	"coreedge_site_identifier",
)


class RemotePlatformError(Exception):
	"""Base error for the product-side CoreEdge service client."""


class RemotePlatformConfigurationError(RemotePlatformError):
	pass


class RemotePlatformAuthenticationError(RemotePlatformError):
	pass


class RemotePlatformUnavailableError(RemotePlatformError):
	pass


class RemotePlatformProtocolError(RemotePlatformError):
	pass


class RemotePlatformAccessDenied(RemotePlatformError):
	def __init__(self, decision: dict):
		self.decision = decision or {}
		message = self.decision.get("reason") or _("Platform access is not available for this site.")
		super().__init__(message)


def get_platform_authority_mode() -> str:
	"""Resolve operator-controlled platform authority without consulting a tenant-facing DocType.

	V3.0B is deliberately migration-safe. Existing sites remain on the legacy adapter until
	remote authority is explicitly selected or any remote connection setting is supplied.
	An unsupported explicit value fails safe to remote authority.
	"""
	raw_mode = _conf_text("coreedge_authority_mode")
	if raw_mode:
		mode = raw_mode.lower().replace("-", "_")
		if mode in _ALLOWED_AUTHORITY_MODES:
			return mode
		_log_warning(f"Unsupported coreedge_authority_mode '{raw_mode}'. Failing safe to remote authority.")
		return REMOTE_AUTHORITY_MODE

	if _conf_bool("coreedge_remote_required"):
		return REMOTE_AUTHORITY_MODE
	if any(_conf_text(key) for key in _REMOTE_CONFIG_KEYS):
		return REMOTE_AUTHORITY_MODE
	return LEGACY_AUTHORITY_MODE


def is_remote_platform_requested() -> bool:
	return get_platform_authority_mode() == REMOTE_AUTHORITY_MODE


def get_remote_platform_config(*, validate: bool = True) -> dict:
	service_url = _normalize_service_url(_conf_text("coreedge_service_url"), validate=validate)
	api_key = _conf_text("coreedge_api_key")
	api_secret = _conf_text("coreedge_api_secret")
	site_identifier = _resolve_site_identifier()
	timeout_seconds = _resolve_timeout_seconds()

	missing = []
	if not service_url:
		missing.append("coreedge_service_url")
	if not api_key:
		missing.append("coreedge_api_key")
	if not api_secret:
		missing.append("coreedge_api_secret")
	if not site_identifier:
		missing.append("coreedge_site_identifier")

	if validate and missing:
		raise RemotePlatformConfigurationError(
		_("Remote platform connection is incomplete. Missing operator configuration: {0}.").format(
			", ".join(missing)
		)
		)

	return {
		"authority_mode": get_platform_authority_mode(),
		"service_url": service_url,
		"api_key": api_key,
		"api_secret": api_secret,
		"site_identifier": site_identifier,
		"product_app": _conf_text("edge_platform_product") or "VetEdge",
		"timeout_seconds": timeout_seconds,
		"configured": not missing,
		"missing": missing,
	}


def get_remote_access_response(
	*,
	force_refresh: bool = False,
	force_handshake: bool = False,
	action: str | None = None,
	reference_doctype: str | None = None,
	reference_name: str | None = None,
) -> dict:
	"""Return a validated CoreEdge gateway response using a server-authoritative TTL cache."""
	config = get_remote_platform_config(validate=True)
	cache_key = _access_cache_key(config)
	cached_before = _get_valid_cache_entry(cache_key)
	if cached_before and not force_refresh:
		return cached_before["response"]

	request_id = _make_request_id(action)
	source_path = _build_source_path(action, reference_doctype, reference_name)
	handshake_key = _handshake_cache_key(config)
	use_handshake = force_handshake or not _get_valid_cache_entry(handshake_key)
	method = COREEDGE_HANDSHAKE_METHOD if use_handshake else COREEDGE_ACCESS_METHOD
	payload = {
		"site_identifier": config["site_identifier"],
		"request_id": request_id,
		"source_path": source_path,
	}
	if use_handshake:
		payload.update(
			{
				"app_version": VETEDGE_VERSION,
				"frappe_version": str(getattr(frappe, "__version__", "") or ""),
			}
		)

	try:
		response = _post_gateway(config, method, payload)
	except RemotePlatformError:
		if cached_before and bool((cached_before.get("response") or {}).get("access", {}).get("allowed")):
			return cached_before["response"]
		raise

	ttl_seconds = _select_response_ttl(response)
	if ttl_seconds > 0:
		_set_cache_entry(cache_key, response, ttl_seconds)

	if use_handshake:
		heartbeat_seconds = _bounded_int(
			response.get("heartbeat_interval_seconds"),
			default=DEFAULT_HEARTBEAT_SECONDS,
			minimum=60,
			maximum=86400,
		)
		_set_cache_entry(handshake_key, {"handshake_complete": True}, heartbeat_seconds)

	return response


def require_remote_platform_access(
	*,
	action: str | None = None,
	reference_doctype: str | None = None,
	reference_name: str | None = None,
) -> dict:
	response = get_remote_access_response(
		action=action,
		reference_doctype=reference_doctype,
		reference_name=reference_name,
	)
	decision = response.get("access") or {}
	if not bool(decision.get("allowed")):
		raise RemotePlatformAccessDenied(decision)
	return decision


def has_remote_platform_access() -> bool:
	try:
		response = get_remote_access_response()
		return bool((response.get("access") or {}).get("allowed"))
	 except RemotePlatformError:
		return False


def get_remote_access_context(*, refresh: bool = False) -> dict:
	response = get_remote_access_response(force_refresh=refresh)
	return {
		"client": response.get("client") or {},
		"access": response.get("access") or {},
		"cache_policy": response.get("cache_policy") or {},
		"heartbeat_interval_seconds": response.get("heartbeat_interval_seconds"),
		"server_time": response.get("server_time"),
		"request_id": response.get("request_id"),
	}


def get_remote_platform_status() -> dict:
	"""Return a boot-safe, secret-free status snapshot without making an HTTP request."""
	config_error = ""
	try:
		config = get_remote_platform_config(validate=False)
	except RemotePlatformError as exc:
		config = {
			"authority_mode": get_platform_authority_mode(),
			"service_url": "",
			"site_identifier": _resolve_site_identifier(),
			"product_app": _conf_text("edge_platform_product") or "VetEdge",
			"configured": False,
			"missing": [],
		}
		config_error = str(exc)

	status = {
		"authority_mode": config.get("authority_mode"),
		"remote_requested": is_remote_platform_requested(),
		"configured": bool(config.get("configured")),
		"service_host": _service_host(config.get("service_url")),
		"site_identifier": config.get("site_identifier"),
		"product_app": config.get("product_app"),
		"missing_configuration": list(config.get("missing") or []),
		"configuration_error": config_error,
		"cached": False,
		"allowed": None,
		"primary_reason_code": None,
		"cache_expires_on": None,
	}
	if not config.get("configured"):
		return status

	entry = _get_valid_cache_entry(_access_cache_key(config))
	if not entry:
		return status

	decision = (entry.get("response") or {}).get("access") or {}
	status.update(
		{
			"cached": True,
			"allowed": bool(decision.get("allowed")),
			"primary_reason_code": decision.get("primary_reason_code"),
			"cache_expires_on": entry.get("expires_on"),
		}
	)
	return status


def clear_remote_platform_cache() -> None:
	config = get_remote_platform_config(validate=False)
	if not config.get("service_url") or not config.get("site_identifier"):
		return
	_cache_delete(_access_cache_key(config))
	_cache_delete(_handshake_cache_key(config))


def refresh_remote_platform_heartbeat() -> None:
	"""Scheduler-safe heartbeat. Failures are logged without breaking the scheduler worker."""
	if not is_remote_platform_requested():
		return
	try:
		get_remote_access_response(force_refresh=True, force_handshake=True, action="scheduled_heartbeat")
	except RemotePlatformError as exc:
		_log_warning(f"Remote platform heartbeat failed: {exc.__class__.__name__}: {exc}")


def extend_bootinfo_with_remote_platform(bootinfo) -> None:
	"""Expose only a secret-free connection summary and hide local platform controls in remote mode."""
	status = get_remote_platform_status()
	bootinfo.edge_platform_authority = status["authority_mode"]
	bootinfo.edge_platform_connection = frappe._dict(status)
	if not status["remote_requested"]:
		return

	bootinfo.should_show_coreedge_controls = False
	menu = bootinfo.get("edgesuite_product_menu")
	if isinstance(menu, dict):
		menu["show_coreedge_controls"] = False
		menu["platform_authority"] = REMOTE_AUTHORITY_MODE
		menu["platform_connection"] = {
			"configured": status["configured"],
			"cached": status["cached"],
			"allowed": status["allowed"],
			"primary_reason_code": status["primary_reason_code"],
		}

	_sidebars = bootinfo.get("workspace_sidebar_item") or {}
	for key in ("vetedge", "veterinary"):
		if key in _sidebars:
			_sidebars[key]["items"] = _filter_local_platform_items(_sidebars[key].get("items") or [])

	workspaces = bootinfo.get("workspaces") or {}
	if isinstance(workspaces, dict) and "pages" in workspaces:
		workspaces["pages"] = [
			page
			for page in workspaces.get("pages") or []
			if not _is_local_platform_item(page.get("title") or page.get("name"), page.get("name"))
		]


def _post_gateway(config: dict, method: str, payload: dict) -> dict:
	url = f"{config['service_url']}/api/method/{method}"
	headers = {
		"Authorization": f"token {config['api_key']}:{config['api_secret']}",
		"Accept": "application/json",
		"Content-Type": "application/json",
		"User-Agent": f"VetEdge/{VETEDGE_VERSION} CoreEdge-Remote-Client/{COREEDGE_GATEWAY_API_VERSION}",
	}
	try:
		response = requests.post(
			url,
			headers=headers,
			json=payload,
			timeout=config["timeout_seconds"],
			allow_redirects=False,
		)
	except requests.RequestException as exc:
		raise RemotePlatformUnavailableError(_("The platform service could not be reached.")) from exc

	if 300 <= response.status_code < 400:
		raise RemotePlatformProtocolError(_("The platform service returned an unsafe redirect."))
	if response.status_code in {401, 403}:
		raise RemotePlatformAuthenticationError(_("The product site's platform credentials were rejected."))
	if response.status_code >= 400:
		raise RemotePlatformUnavailableError(
			_("The platform service returned HTTP status {0}.").format(response.status_code)
		)

	try:
		body = response.json()
	except ValueError as exc:
		raise RemotePlatformProtocolError(_("The platform service returned an invalid JSON response.")) from exc

	if isinstance(body, dict) and isinstance(body.get("message"), dict):
		body = body["message"]
	return _validate_gateway_response(body, config)


def _validate_gateway_response(body, config: dict) -> dict:
	if not isinstance(body, dict):
		raise RemotePlatformProtocolError(_("The platform response must be an object."))
	if body.get("api_version") != COREEDGE_GATEWAY_API_VERSION:
		raise RemotePlatformProtocolError(_("The platform API version is not supported."))
	if body.get("service") != COREEDGE_GATEWAY_SERVICE:
		raise RemotePlatformProtocolError(_("The response did not identify the expected platform service."))

	client = body.get("client")
	access = body.get("access")
	cache_policy = body.get("cache_policy")
	if not isinstance(client, dict) or not isinstance(access, dict) or not isinstance(cache_policy, dict):
		raise RemotePlatformProtocolError(_("The platform response is missing required contract sections."))
	if not bool(cache_policy.get("fail_closed")):
		raise RemotePlatformProtocolError(_("The platform response does not enforce the fail-closed contract."))

	expected_site = _normalize_site_identifier(config.get("site_identifier"))
	returned_site = _normalize_site_identifier(client.get("site_identifier"))
	if not expected_site or returned_site != expected_site:
		raise RemotePlatformProtocolError(_("The platform response is bound to a different product site."))

	expected_product = str(config.get("product_app") or "").strip().casefold()
	returned_product = str(client.get("product_app") or "").strip().casefold()
	access_product = str(access.get("product_app") or "").strip().casefold()
	if not expected_product or returned_product != expected_product or access_product != expected_product:
		raise RemotePlatformProtocolError(_("The platform response is bound to a different product app."))
	if access.get("tenant") != client.get("tenant"):
		raise RemotePlatformProtocolError(_("The platform access decision tenant does not match the client binding."))
	if not isinstance(access.get("allowed"), (bool, int)):
		raise RemotePlatformProtocolError(_("The platform access decision is missing a valid allowed flag."))

	return body


def _select_response_ttl(response: dict) -> int:
	decision = response.get("access") or {}
	policy = response.get("cache_policy") or {}
	fieldname = "allowed_ttl_seconds" if bool(decision.get("allowed")) else "blocked_ttl_seconds"
	return _bounded_int(policy.get(fieldname), default=0, minimum=0, maximum=MAX_CACHE_TTL_SECONDS)


def _normalize_service_url(value: str, *, validate: bool) -> str:
	value = (value or "").strip()
	if not value:
		return ""
	if "://" not in value:
		value = f"https://{value}"
	parsed = urlsplit(value)
	invalid = (
		parsed.scheme not in {"http", "https"}
		or not parsed.netloc
		or parsed.username
		or parsed.password
		or parsed.query
		or parsed.fragment
		or parsed.path not in {"", "/"}
	)
	if invalid:
		if validate:
			raise RemotePlatformConfigurationError(_("coreedge_service_url must be a valid HTTP or HTTPS root URL."))
		return ""
	if parsed.scheme == "http" and not (_conf_bool("developer_mode") and _conf_bool("coreedge_allow_insecure_http")):
		if validate:
			raise RemotePlatformConfigurationError(
				_("Remote platform connections require HTTPS outside an explicit developer-mode override.")
			)
		return ""
	return f"{parsed.scheme.lower()}://{parsed.netloc.lower()}"


def _resolve_site_identifier() -> str:
	configured = _conf_text("coreedge_site_identifier")
	if configured:
		return _normalize_site_identifier(configured)
	host_name = _conf_text("host_name")
	if host_name:
		return _normalize_site_identifier(host_name)
	try:
		return _normalize_site_identifier(getattr(frappe.local, "site", ""))
	except Exception:
		return ""


def _normalize_site_identifier(value) -> str:
	value = str(value or "").strip().lower()
	if not value:
		return ""
	if "://" in value:
		value = urlsplit(value).netloc
	else:
		value = value.split("/", 1)[0]
	return value.rstrip("/")


def _resolve_timeout_seconds() -> int:
	return _bounded_int(
		_conf_text("coreedge_remote_timeout_seconds"),
		default=DEFAULT_TIMEOUT_SECONDS,
		minimum=1,
		maximum=MAX_TIMEOUT_SECONDS,
	)


def _make_request_id(action: str | None) -> str:
	prefix = str(action or "vetedge").strip().lower().replace(" ", "-")[:30].strip("-") or "vetedge"
	return f"{prefix}-{uuid.uuid4().hex[:20]}"


def _build_source_path(action, reference_doctype, reference_name) -> str:
	parts = [str(value or "").strip() for value in (action, reference_doctype, reference_name)]
	return ":".join(part for part in parts if part)[:255]


def _access_cache_key(config: dict) -> str:
	return f"vetedge:coreedge-remote:v1:{_cache_identity(config)}:access"


def _handshake_cache_key(config: dict) -> str:
	return f"vetedge:coreedge-remote:v1:{_cache_identity(config)}:handshake"


def _cache_identity(config: dict) -> str:
	material = "|".join(
		[
			str(config.get("service_url") or ""),
			str(config.get("site_identifier") or ""),
			str(config.get("product_app") or ""),
			str(config.get("api_key") or ""),
		]
	)
	return hashlib.sha256(material.encode("utf-8")).hexdigest()[:20]


def _get_valid_cache_entry(key: str) -> dict | None:
	entry = _cache_get(key)
	if not isinstance(entry, dict):
		return None
	expires_at = float(entry.get("expires_at_epoch") or 0)
	if expires_at <= time.time():
		_cache_delete(key)
		return None
	return entry


def _set_cache_entry(key: str, response: dict, ttl_seconds: int) -> None:
	ttl_seconds = max(int(ttl_seconds or 0), 0)
	if ttl_seconds <= 0:
		return
	expires_at = time.time() + ttl_seconds
	entry = {
		"response": response,
		"cached_at_epoch": time.time(),
		"expires_at_epoch": expires_at,
		"expires_on": time.strftime("%Y-%m-%d %H:%M:%S", time.gmtime(expires_at)),
	}
	_cache_set(key, entry, ttl_seconds)


def _cache_backend():
	cache = frappe.cache
	if callable(cache) and not hasattr(cache, "get_value"):
		cache = cache()
	return cache


def _cache_get(key: str):
	try:
		value = _cache_backend().get_value(key)
		if isinstance(value, bytes):
			value = value.decode("utf-8")
		if isinstance(value, str):
			try:
				return json.loads(value)
			except ValueError:
				return None
		return value
	except Exception:
		return None


def _cache_set(key: str, value: dict, ttl_seconds: int) -> None:
	try:
		_cache_backend().set_value(key, value, expires_in_sec=ttl_seconds)
	except Exception as exc:
		_log_warning(f"Remote platform cache write failed: {exc.__class__.__name__}")


def _cache_delete(key: str) -> None:
	try:
		_cache_backend().delete_value(key)
	except Exception:
		pass


def _filter_local_platform_items(items: list[dict]) -> list[dict]:
	return [
		item
		for item in items
		if not _is_local_platform_item(item.get("label"), item.get("link_to"))
	]


def _is_local_platform_item(label, link_to) -> bool:
	label = str(label or "")
	link_to = str(link_to or "")
	if link_to.startswith(("CoreEdge", "coreedge")):
		return True
	return label in {
		"Platform Settings",
		"Product Activation",
		"Onboarding",
		"Product Access",
		"Branch Context",
		"Company Context",
		"CoreEdge Platform",
	}


def _service_host(service_url) -> str:
	try:
		return urlsplit(str(service_url or "")).netloc
	except ValueError:
		return ""


def _bounded_int(value, *, default: int, minimum: int, maximum: int) -> int:
	try:
		resolved = int(value)
	except (TypeError, ValueError):
		resolved = default
	return min(max(resolved, minimum), maximum)


def _conf_text(key: str) -> str:
	try:
		value = frappe.conf.get(key)
	except Exception:
		value = None
	return str(value or "").strip()


def _conf_bool(key: str) -> bool:
	value = _conf_text(key).lower()
	return value in {"1", "true", "yes", "on"}


def _log_warning(message: str) -> None:
	try:
		frappe.logger("vetedge.platform").warning(message)
	except Exception:
		pass
