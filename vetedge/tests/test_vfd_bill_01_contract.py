from __future__ import annotations

import json
from pathlib import Path

from vetedge.install.dashboard import _organize_veterinary_navigation
from vetedge.install.patient_navigation import organize_direct_patient_navigation


ROOT = Path(__file__).resolve().parents[2]
APP = ROOT / "vetedge"
SIDEBAR = APP / "workspace_sidebar" / "vetedge.json"


def read(path: Path) -> str:
	return path.read_text(encoding="utf-8")


def source_items() -> list[dict]:
	return json.loads(read(SIDEBAR)).get("items") or []


def dashboard_items() -> list[dict]:
	return _organize_veterinary_navigation(source_items())


def transformed_items() -> list[dict]:
	return organize_direct_patient_navigation(dashboard_items())


def labels_in_section(items: list[dict], section: str) -> list[str]:
	current = None
	labels = []
	for item in items:
		if item.get("type") == "Section Break":
			current = item.get("label")
			continue
		if current == section and item.get("type") == "Link":
			labels.append(item.get("label"))
	return labels


def link_by_label(items: list[dict], label: str) -> dict:
	matches = [item for item in items if item.get("type") == "Link" and item.get("label") == label]
	assert len(matches) == 1, (label, matches)
	return matches[0]


def section_by_label(items: list[dict], label: str) -> dict:
	matches = [item for item in items if item.get("type") == "Section Break" and item.get("label") == label]
	assert len(matches) == 1, (label, matches)
	return matches[0]


def test_navigation_transforms_are_idempotent():
	dashboard = dashboard_items()
	assert _organize_veterinary_navigation(dashboard) == dashboard

	first = organize_direct_patient_navigation(dashboard)
	second = organize_direct_patient_navigation(first)
	assert second == first


def test_patients_is_a_separate_primary_navigation_group():
	source = source_items()
	items = transformed_items()
	sections = [item.get("label") for item in items if item.get("type") == "Section Break"]

	assert sections[0] == "Patients"
	assert sections.index("Patients") < sections.index("Dashboard")
	assert labels_in_section(items, "Patients") == ["Patients"]
	assert "Patients" not in labels_in_section(items, "Front Desk")

	patient = link_by_label(items, "Patients")
	assert patient.get("link_type") == "DocType"
	assert patient.get("link_to") == "Veterinary Patient"
	assert patient.get("display_depends_on") == link_by_label(source, "Patients").get("display_depends_on")
	assert section_by_label(items, "Patients").get("display_depends_on") == patient.get("display_depends_on")


def test_patients_shell_contract_is_direct_and_non_collapsible():
	hardening = read(APP / "public/js/vetedge_postqa_navigation_hardening.js")

	for marker in (
		'const PATIENTS_ATTRIBUTE = "data-vetedge-direct-patients"',
		'const PATIENTS_ROUTE = "/desk/vetedge-resource-center?resource=patients"',
		"function patchDirectPatients(shell)",
		'item.removeAttribute("aria-expanded")',
		'item.removeAttribute("aria-controls")',
		'patchDirectPatients(shell);',
		"navigatePatients",
		"directPatients",
	):
		assert marker in hardening

	assert 'directHome.insertAdjacentElement("afterend", directItem)' in hardening


def test_front_desk_contains_booking_work_not_accounting_or_patient_links():
	items = transformed_items()
	front_desk = labels_in_section(items, "Front Desk")

	for expected in (
		"Appointment Queue",
		"Appointments",
		"Pet Boarding Booking",
		"Guest Booking Requests",
		"Missed Appointments",
	):
		assert expected in front_desk

	for removed in ("Patients", "Customer", "Customers", "Sales Invoice", "Payment Entry"):
		assert removed not in front_desk

	assert front_desk.index("Pet Boarding Booking") == front_desk.index("Appointments") + 1
	assert [item.get("label") for item in items].count("Pet Boarding Booking") == 1
	assert "Pet Grooming Appointment" not in [item.get("label") for item in items]


