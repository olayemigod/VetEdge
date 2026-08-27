from __future__ import annotations

import os
from typing import Any

import frappe
from frappe.modules.import_file import import_file_by_path


REGULATORY_PAGE = "vetedge-regulatory-reporting"
OUTBREAK_DOCTYPE = "Veterinary Disease Outbreak"
ADMINISTRATION_PAGE = "vetedge-administration"
SIDEBAR_NAME = "VetEdge"
SECTION_LABEL = "Regulatory Reporting"
ADMINISTRATION_SECTION_LABEL = "Administration"
LINK_LABEL = "VCN / NADIS Reports"
OUTBREAK_LINK_LABEL = "Disease Outbreak Register"
ADMINISTRATION_LINK_LABEL = "Administration"
CONFIGURATION_SECTION_LABEL = "Configuration"

# These routes remain available as compatibility aliases, but their individual
# links must not compete with the consolidated EdgeSuite Administration page.
LEGACY_ADMINISTRATION_LINKS = {
    ("DocType", "Veterinary Notification Preference"),
    ("DocType", "Veterinary Notification Log"),
    ("DocType", "Veterinary Role Bundle"),
    ("DocType", "Veterinary License Profile"),
    ("DocType", "Veterinary Notification Item"),
}

CHILD_METADATA_FIELDS = {
    "name",
    "owner",
    "creation",
    "modified",
    "modified_by",
    "docstatus",
    "idx",
    "doctype",
    "parent",
    "parentfield",
    "parenttype",
}

REGULATORY_DISPLAY_DEPENDS_ON = (
    "eval: frappe.user.has_role('System Manager') || "
    "frappe.user.has_role('VetEdge Administrator') || "
    "frappe.user.has_role('VetEdge Doctor') || "
    "frappe.user.has_role('Veterinary Nurse') || "
    "frappe.user.has_role('Branch Manager')"
)
ADMINISTRATION_DISPLAY_DEPENDS_ON = (
    "eval: frappe.user.has_role('System Manager') || "
    "frappe.user.has_role('VetEdge Administrator')"
)


def _section(label: str) -> dict[str, Any]:
    return {
        "type": "Section Break",
        "label": label,
        "link_type": "DocType",
        "child": 0,
        "collapsible": 1,
        "indent": 1,
        "keep_closed": 1,
        "show_arrow": 0,
    }


def _link(
    *,
    label: str,
    link_type: str,
    link_to: str,
    icon: str,
    display_depends_on: str,
) -> dict[str, Any]:
    return {
        "type": "Link",
        "label": label,
        "link_type": link_type,
        "link_to": link_to,
        "icon": icon,
        "child": 1,
        "collapsible": 0,
        "indent": 0,
        "keep_closed": 0,
        "show_arrow": 0,
        "display_depends_on": display_depends_on,
    }


def _row_payload(item: Any) -> dict[str, Any]:
    if hasattr(item, "as_dict"):
        item = item.as_dict()
    payload = dict(item or {})
    return {key: value for key, value in payload.items() if key not in CHILD_METADATA_FIELDS}


def _is_section(item: dict[str, Any], label: str) -> bool:
    return item.get("type") == "Section Break" and item.get("label") == label


def _is_link(item: dict[str, Any], link_type: str, link_to: str) -> bool:
    return item.get("type") == "Link" and item.get("link_type") == link_type and item.get("link_to") == link_to


def _first_section_index(items: list[dict[str, Any]], labels: tuple[str, ...]) -> int:
    for index, item in enumerate(items):
        if item.get("type") == "Section Break" and item.get("label") in labels:
            return index
    return len(items)


def _next_section_index(items: list[dict[str, Any]], start: int) -> int:
    for index in range(start + 1, len(items)):
        if items[index].get("type") == "Section Break":
            return index
    return len(items)


