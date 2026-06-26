from __future__ import annotations

import json
import os

import frappe
from frappe.modules.import_file import import_file_by_path


SIDEBAR_SYNC_IGNORED_FIELDS = {"name", "doctype", "creation", "modified", "modified_by", "owner", "docstatus", "idx"}

OPTIONAL_COREDGE_WORKSPACE_DOCTYPE_LINKS = {
	"CoreEdge Settings",
	"CoreEdge Product Activation",
	"CoreEdge Tenant",
	"CoreEdge Access Decision Log",
	"CoreEdge Branch Session",
	"CoreEdge Context Switch Log",
}


def _installed_apps() -> set[str]:
	try:
		return set(frappe.get_installed_apps() or [])
	except Exception:
		return set()


def _doctype_exists(doctype: str) -> bool:
	if not doctype:
		return False
	try:
		return bool(frappe.db.exists("DocType", doctype))
	except Exception:
		return False


def _can_link_doctype(doctype: str) -> bool:
	return _doctype_exists(doctype)


def _coreedge_available() -> bool:
	return "coreedge" in _installed_apps()


def _should_keep_sidebar_item(item) -> bool:
	link_to = item.get("link_to") if isinstance(item, dict) else getattr(item, "link_to", None)
	if not link_to:
		return True

	if link_to in OPTIONAL_COREDGE_WORKSPACE_DOCTYPE_LINKS or str(link_to).startswith("CoreEdge "):
		if not (_coreedge_available() and _doctype_exists(link_to)):
			return False

	return True


def _prepare_standard_sidebar_update_payload(standard_doc: dict) -> dict:
	return {key: value for key, value in standard_doc.items() if key not in SIDEBAR_SYNC_IGNORED_FIELDS}


FINANCIAL_DASHBOARD_FILES = (
	("veterinary", "report", "branch_performance_summary", "branch_performance_summary.json"),
	("veterinary", "number_card", "today_revenue", "today_revenue.json"),
	("veterinary", "number_card", "week_revenue", "week_revenue.json"),
	("veterinary", "number_card", "month_revenue", "month_revenue.json"),
	("veterinary", "number_card", "outstanding_receivables", "outstanding_receivables.json"),
	("veterinary", "number_card", "payments_today", "payments_today.json"),
	("veterinary", "dashboard_chart", "daily_revenue_trend", "daily_revenue_trend.json"),
	("veterinary", "dashboard_chart", "revenue_by_cost_center", "revenue_by_cost_center.json"),
	("veterinary", "dashboard_chart", "revenue_by_service_type", "revenue_by_service_type.json"),
	("veterinary", "dashboard_chart", "paid_vs_outstanding", "paid_vs_outstanding.json"),
	("veterinary", "dashboard_chart", "payment_method_breakdown", "payment_method_breakdown.json"),
	("veterinary", "page", "veterinary_financial_dashboard", "veterinary_financial_dashboard.json"),
	("veterinary", "page", "kennel_availability_board", "kennel_availability_board.json"),
	("workspace_sidebar", "vetedge.json"),
	("desktop_icon", "vetedge.json"),
)


def ensure_financial_dashboard() -> None:
	for file_parts in FINANCIAL_DASHBOARD_FILES:
		file_path = frappe.get_app_path("vetedge", *file_parts)
		if os.path.exists(file_path):
			import_file_by_path(file_path, force=True, ignore_version=True)

	ensure_vetedge_workspace_sidebar()
	cleanup_legacy_financial_workspace()
	ensure_vetedge_desktop_icon()


def cleanup_legacy_financial_workspace() -> None:
	if frappe.db.exists("Workspace", "Veterinary Financial Dashboard"):
		frappe.delete_doc_if_exists("Workspace", "Veterinary Financial Dashboard", force=1)


def ensure_vetedge_workspace_sidebar() -> None:
	if not frappe.db.exists("DocType", "Workspace Sidebar"):
		return

	standard_doc = _load_standard_doc("workspace_sidebar", "vetedge.json")

	if "items" in standard_doc:
		standard_doc["items"] = [item for item in standard_doc["items"] if _should_keep_sidebar_item(item)]

	if frappe.db.exists("Workspace Sidebar", "VetEdge"):
		sidebar = frappe.get_doc("Workspace Sidebar", "VetEdge")
		sidebar.update(_prepare_standard_sidebar_update_payload(standard_doc))
		raw_items = sidebar.get("items") if hasattr(sidebar, "get") else getattr(sidebar, "items", None)
		kept_items = [item for item in raw_items or [] if _should_keep_sidebar_item(item)]
		if hasattr(sidebar, "set"):
			sidebar.set("items", kept_items)
		else:
			sidebar.items = kept_items
		sidebar.save(ignore_permissions=True)
	else:
		sidebar = frappe.get_doc(standard_doc)
		raw_items = sidebar.get("items") if hasattr(sidebar, "get") else getattr(sidebar, "items", None)
		kept_items = [item for item in raw_items or [] if _should_keep_sidebar_item(item)]
		if hasattr(sidebar, "set"):
			sidebar.set("items", kept_items)
		else:
			sidebar.items = kept_items
		sidebar.insert(ignore_permissions=True)

	if hasattr(frappe, "cache"):
		frappe.cache.delete_key("bootinfo")


def ensure_vetedge_desktop_icon() -> None:
	if not frappe.db.exists("DocType", "Desktop Icon"):
		return

	if not frappe.db.exists("Desktop Icon", "VetEdge"):
		frappe.get_doc(_load_standard_doc("desktop_icon", "vetedge.json")).insert(ignore_permissions=True)
	else:
		frappe.db.set_value(
			"Desktop Icon",
			"VetEdge",
			{
				"app": "vetedge",
				"hidden": 0,
				"icon_type": "Link",
				"link_type": "Workspace Sidebar",
				"link_to": "VetEdge",
				"link": "",
				"logo_url": "/assets/vetedge/images/vetedge-app-icon.png",
				"standard": 1,
			},
			update_modified=False,
		)
	frappe.cache.delete_key("desktop_icons")
	frappe.cache.delete_key("bootinfo")


def _load_standard_doc(*file_parts: str) -> dict:
	file_path = frappe.get_app_path("vetedge", *file_parts)
	with open(file_path, encoding="utf-8") as handle:
		return json.load(handle)