def test_front_desk_operational_routes_are_real_pages():
	items = transformed_items()
	expected = {
		"Appointment Queue": "vetedge-front-desk-queue",
		"Guest Booking Requests": "vetedge-front-desk-guest-bookings",
		"Missed Appointments": "vetedge-front-desk-missed-appointments",
	}
	for label, target in expected.items():
		link = link_by_label(items, label)
		assert link.get("link_type") == "Page"
		assert link.get("link_to") == target


def test_billing_center_is_a_separate_menu_group_with_requested_links():
	items = transformed_items()
	sections = [item.get("label") for item in items if item.get("type") == "Section Break"]
	assert "Billing Center" in sections
	assert sections.index("Billing Center") == sections.index("Front Desk") + 1
	assert labels_in_section(items, "Billing Center") == [
		"Customers",
		"Sales Invoice",
		"Payment Entry",
		"Billing Session",
		"Billing Center",
	]

	expected = {
		"Customers": ("DocType", "Customer"),
		"Sales Invoice": ("DocType", "Sales Invoice"),
		"Payment Entry": ("DocType", "Payment Entry"),
		"Billing Session": ("DocType", "Veterinary Billing Session"),
		"Billing Center": ("Page", "vetedge-billing-center"),
	}
	for label, (link_type, link_to) in expected.items():
		link = link_by_label(items, label)
		assert link.get("link_type") == link_type
		assert link.get("link_to") == link_to


def test_regrouping_preserves_existing_link_visibility_and_limits_new_billing_workspace():
	source = source_items()
	items = transformed_items()

	assert link_by_label(items, "Customers").get("display_depends_on") == link_by_label(source, "Customer").get("display_depends_on")
	assert link_by_label(items, "Sales Invoice").get("display_depends_on") == link_by_label(source, "Sales Invoice").get("display_depends_on")
	assert link_by_label(items, "Payment Entry").get("display_depends_on") == link_by_label(source, "Payment Entry").get("display_depends_on")
	assert link_by_label(items, "Pet Boarding Booking").get("display_depends_on") == link_by_label(source, "Pet Boarding Booking").get("display_depends_on")
	assert link_by_label(items, "Patients").get("display_depends_on") == link_by_label(source, "Patients").get("display_depends_on")

	section_visibility = section_by_label(items, "Billing Center").get("display_depends_on", "")
	for role in ("VetEdge Front Desk", "VetEdge Doctor", "Accounts/Cashier", "Accounts Manager", "Branch Manager"):
		assert role in section_visibility

	for label in ("Billing Session", "Billing Center"):
		visibility = link_by_label(items, label).get("display_depends_on", "")
		for role in ("System Manager", "VetEdge Administrator", "VetEdge Front Desk", "Accounts/Cashier", "Accounts User", "Branch Manager"):
			assert role in visibility
		assert "VetEdge Doctor" not in visibility
		assert "Accounts Manager" not in visibility


def test_dedicated_front_desk_pages_share_one_fixed_mode_shell():
	host = read(APP / "public/js/vetedge_front_desk_page_host.js")
	bundle = read(APP / "public/js/vetedge_front_desk_action_center.bundle.js")
	component = read(APP / "public/js/vetedge_front_desk_action_center/VetEdgeFrontDeskActionCenter.vue")

	assert "mountVetEdgeFrontDeskActionCenter(root[0], { fixedTab })" in host
	assert "buildFrontDeskRoot(runtime, options = {})" in bundle
	assert "state.fixedTab = fixedTab" in bundle
	assert 'v-if="!fixedTab"' in component

	pages = {
		"vetedge_front_desk_queue/vetedge_front_desk_queue.js": "fixedTab: 'queue'",
		"vetedge_front_desk_guest_bookings/vetedge_front_desk_guest_bookings.js": "fixedTab: 'guest'",
		"vetedge_front_desk_missed_appointments/vetedge_front_desk_missed_appointments.js": "fixedTab: 'missed'",
	}
	for relative, marker in pages.items():
		loader = read(APP / "veterinary/page" / relative)
		assert "vetedge_front_desk_page_host.js" in loader
		assert marker in loader


