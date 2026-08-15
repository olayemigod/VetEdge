from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
APP = ROOT / "vetedge"


def read(relative_path: str) -> str:
    return ROOT.joinpath(relative_path).read_text(encoding="utf-8")


def reuse_block(content: str, marker: str) -> str:
    start = content.index(marker)
    end = content.index("\n\t}", start) + 3
    return content[start:end]


def test_operational_edgesuite_pages_reuse_mounted_surfaces_before_reset_and_assets():
    loaders = {
        "clinical": (
            "vetedge/veterinary/page/vetedge_clinical_workspace/vetedge_clinical_workspace.js",
            "if (wrapper.vue_app?.view)",
            "VETEDGE_CLINICAL_REFRESH_MAX_AGE_MS = 15000",
        ),
        "front_desk": (
            "vetedge/veterinary/page/vetedge_front_desk_action_center/vetedge_front_desk_action_center.js",
            "if (wrapper.vue_app?.view)",
            "VETEDGE_FRONT_DESK_REFRESH_MAX_AGE_MS = 15000",
        ),
        "service_operations": (
            "vetedge/veterinary/page/vetedge_service_operations/vetedge_service_operations.js",
            "if (wrapper.vue_app?.view)",
            "VETEDGE_SERVICE_OPERATIONS_REFRESH_MAX_AGE_MS = 15000",
        ),
        "masters": (
            "vetedge/veterinary/page/vetedge_master_workspace/vetedge_master_workspace.js",
            "if (wrapper.vue_app?.view)",
            "VETEDGE_MASTER_WORKSPACE_REFRESH_MAX_AGE_MS = 15000",
        ),
        "pricing": (
            "vetedge/veterinary/page/vetedge_pricing_master_workspace/vetedge_pricing_master_workspace.js",
            "if (wrapper.vue_app?.view)",
            "VETEDGE_PRICING_WORKSPACE_REFRESH_MAX_AGE_MS = 15000",
        ),
    }

    for name, (path, marker, freshness_contract) in loaders.items():
        content = read(path)
        reuse_index = content.index(marker)
        reset_index = content.index("$(page.body).empty()")
        asset_index = content.index("frappe.require('edgeui.bundle.js'")
        assert reuse_index < reset_index, name
        assert reuse_index < asset_index, name
        assert freshness_contract in content, name
        assert "setInterval(" not in content, name

        block = reuse_block(content, marker)
        assert "return;" in block, name
        assert "frappe.require(" not in block, name
        assert "unmount" not in block, name


def test_clinical_warm_navigation_is_route_aware_and_preserves_dirty_work():
    content = read("vetedge/veterinary/page/vetedge_clinical_workspace/vetedge_clinical_workspace.js")

    for contract in (
        "clinicalRouteState()",
        "routeChanged",
        "view.dirty && routeChanged",
        "view.loadDetail?.(requested.consultation)",
        "view.startNewConsultation?.()",
        "view.refreshList?.()",
        "clinical_last_refresh_at",
    ):
        assert contract in content


def test_front_desk_warm_navigation_refreshes_only_route_changes_or_stale_data():
    content = read("vetedge/veterinary/page/vetedge_front_desk_action_center/vetedge_front_desk_action_center.js")

    for contract in (
        "frontDeskRouteState()",
        "routeChanged || stale",
        "view.refreshAll?.()",
        "view.openGuestDetail?.({ name: requested.name })",
        "view.openMissedDetail?.({ name: requested.name })",
        "view.openQueueDetail?.({ name: requested.name })",
        "front_desk_last_refresh_at",
    ):
        assert contract in content


def test_service_operations_warm_navigation_syncs_resource_without_remounting():
    content = read("vetedge/veterinary/page/vetedge_service_operations/vetedge_service_operations.js")

    for contract in (
        "serviceOperationsRouteState()",
        "view.resource = requested.resource",
        "view.search = requested.search",
        "view.parent = requested.parent",
        "view.requestedName = requested.name",
        "if (routeChanged || stale) await view.load?.()",
        "service_operations_last_refresh_at",
    ):
        assert contract in content


def test_master_and_pricing_reuse_keeps_dirty_form_confirmation():
    for path, prefix in (
        ("vetedge/veterinary/page/vetedge_master_workspace/vetedge_master_workspace.js", "master_workspace"),
        ("vetedge/veterinary/page/vetedge_pricing_master_workspace/vetedge_pricing_master_workspace.js", "pricing_workspace"),
    ):
        content = read(path)
        assert "view.dirty" in content
        assert "view.confirmDiscard(finishRefresh)" in content
        assert "await view.loadCurrentRoute?.()" in content
        assert f"{prefix}_last_refresh_at" in content


def test_existing_resource_and_medical_history_reuse_remain_ahead_of_asset_loading():
    for path, marker in (
        ("vetedge/veterinary/page/vetedge_resource_center/vetedge_resource_center.js", "if (wrapper.vue_app?.refresh)"),
        ("vetedge/veterinary/page/veterinary_medical_history/veterinary_medical_history.js", "if (wrapper.vue_app?.refresh)"),
    ):
        content = read(path)
        assert content.index(marker) < content.index("frappe.require('edgeui.bundle.js'")
        assert content.index(marker) < content.index("$(page.body).empty()")
        assert "setInterval(" not in content
