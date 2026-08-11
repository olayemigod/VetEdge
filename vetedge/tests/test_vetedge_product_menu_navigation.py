from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
APP = ROOT / "vetedge"


def read(path: Path) -> str:
	return path.read_text(encoding="utf-8")


def test_shared_product_menu_owns_same_tab_navigation():
	menu = read(APP / "public/js/edgesuite_product_menu.js")
	assert "navigate(item)" in menu
	assert "routeTo(item);" in menu
	assert 'menu_source: "workspace_sidebar"' in menu


def test_professional_sidebar_uses_desk_router_before_full_navigation_fallback():
	professional = read(APP / "public/js/vetedge_professional_ui.js")
	start = professional.index("function openRoute(route)")
	end = professional.index("function injectStyles()", start)
	block = professional[start:end]

	assert 'const isDeskRoute = /^\\/(app|desk)(\\/|$)/.test(url.pathname);' in block
	assert 'window.history.pushState(null, "", next);' in block
	assert "Promise.resolve(router.route())" in block
	assert "window.frappe.route_options = {};" in block
	assert "for (const [key, value] of url.searchParams)" in block
	assert "window.location.assign(target);" in block
	assert block.index("window.history.pushState") < block.index("window.location.assign(target)")


def test_accepted_route_alignment_uses_desk_router_before_full_reload_fallback():
	alignment = read(APP / "public/js/vetedge_clinical_route.js")

	assert "function navigateAcceptedTarget(target, options = {})" in alignment
	assert 'const method = options.replace ? "replaceState" : "pushState";' in alignment
	assert 'window.history[method](null, "", next);' in alignment
	assert "Promise.resolve(router.route())" in alignment

	redirect_start = alignment.index("function redirectAcceptedRoute()")
	redirect_end = alignment.index("function normalizeRoute", redirect_start)
	redirect_block = alignment[redirect_start:redirect_end]
	assert "navigateAcceptedTarget(target" in redirect_block
	assert "window.location.replace(target);" in redirect_block

	adapter_start = alignment.index("function installNavigationAdapter()")
	adapter_end = alignment.index("function scheduleNavigationAdapter", adapter_start)
	adapter_block = alignment[adapter_start:adapter_end]
	assert "if (navigateAcceptedTarget(target)) return true;" in adapter_block
	assert "window.location.assign(target);" in adapter_block


def test_navigation_assets_are_cache_busted_after_service_route_migration():
	hooks = read(APP / "hooks.py")
	for asset in (
		"edgesuite_product_menu.js?v=20260810-2",
		"vetedge_clinical_route.js?v=20260810-2",
		"vetedge_ui_bridge.js?v=20260810-2",
	):
		assert asset in hooks


def test_hospital_service_routes_target_edgesuite_operations_workspace():
	bridge = read(APP / "public/js/vetedge_ui_bridge.js")
	route_alignment = read(APP / "public/js/vetedge_clinical_route.js")

	for route, resource in (
		("/app/pet-boarding-stay", "boarding-stays"),
		("/app/pet-boarding-care-record", "boarding-care-records"),
		("/app/pet-grooming-session", "grooming-sessions"),
	):
		assert f'"{route}": "{resource}"' in bridge
		assert f'"{route}": "{resource}"' in route_alignment

	for page in ("/app/kennel-availability", "/app/kennel-availability-board"):
		assert page in bridge
		assert page in route_alignment

	assert '"/app/vetedge-service-operations"' in bridge
	assert 'SERVICE_WORKSPACE_PATH = "/app/vetedge-service-operations"' in route_alignment
