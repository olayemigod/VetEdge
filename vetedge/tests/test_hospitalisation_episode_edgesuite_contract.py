from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
PAGE_DIR = ROOT / "vetedge" / "veterinary" / "page" / "vetedge_hospitalisation_episode"
PAGE_JS = PAGE_DIR / "vetedge_hospitalisation_episode.js"
PAGE_JSON = PAGE_DIR / "vetedge_hospitalisation_episode.json"
BUNDLE = ROOT / "vetedge" / "public" / "js" / "vetedge_hospitalisation_episode.bundle.js"
COMPONENT = (
    ROOT
    / "vetedge"
    / "public"
    / "js"
    / "vetedge_hospitalisation_episode"
    / "VetEdgeHospitalisationEpisode.vue"
)
OPERATIONS_COMPONENT = (
    ROOT
    / "vetedge"
    / "public"
    / "js"
    / "vetedge_hospitalisation_operations"
    / "VetEdgeHospitalisationOperations.vue"
)
SERVICE = ROOT / "vetedge" / "services" / "hospitalisation_episode.py"


def read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def test_hospitalisation_episode_page_and_bundle_exist():
    assert PAGE_JS.exists()
    assert PAGE_JSON.exists()
    assert BUNDLE.exists()
    assert COMPONENT.exists()

    page = read(PAGE_JS)
    bundle = read(BUNDLE)
    component = read(COMPONENT)

    assert "vetedge_hospitalisation_episode.bundle.js" in page
    assert "new URLSearchParams(window.location.search" in page
    assert "params.get('name')" in page
    assert "mountVetEdgeHospitalisationEpisode" in page
    assert "VetEdgeHospitalisationEpisode.vue" in bundle
    assert "applyWorkspaceSafety" in bundle
    assert "<EdgeAppShell" in component
    assert "<EdgePageLayout" in component
    assert "Open Native Form" in component


def test_hospitalisation_episode_preserves_shared_edgesuite_navigation_shell():
    component = read(COMPONENT)

    assert ".edge-sidebar" not in component
    assert ".edge-shell-sidebar" not in component
    assert ".edge-shell-body" not in component
    assert "display: none !important" not in component


def test_hospitalisation_operations_drills_into_edgesuite_episode_with_query_preserved():
    component = read(OPERATIONS_COMPONENT)

    assert "/desk/vetedge-hospitalisation-episode?name=${encodeURIComponent(row.hospitalisation)}" in component
    assert "window.location.assign(`/desk/vetedge-hospitalisation-episode?name=" in component
    assert "frappe.set_route('Form', 'Veterinary Hospitalisation', row.hospitalisation)" not in component


def test_hospitalisation_episode_service_is_permission_and_branch_aware():
    service = read(SERVICE)

    for contract in (
        "require_internal_user()",
        'doc.check_permission("write" if write else "read")',
        "validate_hospitalisation_branch_access(doc)",
        "_assert_not_stale",
        "get_hospitalisation_episode",
        "save_hospitalisation_episode_context",
        "add_hospitalisation_activity",
        "add_hospitalisation_vitals",
        "add_hospitalisation_vaccination",
        "add_hospitalisation_lab_order",
        "search_hospitalisation_episode_options",
        "perform_hospitalisation_episode_action",
    ):
        assert contract in service

    assert "ignore_permissions" not in service


def test_hospitalisation_episode_reuses_authoritative_hospitalisation_services():
    service = read(SERVICE)

    for contract in (
        "service.admit_hospitalisation(name)",
        "service.get_hospitalisation_discharge_readiness(name)",
        "service.get_hospitalisation_stock_posting_preview",
        "service.assign_hospitalisation_care_location",
        "service.release_hospitalisation_care_location",
        "service.post_hospitalisation_activity_stock",
        "service.build_hospitalisation_charge_items(name)",
        "service.sync_hospitalisation_charges_to_invoice",
        "service.check_hospitalisation_payment_gate(name)",
        "service.discharge_hospitalisation",
        "force=False",
    ):
        assert contract in service


def test_hospitalisation_episode_uses_bounded_context_searches():
    service = read(SERVICE)

    assert "_bounded_limit(page_length)" in service
    assert 'if field == "care_location"' in service
    assert '"branch": doc.get("service_branch")' in service
    assert 'if field == "practitioner"' in service
    assert 'if field == "vaccine"' in service
    assert 'if field == "lab_test"' in service
    assert 'if field == "item"' in service


def test_hospitalisation_episode_ui_uses_server_facade_for_mutations():
    component = read(COMPONENT)

    for api in (
        "hospitalisation_episode.get_hospitalisation_episode",
        "hospitalisation_episode.save_hospitalisation_episode_context",
        "hospitalisation_episode.add_hospitalisation_activity",
        "hospitalisation_episode.add_hospitalisation_vitals",
        "hospitalisation_episode.add_hospitalisation_vaccination",
        "hospitalisation_episode.add_hospitalisation_lab_order",
        "hospitalisation_episode.perform_hospitalisation_episode_action",
    ):
        assert api in component

    # Accounting and stock truth stay on the backend. The Vue workspace must
    # not construct ERPNext financial or stock documents itself.
    assert "frappe.new_doc('Sales Invoice'" not in component
    assert 'frappe.new_doc("Sales Invoice"' not in component
    assert "frappe.new_doc('Stock Entry'" not in component
    assert 'frappe.new_doc("Stock Entry"' not in component
