from __future__ import annotations

from collections import defaultdict

import frappe
from frappe import _
from frappe.utils import cint, cstr, flt

from vetedge.services import hospitalisation_operations
from vetedge.services.portal_access import require_internal_user
from vetedge.services.reporting_capabilities import require_reporting_action
from vetedge.services.reporting_entitlement_adapter import check_advanced_reporting_entitlement

HOSPITALISATION_DOCTYPE = "Veterinary Hospitalisation"
ACTIVITY_DOCTYPE = "Veterinary Hospitalisation Activity"
CHARGE_DOCTYPE = "Veterinary Hospitalisation Charge Item"
PENDING_ACTIONS_REPORT = "Pending Hospitalisation Actions"
MAX_EXCEPTION_ITEMS = 50
CANDIDATE_PARENT_WINDOW = 250
CANDIDATE_CHILD_WINDOW = 500
SUPPORTED_EXCEPTION_KEYS = {
	"hospitalisation_pending_stock",
	"hospitalisation_pending_billing",
	"hospitalisation_missing_price",
	"hospitalisation_operations",
}


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


def _grouped_activity_candidates(filters: dict) -> list[dict]:
	if not frappe.db.exists("DocType", ACTIVITY_DOCTYPE):
		return []
	return frappe.get_all(
		ACTIVITY_DOCTYPE,
		filters=filters,
		fields=["parent", {"COUNT": "name", "as": "pending_count"}],
		group_by="parent",
		order_by="pending_count desc, parent asc",
		page_length=CANDIDATE_PARENT_WINDOW,
	)


def _pending_stock_candidates() -> list[dict]:
	# A disabled Dispensary Flow means there is no actionable Hospitalisation
	# stock-posting workflow. Preserve historical rows, but do not report them as
	# current stock exceptions that users are unable (and not permitted) to post.
	from vetedge.services.hospitalisation_episode_policy import is_hospitalisation_dispensary_enabled

	if not is_hospitalisation_dispensary_enabled():
		return []
	return _grouped_activity_candidates(
		{
			"stock_affecting": 1,
			"stock_status": ["!=", "Posted"],
			"stock_entry": ["is", "not set"],
		}
	)


def _pending_billing_candidates() -> list[dict]:
	return _grouped_activity_candidates(
		{
			"billable": 1,
			"billing_status": ["not in", ["Charged", "Cancelled"]],
		}
	)


def _missing_price_candidates() -> list[dict]:
	if not frappe.db.exists("DocType", CHARGE_DOCTYPE):
		return []
	rows = frappe.get_all(
		CHARGE_DOCTYPE,
		filters={
			"billing_status": ["not in", ["Invoiced", "Cancelled"]],
			"item": ["is", "set"],
		},
		fields=["parent", "qty", "rate", "amount"],
		order_by="parent asc, idx asc",
		page_length=CANDIDATE_CHILD_WINDOW,
	)
	counts: dict[str, int] = defaultdict(int)
	for row in rows:
		parent = cstr(row.get("parent") or "").strip()
		if not parent:
			continue
		qty = flt(row.get("qty")) or 1
		rate = flt(row.get("rate"))
		amount = flt(row.get("amount")) or qty * rate
		if rate <= 0 or amount <= 0:
			counts[parent] += 1
	return [
		{"parent": parent, "pending_count": count}
		for parent, count in sorted(counts.items(), key=lambda item: (-item[1], item[0]))[:CANDIDATE_PARENT_WINDOW]
	]


def _candidate_counts(rows: list[dict]) -> dict[str, int]:
	return {
		cstr(row.get("parent") or "").strip(): cint(row.get("pending_count"))
		for row in rows
		if cstr(row.get("parent") or "").strip()
	}


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


def _base_item(parent: dict, pending_count: int) -> tuple[str, str, str, int]:
	name = cstr(parent.get("name") or "").strip()
	patient = cstr(parent.get("patient_name") or parent.get("patient") or name)
	branch = cstr(parent.get("service_branch") or "")
	status = cstr(parent.get("status") or "")
	meta = " · ".join(value for value in (branch, status) if value)
	return name, patient, meta, cint(pending_count)


def _hospitalisation_pending_stock(filters: dict) -> dict:
	counts = _candidate_counts(_pending_stock_candidates())
	parents = _visible_hospitalisations(list(counts), filters)
	items = []
	for parent in parents:
		name, patient, meta, pending_count = _base_item(parent, counts.get(parent.get("name"), 0))
		items.append(
			{
				"key": f"stock:{name}",
				"title": _("{0}: {1} pending stock action(s)").format(patient, pending_count),
				"detail": _("Stock-affecting Hospitalisation activities have not yet produced a Stock Entry."),
				"meta": meta,
				"tone": "warning",
				"reference_doctype": HOSPITALISATION_DOCTYPE,
				"reference_name": name,
				"action_label": _("Open Hospitalisation"),
				"pending_count": pending_count,
				"exception_type": "pending_stock",
				"priority": 2,
			}
		)
	return {
		"title": _("Hospitalisation Pending Stock Actions"),
		"description": _("Active Hospitalisations with stock-affecting activities that still require stock posting."),
		"items": items,
		"metadata": {"exception_key": "hospitalisation_pending_stock"},
	}


