from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def read(relative: str) -> str:
	return (ROOT / relative).read_text(encoding="utf-8")


def test_billing_session_drill_through_stays_in_edgesuite():
	bundle = read("vetedge/public/js/vetedge_billing_center.bundle.js")
	loader = read("vetedge/veterinary/page/vetedge_billing_sessions/vetedge_billing_sessions.js")
	detail = read("vetedge/public/js/vetedge_billing_center/VetEdgeBillingSessionDetail.vue")

	assert "mountVetEdgeBillingSessionDetail" in bundle
	assert "/desk/vetedge-billing-sessions?name=${encodeURIComponent(row.name)}" in bundle
	assert "window.location.assign" in bundle
	assert "new URLSearchParams(window.location.search || '').get('name')" in loader
	assert "window.mountVetEdgeBillingSessionDetail" in loader
	assert "vetedge-billing-session-detail-root" in loader
	assert "vetedge.services.billing_session_page.get_billing_session_detail" in detail
	assert "active-route=\"/desk/vetedge-billing-sessions\"" in detail
	assert "Back to Billing Sessions" in detail
	assert "frappe.set_route('Form', 'Veterinary Billing Session'" not in detail


def test_billing_session_detail_service_is_read_only_and_branch_safe():
	service = read("vetedge/services/billing_session_page.py")

	for marker in (
		"_require_billing_center_access()",
		"_branch_scope(user, None)",
		'filters["branch"] = ["in", branches or [NO_BRANCH_SENTINEL]]',
		"frappe.get_list(",
		"frappe.get_doc(BILLING_SESSION_DOCTYPE, session_name)",
		'row["charges"] = charges',
		'row["currency"] = _company_currency',
	):
		assert marker in service

	for forbidden in (
		"ignore_permissions=True",
		"frappe.db.sql",
		".submit(",
		".cancel(",
		"frappe.delete_doc",
		"frappe.db.set_value",
	):
		assert forbidden not in service


def test_detail_keeps_accounting_documents_native_but_not_billing_session():
	detail = read("vetedge/public/js/vetedge_billing_center/VetEdgeBillingSessionDetail.vue")

	assert "frappe.set_route('Form', 'Sales Invoice', this.visibleInvoice)" in detail
	assert "Veterinary Billing Session" not in detail or "frappe.set_route('Form', 'Veterinary Billing Session'" not in detail
	assert "read-only view of the authoritative Veterinary Billing Session" not in detail
