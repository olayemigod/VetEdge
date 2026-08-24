from __future__ import annotations

import os

import frappe
from frappe.modules.import_file import import_file_by_path


REGULATORY_PAGE = "vetedge-regulatory-reporting"
SIDEBAR_NAME = "VetEdge"
SECTION_LABEL = "Regulatory Reporting"
LINK_LABEL = "VCN / NADIS Reports"


def ensure_regulatory_reporting_navigation() -> None:
    """Keep the regulatory workbench discoverable after standard sidebar sync.

    `ensure_financial_dashboard()` refreshes the standard VetEdge sidebar on
    every migrate. This post-sync adapter therefore runs immediately afterwards
    and idempotently inserts the regulatory section without changing the
    checked-in historical sidebar migration contract.
    """
    if not frappe.db.exists("DocType", "Page"):
        return
    if not frappe.db.exists("Page", REGULATORY_PAGE):
        page_file = frappe.get_app_path(
            "vetedge",
            "veterinary",
            "page",
            "vetedge_regulatory_reporting",
            "vetedge_regulatory_reporting.json",
        )
        if os.path.exists(page_file):
            import_file_by_path(page_file, force=True, ignore_version=True)
    if not frappe.db.exists("Page", REGULATORY_PAGE):
        return
    if not frappe.db.exists("DocType", "Workspace Sidebar") or not frappe.db.exists("Workspace Sidebar", SIDEBAR_NAME):
        return

    sidebar = frappe.get_doc("Workspace Sidebar", SIDEBAR_NAME)
    items = list(sidebar.get("items") or [])
    if any(getattr(item, "link_type", None) == "Page" and getattr(item, "link_to", None) == REGULATORY_PAGE for item in items):
        return

    section = {
        "type": "Section Break",
        "label": SECTION_LABEL,
        "link_type": "DocType",
        "child": 0,
        "collapsible": 1,
        "indent": 1,
        "keep_closed": 1,
        "show_arrow": 0,
    }
    link = {
        "type": "Link",
        "label": LINK_LABEL,
        "link_type": "Page",
        "link_to": REGULATORY_PAGE,
        "icon": "shield-check",
        "child": 1,
        "collapsible": 0,
        "indent": 0,
        "keep_closed": 0,
        "show_arrow": 0,
        "display_depends_on": "eval: frappe.user.has_role('System Manager') || frappe.user.has_role('VetEdge Administrator') || frappe.user.has_role('VetEdge Doctor') || frappe.user.has_role('Veterinary Nurse') || frappe.user.has_role('Branch Manager')",
    }

    insert_at = len(items)
    for index, item in enumerate(items):
        if getattr(item, "type", None) == "Section Break" and getattr(item, "label", None) == "Configuration":
            insert_at = index
            break

    payload = []
    for index, item in enumerate(items):
        if index == insert_at:
            payload.extend((section, link))
        payload.append(item.as_dict() if hasattr(item, "as_dict") else item)
    if insert_at == len(items):
        payload.extend((section, link))

    sidebar.set("items", payload)
    sidebar.save(ignore_permissions=True)
    frappe.cache.delete_key("bootinfo")