def _normalise_sidebar_items(
    items: list[Any],
    *,
    include_outbreak: bool = True,
    include_administration: bool = True,
) -> list[dict[str, Any]]:
    """Return a deterministic VetEdge sidebar hierarchy.

    Frappe child rows carry persisted ``idx`` and parent metadata. Reusing those
    values while inserting new rows can cause the new regulatory links to be
    interleaved with Configuration children on save. Strip child metadata first,
    remove only VetEdge-managed navigation entries, then rebuild the managed
    blocks at stable section boundaries.
    """

    cleaned = [_row_payload(item) for item in items]
    filtered: list[dict[str, Any]] = []

    for item in cleaned:
        if _is_section(item, SECTION_LABEL):
            continue
        if _is_link(item, "Page", REGULATORY_PAGE):
            continue
        if _is_link(item, "DocType", OUTBREAK_DOCTYPE):
            continue

        if include_administration:
            if _is_section(item, ADMINISTRATION_SECTION_LABEL):
                continue
            if _is_link(item, "Page", ADMINISTRATION_PAGE):
                continue
            if (item.get("link_type"), item.get("link_to")) in LEGACY_ADMINISTRATION_LINKS:
                continue

        filtered.append(item)

    regulatory_block = [
        _section(SECTION_LABEL),
        _link(
            label=LINK_LABEL,
            link_type="Page",
            link_to=REGULATORY_PAGE,
            icon="shield-check",
            display_depends_on=REGULATORY_DISPLAY_DEPENDS_ON,
        ),
    ]
    if include_outbreak:
        regulatory_block.append(
            _link(
                label=OUTBREAK_LINK_LABEL,
                link_type="DocType",
                link_to=OUTBREAK_DOCTYPE,
                icon="alert-triangle",
                display_depends_on=REGULATORY_DISPLAY_DEPENDS_ON,
            )
        )

    configuration_index = _first_section_index(filtered, (CONFIGURATION_SECTION_LABEL,))
    if configuration_index == len(filtered):
        configuration_index = _first_section_index(filtered, ("Platform", "Help & Training"))
    filtered[configuration_index:configuration_index] = regulatory_block

    if include_administration:
        configuration_index = next(
            (
                index
                for index, item in enumerate(filtered)
                if _is_section(item, CONFIGURATION_SECTION_LABEL)
            ),
            -1,
        )
        if configuration_index >= 0:
            administration_index = _next_section_index(filtered, configuration_index)
        else:
            administration_index = _first_section_index(filtered, ("Platform", "Help & Training"))

        administration_block = [
            _section(ADMINISTRATION_SECTION_LABEL),
            _link(
                label=ADMINISTRATION_LINK_LABEL,
                link_type="Page",
                link_to=ADMINISTRATION_PAGE,
                icon="user-cog",
                display_depends_on=ADMINISTRATION_DISPLAY_DEPENDS_ON,
            ),
        ]
        filtered[administration_index:administration_index] = administration_block

    return filtered


def ensure_regulatory_reporting_navigation() -> None:
    """Repair and keep VetEdge regulatory/administration navigation discoverable.

    ``ensure_financial_dashboard`` first refreshes the authoritative VetEdge
    standard sidebar on every install/migrate. This post-sync adapter then
    deterministically establishes the dynamic Regulatory Reporting block and
    the consolidated Administration block without disturbing unrelated groups.
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
    current_payload = [_row_payload(item) for item in list(sidebar.get("items") or [])]
    normalised_payload = _normalise_sidebar_items(
        list(sidebar.get("items") or []),
        include_outbreak=bool(frappe.db.exists("DocType", OUTBREAK_DOCTYPE)),
        include_administration=bool(frappe.db.exists("Page", ADMINISTRATION_PAGE)),
    )

    if current_payload == normalised_payload:
        return

    sidebar.set("items", normalised_payload)
    sidebar.save(ignore_permissions=True)
    frappe.cache.delete_key("bootinfo")
