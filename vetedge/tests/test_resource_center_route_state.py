from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
APP = ROOT / "vetedge"


def read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def test_resource_center_consumes_frappe_route_options_before_patient_fallback():
    bundle = read(APP / "public/js/vetedge_resource_center.bundle.js")

    assert "RESOURCE_ROUTE_KEYS" in bundle
    assert "window.frappe?.route_options" in bundle
    assert "if (!params.has(key)) params.set(key, String(value))" in bundle
    assert "window.history.replaceState" in bundle
    assert "const params = getRequestedRouteParams();" in bundle
    assert "params.get('resource') || 'patients'" in bundle


def test_lab_and_vaccination_navigation_keep_distinct_resource_keys():
    recovery = read(APP / "public/js/vetedge_navigation_recovery.js")

    assert '"DocType:Veterinary Lab Order": "/desk/vetedge-resource-center?resource=lab-orders"' in recovery
    assert '"DocType:Veterinary Vaccination Record": "/desk/vetedge-resource-center?resource=vaccinations"' in recovery
    assert '"Veterinary Lab Order": { base: "/desk/vetedge-resource-center", resource: "lab-orders" }' in recovery
    assert '"Veterinary Vaccination Record": { base: "/desk/vetedge-resource-center", resource: "vaccinations" }' in recovery
