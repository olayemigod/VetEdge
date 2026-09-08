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
		'DEFAULT_DATE_PRESET = "upcoming"',
		"APPOINTMENT_SORT_FIELDS = frozenset(",
		'"branch"',
		'"patient"',
		'"primary_owner"',
		'"practitioner"',
		'"status"',
		'"appointment_type"',
		'"consultation_type"',
		'date_preset: str = DEFAULT_DATE_PRESET',
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


def test_upcoming_is_server_side_time_and_lifecycle_semantic_scope():
	service = read("vetedge/services/appointment_resource_center.py")

	for marker in (
		"UPCOMING_STATUSES = (",
		'"Awaiting Registration",',
		'"Owner Requested",',
		'"Scheduled",',
		'"Confirmed",',
		'def _append_date_filters(',
		'if preset == "upcoming":',
		'current = now_datetime()',
		'[APPOINTMENT_DOCTYPE, "appointment_datetime", ">=", current]',
		'[APPOINTMENT_DOCTYPE, "status", "in", list(UPCOMING_STATUSES)]',
		'if preset == "past":',
		'[APPOINTMENT_DOCTYPE, "appointment_datetime", "<", current]',
		'if preset == "full_history":',
		'"date_preset": resolved_date_preset',
	):
		assert marker in service

	# Upcoming is intentionally not a static From Date shortcut.
	upcoming_block = service[service.index('if preset == "upcoming":') : service.index('if preset == "past":')]
	assert "from_date" not in upcoming_block
	assert "to_date" not in upcoming_block


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
		'label="Date Preset"',
		'type="date"',
		'label="From Date"',
		'label="To Date"',
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


def test_appointment_date_presets_use_edge_fuzzy_date_and_default_to_upcoming():
	component = read("vetedge/public/js/vetedge_resource_center/VetEdgeResourceCenter.vue")
	bundle = read("vetedge/public/js/vetedge_resource_center.bundle.js")

	for marker in (
		"const DEFAULT_APPOINTMENT_DATE_PRESET = 'upcoming';",
		"frappe.EdgeSuite.FuzzyDate = fuzzyDate;",
		"const EDGE_FUZZY_DATE = installEdgeFuzzyDate();",
		"appointmentDateStateFromParams(params)",
		"appointmentDatePresetOptions()",
		"return EDGE_FUZZY_DATE.getOptions();",
		"onAppointmentDatePresetChange()",
		"onAppointmentManualDateChange()",
		"date_preset: this.appointmentFilters.date_preset || DEFAULT_APPOINTMENT_DATE_PRESET",
		"this.appointmentFilters.date_preset = 'custom';",
		"datePreset: dateState.preset",
		"setField(resourceView.appointmentFilters, 'date_preset', state.datePreset)",
	):
		assert marker in bundle

	for preset in (
		"'upcoming'",
		"'today'",
		"'tomorrow'",
		"'next_7_days'",
		"'this_week'",
		"'next_week'",
		"'this_month'",
		"'next_30_days'",
		"'past'",
		"'full_history'",
		"'custom'",
	):
		assert preset in bundle

	# Existing Vue control remains the rendering surface; the bundle supplies the
	# appointment-specific fuzzy options without changing Billing Center DateRanges.
	assert 'v-model="appointmentFilters.date_preset"' in component
	assert '@change="onAppointmentDatePresetChange"' in component
	assert '@change="onAppointmentManualDateChange"' in component


def test_appointment_filter_grid_is_four_columns_on_desktop_and_responsive():
	component = read("vetedge/public/js/vetedge_resource_center/VetEdgeResourceCenter.vue")

	assert ".vetedge-resource-filters.is-appointment-filters {" in component
	assert "grid-template-columns: repeat(4, minmax(11rem, 1fr));" in component
	assert "@media (max-width: 74rem)" in component
	assert "grid-template-columns: repeat(2, minmax(12rem, 1fr));" in component
	assert "@media (max-width: 47.99rem)" in component
	assert "grid-template-columns: minmax(0, 1fr);" in component


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
		"'date_preset',",
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
