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


def test_patient_rows_do_not_offer_new_consultation_action():
    vue = read("vetedge/public/js/vetedge_resource_center/VetEdgeResourceCenter.vue")
    bundle = read("vetedge/public/js/vetedge_resource_center.bundle.js")

    assert '@click="openNewConsultation(row)"' not in vue
    assert "openNewConsultation(row)" not in vue
    assert "New Consultation" not in vue
    assert "openNewConsultation(row)" not in bundle


def test_resource_center_no_longer_installs_patient_consultation_repeat_route_workaround():
    content = read("vetedge/veterinary/page/vetedge_resource_center/vetedge_resource_center.js")

    assert "vetedgeClinicalIntentSequence" not in content
    assert "withClinicalNavigationIntent" not in content
    assert "installResourceCenterRepeatRouteDispatch" not in content
    assert "_vetedge_intent" not in content
