from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def test_hospitalisation_operations_bundle_keeps_internal_navigation_in_current_page():
    bundle = read(ROOT / "public" / "js" / "vetedge_hospitalisation_operations.bundle.js")

    for expected in (
        "HOSPITALISATION_OPERATIONS_PAGE = 'vetedge-hospitalisation-operations'",
        "window.frappe?.container?.page",
        "wrapper?.page_name === HOSPITALISATION_OPERATIONS_PAGE",
        "window.frappe.router.current_route = hospitalisation",
        "window.history.pushState(window.history.state, '', target)",
        "wrapper.on_page_show(wrapper)",
        "showHospitalisationInCurrentPage(hospitalisation)",
        "originalSetRoute.apply(this, args)",
    ):
        assert expected in bundle


def test_hospitalisation_same_page_router_is_narrow_and_keeps_native_fallback():
    bundle = read(ROOT / "public" / "js" / "vetedge_hospitalisation_operations.bundle.js")

    assert "if (first === HOSPITALISATION_OPERATIONS_PAGE)" in bundle
    assert "if (showHospitalisationInCurrentPage(hospitalisation)) return Promise.resolve();" in bundle
    assert "return originalSetRoute.apply(this, args);" in bundle
    assert "window.location.assign(hospitalisationOperationsTarget(hospitalisation));" in bundle
    assert "window.open(" not in bundle


def test_hospitalisation_router_installs_before_operations_component_mount():
    bundle = read(ROOT / "public" / "js" / "vetedge_hospitalisation_operations.bundle.js")

    install = bundle.index("installHospitalisationSamePageRouter();")
    mount = bundle.index("const app = runtime.createEdgeApp")
    assert install < mount
