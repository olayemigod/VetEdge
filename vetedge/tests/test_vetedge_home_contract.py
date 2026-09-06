from __future__ import annotations

from pathlib import Path
from unittest import TestCase

REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
HOME_LOADER = REPOSITORY_ROOT / "vetedge" / "veterinary" / "page" / "vetedge" / "vetedge.js"
HOME_BUNDLE = REPOSITORY_ROOT / "vetedge" / "public" / "js" / "vetedge_home.bundle.js"
HOME_COMPONENT = REPOSITORY_ROOT / "vetedge" / "public" / "js" / "vetedge_home" / "VetEdgeHome.vue"
HOME_SERVICE = REPOSITORY_ROOT / "vetedge" / "services" / "home.py"
ROLE_BUNDLES = REPOSITORY_ROOT / "vetedge" / "services" / "role_bundles.py"
INSTALL_FOUNDATION = REPOSITORY_ROOT / "vetedge" / "install" / "__init__.py"
SERVICE_OPERATIONS_BUNDLE = REPOSITORY_ROOT / "vetedge" / "public" / "js" / "vetedge_service_operations.bundle.js"
SERVICE_OPERATIONS_COMPONENT = REPOSITORY_ROOT / "vetedge" / "public" / "js" / "vetedge_service_operations" / "VetEdgeServiceOperations.vue"
SERVICE_OPERATIONS_PAGE = REPOSITORY_ROOT / "vetedge" / "veterinary" / "page" / "vetedge_service_operations" / "vetedge_service_operations.js"


