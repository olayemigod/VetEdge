from __future__ import annotations

import unittest

from vetedge.install.regulatory_reporting import (
    ADMINISTRATION_PAGE,
    CHILD_METADATA_FIELDS,
    LEGACY_ADMINISTRATION_LINKS,
    OUTBREAK_DOCTYPE,
    REGULATORY_PAGE,
    _normalise_sidebar_items,
)


def section(label: str, idx: int) -> dict:
    return {
        "doctype": "Workspace Sidebar Item",
        "name": f"section-{idx}",
        "parent": "VetEdge",
        "parentfield": "items",
        "parenttype": "Workspace Sidebar",
        "idx": idx,
        "type": "Section Break",
        "label": label,
        "link_type": "DocType",
        "child": 0,
        "collapsible": 1,
        "indent": 1,
        "keep_closed": 1,
        "show_arrow": 0,
    }


def link(label: str, link_type: str, link_to: str, idx: int) -> dict:
    return {
        "doctype": "Workspace Sidebar Item",
        "name": f"link-{idx}",
        "parent": "VetEdge",
        "parentfield": "items",
        "parenttype": "Workspace Sidebar",
        "idx": idx,
        "type": "Link",
        "label": label,
        "link_type": link_type,
        "link_to": link_to,
        "child": 1,
        "collapsible": 0,
        "indent": 0,
        "keep_closed": 0,
        "show_arrow": 0,
    }


def section_labels(items: list[dict]) -> list[str]:
    return [item["label"] for item in items if item.get("type") == "Section Break"]


def children_of(items: list[dict], section_label: str) -> list[dict]:
    start = next(index for index, item in enumerate(items) if item.get("type") == "Section Break" and item.get("label") == section_label)
    result = []
    for item in items[start + 1 :]:
        if item.get("type") == "Section Break":
            break
        result.append(item)
    return result


class TestVetEdgeSidebarRegrouping(unittest.TestCase):
    def malformed_sidebar(self) -> list[dict]:
        # Mirrors the browser defect: regulatory links have been persisted among
        # Configuration children and retain stale child-row idx metadata.
        return [
            section("Veterinary Masters", 1),
            link("Vaccines", "DocType", "Veterinary Vaccine", 2),
            section("Regulatory Reporting", 3),
            link("Settings", "DocType", "Veterinary Settings", 4),
            link("VCN / NADIS Reports", "Page", REGULATORY_PAGE, 5),
            link("Branch", "DocType", "Branch", 6),
            link("Disease Outbreak Register", "DocType", OUTBREAK_DOCTYPE, 7),
            section("Configuration", 8),
            link("Care Locations", "DocType", "Veterinary Care Location", 9),
            link("Kennel", "DocType", "Kennel", 10),
            link("Cost Center", "DocType", "Cost Center", 11),
            link("Branch User Assignment", "DocType", "Branch User Assignment", 12),
            link("Branch Practitioner Assignment", "DocType", "Branch Practitioner Assignment", 13),
            link("Notification Preference", "DocType", "Veterinary Notification Preference", 14),
            link("Notification Log", "DocType", "Veterinary Notification Log", 15),
            link("Role Bundle", "DocType", "Veterinary Role Bundle", 16),
            link("License Profile", "DocType", "Veterinary License Profile", 17),
            link("Notification Items", "DocType", "Veterinary Notification Item", 18),
            section("Platform", 19),
            link("Platform Settings", "DocType", "CoreEdge Settings", 20),
            section("Help & Training", 21),
            link("Training Centre", "Page", "veterinary-training-centre", 22),
        ]

    def test_regroups_managed_sections_at_stable_boundaries(self):
        result = _normalise_sidebar_items(self.malformed_sidebar())

        self.assertEqual(
            section_labels(result),
            ["Veterinary Masters", "Regulatory Reporting", "Configuration", "Administration", "Platform", "Help & Training"],
        )
        self.assertEqual(
            [(item.get("label"), item.get("link_type"), item.get("link_to")) for item in children_of(result, "Regulatory Reporting")],
            [
                ("VCN / NADIS Reports", "Page", REGULATORY_PAGE),
                ("Disease Outbreak Register", "DocType", OUTBREAK_DOCTYPE),
            ],
        )
        self.assertEqual(
            [(item.get("label"), item.get("link_type"), item.get("link_to")) for item in children_of(result, "Administration")],
            [("Administration", "Page", ADMINISTRATION_PAGE)],
        )

    def test_configuration_keeps_configuration_only_and_removes_legacy_admin_links(self):
        result = _normalise_sidebar_items(self.malformed_sidebar())
        config_targets = {item.get("link_to") for item in children_of(result, "Configuration")}

        self.assertTrue(
            {
                "Veterinary Care Location",
                "Kennel",
                "Cost Center",
                "Branch User Assignment",
                "Branch Practitioner Assignment",
            }.issubset(config_targets)
        )
        for legacy_target in {link_to for _link_type, link_to in LEGACY_ADMINISTRATION_LINKS}:
            self.assertNotIn(legacy_target, config_targets)
            self.assertFalse(any(item.get("link_to") == legacy_target for item in result))

    def test_normalisation_strips_child_metadata_and_is_idempotent(self):
        first = _normalise_sidebar_items(self.malformed_sidebar())
        second = _normalise_sidebar_items(first)

        self.assertEqual(first, second)
        for item in first:
            self.assertFalse(CHILD_METADATA_FIELDS.intersection(item))

        targets = [(item.get("link_type"), item.get("link_to")) for item in first if item.get("type") == "Link"]
        self.assertEqual(targets.count(("Page", REGULATORY_PAGE)), 1)
        self.assertEqual(targets.count(("DocType", OUTBREAK_DOCTYPE)), 1)
        self.assertEqual(targets.count(("Page", ADMINISTRATION_PAGE)), 1)

    def test_legacy_admin_links_are_preserved_if_consolidated_page_is_unavailable(self):
        result = _normalise_sidebar_items(self.malformed_sidebar(), include_administration=False)
        targets = {(item.get("link_type"), item.get("link_to")) for item in result}

        self.assertTrue(LEGACY_ADMINISTRATION_LINKS.issubset(targets))
        self.assertNotIn(("Page", ADMINISTRATION_PAGE), targets)
        self.assertNotIn("Administration", section_labels(result))


if __name__ == "__main__":
    unittest.main()
