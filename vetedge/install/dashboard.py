from __future__ import annotations

import json
import os

import frappe
from frappe.modules.import_file import import_file_by_path


SIDEBAR_SYNC_IGNORED_FIELDS = {"name", "doctype", "creation", "modified", "modified_by", "owner", "docstatus", "idx"}
VETEDGE_DESK_ROUTE = "/desk/vetedge"
HOSPITALISATION_OPERATIONS_PAGE = "vetedge-hospitalisation-operations"
RETIRED_HOSPITALISATION_DASHBOARD_PAGE = "veterinary-hospitalisation-dashboard"
FRONT_DESK_PAGE_ROUTES = {
	"Appointment Queue": "vetedge-front-desk-queue",
	"Guest Booking Requests": "vetedge-front-desk-guest-bookings",
	"Missed Appointments": "vetedge-front-desk-missed-appointments",
}
BILLING_CENTER_SECTION_VISIBILITY = (
	"eval: frappe.user.has_role('System Manager') || frappe.user.has_role('VetEdge Administrator') || "
	"frappe.user.has_role('VetEdge Front Desk') || frappe.user.has_role('VetEdge Doctor') || "
	"frappe.user.has_role('Veterinary Nurse') || frappe.user.has_role('Dispensary User') || "
	"frappe.user.has_role('Branch Manager') || frappe.user.has_role('Accounts/Cashier') || "
	"frappe.user.has_role('Accounts User') || frappe.user.has_role('Accounts Manager') || "
	"frappe.user.has_role('Sales Manager')"
)
BILLING_CENTER_WORKSPACE_VISIBILITY = (
	"eval: frappe.user.has_role('System Manager') || frappe.user.has_role('VetEdge Administrator') || "
	"frappe.user.has_role('VetEdge Front Desk') || frappe.user.has_role('Branch Manager') || "
	"frappe.user.has_role('Accounts/Cashier') || frappe.user.has_role('Accounts User')"
)

OPTIONAL_COREDGE_WORKSPACE_DOCTYPE_LINKS = {
	"CoreEdge Settings",
	"CoreEdge Product Activation",
	"CoreEdge Tenant",
	"CoreEdge Access Decision Log",
	"CoreEdge Branch Session",
	"CoreEdge Context Switch Log",
}

SIDEBAR_TARGET_DOCTYPES = {
	"DocType": "DocType",
	"Page": "Page",
	"Report": "Report",
}

REMOVED_STANDARD_PAGES = {
	RETIRED_HOSPITALISATION_DASHBOARD_PAGE,
}

