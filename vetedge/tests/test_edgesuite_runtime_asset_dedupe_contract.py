from pathlib import Path


APP_ROOT = Path(__file__).resolve().parents[1]
PROFESSIONAL_UI = APP_ROOT / "public" / "js" / "vetedge_professional_ui.js"
PAGE_ROOT = APP_ROOT / "veterinary" / "page"


def test_professional_ui_redirects_legacy_edgesuite_bundle_to_canonical_runtime():
    source = PROFESSIONAL_UI.read_text(encoding="utf-8")

    assert "installCanonicalRuntimeRequireBridge" in source
    assert "__vetedgeCanonicalEdgeSuiteBridge" in source
    assert 'requested.includes("edgeui.bundle.js")' in source
    assert 'remaining.unshift("edgesuite_ui.bundle.js")' in source
    assert "runtime()?.createEdgeApp" in source
    assert 'window.frappe.require("edgesuite_ui.bundle.js"' in source
    assert 'window.frappe.require("edgeui.bundle.js"' not in source


def test_legacy_page_loader_calls_are_single_asset_requests_covered_by_bridge():
    offenders = []
    for path in PAGE_ROOT.rglob("*.js"):
        source = path.read_text(encoding="utf-8")
        if "edgeui.bundle.js" not in source:
            continue
        legacy_calls = source.count("frappe.require('edgeui.bundle.js'") + source.count('frappe.require("edgeui.bundle.js"')
        if legacy_calls == 0:
            offenders.append(str(path.relative_to(APP_ROOT)))

    assert not offenders, (
        "Legacy EdgeSuite references must remain direct frappe.require calls so the canonical "
        f"runtime bridge can deduplicate them. Unexpected references: {offenders}"
    )