def _hospitalisation_pending_billing(filters: dict) -> dict:
	counts = _candidate_counts(_pending_billing_candidates())
	parents = _visible_hospitalisations(list(counts), filters)
	items = []
	for parent in parents:
		name, patient, meta, pending_count = _base_item(parent, counts.get(parent.get("name"), 0))
		items.append(
			{
				"key": f"billing:{name}",
				"title": _("{0}: {1} uncharged billable activity item(s)").format(patient, pending_count),
				"detail": _("Billable Hospitalisation activities are still outside Charged or Cancelled billing states."),
				"meta": meta,
				"tone": "warning",
				"reference_doctype": HOSPITALISATION_DOCTYPE,
				"reference_name": name,
				"action_label": _("Open Hospitalisation"),
				"pending_count": pending_count,
				"exception_type": "pending_billing",
				"priority": 1,
			}
		)
	return {
		"title": _("Hospitalisation Pending Billable Activities"),
		"description": _("Active Hospitalisations with billable activities that still require charge processing."),
		"items": items,
		"metadata": {"exception_key": "hospitalisation_pending_billing"},
	}


def _hospitalisation_missing_price(filters: dict) -> dict:
	counts = _candidate_counts(_missing_price_candidates())
	parents = _visible_hospitalisations(list(counts), filters)
	items = []
	for parent in parents:
		name, patient, meta, pending_count = _base_item(parent, counts.get(parent.get("name"), 0))
		items.append(
			{
				"key": f"price:{name}",
				"title": _("{0}: {1} pending charge item(s) missing a usable price").format(patient, pending_count),
				"detail": _("Pending Hospitalisation charge items have a non-positive rate or effective amount and need pricing review before billing."),
				"meta": meta,
				"tone": "danger",
				"reference_doctype": HOSPITALISATION_DOCTYPE,
				"reference_name": name,
				"action_label": _("Open Hospitalisation"),
				"pending_count": pending_count,
				"exception_type": "missing_price",
				"priority": 3,
			}
		)
	return {
		"title": _("Hospitalisation Missing Prices"),
		"description": _("Active Hospitalisations with pending charge items that cannot be billed safely at the current price."),
		"items": items,
		"metadata": {"exception_key": "hospitalisation_missing_price"},
	}


def _hospitalisation_operations_exceptions(filters: dict) -> dict:
	sections = [
		_hospitalisation_missing_price(filters),
		_hospitalisation_pending_stock(filters),
		_hospitalisation_pending_billing(filters),
	]
	items = [item for section in sections for item in section.get("items", [])]
	items.sort(key=lambda item: (-cint(item.get("priority")), -cint(item.get("pending_count")), cstr(item.get("key"))))
	return {
		"title": _("Hospitalisation Exceptions"),
		"description": _("Pricing, stock and billing exceptions requiring attention across the current Hospitalisation filters."),
		"items": items[:MAX_EXCEPTION_ITEMS],
		"metadata": {
			"exception_key": "hospitalisation_operations",
			"included_types": ["missing_price", "pending_stock", "pending_billing"],
			"candidate_parent_window": CANDIDATE_PARENT_WINDOW,
			"candidate_child_window": CANDIDATE_CHILD_WINDOW,
			"max_items": MAX_EXCEPTION_ITEMS,
			"permission_intersection": "hospitalisation_get_list",
			"read_only": True,
			"browser_request_count": 1,
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
		return _with_metadata(_hospitalisation_pending_stock(parsed_filters))
	if exception_key == "hospitalisation_pending_billing":
		return _with_metadata(_hospitalisation_pending_billing(parsed_filters))
	if exception_key == "hospitalisation_missing_price":
		return _with_metadata(_hospitalisation_missing_price(parsed_filters))
	if exception_key == "hospitalisation_operations":
		return _hospitalisation_operations_exceptions(parsed_filters)
	frappe.throw(_("Unsupported reporting exception."), frappe.ValidationError)


def _with_metadata(payload: dict) -> dict:
	metadata = dict(payload.get("metadata") or {})
	metadata.update(
		{
			"candidate_parent_window": CANDIDATE_PARENT_WINDOW,
			"candidate_child_window": CANDIDATE_CHILD_WINDOW,
			"max_items": MAX_EXCEPTION_ITEMS,
			"permission_intersection": "hospitalisation_get_list",
			"read_only": True,
		}
	)
	return {**payload, "metadata": metadata}
