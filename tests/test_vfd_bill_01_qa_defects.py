from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def read(relative: str) -> str:
	return (ROOT / relative).read_text(encoding="utf-8")


def load_json(relative: str) -> dict:
	return json.loads(read(relative))


def page_roles(relative: str) -> set[str]:
	return {row.get("role") for row in load_json(relative).get("roles") or []}


def test_billing_center_removes_duplicate_shortcuts_and_html_currency_formatter():
	component = read("vetedge/public/js/vetedge_billing_center/VetEdgeBillingCenter.vue")

	assert "billing-shortcuts" not in component
	assert "openList(" not in component
	assert "frappe.format?.(" not in component
	assert "new Intl.NumberFormat('en-NG'" in component
	assert ":value=\"formatCurrency(summary.outstanding_amount)\"" in component
	assert ":value=\"formatCurrency(summary.total_paid)\"" in component


def test_billing_center_uses_friendly_pet_names_for_search_and_list():
	component = read("vetedge/public/js/vetedge_billing_center/VetEdgeBillingCenter.vue")
	service = read("vetedge/services/billing_center.py")

	assert 'placeholder="Search pet name or patient ID"' in component
	assert "{ key: 'patient_display', label: 'Patient' }" in component
	assert 'PATIENT_DOCTYPE = "Veterinary Patient"' in service
	assert "def _patient_display_map(patient_ids: list[str])" in service
	assert "def _patient_link_options(base_filters: dict, search: str, or_filters: dict | None = None)" in service
	assert 'fields=["name", "patient_name"]' in service
	assert 'or_filters={"patient_name": ["like", pattern], "name": ["like", pattern]}' in service
	assert 'row["patient_name"] = patient_name' in service
	assert 'row["patient_display"]' in service
	assert 'if field == "animal":' in service
	assert "return _patient_link_options(base_filters, search, activity_or_filters)" in service


def test_billing_center_defaults_to_actionable_sessions_and_keeps_empty_sessions_diagnostic():
	component = read("vetedge/public/js/vetedge_billing_center/VetEdgeBillingCenter.vue")
	service = read("vetedge/services/billing_center.py")

	assert 'DEFAULT_ACTIVITY_FILTER = "actionable"' in service
	assert 'ALLOWED_ACTIVITY_FILTERS = {"actionable", "all", "empty"}' in service
	assert "def _activity_query(filters: dict)" in service
	assert '"total_charges": ["!=", 0]' in service
	assert '"total_invoiced": ["!=", 0]' in service
	assert '"current_draft_invoice": ["is", "set"]' in service
	assert '"latest_invoice": ["is", "set"]' in service
	assert '"current_draft_invoice": ["is", "not set"]' in service
	assert '"latest_invoice": ["is", "not set"]' in service
	assert 'summary["no_billing_activity_sessions"]' in service
	assert 'scope["activity"] = activity' in service
	assert 'label="Session Activity"' in component
	assert "{ value: 'actionable', label: 'Actionable Billing' }" in component
	assert "{ value: 'all', label: 'All Sessions' }" in component
	assert "{ value: 'empty', label: 'No Billing Activity' }" in component
	assert "activity: 'actionable'" in component
	assert "activity: this.filters.activity || 'actionable'" in component
	assert "Actionable billing view" in component


def test_billing_center_has_fuzzy_date_presets_reusing_shared_date_ranges():
	component = read("vetedge/public/js/vetedge_billing_center/VetEdgeBillingCenter.vue")
	ranges = read("vetedge/public/js/edgesuite_date_ranges.js")

	assert 'label="Date Range"' in component
	assert "const dateRanges = () => frappe.EdgeSuite?.DateRanges || null;" in component
	assert "datePreset: 'full_history'" in component
	assert "dateRanges()?.getOptions?.()" in component
	assert "dateRanges()?.getRange?.(this.datePreset)" in component
	assert "setDatePreset(value)" in component
	assert "setDateField(field, value)" in component
	assert "this.datePreset = 'custom'" in component
	assert "this.datePreset = 'full_history'" in component
	for preset in (
		"today",
		"yesterday",
		"this_week",
		"last_week",
		"this_month",
		"last_month",
		"this_quarter",
		"last_quarter",
		"this_year",
		"last_year",
		"full_history",
	):
		assert f'case "{preset}":' in ranges