def test_front_desk_page_roles_preserve_replaced_link_access():
	queue = json.loads(read(APP / "veterinary/page/vetedge_front_desk_queue/vetedge_front_desk_queue.json"))
	missed = json.loads(read(APP / "veterinary/page/vetedge_front_desk_missed_appointments/vetedge_front_desk_missed_appointments.json"))
	legacy = json.loads(read(APP / "veterinary/page/vetedge_front_desk_action_center/vetedge_front_desk_action_center.json"))

	queue_roles = {row.get("role") for row in queue.get("roles") or []}
	missed_roles = {row.get("role") for row in missed.get("roles") or []}
	legacy_roles = {row.get("role") for row in legacy.get("roles") or []}

	for role in ("Veterinary Nurse", "Dispensary User"):
		assert role in queue_roles
		assert role in legacy_roles
	assert "Veterinary Nurse" in missed_roles


def test_old_action_center_and_queue_are_compatibility_only():
	old_center = read(APP / "veterinary/page/vetedge_front_desk_action_center/vetedge_front_desk_action_center.js")
	old_queue = read(APP / "veterinary/page/veterinary_appointment_queue/veterinary_appointment_queue.js")

	for route in (
		"/desk/vetedge-front-desk-queue",
		"/desk/vetedge-front-desk-guest-bookings",
		"/desk/vetedge-front-desk-missed-appointments",
	):
		assert route in old_center
	assert "mountVetEdgeFrontDeskActionCenter" not in old_center
	assert "/desk/vetedge-front-desk-queue" in old_queue
	assert "?tab=queue" not in old_queue


def test_billing_center_is_read_only_over_authoritative_accounting_documents():
	service = read(APP / "services/billing_center.py")
	component = read(APP / "public/js/vetedge_billing_center/VetEdgeBillingCenter.vue")

	for forbidden in (
		"ignore_permissions=True",
		"frappe.db.sql",
		".submit(",
		".cancel(",
		"frappe.delete_doc",
		"frappe.db.set_value",
	):
		assert forbidden not in service

	assert 'BILLING_SESSION_DOCTYPE = "Veterinary Billing Session"' in service
	assert "PAGE_LENGTH_MAX = 100" in service
	assert '"__vetedge_no_permitted_branch__"' in service
	assert "frappe.get_list(" in service
	assert "current_draft_invoice" in service
	assert "latest_invoice" in service
	assert "frappe.set_route('Form', 'Veterinary Billing Session'" in component
	assert "frappe.set_route('Form', 'Sales Invoice'" in component
	assert "frappe.set_route('List', doctype)" in component
	for mutation_word in ("submit_invoice", "cancel_invoice", "create_payment_entry", "allocate_payment"):
		assert mutation_word not in component


def test_billing_center_filters_are_contextual_cascading_and_branch_safe():
	service = read(APP / "services/billing_center.py")
	component = read(APP / "public/js/vetedge_billing_center/VetEdgeBillingCenter.vue")

	assert "get_billing_center_link_options" in service
	assert "group_by=field" in service
	assert "page_length=20" in service
	assert 'if field == "branch" and scope.get("restricted")' in service
	assert 'customer: str | None = None' in service
	assert 'context["customer"] = cstr(customer or "").strip()' in service
	assert "if (field === 'company')" in component
	assert "this.filters.branch = ''" in component
	assert "this.filters.customer = ''" in component
	assert "this.filters.animal = ''" in component
	assert "customer: this.filters.customer || undefined" in component
	assert 'active-route="/desk/vetedge-billing-center"' in component


def test_billing_center_page_roles_match_workspace_data_access_contract():
	page = json.loads(read(APP / "veterinary/page/vetedge_billing_center/vetedge_billing_center.json"))
	roles = {row.get("role") for row in page.get("roles") or []}
	for role in ("System Manager", "VetEdge Administrator", "VetEdge Front Desk", "Branch Manager", "Accounts/Cashier", "Accounts User"):
		assert role in roles
	assert "Accounts Manager" not in roles
