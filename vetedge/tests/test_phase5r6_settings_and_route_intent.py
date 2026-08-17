from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]


def read(relative_path: str) -> str:
    return ROOT.joinpath(relative_path).read_text(encoding="utf-8")


def test_settings_boolean_helpers_are_normalized_before_mount():
    content = read("vetedge/public/js/veterinary_settings_center.bundle.js")

    assert 'function normalizeBooleanMethod(name)' in content
    assert 'return Boolean(original.apply(this, args));' in content
    for method in ("isReadOnly", "isRequired", "isChildReadOnly", "isChildRequired"):
        assert f'"{method}"' in content
    assert content.index("normalizeBooleanMethod(method)") < content.index("export function mountVeterinarySettingsCenter")


def test_resource_center_dispatches_patient_scoped_clinical_intent_without_full_navigation():
    content = read("vetedge/veterinary/page/vetedge_resource_center/vetedge_resource_center.js")

    assert "VETEDGE_CLINICAL_ROUTE_REQUEST_EVENT = 'vetedge:clinical-route-request'" in content
    assert "url.pathname !== '/desk/vetedge-clinical-workspace'" in content
    assert "url.searchParams.get('new') !== '1'" in content
    assert "window.dispatchEvent(new CustomEvent(VETEDGE_CLINICAL_ROUTE_REQUEST_EVENT" in content
    assert "patient: String(url.searchParams.get('patient') || '').trim()" in content
    assert "dispatchClinicalRouteRequest(url);" in content


def test_mounted_clinical_workspace_consumes_repeated_new_consultation_intent():
    content = read("vetedge/veterinary/page/vetedge_clinical_workspace/vetedge_clinical_workspace.js")

    for contract in (
        "VETEDGE_CLINICAL_ROUTE_REQUEST_EVENT = 'vetedge:clinical-route-request'",
        "function installClinicalRouteRequestListener(wrapper)",
        "window.addEventListener(VETEDGE_CLINICAL_ROUTE_REQUEST_EVENT, handler);",
        "wrapper.pending_clinical_route_request = requested;",
        "openRequestedNewConsultation(view, requested, false)",
        "function consumePendingClinicalRouteRequest(wrapper)",
        "consumePendingClinicalRouteRequest(wrapper);",
    ):
        assert contract in content

    assert "window.location.assign" not in content