def test_billing_sessions_is_a_real_edgesuite_page_reusing_safe_dataset():
	loader = read("vetedge/veterinary/page/vetedge_billing_sessions/vetedge_billing_sessions.js")
	page = load_json("vetedge/veterinary/page/vetedge_billing_sessions/vetedge_billing_sessions.json")
	center_page = load_json("vetedge/veterinary/page/vetedge_billing_center/vetedge_billing_center.json")
	component = read("vetedge/public/js/vetedge_billing_center/VetEdgeBillingCenter.vue")

	assert "edgeui.bundle.js" in loader
	assert "vetedge_billing_center.bundle.js" in loader
	assert "mountVetEdgeBillingCenter" in loader
	assert page.get("name") == "vetedge-billing-sessions"
	assert page.get("title") == "Billing Sessions"
	assert page_roles("vetedge/veterinary/page/vetedge_billing_sessions/vetedge_billing_sessions.json") == page_roles(
		"vetedge/veterinary/page/vetedge_billing_center/vetedge_billing_center.json"
	)
	assert center_page.get("name") == "vetedge-billing-center"
	assert "'/desk/vetedge-billing-sessions'" in component
	assert "pageTitle() { return this.isSessionsPage ? 'Billing Sessions' : 'Billing Center'; }" in component


def test_product_menu_and_billing_routes_are_same_tab_and_clickable():
	hardening = read("vetedge/public/js/vetedge_postqa_navigation_hardening.js")

	for marker in (
		'const BILLING_CENTER_ROUTE = "/desk/vetedge-billing-center"',
		'const BILLING_SESSIONS_ROUTE = "/desk/vetedge-billing-sessions"',
		'const BILLING_SESSION_DOCTYPE = "Veterinary Billing Session"',
		"function bindSharedProductMenuNavigation(panel)",
		"function sidebarSameTabRoute(item)",
		"return navigateRoute(BILLING_CENTER_ROUTE)",
		"return navigateRoute(BILLING_SESSIONS_ROUTE)",
		"event.stopImmediatePropagation();",
	):
		assert marker in hardening

	assert "window.open(" not in hardening
	assert "target=\"_blank\"" not in hardening


def test_browser_guard_repairs_product_menu_search_same_tab_billing_and_native_session_routes():
	guard = read("vetedge/public/js/edgesuite_date_ranges.js")

	for marker in (
		"installVetEdgeBillingNavigationGuard",
		'const BILLING_CENTER_ROUTE = "/desk/vetedge-billing-center"',
		'const BILLING_SESSIONS_ROUTE = "/desk/vetedge-billing-sessions"',
		'const NATIVE_BILLING_SESSION_PATH = "/desk/veterinary-billing-session"',
		"function filterProductMenu(panel, query)",
		"function routeProductItem(node)",
		"function reconcileBillingSidebar()",
		"function redirectNativeBillingSession()",
		'anchor.setAttribute("target", "_self")',
		'global.document?.addEventListener("input"',
		'global.document?.addEventListener("click"',
		'global.frappe?.router?.on?.("change"',
		"billingSessionDetailRoute(name)",
	):
		assert marker in guard

	assert 'global.location.assign(next)' in guard
	assert 'global.location.replace(next)' in guard
	assert 'window.open(' not in guard
	assert 'target="_blank"' not in guard


def test_rendered_sidebar_rechecks_approved_primary_order_after_dom_changes():
	hardening = read("vetedge/public/js/vetedge_postqa_navigation_hardening.js")

	for label in (
		"Appointments",
		"Clinical Operations",
		"Hospital & Services",
		"Inventory / Pharmacy",
		"Billing Center",
		"Dashboard",
		"Reports",
	):
		assert f'\t\t"{label}",' in hardening

	assert "function primaryOrderAligned(shell)" in hardening
	assert "!primaryOrderAligned(shell)" in hardening
	assert "primaryOrderAligned: Boolean(shell && primaryOrderAligned(shell))" in hardening
