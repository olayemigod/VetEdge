from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]


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
        "stateMismatch",
        "needsRouteSync",
        "view.dirty && needsRouteSync",
        "await view.confirmDiscard?.()",
        "view.loadDetail?.(requested.consultation)",
        "openRequestedNewConsultation(view, requested)",
        "await view.selectPatient?.(requested.patient)",
        "patient=${encodeURIComponent(requested.patient)}",
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


def test_settings_refresh_is_stale_aware_and_never_overwrites_dirty_values():
    content = read("vetedge/veterinary/page/veterinary_settings_center/veterinary_settings_center.js")

    assert "VETEDGE_SETTINGS_REFRESH_MAX_AGE_MS = 15000" in content
    assert "if (view.dirty) return;" in content
    assert "if (!stale) return;" in content
    assert "Promise.resolve(view.load?.())" in content
    assert "setInterval(" not in content


def test_settings_write_access_is_reconciled_from_authoritative_server_permission():
    loader = read("vetedge/veterinary/page/veterinary_settings_center/veterinary_settings_center.js")
    service = read("vetedge/services/settings_page.py")

    for contract in (
        "syncVeterinarySettingsWriteAccess(wrapper)",
        "reconcileVeterinarySettingsWriteAccess(wrapper)",
        "get_veterinary_settings_access",
        "view.canWrite = payload.can_write === true || Number(payload.can_write || 0) === 1;",
        "runtime?.Vue?.watch",
        "wrapper.settings_access_checked",
    ):
        assert contract in loader

    for contract in (
        "def _write_access_payload() -> dict:",
        '"can_write": bool(frappe.has_permission(SETTINGS_DOCTYPE, ptype="write")),',
        "def get_veterinary_settings_access() -> dict:",
        "return _write_access_payload()",
        "**_write_access_payload(),",
    ):
        assert contract in service

    assert "ignore_permissions" not in service


def test_settings_child_tables_use_smart_links_and_respect_write_permission():
    component = read("vetedge/public/js/veterinary_settings_center/VeterinarySettingsCenter.vue")
    service = read("vetedge/services/settings_page.py")

    for contract in (
        "v-else-if=\"child.fieldtype === 'Link'\"",
        ":searcher=\"(term) => searchChildLink(field, child, term)\"",
        ":disabled=\"isChildReadOnly(field, child, row)\"",
        ":disabled=\"isReadOnly(field)\" @click=\"addRow(field)\"",
        "Veterinary Settings is read-only for this account.",
        "this.writeRoles = payload.write_roles || [];",
    ):
        assert contract in component

    for contract in (
        '"registration_item",',
        "def _resolve_settings_link_field(fieldname: str, child_fieldname: str | None = None):",
        "child_fieldname: str | None = None,",
        "filter_fieldname = child_fieldname or fieldname",
    ):
        assert contract in service

    assert "ignore_permissions" not in service


def test_resource_center_redispatches_same_patient_consultation_route_instead_of_noop():
    content = read("vetedge/veterinary/page/vetedge_resource_center/vetedge_resource_center.js")

    for contract in (
        "function installResourceCenterRepeatRouteDispatch()",
        "adapter.__vetedgeRepeatRouteDispatchInstalled",
        "url.pathname === '/desk/vetedge-clinical-workspace'",
        "next === current",
        "Promise.resolve(frappeRouter.route())",
        "installResourceCenterRepeatRouteDispatch();",
    ):
        assert contract in content

    assert "window.location.reload" not in content


def test_existing_resource_and_medical_history_reuse_remain_ahead_of_asset_loading():
    for path, marker in (
        ("vetedge/veterinary/page/vetedge_resource_center/vetedge_resource_center.js", "if (wrapper.vue_app?.refresh)"),
        ("vetedge/veterinary/page/veterinary_medical_history/veterinary_medical_history.js", "if (wrapper.vue_app?.refresh)"),
    ):
        content = read(path)
        assert content.index(marker) < content.index("frappe.require('edgeui.bundle.js'")
        assert content.index(marker) < content.index("$(page.body).empty()")
        assert "setInterval(" not in content


def test_resource_center_patient_consultation_action_uses_shared_spa_navigation():
    content = read("vetedge/public/js/vetedge_resource_center.bundle.js")
    start = content.index("\t\t\topenNewConsultation(row) {")
    end = content.index("\n\t\t\t},", start) + 6
    block = content[start:end]

    assert "this.openRoute(`/desk/vetedge-clinical-workspace?new=1&patient=${encodeURIComponent(row.name)}`);" in block
    assert "window.location.assign" not in block


def test_shared_navigation_adapter_uses_frappe_spa_router_before_full_navigation_fallback():
    content = read("vetedge/public/js/vetedge_ui_bridge.js")
    start = content.index("\tfunction openSameTab(route) {")
    end = content.index("\n\tfunction openNewTab(route)", start)
    block = content[start:end]

    assert "const target = deskRoute(route);" in block
    assert 'const isDeskRoute = url.pathname === "/desk" || url.pathname.startsWith("/desk/");' in block
    assert "window.history.pushState(null, \"\", next);" in block
    assert "Promise.resolve(frappeRouter.route())" in block
    assert "const next = `${url.pathname}${url.search}${url.hash}`;" in block
    assert "const current = `${window.location.pathname}${window.location.search}${window.location.hash}`;" in block
    assert block.index("window.history.pushState") < block.index("window.location.assign(target)")
    assert "window.location.assign(deskRoute(route));" not in block


def test_veterinary_home_redirect_guard_is_transient_for_repeated_spa_visits():
    content = read("vetedge/veterinary/page/vetedge/vetedge.js")

    assert "if (wrapper.__vetedge_home_redirecting) return;" in content
    assert "wrapper.__vetedge_home_redirecting = true;" in content
    assert "const finishRedirect = () => {" in content
    assert "wrapper.__vetedge_home_redirecting = false;" in content
    assert 'Promise.resolve(frappe.set_route("vetedge-resource-center")).finally(finishRedirect);' in content
    assert content.index("wrapper.__vetedge_home_redirecting = false;") > content.index("wrapper.__vetedge_home_redirecting = true;")
