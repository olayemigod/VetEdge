from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
APP = ROOT / "vetedge"


def read(path: Path) -> str:
	return path.read_text(encoding="utf-8")


def test_shared_product_menu_still_owns_same_tab_navigation():
	menu = read(APP / "public/js/edgesuite_product_menu.js")
	assert "navigate(item)" in menu
	assert "routeTo(item);" in menu
	assert 'menu_source: "workspace_sidebar"' in menu


def test_vetedge_emergency_menu_is_edgesuite_shell_only():
	menu = read(APP / "public/js/edgesuite_product_menu.js")

	for expected in (
		'function edgeShellPresent()',
		'".edge-app-shell[data-edge-product] .edge-topbar__brand"',
		'".edge-app-shell[data-edge-product] .edge-topbar-actions"',
		'if (!edgeShellPresent()) {',
		'state.mode = "native-desk-hidden"',
		'return result(false, "native-desk-hidden", null);',
	):
		assert expected in menu

	for forbidden in (
		'".page-head .page-actions"',
		'".page-head-content .page-actions"',
		'".page-actions"',
		'"header .navbar .navbar-right"',
		'vetedge-product-menu-slot--floating',
	):
		assert forbidden not in menu


def test_v16_navigation_recovery_makes_desk_routes_canonical():
	recovery = read(APP / "public/js/vetedge_navigation_recovery.js")

	for expected in (
		'const DESK_PREFIX = "/desk";',
		'"Page:veterinary-appointment-queue": "/desk/vetedge-front-desk-action-center?tab=queue"',
		'"DocType:Veterinary Patient": "/desk/vetedge-resource-center?resource=patients"',
		'"DocType:Veterinary Consultation": "/desk/vetedge-clinical-workspace"',
		'route: "/desk/vetedge"',
		"function toDeskRoute(route)",
		'url.pathname === "/app" || url.pathname.startsWith("/app/")',
	):
		assert expected in recovery

	assert '"Page:veterinary-appointment-queue": "/app/' not in recovery
	assert 'route: "/app/vetedge"' not in recovery


def test_v16_router_preserves_native_frappe_semantics():
	recovery = read(APP / "public/js/vetedge_navigation_recovery.js")
	start = recovery.index("function applyDeskRoute(target, itemOverride = null)")
	end = recovery.index("function alignCurrentFrappeRoute()", start)
	block = recovery[start:end]

	assert 'window.frappe.set_route("query-report", item.link_to)' in block
	assert 'window.frappe.set_route("List", item.link_to)' in block
	assert "window.frappe.set_route(item.link_to)" in block
	assert "window.frappe.set_route(...parts)" in block
	assert "window.history.pushState" not in block
	assert "router.route()" not in block


def test_migrated_native_routes_align_to_edgesuite_desk_workspaces():
	recovery = read(APP / "public/js/vetedge_navigation_recovery.js")

	for expected in (
		'"Veterinary Patient": { base: "/desk/vetedge-resource-center", resource: "patients" }',
		'"Veterinary Appointment": { base: "/desk/vetedge-resource-center", resource: "appointments" }',
		'"Veterinary Lab Order": { base: "/desk/vetedge-resource-center", resource: "lab-orders" }',
		'"Veterinary Consultation"',
		'"Veterinary Vital Signs"',
		'return "/desk/vetedge-clinical-workspace";',
		'return "/desk/veterinary-settings-center";',
	):
		assert expected in recovery

	# Standalone Vital Signs stays native until its dedicated EdgeSuite migration.
	assert 'if (doctype === "Veterinary Vital Signs") return "";' in recovery


def test_legacy_clinical_route_bridge_is_not_globally_loaded():
	hooks = read(APP / "hooks.py")
	assert 'app_home = "/desk/vetedge"' in hooks
	assert "vetedge_clinical_route.js" not in hooks
	assert "vetedge_navigation_recovery.js?v=20260812-2" in hooks


def test_hospital_service_routes_target_desk_operations_workspace():
	recovery = read(APP / "public/js/vetedge_navigation_recovery.js")

	for route in (
		'"DocType:Pet Boarding Stay": "/desk/vetedge-service-operations?resource=boarding-stays"',
		'"DocType:Pet Boarding Care Record": "/desk/vetedge-service-operations?resource=boarding-care-records"',
		'"DocType:Pet Grooming Session": "/desk/vetedge-service-operations?resource=grooming-sessions"',
		'"Page:kennel-availability": "/desk/vetedge-service-operations?resource=availability"',
	):
		assert route in recovery


def test_composite_edgesuite_pages_publish_exact_sidebar_focus_targets():
	bridge = read(APP / "public/js/vetedge_ui_bridge.js")

	for expected in (
		'queue: { section: "Front Desk", items: ["Appointment Queue"] }',
		'guest: { section: "Front Desk", items: ["Guest Booking Requests"] }',
		'missed: { section: "Front Desk", items: ["Missed Appointments"] }',
		'"/desk/vetedge-clinical-workspace": { section: "Clinical", items: ["Consultations"] }',
		'"/desk/veterinary-medical-history": { section: "Clinical", items: ["Medical History"] }',
		'boarding: { section: "Hospital & Services", items: ["Pet Boarding Booking"] }',
		'grooming: { section: "Hospital & Services", items: ["Pet Grooming Appointment"] }',
	):
		assert expected in bridge

	assert 'if (path === "/desk/vetedge-front-desk-action-center")' in bridge
	assert 'if (path === "/desk/vetedge-resource-center")' in bridge
	assert 'window.EdgeSuiteNavigation?.syncActiveSection?.(shell);' in bridge
	assert 'for (const methodName of ["pushState", "replaceState"])' in bridge
	assert 'resolveSidebarFocus: currentSidebarFocus' in bridge
