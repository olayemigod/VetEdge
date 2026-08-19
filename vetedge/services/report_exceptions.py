from __future__ import annotations

import frappe
from frappe import _
from frappe.utils import cint, cstr

from vetedge.services import hospitalisation_operations
from vetedge.services.portal_access import require_internal_user
from vetedge.services.reporting_capabilities import require_reporting_action
from vetedge.services.reporting_entitlement_adapter import check_advanced_reporting_entitlement

HOSPITALISATION_DOCTYPE = "Veterinary Hospitalisation"
ACTIVITY_DOCTYPE = "Veterinary Hospitalisation Activity"
PENDING_ACTIONS_REPORT = "Pending Hospitalisation Actions"
MAX_EXCEPTION_ITEMS = 50
CANDIDATE_PARENT_WINDOW = 250
SUPPORTED_EXCEPTION_KEYS = {"hospitalisation_pending_stock"}


def _parse_filters(value) -> dict:
	if not value:
		return {}
	parsed = value if isinstance(value, dict) else frappe.parse_json(value)
	if not isinstance(parsed, dict):
		frappe.throw(_("Expected exception filters as a JSON object."), frappe.ValidationError)
	return {str(key): item for key, item in parsed.items() if item not in (None, "")}


def _require_advanced_exceptions() -> None:
	entitlement = check_advanced_reporting_entitlement()
	if entitlement.get("allowed"):
		return
	frappe.throw(
		_("Operational exception reporting is an Advanced reporting feature and is not included in the current Plan."),
		frappe.PermissionError,
	)


def _pending_stock_candidates() -> list[dict]:
	if not frappe.db.exists("DocType", ACTIVITY_DOCTYPE):
		return []
	return frappe.get_all(
		ACTIVITY_DOCTYPE,
		filters={
			"stock_affecting": 1,
			"stock_status": ["!=", "Posted"],
			"stock_entry": ["is", "not set"],
		},
		fields=["parent", {"COUNT": "name", "as": "pending_count"}],
		group_by="parent",
		order_by="pending_count desc, parent asc",
		page_length=CANDIDATE_PARENT_WINDOW,
	)


def _visible_hospitalisations(parent_names: list[str], filters: dict) -> list[dict]:
	if not parent_names:
		return []
	report_filters = hospitalisation_operations._filters(filters)
	query_filters = hospitalisation_operations._query_filters(report_filters)
	query_filters["name"] = ["in", parent_names]
	return frappe.get_list(
		HOSPITALISATION_DOCTYPE,
		filters=query_filters,
		fields=[
			"name",
			"patient",
			"patient_name",
			"customer",
			"service_branch",
			"status",
			"care_location",
			"attending_veterinarian",
		],
		order_by="admission_datetime desc, name desc",
		page_length=MAX_EXCEPTION_ITEMS,
	)


def _hospitalisation_pending_stock(filters: dict) -> dict:
	candidates = _pending_stock_candidates()
	counts = {
		cstr(row.get("parent") or "").strip(): cint(row.get("pending_count"))
		for row in candidates
		if cstr(row.get("parent") or "").strip()
	}
	parents = _visible_hospitalisations(list(counts), filters)
	items = []
	for parent in parents:
		name = cstr(parent.get("name") or "").strip()
		pending_count = cint(counts.get(name))
		patient = cstr(parent.get("patient_name") or parent.get("patient") or name)
		branch = cstr(parent.get("service_branch") or "")
		status = cstr(parent.get("status") or "")
		items.append(
			{
				"key": name,
				"title": _("{0}: {1} pending stock action(s)").format(patient, pending_count),
				"detail": _("Stock-affecting Hospitalisation activities have not yet produced a Stock Entry."),
				"meta": " · ".join(value for value in (branch, status) if value),
				"tone": "warning",
				"reference_doctype": HOSPITALISATION_DOCTYPE,
				"reference_name": name,
				"action_label": _("Open Hospitalisation"),
				"pending_count": pending_count,
			}
		)
	return {
		"title": _("Hospitalisation Pending Stock Actions"),
		"description": _("Active Hospitalisations with stock-affecting activities that still require stock posting."),
		"items": items,
		"metadata": {
			"exception_key": "hospitalisation_pending_stock",
			"candidate_parent_window": CANDIDATE_PARENT_WINDOW,
			"max_items": MAX_EXCEPTION_ITEMS,
			"permission_intersection": "hospitalisation_get_list",
			"read_only": True,
		},
	}


@frappe.whitelist()
@frappe.read_only()
def get_report_exceptions(exception_key: str, filters=None) -> dict:
	require_internal_user()
	exception_key = cstr(exception_key or "").strip()
	if exception_key not in SUPPORTED_EXCEPTION_KEYS:
		frappe.throw(_("Unsupported reporting exception."), frappe.ValidationError)

	require_reporting_action(PENDING_ACTIONS_REPORT, "report", "view")
	_require_advanced_exceptions()
	if not frappe.has_permission(HOSPITALISATION_DOCTYPE, "read"):
		frappe.throw(_("You do not have permission to view Hospitalisations."), frappe.PermissionError)

	parsed_filters = _parse_filters(filters)
	if exception_key == "hospitalisation_pending_stock":
		return _hospitalisation_pending_stock(parsed_filters)
	frappe.throw(_("Unsupported reporting exception."), frappe.ValidationError)
