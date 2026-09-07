from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def read(relative: str) -> str:
	return (ROOT / relative).read_text(encoding="utf-8")


def test_appointment_worklist_backend_is_permission_aware_filtered_and_safely_sorted():
	service = read("vetedge/services/appointment_resource_center.py")

	for marker in (
		'APPOINTMENT_DOCTYPE = "Veterinary Appointment"',
		'DEFAULT_SORT_BY = "appointment_datetime"',
		'DEFAULT_SORT_ORDER = "asc"',
		"APPOINTMENT_SORT_FIELDS = frozenset(",
		'"branch"',
		'"patient"',
		'"primary_owner"',
		'"practitioner"',
		'"status"',
		'"appointment_type"',
		'"consultation_type"',
		'from_date: str = ""',
		'to_date: str = ""',
		"can_access_branch_data(frappe.session.user, selected, raise_exception=True)",
		"frappe.get_list(",
		'if fieldname not in APPOINTMENT_SORT_FIELDS:',
		'if order not in {"asc", "desc"}:',
		'order_by=f"{sort_field} {order}, name asc"',
		'"sortable": fieldname in APPOINTMENT_SORT_FIELDS',
	):
		assert marker in service

	for forbidden in (
		"ignore_permissions=True",
		"frappe.db.sql",
		".submit(",
		".cancel(",
		"frappe.db.set_value",
		"frappe.delete_doc",
	):
		assert forbidden not in service


def test_appointment_page_exposes_operational_filters_with_cascading_context():
	component = read("vetedge/public/js/vetedge_resource_center/VetEdgeResourceCenter.vue")

	for marker in (
		"'is-appointment-filters': isAppointments",
		'label="Branch"',
		'label="Status"',
		'label="Appointment Type"',
		'label="Patient"',
		'label="Primary Owner"',
		'label="Practitioner"',
		'label="Consultation Type"',
		'type="date" label="From Date"',
		'type="date" label="To Date"',
		'appointmentFilters: {',
		'appointmentFilterLabels: {',
		'appointmentSort: {',
		'vetedge.services.appointment_edgeui.search_appointment_link',
		'vetedge.services.appointment_resource_center.get_appointment_page',
		'this.clearAppointmentFilter("patient")',
		'this.clearAppointmentFilter("practitioner")',
		'this.clearAppointmentFilter("consultation_type")',
	):
		assert marker in component


def test_appointment_table_sorting_is_server_side_and_route_persistent():
	component = read("vetedge/public/js/vetedge_resource_center/VetEdgeResourceCenter.vue")
	bundle = read("vetedge/public/js/vetedge_resource_center.bundle.js")

	for marker in (
		"column.sortable",
		'@click="sortColumn(column)"',
		"sortColumn(column)",
		"sortIndicator(column)",
		'parameters.set("sort_by", this.appointmentSort.by',
		'parameters.set("sort_order", this.appointmentSort.order',
		'sort_by: this.appointmentSort.by',
		'sort_order: this.appointmentSort.order',
	):
		assert marker in component

	for marker in (
		"'owner',",
		"'practitioner',",
		"'consultation_type',",
		"'sort_by',",
		"'sort_order',",
		"owner: valueFrom(params, 'owner')",
		"practitioner: valueFrom(params, 'practitioner')",
		"consultationType: valueFrom(params, 'consultation_type')",
		"sortBy: valueFrom(params, 'sort_by', DEFAULT_APPOINTMENT_SORT.by)",
		"setLinkField(resourceView.appointmentFilters, resourceView.appointmentFilterLabels, 'patient', state.patient)",
		"setField(resourceView.appointmentSort, 'by', state.sortBy)",
		"setField(resourceView.appointmentSort, 'order', state.sortOrder)",
	):
		assert marker in bundle

	assert "window.open" not in component
