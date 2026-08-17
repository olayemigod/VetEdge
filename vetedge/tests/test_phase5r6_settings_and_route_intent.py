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
    assert content.index("normalizeBooleanMethod(method)") < content.index(
        "export function mountVeterinarySettingsCenter"
    )


def test_resource_center_gives_each_new_consultation_click_a_unique_spa_intent():
    content = read("vetedge/veterinary/page/vetedge_resource_center/vetedge_resource_center.js")

    for contract in (
        "let vetedgeClinicalIntentSequence = 0;",
        "function withClinicalNavigationIntent(route)",
        "url.pathname === '/desk/vetedge-clinical-workspace'",
        "url.searchParams.get('new') === '1'",
        "vetedgeClinicalIntentSequence += 1;",
        "url.searchParams.set(",
        "'_vetedge_intent'",
        "return originalOpen(withClinicalNavigationIntent(route));",
    ):
        assert contract in content

    assert "window.location.assign" not in content
    assert "window.dispatchEvent(new CustomEvent" not in content


def test_clinical_workspace_normalizes_transient_intent_back_to_clean_patient_route():
    content = read(
        "vetedge/veterinary/page/vetedge_clinical_workspace/vetedge_clinical_workspace.js"
    )

    assert "const patient = String(params.get('patient') || '').trim();" in content
    assert "const patientQuery = requested.patient ? `&patient=${encodeURIComponent(requested.patient)}` : '';" in content
    assert "`/desk/vetedge-clinical-workspace?new=1${patientQuery}`" in content
    assert "_vetedge_intent" not in content
    assert "window.location.assign" not in content
