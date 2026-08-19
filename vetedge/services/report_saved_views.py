from __future__ import annotations

from typing import Any

import frappe
from frappe import _
from frappe.model.utils.user_settings import get_user_settings, update_user_settings
from frappe.utils import cint, now

from vetedge.services.report_filter_search import REPORT_FIELDS, search_report_filter_options
from vetedge.services.report_visibility import normalize_report_filters
from vetedge.services.reporting_capabilities import require_reporting_action

USER_SETTINGS_SCOPE = "VetEdge Report Center"
SETTINGS_KEY = "vetedge_report_views_v1"
MAX_VIEWS_PER_USER = 25
MAX_LABEL_LENGTH = 80
MAX_REPORT_NAME_LENGTH = 140
MAX_FILTER_VALUE_LENGTH = 500
MAX_VISIBLE_COLUMNS = 100
MAX_COLUMN_KEY_LENGTH = 140

ALLOWED_FILTER_KEYS = {
	"branch",
	"from_date",
	"to_date",
	"date_preset",
	"customer",
	"patient",
	"practitioner",
	"consultation_type",
	"status",
	"payment_status",
	"service_category",
	"item",
	"vaccine",
	"due_status",
	"species",
	"breed",
	"registration_status",
	"outstanding_only",
}


def _require_system_user() -> str:
	user = str(frappe.session.user or "").strip()
	if not user or user == "Guest":
		frappe.throw(_("Please sign in to use saved report views."), frappe.PermissionError)
	return user


def _parse_mapping(value: Any) -> dict:
	if value in (None, ""):
		return {}
	if isinstance(value, dict):
		return dict(value)
	parsed = frappe.parse_json(value)
	if not isinstance(parsed, dict):
		frappe.throw(_("Saved report filters must be an object."))
	return dict(parsed)


def _normalize_filters(value: Any) -> dict[str, str | int]:
	filters = _parse_mapping(value)
	result: dict[str, str | int] = {}
	for key, raw in filters.items():
		key = str(key or "").strip()
		if key not in ALLOWED_FILTER_KEYS or raw in (None, ""):
			continue
		if key == "outstanding_only":
			result[key] = cint(raw)
			continue
		text = str(raw).strip()
		if not text:
			continue
		if len(text) > MAX_FILTER_VALUE_LENGTH:
			frappe.throw(_("A saved report filter value is too long."))
		result[key] = text
	return result


def _normalize_columns(value: Any) -> list[str]:
	if value in (None, ""):
		return []
	if isinstance(value, str):
		try:
			parsed = frappe.parse_json(value)
		except Exception:
			parsed = value.split(",")
	else:
		parsed = value
	if not isinstance(parsed, (list, tuple)):
		frappe.throw(_("Saved report columns must be a list."))

	columns: list[str] = []
	seen: set[str] = set()
	for raw in parsed:
		key = str(raw or "").strip()
		if not key or key in seen:
			continue
		if len(key) > MAX_COLUMN_KEY_LENGTH:
			frappe.throw(_("A saved report column key is too long."))
		seen.add(key)
		columns.append(key)
		if len(columns) > MAX_VISIBLE_COLUMNS:
			frappe.throw(_("Too many saved report columns were supplied."))
	return columns


def _normalize_report_name(report_name: str) -> str:
	name = str(report_name or "").strip()
	if not name:
		frappe.throw(_("Report is required."))
	if len(name) > MAX_REPORT_NAME_LENGTH:
		frappe.throw(_("Report name is too long."))
	require_reporting_action(name, "report", "view", user=frappe.session.user)
	return name


def _load_settings() -> dict:
	raw = get_user_settings(USER_SETTINGS_SCOPE)
	try:
		settings = frappe.parse_json(raw) if isinstance(raw, str) else raw
	except Exception:
		settings = {}
	return dict(settings) if isinstance(settings, dict) else {}


def _load_views() -> list[dict]:
	settings = _load_settings()
	views = settings.get(SETTINGS_KEY) or []
	return [dict(view) for view in views if isinstance(view, dict)] if isinstance(views, list) else []


def _save_views(views: list[dict]) -> None:
	update_user_settings(USER_SETTINGS_SCOPE, {SETTINGS_KEY: views})


def _public_view(view: dict, include_state: bool = False) -> dict:
	result = {
		"view_id": str(view.get("view_id") or ""),
		"label": str(view.get("label") or ""),
		"report_name": str(view.get("report_name") or ""),
		"is_default": cint(view.get("is_default")),
		"created_on": view.get("created_on"),
		"modified_on": view.get("modified_on"),
	}
	if include_state:
		result["filters"] = dict(view.get("filters") or {})
		result["visible_columns"] = list(view.get("visible_columns") or [])
	return result


def _find_view(view_id: str, report_name: str | None = None) -> dict:
	view_id = str(view_id or "").strip()
	if not view_id:
		frappe.throw(_("Saved report view is required."))
	view = next((item for item in _load_views() if str(item.get("view_id") or "") == view_id), None)
	if not view or (report_name and str(view.get("report_name") or "") != report_name):
		frappe.throw(_("Saved report view was not found."), frappe.DoesNotExistError)
	return view


