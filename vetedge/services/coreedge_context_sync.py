from __future__ import annotations

import hashlib
import json
from urllib.parse import urlsplit

import frappe
import requests
from frappe import _
from frappe.utils import cint, now_datetime

from vetedge.services.coreedge_context_reconciliation import get_context_reconciliation_rows

_ENDPOINT_PATH = "/api/method/coreedge.api.v1.service_context.submit_context_inventory"
_PRODUCT_SLUG = "vetedge"
_ALLOWED_ROW_KEYS = (
	"local_doctype",
	"local_name",
	"local_label",
	"local_code",
	"company",
	"active",
	"normalization_issue",
)
_REQUIRED_CONFIG = (
	"coreedge_service_url",
	"coreedge_service_site_identifier",
	"coreedge_service_api_key",
	"coreedge_service_api_secret",
)
_DEFAULT_TIMEOUT_SECONDS = 15
_MIN_TIMEOUT_SECONDS = 3
_MAX_TIMEOUT_SECONDS = 60


@frappe.whitelist()
def get_context_inventory_sync_status() -> dict:
	_assert_operator()
	config, missing = _load_config(allow_missing=True)
	return {
		"configured": not missing,
		"missing_settings": missing,
		"service_url": config.get("service_url") or "",
		"site_identifier": config.get("site_identifier") or "",
		"api_key_configured": bool(config.get("api_key")),
		"api_secret_configured": bool(config.get("api_secret")),
		"timeout_seconds": config.get("timeout_seconds") or _DEFAULT_TIMEOUT_SECONDS,
	}


@frappe.whitelist()
def submit_context_inventory_to_coreedge(idempotency_key: str | None = None) -> dict:
	"""
	Submit the product's full normalized operating-unit inventory to CoreEdge.

	This is an operator action. It does not change local Branch/Campus records,
	permissions, accounting defaults, or active runtime context.
	"""
	_assert_operator()
	config, missing = _load_config()
	if missing:
		frappe.throw(
			_("CoreEdge context sync is not configured. Missing site settings: {0}").format(
				", ".join(missing)
			),
			frappe.ValidationError,
		)

	rows = _payload_rows(get_context_reconciliation_rows())
	resolved_idempotency_key = _normalize_idempotency_key(idempotency_key) or _default_idempotency_key(rows)
	payload = {
		"site_identifier": config["site_identifier"],
		"records": rows,
		"idempotency_key": resolved_idempotency_key,
		"request_id": resolved_idempotency_key,
		"source_path": f"vetedge.context_inventory_sync",
	}

	result = _post_context_inventory(config=config, payload=payload)
	result["local_submission"] = {
		"product": _PRODUCT_SLUG,
		"record_count": len(rows),
		"idempotency_key": resolved_idempotency_key,
	}
	return result


def _post_context_inventory(*, config: dict, payload: dict) -> dict:
	endpoint = f'{config["service_url"]}{_ENDPOINT_PATH}'
	headers = {
		"Authorization": f'token {config["api_key"]}:{config["api_secret"]}',
		"Accept": "application/json",
	}
	try:
		response = requests.post(
			endpoint,
			json=payload,
			headers=headers,
			timeout=config["timeout_seconds"],
		)
	except requests.RequestException:
		return {
			"data": {
				"ok": False,
				"status": "Unavailable",
				"reason_code": "COREDGE_SERVICE_UNREACHABLE",
				"message": _("CoreEdge context service could not be reached."),
			}
		}

	try:
		body = response.json()
	except ValueError:
		body = {}

	if response.status_code >= 400:
		return {
			"data": {
				"ok": False,
				"status": "Failed",
				"reason_code": "COREDGE_HTTP_ERROR",
				"http_status": response.status_code,
				"message": _safe_remote_message(body)
				or _("CoreEdge rejected the context inventory request."),
			}
		}

	message = body.get("message", body) if isinstance(body, dict) else {}
	if not isinstance(message, dict):
		return {
			"data": {
				"ok": False,
				"status": "Failed",
				"reason_code": "COREDGE_INVALID_RESPONSE",
				"message": _("CoreEdge returned an invalid context inventory response."),
			}
		}
	return message


def _payload_rows(rows) -> list[dict]:
	payload = []
	for raw in rows or []:
		if not isinstance(raw, dict):
			continue
		payload.append(
			{
				key: raw.get(key)
				for key in _ALLOWED_ROW_KEYS
				if key in raw
			}
		)
	return sorted(
		payload,
		key=lambda row: (
			str(row.get("local_doctype") or ""),
			str(row.get("local_name") or ""),
			str(row.get("local_code") or ""),
			str(row.get("company") or ""),
		),
	)


def _default_idempotency_key(rows: list[dict]) -> str:
	fingerprint = hashlib.sha256(
		json.dumps(rows, sort_keys=True, separators=(",", ":"), default=str).encode("utf-8")
	).hexdigest()[:24]
	hour_bucket = now_datetime().strftime("%Y%m%d%H")
	return f"context-{_PRODUCT_SLUG}-{hour_bucket}-{fingerprint}"


def _normalize_idempotency_key(value: str | None) -> str:
	return str(value or "").strip()[:140]


def _load_config(*, allow_missing: bool = False) -> tuple[dict, list[str]]:
	values = {key: str(frappe.conf.get(key) or "").strip() for key in _REQUIRED_CONFIG}
	missing = [key for key in _REQUIRED_CONFIG if not values[key]]

	service_url = values["coreedge_service_url"].rstrip("/")
	if service_url:
		parts = urlsplit(service_url)
		if parts.scheme not in {"http", "https"} or not parts.netloc:
			frappe.throw(_("CoreEdge service URL is invalid."), frappe.ValidationError)
		if parts.scheme != "https" and not cint(
			frappe.conf.get("coreedge_service_allow_insecure_http") or 0
		):
			frappe.throw(
				_(
					"CoreEdge service URL must use HTTPS. "
					"Set coreedge_service_allow_insecure_http only for controlled local QA."
				),
				frappe.ValidationError,
			)

	timeout = cint(
		frappe.conf.get("coreedge_service_timeout_seconds") or _DEFAULT_TIMEOUT_SECONDS
	)
	timeout = min(max(timeout, _MIN_TIMEOUT_SECONDS), _MAX_TIMEOUT_SECONDS)
	config = {
		"service_url": service_url,
		"site_identifier": values["coreedge_service_site_identifier"],
		"api_key": values["coreedge_service_api_key"],
		"api_secret": values["coreedge_service_api_secret"],
		"timeout_seconds": timeout,
	}
	if missing and not allow_missing:
		return config, missing
	return config, missing


def _safe_remote_message(body: dict) -> str:
	if not isinstance(body, dict):
		return ""
	message = body.get("message")
	if isinstance(message, str):
		return message[:500]
	if isinstance(message, dict):
		data = message.get("data")
		if isinstance(data, dict):
			return str(data.get("message") or "")[:500]
	return ""


def _assert_operator() -> None:
	if frappe.session.user == "Administrator":
		return
	if "System Manager" not in set(frappe.get_roles(frappe.session.user)):
		frappe.throw(
			_("Only a System Manager can submit product context inventory to CoreEdge."),
			frappe.PermissionError,
		)
