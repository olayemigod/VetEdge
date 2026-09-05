from __future__ import annotations

from pathlib import Path
from unittest import TestCase

REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
HOME_LOADER = REPOSITORY_ROOT / "vetedge" / "veterinary" / "page" / "vetedge" / "vetedge.js"
HOME_BUNDLE = REPOSITORY_ROOT / "vetedge" / "public" / "js" / "vetedge_home.bundle.js"
HOME_COMPONENT = REPOSITORY_ROOT / "vetedge" / "public" / "js" / "vetedge_home" / "VetEdgeHome.vue"
HOME_SERVICE = REPOSITORY_ROOT / "vetedge" / "services" / "home.py"


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
		self.assertNotIn('const target = "/desk/vetedge-resource-center"', loader)
		self.assertNotIn('frappe.set_route("vetedge-resource-center")', loader)

		self.assertIn("applyWorkspaceSafety(VetEdgeHome)", bundle)
		self.assertIn("window.mountVetEdgeHome", bundle)
		self.assertIn('active-route="/desk/vetedge"', component)

	def test_home_exposes_action_center_mini_dashboard_and_access_context(self):
		component = self.read(HOME_COMPONENT)
		for contract in (
			"Needs Your Attention",
			"Your Operational Snapshot",
			"Quick Actions",
			"Working as",
			"Branch scope",
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