class TestVetEdgeHomeContract(TestCase):
	def read(self, path: Path) -> str:
		self.assertTrue(path.exists(), path)
		return path.read_text(encoding="utf-8")

	def test_home_is_a_real_edgesuite_page_not_a_patient_redirect(self):
		loader = self.read(HOME_LOADER)
		bundle = self.read(HOME_BUNDLE)
		component = self.read(HOME_COMPONENT)

		self.assertIn("vetedge_home.bundle.js", loader)
		self.assertIn("window.mountVetEdgeHome", loader)
		self.assertIn("refreshMountedVetEdgeHome", loader)
		self.assertIn('"EdgeDataTable"', loader)
		self.assertNotIn('const target = "/desk/vetedge-resource-center"', loader)
		self.assertNotIn('frappe.set_route("vetedge-resource-center")', loader)

		self.assertIn("applyWorkspaceSafety(VetEdgeHome)", bundle)
		self.assertIn("window.mountVetEdgeHome", bundle)
		self.assertIn('active-route="/desk/vetedge"', component)

	def test_warm_navigation_refresh_age_only_moves_after_real_refresh(self):
		loader = self.read(HOME_LOADER)
		stale_block = loader[loader.index("if (stale) {") : loader.index("return true;")]
		self.assertIn("await view.loadHome?.();", stale_block)
		self.assertIn("wrapper.vetedge_home_last_refresh_at = Date.now();", stale_block)
		self.assertLess(
			stale_block.index("await view.loadHome?.();"),
			stale_block.index("wrapper.vetedge_home_last_refresh_at = Date.now();"),
		)
		self.assertEqual(stale_block.count("wrapper.vetedge_home_last_refresh_at = Date.now();"), 1)

	def test_home_exposes_action_center_mini_dashboard_and_access_context(self):
		component = self.read(HOME_COMPONENT)
		for contract in (
			"Needs Your Attention",
			"Your Operational Snapshot",
			"Quick Actions",
			"Working as",
			"Branch scope",
			"Operational date",
			"Additional access",
			"payload.attention",
			"payload.metrics",
			"payload.quick_actions",
			"primaryPersonaLabel",
			"actionGroups",
		):
			self.assertIn(contract, component)

	def test_home_payload_is_role_branch_and_permission_aware(self):
		service = self.read(HOME_SERVICE)
		for contract in (
			"is_internal_staff_user",
			"get_user_roles",
			"get_assigned_branches",
			"user_has_global_branch_access",
			"can_access_branch_data",
			"frappe.has_permission",
			"frappe.get_list",
			"_branch_filters",
			"_matched_personas",
			"primary_persona",
			"personas",
			"quick_actions",
			"attention",
			"metrics",
		):
			self.assertIn(contract, service)

		for forbidden in (
			"ignore_permissions=True",
			"ignore_permissions = True",
			"frappe.db.sql",
			"frappe.db.set_value",
			"frappe.delete_doc",
			"submit()",
			"cancel()",
		):
			self.assertNotIn(forbidden, service)

	def test_home_metric_drilldown_reuses_the_server_metric_query(self):
		service = self.read(HOME_SERVICE)
		component = self.read(HOME_COMPONENT)
		for contract in (
			"def get_metric_drilldown(",
			'query = metric["_query"]',
			'filters = query["filters"]',
			"_permission_count(doctype, filters)",
			"_public_metric(metric)",
			'"metrics": [_public_metric(metric) for metric in metrics]',
			"limit_page_length=page_length",
		):
			self.assertIn(contract, service)
		for contract in (
			"openMetric(metric.key)",
			"openMetric(item.key)",
			"vetedge.services.home.get_metric_drilldown",
			"reconcileMetricCount",
			"Exact card records",
			"Showing {{ drilldownFirst }}-{{ drilldownLast }} of {{ drilldown.total }}",
		):
			if contract.startswith("Showing"):
				self.assertIn("Showing {{ drilldownFirst }}", component)
				self.assertIn("of {{ drilldown.total }}", component)
			else:
				self.assertIn(contract, component)

	def test_home_drilldown_rows_open_exact_approved_record_destinations(self):
		bundle = self.read(HOME_BUNDLE)
		for contract in (
			"APPROVED_DRILLDOWN_ROUTES",
			"approvedDrilldownRoute",
			"'Veterinary Appointment': (name) => `/desk/vetedge-resource-center?resource=appointments&name=${encodeURIComponent(name)}`",
			"'Veterinary Consultation': (name) => `/desk/vetedge-clinical-workspace?consultation=${encodeURIComponent(name)}`",
			"'Veterinary Lab Order': (name) => `/desk/vetedge-resource-center?resource=lab-orders&name=${encodeURIComponent(name)}`",
			"'Veterinary Missed Appointment': (name) => `/desk/vetedge-front-desk-action-center?tab=missed&name=${encodeURIComponent(name)}`",
			"'Pet Grooming Appointment': (name) => `/desk/vetedge-service-operations?resource=grooming-appointments&name=${encodeURIComponent(name)}`",
			"'Sales Invoice': (name) => `/desk/sales-invoice/${encodeURIComponent(name)}`",
			"this.openRoute(route)",
			"does not have an approved Veterinary Home drill-through",
		):
			self.assertIn(contract, bundle)
		self.assertNotIn("frappe.set_route('Form'", bundle)
		self.assertNotIn('frappe.set_route("Form"', bundle)

	def test_grooming_drilldown_deep_link_opens_service_detail_not_retired_list(self):
		bundle = self.read(SERVICE_OPERATIONS_BUNDLE)
		component = self.read(SERVICE_OPERATIONS_COMPONENT)
		page = self.read(SERVICE_OPERATIONS_PAGE)

		for contract in (
			"GROOMING_APPOINTMENTS_TAB",
			"value: 'grooming-appointments'",
			"state.resource = GROOMING_APPOINTMENTS_TAB.value",
			"requestedServiceResource()",
		):
			self.assertIn(contract, bundle)
		self.assertIn("'grooming-appointments'", page)
		self.assertIn('requestedName: params.get("name") || ""', component)
		self.assertIn('await this.openDetail({ name });', component)
		self.assertIn("if (this.requestedName && this.resource !== \"availability\")", component)

	def test_home_branch_and_operational_date_are_first_class_context(self):
		service = self.read(HOME_SERVICE)
		component = self.read(HOME_COMPONENT)
		for contract in (
			'ALL_BRANCHES_KEY = "__all__"',
			"_resolve_operational_date",
			"_branch_options",
			"branch_options",
			"operational_date",
			"_date_range(operational_date)",
		):
			self.assertIn(contract, service)
		for contract in (
			"Working branch",
			"Operational date",
			"selectedBranch",
			"selectedDate",
			"applyContext",
			"updateLocation",
		):
			self.assertIn(contract, component)

	def test_waiting_queue_uses_selected_date_not_unbounded_status_backlog(self):
		service = self.read(HOME_SERVICE)
		self.assertIn("waiting_filters = _with(\n\t\t\tdate_filters,", service)
		self.assertIn("waiting_for_me_filters = _with(\n\t\t\tmy_date_filters,", service)
		self.assertIn('status=["in", ["Confirmed", "Checked In"]]', service)

	def test_branch_specific_metrics_fail_closed_if_source_has_no_branch_field(self):
		service = self.read(HOME_SERVICE)
		self.assertIn("if branch or (assigned and not global_access):", service)
		self.assertIn("return None", service)
		self.assertIn("if value is None or filters is None:", service)

	def test_generic_accounts_support_roles_do_not_pollute_clinical_personas(self):
		service = self.read(HOME_SERVICE)
		self.assertIn('GENERIC_ACCOUNTS_ROLES = {ROLE_ACCOUNTS_MANAGER, ROLE_ACCOUNTS_USER}', service)
		self.assertIn('"roles": {ROLE_ACCOUNTS_CASHIER, "VetEdge Accounts/Cashier"}', service)
		self.assertIn("if not personas and roles & GENERIC_ACCOUNTS_ROLES", service)
		self.assertIn("starter bundles deliberately add generic ERPNext support roles", service)

	def test_role_specific_and_multi_role_metrics_keep_distinct_scopes(self):
		service = self.read(HOME_SERVICE)
		for contract in (
			"_build_appointment_metrics",
			'broad_personas = {"administrator", "branch-manager", "front-desk", "nurse"}',
			'"my-appointments-today"',
			'"waiting-for-me"',
			"_build_consultation_metrics",
			'broad_personas = {"administrator", "branch-manager", "nurse"}',
			'"my-active-consultations"',
			'"my-completed-today"',
			'persona_keys & {"accounts", "branch-manager", "administrator"}',
		):
			self.assertIn(contract, service)

	def test_home_respects_existing_veterinary_feature_switches(self):
		service = self.read(HOME_SERVICE)
		for contract in (
			"get_veterinary_settings_flag",
			"FEATURE_ROUTE_FLAGS",
			"_route_feature_enabled",
			'_feature_enabled("enable_appointments")',
			'_feature_enabled("enable_consultations")',
			'_feature_enabled("enable_dispensary_flow")',
			'_feature_enabled("enable_vetedge")',
			'("/desk/vetedge-resource-center?resource=vaccinations", "enable_vaccination")',
			'("/desk/vetedge-hospitalisation-operations", "enable_veterinary_hospitalisation")',
			'("/desk/stock-expiry-monitor", "enable_stock_expiry_monitor")',
			'("/desk/vetedge-resource-center?resource=grooming", "enable_grooming")',
			"not _route_feature_enabled(route)",
		):
			self.assertIn(contract, service)

	def test_home_reuses_existing_operational_routes_instead_of_rebuilding_workflows(self):
		service = self.read(HOME_SERVICE)
		for route in (
			"/desk/vetedge-clinical-workspace",
			"/desk/vetedge-front-desk-action-center?tab=queue",
			"/desk/vetedge-resource-center?resource=patients",
			"/desk/vetedge-resource-center?resource=lab-orders",
			"/desk/vetedge-resource-center?resource=vaccinations",
			"/desk/vetedge-hospitalisation-operations",
			"/desk/vetedge-service-operations?resource=grooming-sessions",
			"/desk/vetedge-executive-dashboard",
		):
			self.assertIn(route, service)

	def test_vetedge_default_app_is_user_scoped_and_preserves_existing_preference(self):
		role_bundles = self.read(ROLE_BUNDLES)
		for contract in (
			"def _ensure_vetedge_default_app(user_doc)",
			'if getattr(user_doc, "default_app", None):',
			'user_doc.db_set("default_app", "vetedge", update_modified=False)',
			"_ensure_vetedge_default_app(user_doc)",
		):
			self.assertIn(contract, role_bundles)
		self.assertNotIn('frappe.db.set_value("Role"', role_bundles)

	def test_vetedge_starter_roles_have_guarded_home_page_landing(self):
		install = self.read(INSTALL_FOUNDATION)
		for contract in (
			'VETEDGE_HOME_PAGE = "desk/vetedge"',
			"ensure_vetedge_role_home_pages()",
			"for role in dict.fromkeys(STARTER_BUNDLE_PRIMARY_ROLES.values()):",
			'current_home = frappe.db.get_value("Role", role, "home_page")',
			"if current_home:",
			'frappe.db.set_value("Role", role, "home_page", VETEDGE_HOME_PAGE, update_modified=False)',
		):
			self.assertIn(contract, install)
		self.assertNotIn('"VetEdge Portal User":', install)

	def test_home_frontend_contains_no_business_document_writes(self):
		component = self.read(HOME_COMPONENT)
		bundle = self.read(HOME_BUNDLE)
		for content in (component, bundle):
			for forbidden in (
				"frappe.db.set_value",
				"frappe.client.insert",
				"frappe.client.set_value",
				"frappe.client.delete",
				"frappe.client.submit",
			):
				self.assertNotIn(forbidden, content)
