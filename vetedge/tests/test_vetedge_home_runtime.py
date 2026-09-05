from __future__ import annotations

import frappe
from frappe.tests.utils import FrappeTestCase
from frappe.utils import nowdate

from vetedge.services.home import (
	ALL_BRANCHES_KEY,
	_build_metrics,
	get_home_payload,
	get_metric_drilldown,
)


class TestVetEdgeHomeRuntime(FrappeTestCase):
	def setUp(self):
		frappe.set_user("Administrator")

	def tearDown(self):
		frappe.set_user("Administrator")

	def ensure_user(self, email: str, roles: tuple[str, ...]) -> str:
		if not frappe.db.exists("User", email):
			frappe.get_doc(
				{
					"doctype": "User",
					"email": email,
					"first_name": "VHOME",
					"enabled": 1,
					"send_welcome_email": 0,
				}
			).insert(ignore_permissions=True)
		user = frappe.get_doc("User", email)
		existing = {row.role for row in user.get("roles") or []}
		for role in roles:
			if role not in existing:
				user.add_roles(role)
		return email

	def save_flags(self, *fieldnames: str) -> dict[str, object]:
		return {
			fieldname: frappe.db.get_single_value("Veterinary Settings", fieldname)
			for fieldname in fieldnames
		}

	def restore_flags(self, values: dict[str, object]) -> None:
		frappe.set_user("Administrator")
		for fieldname, value in values.items():
			frappe.db.set_single_value("Veterinary Settings", fieldname, value or 0, update_modified=False)

	def test_administrator_home_payload_executes_on_installed_site(self):
		payload = get_home_payload()
		self.assertEqual(payload["primary_persona"]["key"], "administrator")
		self.assertIn("context", payload)
		self.assertIn("metrics", payload)
		self.assertIn("attention", payload)
		self.assertIn("quick_actions", payload)
		self.assertEqual(payload["context"]["operational_date"], nowdate())
		self.assertIn("branch_options", payload["context"])

	def test_home_accepts_explicit_operational_date_and_all_branch_scope(self):
		payload = get_home_payload(operational_date="2026-09-04", branch=ALL_BRANCHES_KEY)
		self.assertEqual(payload["context"]["operational_date"], "2026-09-04")
		self.assertEqual(payload["context"]["branch"], "")
		self.assertEqual(payload["context"]["branch_value"], ALL_BRANCHES_KEY)

	def test_guest_cannot_load_veterinary_home_payload(self):
		frappe.set_user("Guest")
		with self.assertRaises(frappe.PermissionError):
			get_home_payload()

	def test_non_veterinary_desk_user_cannot_load_home_payload(self):
		user = self.ensure_user("vhome-desk-only@example.com", ("Desk User",))
		frappe.set_user(user)
		with self.assertRaises(frappe.PermissionError):
			get_home_payload()

	def test_doctor_starter_support_role_does_not_add_accounts_persona(self):
		user = self.ensure_user(
			"vhome-doctor@example.com",
			("VetEdge Doctor", "Desk User", "Accounts User", "Sales User", "Stock User"),
		)
		frappe.set_user(user)
		payload = get_home_payload()
		persona_keys = {persona["key"] for persona in payload["personas"]}
		self.assertEqual(payload["primary_persona"]["key"], "doctor")
		self.assertIn("doctor", persona_keys)
		self.assertNotIn("accounts", persona_keys)

	def test_front_desk_starter_support_role_does_not_add_accounts_persona(self):
		user = self.ensure_user(
			"vhome-frontdesk@example.com",
			("VetEdge Front Desk", "Desk User", "Accounts User", "Sales User"),
		)
		frappe.set_user(user)
		payload = get_home_payload()
		persona_keys = {persona["key"] for persona in payload["personas"]}
		self.assertEqual(payload["primary_persona"]["key"], "front-desk")
		self.assertNotIn("accounts", persona_keys)

	def test_accounts_user_without_vetedge_primary_role_uses_accounts_fallback(self):
		user = self.ensure_user(
			"vhome-accounts@example.com",
			("Desk User", "Accounts User"),
		)
		frappe.set_user(user)
		payload = get_home_payload()
		self.assertEqual(payload["primary_persona"]["key"], "accounts")

	def test_manager_doctor_receives_branch_and_personal_metric_scopes(self):
		original = self.save_flags("enable_vetedge", "enable_appointments", "enable_consultations")
		try:
			frappe.db.set_single_value("Veterinary Settings", "enable_vetedge", 1, update_modified=False)
			frappe.db.set_single_value("Veterinary Settings", "enable_appointments", 1, update_modified=False)
			frappe.db.set_single_value("Veterinary Settings", "enable_consultations", 1, update_modified=False)
			user = self.ensure_user(
				"vhome-manager-doctor@example.com",
				("Branch Manager", "VetEdge Doctor", "Desk User", "Accounts User", "Sales User", "Stock User"),
			)
			frappe.set_user(user)
			payload = get_home_payload()
			persona_keys = {persona["key"] for persona in payload["personas"]}
			metric_keys = {metric["key"] for metric in payload["metrics"]}

			self.assertEqual(payload["primary_persona"]["key"], "branch-manager")
			self.assertIn("doctor", persona_keys)
			self.assertIn("today-appointments", metric_keys)
			self.assertIn("my-appointments-today", metric_keys)
			self.assertIn("waiting-appointments", metric_keys)
			self.assertIn("waiting-for-me", metric_keys)
			self.assertIn("active-consultations", metric_keys)
			self.assertIn("my-active-consultations", metric_keys)
		finally:
			self.restore_flags(original)

	def test_waiting_appointment_metric_is_bounded_to_operational_date(self):
		original = self.save_flags("enable_vetedge", "enable_appointments")
		try:
			frappe.db.set_single_value("Veterinary Settings", "enable_vetedge", 1, update_modified=False)
			frappe.db.set_single_value("Veterinary Settings", "enable_appointments", 1, update_modified=False)
			metrics = _build_metrics(
				"Administrator",
				{"administrator"},
				"",
				[],
				True,
				"2026-09-04",
			)
			waiting = next(metric for metric in metrics if metric["key"] == "waiting-appointments")
			filters = waiting["_query"]["filters"]
			self.assertEqual(filters["status"], ["in", ["Confirmed", "Checked In"]])
			self.assertEqual(
				filters["appointment_datetime"],
				["between", ["2026-09-04 00:00:00", "2026-09-04 23:59:59"]],
			)
		finally:
			self.restore_flags(original)

	def test_card_count_matches_exact_metric_drilldown_total(self):
		original = self.save_flags("enable_vetedge", "enable_appointments")
		try:
			frappe.db.set_single_value("Veterinary Settings", "enable_vetedge", 1, update_modified=False)
			frappe.db.set_single_value("Veterinary Settings", "enable_appointments", 1, update_modified=False)
			payload = get_home_payload(operational_date=nowdate(), branch=ALL_BRANCHES_KEY)
			metric = next(row for row in payload["metrics"] if row["key"] == "today-appointments")
			drilldown = get_metric_drilldown(
				"today-appointments",
				operational_date=nowdate(),
				branch=ALL_BRANCHES_KEY,
			)
			self.assertEqual(metric["value"], drilldown["total"])
			self.assertEqual(drilldown["metric"]["key"], "today-appointments")
			self.assertEqual(drilldown["doctype"], "Veterinary Appointment")
			self.assertLessEqual(len(drilldown["rows"]), drilldown["total"])
		finally:
			self.restore_flags(original)

	def test_unknown_metric_cannot_be_used_as_generic_doctype_browser(self):
		with self.assertRaises(frappe.PermissionError):
			get_metric_drilldown("not-a-vetedge-home-metric")

	def test_groomer_receives_permission_safe_operational_snapshot(self):
		original = self.save_flags("enable_vetedge", "enable_grooming")
		try:
			frappe.db.set_single_value("Veterinary Settings", "enable_vetedge", 1, update_modified=False)
			frappe.db.set_single_value("Veterinary Settings", "enable_grooming", 1, update_modified=False)
			user = self.ensure_user(
				"vhome-groomer@example.com",
				("VetEdge Groomer", "Desk User"),
			)
			frappe.set_user(user)
			payload = get_home_payload()
			metric_keys = {metric["key"] for metric in payload["metrics"]}
			action_routes = {action["route"] for action in payload["quick_actions"]}

			self.assertEqual(payload["primary_persona"]["key"], "groomer")
			self.assertIn("grooming-today", metric_keys)
			self.assertIn("/desk/vetedge-resource-center?resource=grooming", action_routes)
		finally:
			self.restore_flags(original)

	def test_disabled_appointments_hide_front_desk_actions_and_metrics(self):
		original = self.save_flags("enable_vetedge", "enable_appointments")
		try:
			frappe.db.set_single_value("Veterinary Settings", "enable_vetedge", 1, update_modified=False)
			frappe.db.set_single_value("Veterinary Settings", "enable_appointments", 0, update_modified=False)
			user = self.ensure_user(
				"vhome-frontdesk-feature@example.com",
				("VetEdge Front Desk", "Desk User", "Accounts User", "Sales User"),
			)
			frappe.set_user(user)
			payload = get_home_payload()
			action_routes = {action["route"] for action in payload["quick_actions"]}
			metric_keys = {metric["key"] for metric in payload["metrics"]}

			self.assertNotIn("/desk/vetedge-resource-center?resource=appointments&new=1", action_routes)
			self.assertNotIn("/desk/vetedge-front-desk-action-center?tab=queue", action_routes)
			self.assertNotIn("/desk/vetedge-front-desk-action-center?tab=guest", action_routes)
			self.assertNotIn("/desk/vetedge-front-desk-action-center?tab=missed", action_routes)
			self.assertNotIn("today-appointments", metric_keys)
			self.assertNotIn("waiting-appointments", metric_keys)
			self.assertNotIn("missed-follow-up", metric_keys)
		finally:
			self.restore_flags(original)
