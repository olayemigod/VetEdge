from __future__ import annotations

import json
import os

import frappe
from frappe.modules.import_file import import_file_by_path


SIDEBAR_SYNC_IGNORED_FIELDS = {"name", "doctype", "creation", "modified", "modified_by", "owner", "docstatus", "idx"}
VETEDGE_DESK_ROUTE = "/app/vetedge-home"

OPTIONAL_COREDGE_WORKSPACE_DOCTYPE_LINKS = {
	"CoreEdge Settings",
	"CoreEdge Product Activation",
	"CoreEdge Tenant",
	"CoreEdge Access Decision Log",
	"CoreEdge Branch Session",
	"CoreEdge Context Switch Log",
}

VETERINARY_HOME_ITEM = {
	"child": 1,
	"collapsible": 0,
	"indent": 0,
	"keep_closed": 0,
	"label": "Veterinary Home",
	"link_to": "vetedge-home",
	"link_type": "Page",
	"show_arrow": 0,
	"type": "Link",
	"icon": "home",
	"display_depends_on": (
		"eval: frappe.user.has_role('System Manager') || "
		"frappe.user.has_role('VetEdge Administrator') || "
		"frappe.user.has_role('VetEdge Doctor') || "
		"frappe.user.has_role('VetEdge Nurse') || "
		"frappe.user.has_role('Veterinary Nurse') || "
		"frappe.user.has_role('VetEdge Front Desk') || "
		"frappe.user.has_role('VetEdge Groomer') || "
		"frappe.user.has_role('Dispensary User') || "
		"frappe.user.has_role('Lab Technician') || "
		"frappe.user.has_role('Branch Manager') || "
		"frappe.user.has_role('Accounts/Cashier') || "
		"frappe.user.has_role('Accounts Manager') || "
		"frappe.user.has_role('Accounts User')"
	),
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


def _with_veterinary_home(items: list[dict]) -> list[dict]:
	cleaned = [item for item in items if item.get("link_to") != "vetedge-home"]
	result: list[dict] = []
	inserted = False
	for item in cleaned:
		result.append(item)
		if (
			not inserted
			and item.get("type") == "Section Break"
			and item.get("label") in {"Dashboard", "Overview"}
		):
			result.append(dict(VETERINARY_HOME_ITEM))
			inserted = True
	if not inserted:
		result.insert(0, dict(VETERINARY_HOME_ITEM))
	return result


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
	("veterinary", "page", "veterinary_hospitalisation_dashboard", "veterinary_hospitalisation_dashboard.json"),
	("veterinary", "page", "kennel_availability_board", "kennel_availability_board.json"),
	("workspace_sidebar", "vetedge.json"),
	("desktop_icon", "vetedge.json"),
)

SIDEBAR_PAGE_FILES = (
	("veterinary", "page", "veterinary_financial_dashboard", "veterinary_financial_dashboard.json"),
	("veterinary", "page", "veterinary_hospitalisation_dashboard", "veterinary_hospitalisation_dashboard.json"),
)


def ensure_financial_dashboard() -> None:
	for file_parts in FINANCIAL_DASHBOARD_FILES:
		file_path = frappe.get_app_path("vetedge", *file_parts)
		if os.path.exists(file_path):
			import_file_by_path(file_path, force=True, ignore_version=True)

	ensure_vetedge_workspace_sidebar()
	cleanup_legacy_workspace_sidebars()
	cleanup_legacy_financial_workspace()
	ensure_vetedge_desktop_icon()


def cleanup_legacy_financial_workspace() -> None:
	if frappe.db.exists("Workspace", "Veterinary Financial Dashboard"):
		frappe.delete_doc_if_exists("Workspace", "Veterinary Financial Dashboard", force=1)


def cleanup_legacy_workspace_sidebars() -> None:
	if not frappe.db.exists("DocType", "Workspace Sidebar"):
		return
	for sidebar in ("Veterinary Hospitalisation Dashboard", "Veterinary Financial Dashboard"):
		if frappe.db.exists("Workspace Sidebar", sidebar):
			frappe.delete_doc("Workspace Sidebar", sidebar, force=True)


def ensure_vetedge_workspace_sidebar() -> None:
	if not frappe.db.exists("DocType", "Workspace Sidebar"):
		return

	_import_standard_files(SIDEBAR_PAGE_FILES)

	# Migrate legacy Veterinary record back to VetEdge if Veterinary exists but VetEdge doesn't
	if frappe.db.exists("Workspace Sidebar", "Veterinary") and not frappe.db.exists("Workspace Sidebar", "VetEdge"):
		frappe.rename_doc("Workspace Sidebar", "Veterinary", "VetEdge", force=True)

	# Clean up duplicate if both exist
	if frappe.db.exists("Workspace Sidebar", "Veterinary") and frappe.db.exists("Workspace Sidebar", "VetEdge"):
		frappe.delete_doc("Workspace Sidebar", "Veterinary", force=True)

	standard_doc = _load_standard_doc("workspace_sidebar", "vetedge.json")
	standard_doc["title"] = "Veterinary"

	standard_items = standard_doc.get("items") or []
	kept_items = _with_veterinary_home([item for item in standard_items if _should_keep_sidebar_item(item)])

	if frappe.db.exists("Workspace Sidebar", "VetEdge"):
		sidebar = frappe.get_doc("Workspace Sidebar", "VetEdge")
		sidebar.set("items", [])
		sidebar.update(_prepare_standard_sidebar_update_payload(standard_doc))
		sidebar.set("items", kept_items)
		sidebar.save(ignore_permissions=True)
		sidebar.db_set("title", "Veterinary")
	else:
		standard_doc["items"] = kept_items
		sidebar = frappe.get_doc(standard_doc)
		if hasattr(sidebar, "set"):
			sidebar.set("items", kept_items)
		else:
			sidebar.items = kept_items
		sidebar.insert(ignore_permissions=True)
		sidebar.db_set("title", "Veterinary")

	if hasattr(frappe, "cache"):
		frappe.cache.delete_key("bootinfo")


def ensure_vetedge_desktop_icon() -> None:
	if not frappe.db.exists("DocType", "Desktop Icon"):
		return

	# Migrate legacy Veterinary record back to VetEdge if Veterinary exists but VetEdge doesn't
	if frappe.db.exists("Desktop Icon", "Veterinary") and not frappe.db.exists("Desktop Icon", "VetEdge"):
		frappe.rename_doc("Desktop Icon", "Veterinary", "VetEdge", force=True)

	# Clean up duplicate if both exist
	if frappe.db.exists("Desktop Icon", "Veterinary") and frappe.db.exists("Desktop Icon", "VetEdge"):
		frappe.delete_doc("Desktop Icon", "Veterinary", force=True)

	from vetedge.services.branding import get_branding

	branding = get_branding()
	default_label = branding.get("app_title") or branding.get("brand_name") or "VetEdge"

	if not frappe.db.exists("Desktop Icon", "VetEdge"):
		icon = frappe.get_doc(_load_standard_doc("desktop_icon", "vetedge.json"))
		icon.insert(ignore_permissions=True)
		icon.db_set("label", default_label)
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
				"label": default_label,
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


def _import_standard_files(file_parts_collection) -> None:
	if not hasattr(frappe, "get_app_path"):
		return
	for file_parts in file_parts_collection:
		file_path = frappe.get_app_path("vetedge", *file_parts)
		if os.path.exists(file_path):
			import_file_by_path(file_path, force=True, ignore_version=True)
