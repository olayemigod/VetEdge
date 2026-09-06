from __future__ import annotations

import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
APP = ROOT / "vetedge"


def read(relative: str) -> str:
	return (ROOT / relative).read_text(encoding="utf-8")


def load_json(relative: str) -> dict:
	return json.loads(read(relative))


def page_roles(relative: str) -> set[str]:
	return {row.get("role") for row in load_json(relative).get("roles") or []}


def test_navigation_source_contract_is_bounded_and_idempotent_by_design():
	dashboard = read("vetedge/install/dashboard.py")
	for marker in (
		'"Appointment Queue": "vetedge-front-desk-queue"',
		'"Guest Booking Requests": "vetedge-front-desk-guest-bookings"',
		'"Missed Appointments": "vetedge-front-desk-missed-appointments"',
		'def _organize_veterinary_navigation(items: list[dict]) -> list[dict]:',
		'if label == "Pet Grooming Appointment":',
		'if label == "Pet Boarding Booking":',
		'insert_billing_center()',
		'"Billing Center"',
	):
		assert marker in dashboard

	assert 'standard_items = _organize_veterinary_navigation(standard_items)' in dashboard


def test_dedicated_front_desk_pages_reuse_one_fixed_mode_bundle():
	host = read("vetedge/public/js/vetedge_front_desk_page_host.js")
	bundle = read("vetedge/public/js/vetedge_front_desk_action_center.bundle.js")
	component = read("vetedge/public/js/vetedge_front_desk_action_center/VetEdgeFrontDeskActionCenter.vue")

	assert "mountVetEdgeFrontDeskActionCenter(root[0], { fixedTab })" in host
	assert "buildFrontDeskRoot(runtime, options = {})" in bundle
	assert "state.fixedTab = fixedTab" in bundle
	assert 'v-if="!fixedTab"' in component

	for relative, mode in (
		("vetedge/veterinary/page/vetedge_front_desk_queue/vetedge_front_desk_queue.js", "queue"),
		("vetedge/veterinary/page/vetedge_front_desk_guest_bookings/vetedge_front_desk_guest_bookings.js", "guest"),
		("vetedge/veterinary/page/vetedge_front_desk_missed_appointments/vetedge_front_desk_missed_appointments.js", "missed"),
	):
		loader = read(relative)
		assert "vetedge_front_desk_page_host.js" in loader
		assert f"fixedTab: '{mode}'" in loader


def test_front_desk_page_roles_preserve_replaced_visibility_contracts():
	queue = page_roles("vetedge/veterinary/page/vetedge_front_desk_queue/vetedge_front_desk_queue.json")
	guest = page_roles("vetedge/veterinary/page/vetedge_front_desk_guest_bookings/vetedge_front_desk_guest_bookings.json")
	missed = page_roles("vetedge/veterinary/page/vetedge_front_desk_missed_appointments/vetedge_front_desk_missed_appointments.json")
	legacy = page_roles("vetedge/veterinary/page/vetedge_front_desk_action_center/vetedge_front_desk_action_center.json")

	for role in ("System Manager", "VetEdge Administrator", "VetEdge Front Desk", "VetEdge Doctor", "Branch Manager"):
		assert role in queue
		assert role in guest
		assert role in missed

	for role in ("Veterinary Nurse", "Dispensary User"):
		assert role in queue
		assert role in legacy
	assert "Veterinary Nurse" in missed
	assert "Dispensary User" not in guest


def test_legacy_front_desk_routes_are_redirect_only():
	legacy = read("vetedge/veterinary/page/vetedge_front_desk_action_center/vetedge_front_desk_action_center.js")
	queue = read("vetedge/veterinary/page/veterinary_appointment_queue/veterinary_appointment_queue.js")

	for route in (
		"/desk/vetedge-front-desk-queue",
		"/desk/vetedge-front-desk-guest-bookings",
		"/desk/vetedge-front-desk-missed-appointments",
	):
		assert route in legacy
	assert "mountVetEdgeFrontDeskActionCenter" not in legacy
	assert "/desk/vetedge-front-desk-queue" in queue
	assert "?tab=queue" not in queue


def test_billing_center_service_is_read_only_bounded_and_branch_safe():
	service = read("vetedge/services/billing_center.py")

	for forbidden in (
		"ignore_permissions=True",
		"frappe.db.sql",
		".submit(",
		".cancel(",
		"frappe.delete_doc",
		"frappe.db.set_value",
	):
		assert forbidden not in service

	for marker in (
		'BILLING_SESSION_DOCTYPE = "Veterinary Billing Session"',
		"PAGE_LENGTH_MAX = 100",
		'"__vetedge_no_permitted_branch__"',
		'if field == "branch" and scope.get("restricted")',
		'customer: str | None = None',
		'context["customer"] = cstr(customer or "").strip()',
		"page_length=20",
	):
		assert marker in service


def test_billing_center_ui_uses_canonical_route_and_full_filter_cascade():
	component = read("vetedge/public/js/vetedge_billing_center/VetEdgeBillingCenter.vue")
	bundle = read("vetedge/public/js/vetedge_billing_center.bundle.js")

	assert 'active-route="/desk/vetedge-billing-center"' in component
	assert "customer: this.filters.customer || undefined" in component
	assert "this.filters.branch = ''" in component
	assert "this.filters.customer = ''" in component
	assert "this.filters.animal = ''" in component
	assert "frappe.set_route('Form', 'Veterinary Billing Session'" in component
	assert "frappe.set_route('Form', 'Sales Invoice'" in component
	assert "mountVetEdgeBillingCenter" in bundle


def test_billing_center_page_roles_do_not_promise_access_beyond_session_permissions():
	roles = page_roles("vetedge/veterinary/page/vetedge_billing_center/vetedge_billing_center.json")
	for role in ("System Manager", "VetEdge Administrator", "VetEdge Front Desk", "Branch Manager", "Accounts/Cashier", "Accounts User"):
		assert role in roles
	assert "Accounts Manager" not in roles
