from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
OPERATIONS_PAGE = (
    ROOT
    / "vetedge"
    / "veterinary"
    / "page"
    / "vetedge_hospitalisation_operations"
    / "vetedge_hospitalisation_operations.js"
)
OPERATIONS_BUNDLE = ROOT / "vetedge" / "public" / "js" / "vetedge_hospitalisation_operations.bundle.js"
SIDEBAR_ALIGNMENT = ROOT / "vetedge" / "public" / "js" / "vetedge_sidebar_qa_alignment.js"
EPISODE_COMPONENT = (
    ROOT
    / "vetedge"
    / "public"
    / "js"
    / "vetedge_hospitalisation_episode"
    / "VetEdgeHospitalisationEpisode.vue"
)


def read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def test_operations_page_hosts_selected_episode_without_changing_page_identity():
    page = read(OPERATIONS_PAGE)

    assert "frappe.set_route('vetedge-hospitalisation-operations', hospitalisation)" in page
    assert "/desk/vetedge-hospitalisation-operations/${encodeURIComponent(hospitalisation)}" in page
    assert "wrapper.operations_vue_app" in page
    assert "wrapper.episode_vue_app" in page
    assert "showHospitalisationWorkspace(wrapper, 'episode')" in page
    assert "view.openHospitalisationEpisode = openHospitalisationEpisodeRoute" in page
    assert "view.backToOperations = () => routeToHospitalisationOperations()" in page
    assert "else if (!view.dirty)" in page


def test_operations_bundle_cannot_fall_back_to_old_episode_destination():
    bundle = read(OPERATIONS_BUNDLE)

    assert "VetEdgeHospitalisationOperations.methods.openHospitalisationEpisode = openHospitalisationInOperations" in bundle
    assert "window.frappe.set_route('vetedge-hospitalisation-operations', hospitalisation)" in bundle
    assert "/desk/vetedge-hospitalisation-operations/${encodeURIComponent(hospitalisation)}" in bundle
    assert "/app/vetedge-hospitalisation-episode" not in bundle
    assert "/desk/vetedge-hospitalisation-episode" not in bundle


def test_sidebar_exposes_operations_not_native_hospitalisation_list():
    alignment = read(SIDEBAR_ALIGNMENT)

    assert 'const HOSPITALISATION_DOCTYPE = "Veterinary Hospitalisation";' in alignment
    assert 'const HOSPITALISATION_OPERATIONS_ROUTE = "/desk/vetedge-hospitalisation-operations";' in alignment
    assert "function suppressNativeHospitalisationSidebarSource()" in alignment
    assert "sidebar.items = filtered" in alignment
    assert "function removeNativeHospitalisationSidebarItems(shell)" in alignment
    assert 'label === "Hospitalisations"' in alignment
    assert "String(item?.link_to || item?.linkTo || \"\") === HOSPITALISATION_DOCTYPE" in alignment
    assert 'if (linkType === "DocType" && linkTo === HOSPITALISATION_DOCTYPE) return HOSPITALISATION_OPERATIONS_ROUTE;' in alignment


def test_legacy_episode_and_native_list_routes_recover_to_operations_but_native_form_remains_available():
    alignment = read(SIDEBAR_ALIGNMENT)
    episode = read(EPISODE_COMPONENT)

    assert 'const LEGACY_HOSPITALISATION_EPISODE_ROUTE = "/desk/vetedge-hospitalisation-episode";' in alignment
    assert "function hospitalisationTargetFromLegacyRoute(route)" in alignment
    assert "if (path === nativeListPath) return HOSPITALISATION_OPERATIONS_ROUTE;" in alignment
    assert "path.startsWith(`${LEGACY_HOSPITALISATION_EPISODE_ROUTE}/`)" in alignment
    assert "? `${HOSPITALISATION_OPERATIONS_ROUTE}/${encodeURIComponent(name)}`" in alignment

    # The redirect deliberately matches only the native LIST path. A specific
    # native Form remains the explicit secondary fallback from the Episode UI.
    assert "if (path === nativeListPath)" in alignment
    assert "if (path.startsWith(`${nativeListPath}/`))" not in alignment
    assert "frappe.set_route('Form', 'Veterinary Hospitalisation', this.episode.name)" in episode
