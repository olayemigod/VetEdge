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

API_VERSION = "v1"
SERVICE_NAME = "CoreEdge Service Gateway"
HANDSHAKE_METHOD = "coreedge.api.v1.service_gateway.handshake"
ACCESS_METHOD = "coreedge.api.v1.service_gateway.check_runtime_access"
REMOTE_MODE = "remote"
LEGACY_MODE = "legacy_auto"
DEFAULT_TIMEOUT_SECONDS = 5
MAX_TIMEOUT_SECONDS = 30
MAX_CACHE_TTL_SECONDS = 300
DEFAULT_HEARTBEAT_SECONDS = 300
class RemotePlatformError(Exception):
	"""Base error for CoreEdge remote service operations."""


class RemotePlatformConfigurationError(RemotePlatformError):
	pass


class RemotePlatformAuthenticationError(RemotePlatformError):
	pass


class RemotePlatformUnavailableError(RemotePlatformError):
	pass


class RemotePlatformProtocolError(RemotePlatformError):
	pass


class RemotePlatformAccessDenied(RemotePlatformError):
	def __init__(self, decision: dict | None = None):
		self.decision = decision or {}
		super().__init__(
			self.decision.get("reason") or _("Platform access is not available for this site.")
		)


def get_platform_authority_mode() -> str:
	"""Resolve operator-controlled authority without consulting a tenant-facing DocType.

	`coreedge_remote_required` is the non-bypassable operator policy. Connection
	credentials alone never activate remote authority, allowing them to be provisioned
	and tested before the controlled cutover.
	"""
	if _conf_bool("coreedge_remote_required"):
		return REMOTE_MODE

	raw_mode = _conf_text("coreedge_authority_mode")
	if raw_mode:
		mode = raw_mode.lower().replace("-", "_")
		if mode in {REMOTE_MODE, LEGACY_MODE}:
			return mode
		_log_warning(
			f"Unsupported coreedge_authority_mode '{raw_mode}'. Failing safe to remote authority."
		)
		return REMOTE_MODE
	return LEGACY_MODE


def is_remote_platform_requested() -> bool:
	return get_platform_authority_mode() == REMOTE_MODE


def get_remote_platform_config(*, validate: bool = True) -> dict:
	service_url = _normalize_service_url(_conf_text("coreedge_service_url"), validate=validate)
	api_key = _conf_text("coreedge_api_key")
	api_secret = _conf_text("coreedge_api_secret")
	site_identifier = _resolve_site_identifier()
	missing = []
	for key, value in (
		("coreedge_service_url", service_url),
		("coreedge_api_key", api_key),
		("coreedge_api_secret", api_secret),
		("coreedge_site_identifier", site_identifier),
	):
		if not value:
			missing.append(key)
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
		"timeout_seconds": _bounded_int(
			_conf_text("coreedge_remote_timeout_seconds"),
			default=DEFAULT_TIMEOUT_SECONDS,
			minimum=1,
			maximum=MAX_TIMEOUT_SECONDS,
		),
		"configured": not missing,
		"missing": missing,
	}


