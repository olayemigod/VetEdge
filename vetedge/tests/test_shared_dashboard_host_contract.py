from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
APP = ROOT / "vetedge"
HOST = APP / "public/js/vetedge_dashboard_host.bundle.js"
HOST_CSS = APP / "public/css/vetedge_shared_dashboard_host.css"

DASHBOARD_LOADERS = (
	APP / "veterinary/page/vetedge_clinical_dashboard/vetedge_clinical_dashboard.js",
	APP / "veterinary/page/veterinary_financial_dashboard/veterinary_financial_dashboard.js",
	APP / "veterinary/page/vetedge_inventory_dispensary_dashboard/vetedge_inventory_dispensary_dashboard.js",
	APP / "veterinary/page/vetedge_lab_dashboard/vetedge_lab_dashboard.js",
	APP / "veterinary/page/vetedge_vaccination_dashboard/vetedge_vaccination_dashboard.js",
	APP / "veterinary/page/vetedge_boarding_dashboard/vetedge_boarding_dashboard.js",
	APP / "veterinary/page/vetedge_grooming_dashboard/vetedge_grooming_dashboard.js",
	APP / "veterinary/page/vetedge_practitioner_performance_dashboard/vetedge_practitioner_performance_dashboard.js",
	APP / "veterinary/page/vetedge_branch_performance_dashboard/vetedge_branch_performance_dashboard.js",
)


def read(path: Path) -> str:
	return path.read_text(encoding="utf-8")


def test_all_secondary_dashboards_use_shared_edgesuite_host():
	for loader in DASHBOARD_LOADERS:
		content = read(loader)
		assert "vetedge_dashboard_host.bundle.js" in content, loader
		assert "mountVetEdgeDashboardHost" in content, loader
		assert 'frappe.require("/assets/vetedge/js/dashboard_shell.js"' not in content, loader


def test_shared_host_owns_filters_inside_edgesuite_shell():
	content = read(HOST)
	for contract in (
		"EdgeAppShell",
		"EdgePageLayout",
		"EdgePageHeader",
		"EdgeFilterBar",
		"Dashboard Filters",
		"frappe.ui.form.make_control",
		"vetedge-shared-dashboard-filter-grid",
		"vetedge-shared-dashboard-filter-actions",
		"edge-button--primary",
		"HOST_STYLE_URL",
	):
		assert contract in content
	assert 'page.add_field.bind(page)' not in content


def test_shared_host_theme_layer_covers_legacy_cards_labels_tables_charts_and_reports():
	content = read(HOST_CSS)
	for contract in (
		"vetedge-dashboard-report",
		"edge-color-brand-50",
		".bg-white",
		".text-muted",
		".control-label",
		".form-control",
		".table td",
		".table th",
		"svg text",
		".graph-svg-tip",
		'data-edge-appearance="dark"',
	):
		assert contract in content