def _normalize_saved_scope(report_name: str, stored_filters: dict) -> tuple[dict, list[str]]:
	filters = _normalize_filters(stored_filters)
	removed: list[str] = []
	try:
		normalized = dict(normalize_report_filters(report_name, filters) or {})
	except frappe.PermissionError:
		if "branch" not in filters:
			raise
		filters.pop("branch", None)
		removed.append("branch")
		normalized = dict(normalize_report_filters(report_name, filters) or {})

	for field in sorted(REPORT_FIELDS.get(report_name, set()) - {"branch"}):
		value = normalized.get(field)
		if value in (None, ""):
			continue
		options = search_report_filter_options(
			report_name=report_name,
			field=field,
			txt=str(value),
			start=0,
			page_length=20,
			filters=normalized,
		)
		if any(str(option.get("value") or "") == str(value) for option in options):
			continue
		normalized.pop(field, None)
		removed.append(field)

	return {key: value for key, value in normalized.items() if key in ALLOWED_FILTER_KEYS and value not in (None, "")}, sorted(set(removed))


@frappe.whitelist()
def get_saved_report_views(report_name: str) -> list[dict]:
	_require_system_user()
	report_name = _normalize_report_name(report_name)
	views = [_public_view(view, include_state=False) for view in _load_views() if view.get("report_name") == report_name]
	return sorted(views, key=lambda view: (not bool(view["is_default"]), view["label"].lower(), view["view_id"]))


@frappe.whitelist()
def apply_saved_report_view(view_id: str, report_name: str) -> dict:
	_require_system_user()
	report_name = _normalize_report_name(report_name)
	view = _find_view(view_id, report_name=report_name)
	filters, removed = _normalize_saved_scope(report_name, dict(view.get("filters") or {}))
	return {
		"view": _public_view(view, include_state=False),
		"filters": filters,
		"visible_columns": _normalize_columns(view.get("visible_columns") or []),
		"removed_filter_keys": removed,
	}


@frappe.whitelist()
def save_report_view(
	label: str,
	report_name: str,
	filters: Any = None,
	visible_columns: Any = None,
	view_id: str | None = None,
	set_default: int | bool = 0,
) -> dict:
	_require_system_user()
	report_name = _normalize_report_name(report_name)
	label = str(label or "").strip()
	if not label:
		frappe.throw(_("View name is required."))
	if len(label) > MAX_LABEL_LENGTH:
		frappe.throw(_("View name must be {0} characters or fewer.").format(MAX_LABEL_LENGTH))

	filters = _normalize_filters(filters)
	columns = _normalize_columns(visible_columns)
	requested_id = str(view_id or "").strip()
	views = _load_views()

	duplicate = next(
		(
			view
			for view in views
			if view.get("report_name") == report_name
			and str(view.get("label") or "").strip().casefold() == label.casefold()
			and str(view.get("view_id") or "") != requested_id
		),
		None,
	)
	if duplicate:
		frappe.throw(_("A saved view with this name already exists for the report."))

	index = next(
		(index for index, view in enumerate(views) if str(view.get("view_id") or "") == requested_id),
		None,
	)
	if requested_id and index is None:
		frappe.throw(_("Saved report view was not found."), frappe.DoesNotExistError)
	if index is None and len(views) >= MAX_VIEWS_PER_USER:
		frappe.throw(_("You can save up to {0} private report views.").format(MAX_VIEWS_PER_USER))

	timestamp = now()
	is_default = cint(set_default)
	if is_default:
		for view in views:
			if view.get("report_name") == report_name:
				view["is_default"] = 0

	if index is None:
		view = {
			"view_id": frappe.generate_hash(length=12),
			"label": label,
			"report_name": report_name,
			"filters": filters,
			"visible_columns": columns,
			"is_default": is_default,
			"created_on": timestamp,
			"modified_on": timestamp,
		}
		views.append(view)
	else:
		view = views[index]
		view.update(
			{
				"label": label,
				"report_name": report_name,
				"filters": filters,
				"visible_columns": columns,
				"is_default": is_default,
				"modified_on": timestamp,
			}
		)
		view.setdefault("created_on", timestamp)

	_save_views(views)
	return _public_view(view, include_state=False)


@frappe.whitelist()
def rename_saved_report_view(view_id: str, report_name: str, label: str) -> dict:
	_require_system_user()
	report_name = _normalize_report_name(report_name)
	label = str(label or "").strip()
	if not label:
		frappe.throw(_("View name is required."))
	if len(label) > MAX_LABEL_LENGTH:
		frappe.throw(_("View name must be {0} characters or fewer.").format(MAX_LABEL_LENGTH))

	views = _load_views()
	view = next(
		(item for item in views if str(item.get("view_id") or "") == str(view_id or "").strip() and item.get("report_name") == report_name),
		None,
	)
	if not view:
		frappe.throw(_("Saved report view was not found."), frappe.DoesNotExistError)
	if any(
		item.get("report_name") == report_name
		and str(item.get("view_id") or "") != str(view.get("view_id") or "")
		and str(item.get("label") or "").strip().casefold() == label.casefold()
		for item in views
	):
		frappe.throw(_("A saved view with this name already exists for the report."))
	view["label"] = label
	view["modified_on"] = now()
	_save_views(views)
	return _public_view(view, include_state=False)


@frappe.whitelist()
def delete_saved_report_view(view_id: str) -> dict:
	_require_system_user()
	view_id = str(view_id or "").strip()
	if not view_id:
		frappe.throw(_("Saved report view is required."))

	views = _load_views()
	remaining = [view for view in views if str(view.get("view_id") or "") != view_id]
	if len(remaining) == len(views):
		frappe.throw(_("Saved report view was not found."), frappe.DoesNotExistError)
	_save_views(remaining)
	return {"deleted": True, "view_id": view_id}