def get_remote_access_response(
	*,
	force_refresh: bool = False,
	force_handshake: bool = False,
	allow_cached_on_error: bool = True,
	action: str | None = None,
	reference_doctype: str | None = None,
	reference_name: str | None = None,
) -> dict:
	"""Return a validated response using only the server-authoritative cache TTL."""
	config = get_remote_platform_config(validate=True)
	access_key = _access_cache_key(config)
	cached = _get_valid_cache_entry(access_key)
	if cached and not force_refresh:
		return cached["response"]

	handshake_key = _handshake_cache_key(config)
	use_handshake = force_handshake or not _get_valid_cache_entry(handshake_key)
	method = HANDSHAKE_METHOD if use_handshake else ACCESS_METHOD
	payload = {
		"site_identifier": config["site_identifier"],
		"request_id": _make_request_id(action),
		"source_path": _build_source_path(action, reference_doctype, reference_name),
	}
	if use_handshake:
		payload["app_version"] = VETEDGE_VERSION
		payload["frappe_version"] = str(getattr(frappe, "__version__", "") or "")

	try:
		response = _post_gateway(config, method, payload)
	except RemotePlatformError:
		if allow_cached_on_error and cached and bool(
			((cached.get("response") or {}).get("access") or {}).get("allowed")
		):
			return cached["response"]
		raise

	ttl_seconds = _response_ttl(response)
	if ttl_seconds:
		_set_cache_entry(access_key, response, ttl_seconds)
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
		return bool((get_remote_access_response().get("access") or {}).get("allowed"))
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
	"""Return a secret-free, cache-only status snapshot suitable for bootinfo."""
	configuration_error = ""
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
		configuration_error = str(exc)
	status = {
		"authority_mode": config.get("authority_mode"),
		"remote_requested": is_remote_platform_requested(),
		"configured": bool(config.get("configured")),
		"service_host": _service_host(config.get("service_url")),
		"site_identifier": config.get("site_identifier"),
		"product_app": config.get("product_app"),
		"missing_configuration": list(config.get("missing") or []),
		"configuration_error": configuration_error,
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
	decision = ((entry.get("response") or {}).get("access") or {})
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
	"""Scheduler-safe heartbeat; a failure must not crash the scheduler worker."""
	if not is_remote_platform_requested():
		return
	try:
		get_remote_access_response(
			force_refresh=True,
			force_handshake=True,
			allow_cached_on_error=False,
			action="scheduled_heartbeat",
		)
	except RemotePlatformError as exc:
		_log_warning(f"Remote platform heartbeat failed: {exc.__class__.__name__}: {exc}")


def extend_bootinfo_with_remote_platform(bootinfo) -> None:
	"""Expose a secret-free connection summary and hide local controls in remote mode."""
	status = get_remote_platform_status()
	bootinfo.edge_platform_authority = status["authority_mode"]
	bootinfo.edge_platform_connection = frappe._dict(status)
	if not status["remote_requested"]:
		return
	bootinfo.should_show_coreedge_controls = False
	menu = bootinfo.get("edgesuite_product_menu")
	if isinstance(menu, dict):
		menu["show_coreedge_controls"] = False
		menu["platform_authority"] = REMOTE_MODE
		menu["platform_connection"] = {
			"configured": status["configured"],
			"cached": status["cached"],
			"allowed": status["allowed"],
			"primary_reason_code": status["primary_reason_code"],
		}
	for sidebar in (bootinfo.get("workspace_sidebar_item") or {}).values():
		if isinstance(sidebar, dict):
			sidebar["items"] = _filter_local_platform_items(sidebar.get("items") or [])
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
		"User-Agent": f"VetEdge/{VETEDGE_VERSION} CoreEdge-Remote-Client/{API_VERSION}",
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
		raise RemotePlatformAuthenticationError(
			_("The product site's platform credentials were rejected.")
		)
	if response.status_code >= 400:
		raise RemotePlatformUnavailableError(
			_("The platform service returned HTTP status {0}.").format(response.status_code)
		)
	try:
		body = response.json()
	except ValueError as exc:
		raise RemotePlatformProtocolError(
			_("The platform service returned an invalid JSON response.")
		) from exc
	if isinstance(body, dict) and isinstance(body.get("message"), dict):
		body = body["message"]
	return _validate_gateway_response(body, config)


def _validate_gateway_response(body, config: dict) -> dict:
	if not isinstance(body, dict):
		raise RemotePlatformProtocolError(_("The platform response must be an object."))
	if body.get("api_version") != API_VERSION or body.get("service") != SERVICE_NAME:
		raise RemotePlatformProtocolError(_("The response did not match the CoreEdge gateway contract."))
	client = body.get("client")
	access = body.get("access")
	cache_policy = body.get("cache_policy")
	if not all(isinstance(value, dict) for value in (client, access, cache_policy)):
		raise RemotePlatformProtocolError(
			_("The platform response is missing required contract sections.")
		)
	if not bool(cache_policy.get("fail_closed")):
		raise RemotePlatformProtocolError(
			_("The platform response does not enforce the fail-closed contract.")
		)
	if _normalize_site_identifier(client.get("site_identifier")) != config["site_identifier"]:
		raise RemotePlatformProtocolError(
			_("The platform response is bound to a different product site.")
		)
	expected_product = str(config.get("product_app") or "").strip().casefold()
	client_product = str(client.get("product_app") or "").strip().casefold()
	access_product = str(access.get("product_app") or "").strip().casefold()
	if not expected_product or {client_product, access_product} != {expected_product}:
		raise RemotePlatformProtocolError(
			_("The platform response is bound to a different product app.")
		)
	if access.get("tenant") != client.get("tenant"):
		raise RemotePlatformProtocolError(
			_("The access decision tenant does not match the registered client.")
		)
	if not isinstance(access.get("allowed"), (bool, int)):
		raise RemotePlatformProtocolError(
			_("The platform access decision has no valid allowed flag.")
		)
	return body


def _response_ttl(response: dict) -> int:
	allowed = bool((response.get("access") or {}).get("allowed"))
	fieldname = "allowed_ttl_seconds" if allowed else "blocked_ttl_seconds"
	return _bounded_int(
		(response.get("cache_policy") or {}).get(fieldname),
		default=0,
		minimum=0,
		maximum=MAX_CACHE_TTL_SECONDS,
	)


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
			raise RemotePlatformConfigurationError(
				_("coreedge_service_url must be a valid HTTP or HTTPS root URL.")
			)
		return ""
	if parsed.scheme == "http" and not (
		_conf_bool("developer_mode") and _conf_bool("coreedge_allow_insecure_http")
	):
		if validate:
			raise RemotePlatformConfigurationError(
				_("Remote platform connections require HTTPS outside an explicit developer-mode override.")
			)
		return ""
	return f"{parsed.scheme.lower()}://{parsed.netloc.lower()}"


def _resolve_site_identifier() -> str:
	for value in (
		_conf_text("coreedge_site_identifier"),
		_conf_text("host_name"),
		_get_local_site(),
	):
		identifier = _normalize_site_identifier(value)
		if identifier:
			return identifier
	return ""


def _get_local_site() -> str:
	try:
		return str(getattr(frappe.local, "site", "") or "")
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


def _make_request_id(action: str | None) -> str:
	prefix = str(action or "vetedge").strip().lower().replace(" ", "-")[:30]
	return f"{prefix or 'vetedge'}-{uuid.uuid4().hex[:20]}"


def _build_source_path(action, reference_doctype, reference_name) -> str:
	parts = [str(value or "").strip() for value in (action, reference_doctype, reference_name)]
	return ":".join(part for part in parts if part)[:255]


def _cache_identity(config: dict) -> str:
	material = "|".join(
		str(config.get(key) or "")
		for key in ("service_url", "site_identifier", "product_app", "api_key")
	)
	return hashlib.sha256(material.encode()).hexdigest()[:20]


def _access_cache_key(config: dict) -> str:
	return f"vetedge:coreedge-remote:v1:{_cache_identity(config)}:access"


def _handshake_cache_key(config: dict) -> str:
	return f"vetedge:coreedge-remote:v1:{_cache_identity(config)}:handshake"


def _get_valid_cache_entry(key: str) -> dict | None:
	entry = _cache_get(key)
	if not isinstance(entry, dict):
		return None
	if float(entry.get("expires_at_epoch") or 0) <= time.time():
		_cache_delete(key)
		return None
	return entry


def _set_cache_entry(key: str, response: dict, ttl_seconds: int) -> None:
	ttl_seconds = max(int(ttl_seconds or 0), 0)
	if not ttl_seconds:
		return
	expires_at = time.time() + ttl_seconds
	_cache_set(
		key,
		{
			"response": response,
			"expires_at_epoch": expires_at,
			"expires_on": time.strftime("%Y-%m-%d %H:%M:%S UTC", time.gmtime(expires_at)),
		},
		ttl_seconds,
	)


def _cache_backend():
	cache = frappe.cache
	return cache() if callable(cache) and not hasattr(cache, "get_value") else cache


def _cache_get(key: str):
	try:
		value = _cache_backend().get_value(key)
		if isinstance(value, bytes):
			value = value.decode()
		if isinstance(value, str):
			return json.loads(value)
		return value
	except (TypeError, ValueError, json.JSONDecodeError, AttributeError):
		return None
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


def _service_host(value) -> str:
	try:
		return urlsplit(str(value or "")).netloc
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
		return str(frappe.conf.get(key) or "").strip()
	except Exception:
		return ""


def _conf_bool(key: str) -> bool:
	return _conf_text(key).lower() in {"1", "true", "yes", "on"}


def _log_warning(message: str) -> None:
	try:
		frappe.logger("vetedge.platform").warning(message)
	except Exception:
		pass
