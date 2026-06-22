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

	def test_veterinary_missed_appointment_is_in_appointment_cluster(self):
		items = _load_sidebar()["items"]
		labels = [item.get("label") for item in items]
		missed_index = labels.index("Veterinary Missed Appointment")

		self.assertGreater(missed_index, labels.index("Veterinary Appointment"))
		self.assertLess(missed_index, labels.index("Veterinary Guest Booking Request"))

		link = _links_by_label(items)["Veterinary Missed Appointment"]
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
			"Veterinary Hospitalisation Dashboard",
			"Veterinary Hospitalisation",
			"Veterinary Care Location",
			"Active Hospitalisations",
			"Hospitalisation Charge Summary",
			"Care Location Occupancy",
			"Hospitalisation Discharge Watch",
			"Pending Hospitalisation Actions",
		):
			self.assertGreater(labels.index(label), hospitalisation_index)
			self.assertLess(labels.index(label), records_index)

		link = _links_by_label(items)["Veterinary Hospitalisation"]
		self.assertEqual(link["link_to"], "Veterinary Hospitalisation")
		self.assertEqual(link["link_type"], "DocType")
		self.assertIn("VetEdge Doctor", link.get("display_depends_on", ""))
		self.assertIn("Veterinary Nurse", link.get("display_depends_on", ""))

	def test_veterinary_notification_item_is_admin_monitoring_link(self):
		items = _load_sidebar()["items"]
		labels = [item.get("label") for item in items]
		item_index = labels.index("Veterinary Notification Item")

		self.assertGreater(item_index, labels.index("VetEdge Notification Event Registry"))
		self.assertLess(item_index, labels.index("VetEdge Notification Log"))

		link = _links_by_label(items)["Veterinary Notification Item"]
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
			("Veterinary Hospitalisation", "Veterinary Hospitalisation", "DocType"),
			("Veterinary Missed Appointment", "Veterinary Missed Appointment", "DocType"),
			("Veterinary Notification Item", "Veterinary Notification Item", "DocType"),
		):
			self.assertEqual(counts[key], 1)

	def test_veterinary_patient_link_is_only_under_veterinary_records(self):
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

	def test_new_notification_item_label_uses_veterinary(self):
		links = _links_by_label(_load_sidebar()["items"])
		self.assertIn("Veterinary Notification Item", links)
		self.assertNotIn("VetEdge Notification Item", links)

	def test_veterinary_sections_are_collapsed_by_default(self):
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
