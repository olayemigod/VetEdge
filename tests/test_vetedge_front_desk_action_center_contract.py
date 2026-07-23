from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SERVICE = ROOT / "vetedge" / "services" / "front_desk_action_center.py"
COMPONENT = (
	ROOT
	/ "vetedge"
	/ "public"
	/ "js"
	/ "vetedge_front_desk_action_center"
	/ "VetEdgeFrontDeskActionCenter.vue"
)
BUNDLE = ROOT / "vetedge" / "public" / "js" / "vetedge_front_desk_action_center.bundle.js"
PAGE_ROOT = ROOT / "vetedge" / "veterinary" / "page" / "vetedge_front_desk_action_center"


def read(path: Path) -> str:
	return path.read_text(encoding="utf-8")


def test_phase_3_scope_is_a_dedicated_read_and_act_provider():
	service = read(SERVICE)
	component = read(COMPONENT)
	for contract in (
		"get_guest_requests",
		"get_guest_request_detail",
		"perform_guest_request_action",
		"get_appointment_queue_view",
		"get_appointment_action_detail",
		"perform_appointment_queue_action",
		"get_missed_appointments",
		"get_missed_appointment_detail",
		"perform_missed_appointment_action",
	):
		assert f"def {contract}" in service

	for tab in ("Appointment Queue", "Guest Requests", "Missed Appointments"):
		assert tab in component

	for excluded in (
		'frappe.get_doc("Sales Invoice"',
		'frappe.get_doc("Payment Entry"',
		'frappe.get_doc("Stock Entry"',
		"doc.submit()",
		"doc.cancel()",
	):
		assert excluded not in service


def test_reads_are_permission_and_branch_aware():
	service = read(SERVICE)
	for contract in (
		"require_internal_user()",
		"frappe.get_list(",
		'doc.check_permission("read")',
		'doc.check_permission("write")',
		"can_access_branch_data",
		"get_assigned_branches",
		"user_has_global_branch_access",
	):
		assert contract in service

	assert 'frappe.get_all(\n\t\t"Veterinary Appointment"' not in service
	assert "ignore_permissions=True" not in service


def test_actions_preserve_existing_business_controllers_and_platform_access():
	service = read(SERVICE)
	for contract in (
		"require_vetedge_platform_access",
		"confirm_guest_registration(doc.name)",
		"create_appointment_from_booking_request(doc.name)",
		"transition_appointment_status(doc.name, \"Confirmed\")",
		"transition_appointment_status(doc.name, \"Checked In\")",
		"create_consultation_from_appointment(doc.name)",
		"mark_missed_appointment_contacted",
		"reschedule_missed_appointment",
		"cancel_missed_appointment",
		"resolve_missed_appointment",
		"reopen_missed_appointment",
	):
		assert contract in service

	assert "appointment.save()" in service
	assert "doc.save()" in service
	assert "frappe.db.set_value" not in service


def test_modified_after_open_is_replaced_with_explicit_optimistic_locking():
	service = read(SERVICE)
	component = read(COMPONENT)
	for contract in (
		"def _assert_timestamp",
		"frappe.TimestampMismatchError",
		"This record changed after it was opened",
		"modified: this.detail.payload.modified",
		"Conflict-safe actions",
	):
		assert contract in service or contract in component


def test_frontend_is_full_edgesuite_and_uses_collision_safe_runtime():
	for path in (
		SERVICE,
		COMPONENT,
		BUNDLE,
		PAGE_ROOT / "vetedge_front_desk_action_center.js",
		PAGE_ROOT / "vetedge_front_desk_action_center.json",
	):
		assert path.exists(), path

	component = read(COMPONENT)
	loader = read(PAGE_ROOT / "vetedge_front_desk_action_center.js")
	bundle = read(BUNDLE)
	for contract in (
		"EdgeAppShell",
		"EdgePageLayout",
		"EdgePageHeader",
		"EdgeStatCard",
		"EdgeFilterBar",
		"EdgeDataTable",
		"EdgeStatusBadge",
		"EdgeLinkField",
		"EdgeModal",
		"EdgeLoadingState",
		"EdgeErrorState",
	):
		assert contract in component

	assert "frappe.ui.form" not in component
	assert "cur_frm" not in component
	assert "frappe.require('edgesuite_ui.bundle.js'" in loader
	assert "const runtime = window.EdgeSuiteUI;" in loader
	assert "frappe.require('edgeui.bundle.js'" not in loader
	assert "const runtime = window.EdgeSuiteUI;" in bundle
	assert "window.EdgeUI" not in bundle
	assert "applyWorkspaceSafety(VetEdgeFrontDeskActionCenter)" in bundle


def test_action_dialog_and_converted_patient_regressions_are_guarded():
	bundle = read(BUNDLE)
	for contract in (
		"detailLinksWithConvertedPatient",
		"values?.linked_patient",
		"closeActionDialog(force = false)",
		"closeActionDialog(true)",
	):
		assert contract in bundle


def test_native_front_desk_routes_redirect_to_action_center():
	guest_root = ROOT / "vetedge" / "veterinary" / "doctype" / "veterinary_guest_booking_request"
	missed_root = ROOT / "vetedge" / "veterinary" / "doctype" / "veterinary_missed_appointment"
	queue = ROOT / "vetedge" / "veterinary" / "page" / "veterinary_appointment_queue" / "veterinary_appointment_queue.js"

	for path, tab in (
		(guest_root / "veterinary_guest_booking_request.js", "guest"),
		(guest_root / "veterinary_guest_booking_request_list.js", "guest"),
		(missed_root / "veterinary_missed_appointment.js", "missed"),
		(missed_root / "veterinary_missed_appointment_list.js", "missed"),
		(queue, "queue"),
	):
		content = read(path)
		assert "/app/vetedge-front-desk-action-center" in content
		assert f"tab={tab}" in content