# The obsolete Hospitalisation Dashboard must not reappear during recurring
# standard sidebar synchronization. Its position is reused by the Operations
# workbench when the new standard Page is available.
REMOVED_SIDEBAR_LINKS = {
	("Page", RETIRED_HOSPITALISATION_DASHBOARD_PAGE),
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


def _sidebar_target_exists(link_type: str | None, link_to: str | None) -> bool:
	if not link_to:
		return True
	target_doctype = SIDEBAR_TARGET_DOCTYPES.get(str(link_type or ""))
	if not target_doctype:
		return True
	try:
		return bool(frappe.db.exists(target_doctype, str(link_to)))
	except Exception:
		return False


def _coreedge_available() -> bool:
	return "coreedge" in _installed_apps()


def _should_keep_sidebar_item(item) -> bool:
	link_to = item.get("link_to") if isinstance(item, dict) else getattr(item, "link_to", None)
	link_type = item.get("link_type") if isinstance(item, dict) else getattr(item, "link_type", None)
	if not link_to:
		return True

	if (str(link_type or ""), str(link_to)) in REMOVED_SIDEBAR_LINKS:
		return False

	if link_to in OPTIONAL_COREDGE_WORKSPACE_DOCTYPE_LINKS or str(link_to).startswith("CoreEdge "):
		if not (_coreedge_available() and _doctype_exists(link_to)):
			return False

	return _sidebar_target_exists(link_type, link_to)


def _replace_retired_hospitalisation_dashboard(items: list[dict]) -> list[dict]:
	"""Keep the old dashboard retired while preserving its sidebar position.

	The checked-in sidebar still contains the historical dashboard item for
	backward-compatible standard-file history. At runtime/migrate we replace that
	item with the EdgeSuite Hospitalisation Operations Page once the Page exists.
	"""
	result = []
	operations_available = _sidebar_target_exists("Page", HOSPITALISATION_OPERATIONS_PAGE)
	for item in items:
		link_type = str(item.get("link_type") or "")
		link_to = str(item.get("link_to") or "")
		if (link_type, link_to) != ("Page", RETIRED_HOSPITALISATION_DASHBOARD_PAGE):
			result.append(item)
			continue
		if not operations_available:
			continue
		replacement = dict(item)
		replacement.update(
			{
				"label": "Hospitalisation Operations",
				"link_to": HOSPITALISATION_OPERATIONS_PAGE,
				"link_type": "Page",
				"icon": "hospital",
			}
		)
		result.append(replacement)
	return result


def _front_desk_boarding_item(template: dict | None = None) -> dict:
	item = dict(template or {})
	item.update(
		{
			"child": 1,
			"collapsible": 0,
			"icon": "hotel",
			"indent": 0,
			"keep_closed": 0,
			"label": "Pet Boarding Booking",
			"link_to": "Pet Boarding Booking",
			"link_type": "DocType",
			"show_arrow": 0,
			"type": "Link",
		}
	)
	return item


def _patients_navigation_items(template: dict | None = None) -> list[dict]:
	"""Build the dedicated Patients navigation group without broadening visibility."""
	if not template:
		return []

	visibility = template.get("display_depends_on")
	section = {
		"child": 0,
		"collapsible": 1,
		"icon": "users-round",
		"indent": 1,
		"keep_closed": 0,
		"label": "Patients",
		"link_type": "DocType",
		"show_arrow": 0,
		"type": "Section Break",
	}
	if visibility:
		section["display_depends_on"] = visibility

	item = dict(template)
	item.update(
		{
			"child": 1,
			"collapsible": 0,
			"icon": "users-round",
			"indent": 0,
			"keep_closed": 0,
			"label": "Patients",
			"link_to": "Veterinary Patient",
			"link_type": "DocType",
			"show_arrow": 0,
			"type": "Link",
		}
	)
	return [section, item]


def _billing_link(
	label: str,
	link_to: str,
	link_type: str,
	icon: str,
	*,
	template: dict | None = None,
	display_depends_on: str | None = None,
) -> dict:
	item = dict(template or {})
	item.update(
		{
			"child": 1,
			"collapsible": 0,
			"icon": icon,
			"indent": 0,
			"keep_closed": 0,
			"label": label,
			"link_to": link_to,
			"link_type": link_type,
			"show_arrow": 0,
			"type": "Link",
		}
	)
	if display_depends_on:
		item["display_depends_on"] = display_depends_on
	return item


def _billing_center_items(templates: dict[str, dict] | None = None) -> list[dict]:
	templates = templates or {}
	section = {
		"child": 0,
		"collapsible": 1,
		"indent": 1,
		"keep_closed": 1,
		"label": "Billing Center",
		"link_type": "DocType",
		"show_arrow": 0,
		"type": "Section Break",
		"display_depends_on": BILLING_CENTER_SECTION_VISIBILITY,
	}
	return [
		section,
		_billing_link("Customers", "Customer", "DocType", "customer", template=templates.get("Customer")),
		_billing_link("Sales Invoice", "Sales Invoice", "DocType", "receipt-text", template=templates.get("Sales Invoice")),
		_billing_link("Payment Entry", "Payment Entry", "DocType", "money-coins-1", template=templates.get("Payment Entry")),
		_billing_link(
			"Billing Session",
			"Veterinary Billing Session",
			"DocType",
			"file-text",
			template=templates.get("Billing Session"),
			display_depends_on=BILLING_CENTER_WORKSPACE_VISIBILITY,
		),
		_billing_link(
			"Billing Center",
			"vetedge-billing-center",
			"Page",
			"landmark",
			template=templates.get("Billing Center"),
			display_depends_on=BILLING_CENTER_WORKSPACE_VISIBILITY,
		),
	]


def _navigation_templates(items: list[dict]) -> tuple[dict[str, dict], dict | None, dict | None]:
	billing_templates: dict[str, dict] = {}
	boarding_template = None
	patients_template = None
	for original in items:
		if original.get("type") != "Link":
			continue
		label = str(original.get("label") or "").strip()
		if label in {"Customer", "Customers"}:
			billing_templates["Customer"] = dict(original)
		elif label in {"Sales Invoice", "Payment Entry", "Billing Session", "Billing Center"}:
			billing_templates[label] = dict(original)
		if label == "Pet Boarding Booking":
			boarding_template = dict(original)
		if label == "Patients":
			patients_template = dict(original)
	return billing_templates, boarding_template, patients_template


def _organize_veterinary_navigation(items: list[dict]) -> list[dict]:
	"""Apply the VFD-BILL-01 menu contract without disturbing unrelated sections.

	The checked-in sidebar is still useful as the long-lived standard source, but
	this transformation is authoritative at install/migrate time. It is deliberately
	idempotent because recurring sidebar synchronization must never recreate the old
	Front Desk accounting links, duplicate Boarding, restore Grooming Appointment,
	or move Patients back under appointment/front-desk work. Existing link visibility
	rules are preserved when links move sections.
	"""
	billing_templates, boarding_template, patients_template = _navigation_templates(items)
	result: list[dict] = []
	current_section = ""
	front_desk_seen = False
	billing_inserted = False
	boarding_inserted = False
	patients_inserted = False
	skip_billing_children = False
	skip_patients_children = False

	def insert_patients() -> None:
		nonlocal patients_inserted
		if patients_inserted:
			return
		result.extend(_patients_navigation_items(patients_template))
		patients_inserted = True

	def insert_billing_center() -> None:
		nonlocal billing_inserted
		if billing_inserted:
			return
		result.extend(_billing_center_items(billing_templates))
		billing_inserted = True

	for original in items:
		item = dict(original)
		label = str(item.get("label") or "").strip()
		is_section = item.get("type") == "Section Break" and not int(item.get("child") or 0)

		if is_section:
			if not patients_inserted:
				insert_patients()
			if current_section == "Front Desk" and label != "Front Desk":
				insert_billing_center()
			if label == "Patients":
				current_section = "Patients"
				skip_patients_children = True
				skip_billing_children = False
				continue
			if label == "Billing Center":
				current_section = "Billing Center"
				skip_billing_children = True
				skip_patients_children = False
				continue
			current_section = label
			skip_billing_children = False
			skip_patients_children = False
			if label == "Front Desk":
				front_desk_seen = True
			result.append(item)
			continue

		if skip_billing_children or current_section == "Billing Center":
			continue
		if skip_patients_children or current_section == "Patients":
			continue

		# Patients is a primary product resource, not an appointment sub-workflow.
		# Its dedicated group is inserted once before Dashboard and flattened into
		# a direct sidebar control by the shared navigation hardening layer.
		if label == "Patients":
			continue

		# Grooming appointment is an implementation detail of the appointment flow;
		# keep its DocType/history intact but remove the duplicate product-menu entry.
		if label == "Pet Grooming Appointment":
			continue

		# Boarding Booking is a Front Desk booking activity. Remove any historical
		# copy first, then add exactly one copy immediately after Appointments.
		if label == "Pet Boarding Booking":
			continue

		if current_section == "Front Desk":
			if label in {"Customer", "Customers", "Sales Invoice", "Payment Entry"}:
				continue
			if label in FRONT_DESK_PAGE_ROUTES:
				item["link_type"] = "Page"
				item["link_to"] = FRONT_DESK_PAGE_ROUTES[label]
			if label == "Appointments":
				result.append(item)
				result.append(_front_desk_boarding_item(boarding_template))
				boarding_inserted = True
				continue

		result.append(item)

	if not patients_inserted:
		patient_items = _patients_navigation_items(patients_template)
		if patient_items:
			result[0:0] = patient_items

	if front_desk_seen and not billing_inserted:
		insert_billing_center()

	# Defensive fallback for unusually customized source files that lost the
	# Appointments row but still contain Front Desk. This keeps Boarding visible
	# without duplicating it in another section.
	if front_desk_seen and not boarding_inserted:
		front_index = next((index for index, row in enumerate(result) if str(row.get("label") or "").strip() == "Front Desk"), -1)
		if front_index >= 0:
			insert_at = front_index + 1
			while insert_at < len(result) and int(result[insert_at].get("child") or 0):
				insert_at += 1
			result.insert(insert_at, _front_desk_boarding_item(boarding_template))

	return result


def _prepend_veterinary_home_link(items: list[dict]) -> list[dict]:
	"""Make Veterinary Home the first navigable sidebar item.

	Frappe's legacy Desktop Icons screen resolves a Workspace Sidebar launcher to
	the sidebar's first Link. A relative URL is intentionally used here: Frappe
	keeps relative routes in the current tab, while External Desktop Icon routes
	are expanded to an absolute URL and opened in a new tab.
	"""
	home = {
		"child": 0,
		"collapsible": 0,
		"indent": 0,
		"keep_closed": 0,
		"label": "Veterinary Home",
		"link_type": "URL",
		"show_arrow": 0,
		"type": "Link",
		"url": VETEDGE_DESK_ROUTE,
		"icon": "home",
	}
	remaining = []
	for item in items:
		label = str(item.get("label") or "").strip()
		url = str(item.get("url") or "").strip()
		link_to = str(item.get("link_to") or "").strip()
		if label == "Veterinary Home" or url == VETEDGE_DESK_ROUTE or link_to == "vetedge":
			continue
		remaining.append(item)
	return [home, *remaining]


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

SIDEBAR_PAGE_FILES = (
	("veterinary", "page", "veterinary_financial_dashboard", "veterinary_financial_dashboard.json"),
	("veterinary", "page", "vetedge_hospitalisation_operations", "vetedge_hospitalisation_operations.json"),
	("veterinary", "page", "vetedge_front_desk_queue", "vetedge_front_desk_queue.json"),
	("veterinary", "page", "vetedge_front_desk_guest_bookings", "vetedge_front_desk_guest_bookings.json"),
	("veterinary", "page", "vetedge_front_desk_missed_appointments", "vetedge_front_desk_missed_appointments.json"),
	("veterinary", "page", "vetedge_billing_center", "vetedge_billing_center.json"),
)


def ensure_financial_dashboard() -> None:
	for file_parts in FINANCIAL_DASHBOARD_FILES:
		file_path = frappe.get_app_path("vetedge", *file_parts)
		if os.path.exists(file_path):
			import_file_by_path(file_path, force=True, ignore_version=True)

	cleanup_removed_pages()
	ensure_vetedge_workspace_sidebar()
	cleanup_legacy_workspace_sidebars()
	cleanup_legacy_financial_workspace()
	ensure_vetedge_desktop_icon()


def cleanup_removed_pages() -> None:
	for page in REMOVED_STANDARD_PAGES:
		frappe.delete_doc_if_exists("Page", page, force=1)


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

	standard_items = _replace_retired_hospitalisation_dashboard(standard_doc.get("items") or [])
	standard_items = _organize_veterinary_navigation(standard_items)
	standard_items = _prepend_veterinary_home_link(standard_items)
	kept_items = [item for item in standard_items if _should_keep_sidebar_item(item)]

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
		frappe.delete_doc("Workspace Sidebar", "Veterinary", force=True)

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
