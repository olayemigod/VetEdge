from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def read(path: str) -> str:
    return (ROOT / path).read_text(encoding="utf-8")


def test_home_drilldown_uses_permission_safe_display_enrichment():
    service = read("vetedge/services/home_postqa.py")

    assert "home_service.get_metric_drilldown(" in service
    assert "enrich_link_display_values(rows, enriched_columns, replace_values=True)" in service
    assert 'resolved["options"] = field.options or ""' in service
    assert "ignore_permissions" not in service
    assert "frappe.db.sql" not in service


def test_home_record_clicks_preserve_exact_edgesuite_deep_links():
    controller = read("vetedge/veterinary/page/vetedge/vetedge.js")

    assert 'vetedge.services.home_postqa.get_metric_drilldown' in controller
    assert '/desk/vetedge-clinical-workspace?consultation=${record}' in controller
    assert '/desk/vetedge-resource-center?resource=appointments&name=${record}' in controller
    assert '/desk/vetedge-front-desk-action-center?tab=missed&name=${record}' in controller
    assert '/desk/vetedge-resource-center?resource=lab-orders&name=${record}' in controller
    assert '/desk/sales-invoice/${record}' in controller
    assert "window.location.assign(route);" in controller
    assert "installVetEdgeHomeFinalQaFixes(wrapper.vue_app?.view);" in controller


def test_downstream_pages_accept_the_record_query_contract():
    clinical = read("vetedge/public/js/vetedge_clinical_workspace/VetEdgeClinicalWorkspace.vue")
    front_desk = read(
        "vetedge/veterinary/page/vetedge_front_desk_action_center/vetedge_front_desk_action_center.js"
    )
    resource_bundle = read("vetedge/public/js/vetedge_resource_center.bundle.js")

    assert 'params.get("consultation")' in clinical
    assert "params.get('name')" in front_desk
    assert "view.openMissedDetail?.({ name: requested.name })" in front_desk
    assert "const requestedName = valueFrom(requestedRoute, 'name');" in resource_bundle
    assert "resourceView.openClinicalRecord?.({ name: state.name });" in resource_bundle
    assert "quickEditorView?.open?.({" in resource_bundle


def test_sidebar_veterinary_home_is_a_true_direct_item_not_a_hidden_accordion():
    hardening = read("vetedge/public/js/vetedge_postqa_navigation_hardening.js")

    assert 'const HOME_LABEL = "Veterinary Home";' in hardening
    assert 'homeSection.querySelector(".edge-sidebar__items .edge-sidebar-item")' in hardening
    assert 'directItem.classList.add("edge-sidebar-item")' in hardening
    assert "setVisibleLabel(item, HOME_LABEL);" in hardening
    assert 'item.setAttribute("aria-label", HOME_LABEL)' in hardening
    assert "homeSection.replaceWith(directItem);" in hardening
    assert 'item.removeAttribute("aria-expanded")' in hardening
    assert "nestedItems.hidden = true" not in hardening


def test_sidebar_primary_groups_use_veterinary_operational_labels_and_order():
    hardening = read("vetedge/public/js/vetedge_postqa_navigation_hardening.js")

    assert 'Clinical: "Clinical Operations"' in hardening
    assert '"Front Desk": "Appointments"' in hardening
    assert 'Object.freeze(["Dashboard", "Clinical Operations", "Appointments"])' in hardening
    assert "normalizePrimarySections(shell);" in hardening


def test_veterinary_desktop_icon_opens_new_home_directly():
    icon = json.loads(read("vetedge/desktop_icon/vetedge.json"))
    hooks = read("vetedge/hooks.py")

    assert icon["label"] == "Veterinary"
    assert icon["icon_type"] == "App"
    assert icon["link_type"] == "External"
    assert icon["link"] == "/desk/vetedge"
    assert not icon.get("link_to")
    assert 'app_home = "/desk/vetedge"' in hooks
    assert '"route": app_home' in hooks
    assert "/desk/vetedge-executive-dashboard" not in icon.get("link", "")
