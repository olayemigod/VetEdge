from __future__ import annotations

import json
from collections import Counter
from pathlib import Path
from unittest import TestCase


APP_ROOT = Path("/home/olayemigod/frappe-bench/apps/vetedge/vetedge")
WORKSPACE_SIDEBAR = APP_ROOT / "workspace_sidebar/vetedge.json"


def _load_sidebar() -> dict:
	return json.loads(WORKSPACE_SIDEBAR.read_text())


def _links_by_label(items: list[dict]) -> dict[str, dict]:
	return {
		item["label"]: item
		for item in items
		if item.get("type") == "Link" and item.get("label")
	}


class TestWorkspaceSidebar(TestCase):
	def test_vetedge_workspace_sidebar_json_is_valid(self):
		sidebar = _load_sidebar()
		self.assertEqual(sidebar["doctype"], "Workspace Sidebar")
		self.assertEqual(sidebar["name"], "VetEdge")
		self.assertIsInstance(sidebar.get("items"), list)

	def test_sidebar_labels_do_not_expose_veterinary_as_navigation_surface(self):
		items = _load_sidebar()["items"]
		for item in items:
			label = item.get("label") or ""
			if label in ("Veterinary Records", "Veterinary Masters"):
				continue
			self.assertFalse(label.startswith("Veterinary"), label)

	def test_missed_appointments_is_in_appointment_cluster(self):
		items = _load_sidebar()["items"]
		labels = [item.get("label") for item in items]
		missed_index = labels.index("Missed Appointments")

		self.assertGreater(missed_index, labels.index("Appointments"))
		self.assertLess(missed_index, labels.index("Guest Booking Requests"))

		link = _links_by_label(items)["Missed Appointments"]
		self.assertEqual(link["link_to"], "Veterinary Missed Appointment")
		self.assertEqual(link["link_type"], "DocType")
		self.assertIn("VetEdge Front Desk", link.get("display_depends_on", ""))
		self.assertIn("Branch Manager", link.get("display_depends_on", ""))

	def test_hospitalisation_navigation_is_grouped_in_dedicated_section(self):
		items = _load_sidebar()["items"]
		labels = [item.get("label") for item in items]
		hospitalisation_index = labels.index("Hospitalisation")
		records_index = labels.index("Veterinary Records")

		for label in (
			"Hospitalisations",
			"Care Locations",
			"Active Hospitalisations",
			"Hospitalisation Charge Summary",
			"Care Location Occupancy",
			"Hospitalisation Discharge Watch",
			"Pending Hospitalisation Actions",
		):
			self.assertGreater(labels.index(label), hospitalisation_index)
			self.assertLess(labels.index(label), records_index)

		link = _links_by_label(items)["Hospitalisations"]
		self.assertEqual(link["link_to"], "Veterinary Hospitalisation")
		self.assertEqual(link["link_type"], "DocType")
		self.assertIn("VetEdge Doctor", link.get("display_depends_on", ""))
		self.assertIn("Veterinary Nurse", link.get("display_depends_on", ""))

	def test_hospitalisation_dashboard_page_is_not_exposed(self):
		items = _load_sidebar()["items"]
		links = _links_by_label(items)
		self.assertNotIn("Hospitalisation Dashboard", links)
		for item in items:
			self.assertFalse(item.get("link_to") == "veterinary-hospitalisation-dashboard", item)

	def test_hospitalisation_operational_reports_remain_linked(self):
		links = _links_by_label(_load_sidebar()["items"])
		for label in (
			"Active Hospitalisations",
			"Hospitalisation Charge Summary",
			"Care Location Occupancy",
			"Hospitalisation Discharge Watch",
			"Pending Hospitalisation Actions",
		):
			self.assertIn(label, links)
			self.assertEqual(links[label]["link_type"], "Report")
			self.assertEqual(links[label]["link_to"], label)

	def test_notification_items_is_admin_monitoring_link(self):
		items = _load_sidebar()["items"]
		labels = [item.get("label") for item in items]
		item_index = labels.index("Notification Items")

		self.assertGreater(item_index, labels.index("Notification Event Registry"))
		self.assertLess(item_index, labels.index("Notification Log"))

		link = _links_by_label(items)["Notification Items"]
		self.assertEqual(link["link_to"], "Veterinary Notification Item")
		self.assertEqual(link["link_type"], "DocType")
		self.assertIn("System Manager", link.get("display_depends_on", ""))
		self.assertIn("VetEdge Administrator", link.get("display_depends_on", ""))

	def test_workspace_sidebar_has_no_duplicate_links_for_added_doctypes(self):
		links = [
			(item.get("label"), item.get("link_to"), item.get("link_type"))
			for item in _load_sidebar()["items"]
			if item.get("type") == "Link"
		]
		counts = Counter(links)
		for key in (
			("Hospitalisations", "Veterinary Hospitalisation", "DocType"),
			("Missed Appointments", "Veterinary Missed Appointment", "DocType"),
			("Notification Items", "Veterinary Notification Item", "DocType"),
		):
			self.assertEqual(counts[key], 1)

	def test_patient_link_is_only_under_vetedge_records(self):
		items = _load_sidebar()["items"]
		labels = [item.get("label") for item in items]
		patient_indexes = [
			index
			for index, item in enumerate(items)
			if item.get("type") == "Link" and item.get("link_to") == "Veterinary Patient"
		]

		self.assertEqual(len(patient_indexes), 1)
		self.assertGreater(patient_indexes[0], labels.index("Veterinary Records"))
		self.assertEqual(items[patient_indexes[0]]["icon"], "users-round")

	def test_notification_item_label_uses_vetedge_navigation_language(self):
		links = _links_by_label(_load_sidebar()["items"])
		self.assertIn("Notification Items", links)
		self.assertNotIn("Veterinary Notification Item", links)

	def test_vetedge_sections_are_collapsed_by_default(self):
		sections = {
			item["label"]: item
			for item in _load_sidebar()["items"]
			if item.get("type") == "Section Break"
		}

		for label in ("Dashboards", "Hospitalisation", "Veterinary Records", "Veterinary Masters", "Reports"):
			self.assertEqual(sections[label]["collapsible"], 1)
			self.assertEqual(sections[label]["keep_closed"], 1)
			self.assertEqual(sections[label]["show_arrow"], 0)

	def test_collapsed_sidebar_sections_use_native_collapse_control(self):
		sections = [
			item
			for item in _load_sidebar()["items"]
			if item.get("type") == "Section Break" and item.get("keep_closed")
		]

		self.assertGreater(len(sections), 0)
		for section in sections:
			self.assertEqual(section["collapsible"], 1)
			self.assertEqual(section["show_arrow"], 0)


	def test_sidebar_links_do_not_use_section_collapse_defaults(self):
		links = [item for item in _load_sidebar()["items"] if item.get("type") == "Link"]

		self.assertGreater(len(links), 0)
		for link in links:
			self.assertEqual(link["collapsible"], 0)
			self.assertEqual(link["keep_closed"], 0)
			self.assertEqual(link["show_arrow"], 0)

	def test_planned_treatment_report_is_in_collapsed_reports_section(self):
		items = _load_sidebar()["items"]
		labels = [item.get("label") for item in items]
		report_index = labels.index("Reports")
		planned_index = labels.index("Planned Treatment")

		self.assertGreater(planned_index, report_index)
		link = _links_by_label(items)["Planned Treatment"]
		self.assertEqual(link["link_to"], "Planned Treatment")
		self.assertEqual(link["link_type"], "Report")

	def test_refined_sidebar_labels(self):
		sidebar = _load_sidebar()
		items = sidebar.get("items", [])
		links = _links_by_label(items)
		labels = [item.get("label") for item in items if item.get("label")]

		# 1. Executive dashboard label is "Executive Dashboard"
		self.assertIn("Executive Dashboard", links)
		self.assertNotIn("VetEdge Executive Dashboard", links)
		self.assertEqual(links["Executive Dashboard"]["link_to"], "vetedge-executive-dashboard")

		# 2. Records section label is "Veterinary Records"
		self.assertIn("Veterinary Records", labels)
		self.assertNotIn("VetEdge Records", labels)

		# 3. Masters section label is "Veterinary Masters"
		self.assertIn("Veterinary Masters", labels)
		self.assertNotIn("VetEdge Masters", labels)

		# 4. Role Bundle label is "Role Bundle"
		self.assertIn("Role Bundle", links)
		self.assertNotIn("VetEdge Role Bundle", links)
		self.assertEqual(links["Role Bundle"]["link_to"], "Veterinary Role Bundle")

		# 5. Setup link labels do not start with "VetEdge " or "Veterinary "
		setup_index = labels.index("Setup")
		for item in items[setup_index + 1:]:
			if item.get("type") == "Link" and item.get("label"):
				label = item.get("label")
				self.assertFalse(label.startswith("VetEdge "), f"Label '{label}' under Setup starts with VetEdge")
				self.assertFalse(label.startswith("Veterinary "), f"Label '{label}' under Setup starts with Veterinary")

		# 6. "link_to" targets remain unchanged and valid
		self.assertEqual(links["Settings"]["link_to"], "Veterinary Settings")
		self.assertEqual(links["Notification Event Registry"]["link_to"], "Veterinary Notification Event Registry")
		self.assertEqual(links["Notification Log"]["link_to"], "Veterinary Notification Log")
		self.assertEqual(links["Notification Preference"]["link_to"], "Veterinary Notification Preference")
