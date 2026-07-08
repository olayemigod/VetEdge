from __future__ import annotations

import json
import frappe
from collections import Counter
from pathlib import Path
from unittest import TestCase


APP_ROOT = Path("/home/olayemigod/frappe-bench/apps/vetedge/vetedge")
WORKSPACE_SIDEBAR = APP_ROOT / "workspace_sidebar/vetedge.json"
EXPECTED_WORKFLOW_GROUPS = [
	"Dashboard",
	"Front Desk",
	"Clinical",
	"Hospital & Services",
	"Inventory / Pharmacy",
	"Reports",
	"Veterinary Masters",
	"Configuration",
	"Platform",
	"Help & Training",
]


def _load_sidebar() -> dict:
	return json.loads(WORKSPACE_SIDEBAR.read_text())


def _links_by_label(items: list[dict]) -> dict[str, dict]:
	return {
		item["label"]: item
		for item in items
		if item.get("type") == "Link" and item.get("label")
	}


def _labels(items: list[dict]) -> list[str]:
	return [item.get("label") for item in items if item.get("label")]


def _section_bounds(items: list[dict], section: str) -> tuple[int, int]:
	labels = _labels(items)
	start = labels.index(section)
	section_indexes = [
		index
		for index, item in enumerate(items)
		if item.get("type") == "Section Break"
	]
	start_item_index = next(index for index in section_indexes if items[index].get("label") == section)
	next_indexes = [index for index in section_indexes if index > start_item_index]
	end_item_index = next_indexes[0] if next_indexes else len(items)
	return start_item_index, end_item_index


def _labels_in_section(items: list[dict], section: str) -> list[str]:
	start, end = _section_bounds(items, section)
	return [
		item.get("label")
		for item in items[start + 1:end]
		if item.get("type") == "Link"
	]


def _section_for_label(items: list[dict], label: str) -> str:
	current_section = None
	for item in items:
		if item.get("type") == "Section Break":
			current_section = item.get("label")
		elif item.get("type") == "Link" and item.get("label") == label:
			return current_section
	raise AssertionError(f"Label {label!r} not found in sidebar")


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
		self.assertGreater(missed_index, labels.index("Guest Booking Requests"))
		self.assertEqual(_section_for_label(items, "Missed Appointments"), "Front Desk")

		link = _links_by_label(items)["Missed Appointments"]
		self.assertEqual(link["link_to"], "Veterinary Missed Appointment")
		self.assertEqual(link["link_type"], "DocType")
		self.assertIn("VetEdge Front Desk", link.get("display_depends_on", ""))
		self.assertIn("Branch Manager", link.get("display_depends_on", ""))

	def test_hospitalisation_navigation_is_grouped_in_dedicated_section(self):
		items = _load_sidebar()["items"]
		labels = [item.get("label") for item in items]
		reports_index = labels.index("Reports")

		for label in (
			"Hospitalisation Dashboard",
			"Hospitalisations",
			"Kennel Availability Board",
			"Pet Boarding Booking",
			"Pet Boarding Stay",
			"Pet Boarding Care Record",
			"Pet Grooming Appointment",
			"Pet Grooming Session",
		):
			self.assertEqual(_section_for_label(items, label), "Hospital & Services")
		self.assertEqual(_section_for_label(items, "Care Locations"), "Configuration")
		for label in (
			"Active Hospitalisations",
			"Hospitalisation Charge Summary",
			"Care Location Occupancy",
			"Hospitalisation Discharge Watch",
			"Pending Hospitalisation Actions",
		):
			self.assertGreater(labels.index(label), reports_index)
			self.assertEqual(_section_for_label(items, label), "Reports")

		link = _links_by_label(items)["Hospitalisations"]
		self.assertEqual(link["link_to"], "Veterinary Hospitalisation")
		self.assertEqual(link["link_type"], "DocType")
		self.assertIn("VetEdge Doctor", link.get("display_depends_on", ""))
		self.assertIn("Veterinary Nurse", link.get("display_depends_on", ""))

	def test_hospitalisation_dashboard_page_is_under_hospitalisation_section(self):
		items = _load_sidebar()["items"]
		links = _links_by_label(items)
		self.assertIn("Hospitalisation Dashboard", links)
		self.assertEqual(_section_for_label(items, "Hospitalisation Dashboard"), "Hospital & Services")
		self.assertEqual(links["Hospitalisation Dashboard"]["link_to"], "veterinary-hospitalisation-dashboard")
		self.assertEqual(links["Hospitalisation Dashboard"]["link_type"], "Page")

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
		self.assertEqual(_section_for_label(items, "Notification Items"), "Configuration")

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
			("Hospitalisation Dashboard", "veterinary-hospitalisation-dashboard", "Page"),
			("Missed Appointments", "Veterinary Missed Appointment", "DocType"),
			("Notification Items", "Veterinary Notification Item", "DocType"),
			("Stock Expiry Status", "Stock Expiry Status", "Report"),
		):
			self.assertEqual(counts[key], 1)

	def test_sidebar_has_no_duplicate_route_targets(self):
		links = [
			(item.get("link_type"), item.get("link_to"))
			for item in _load_sidebar()["items"]
			if item.get("type") == "Link"
		]
		counts = Counter(links)
		duplicates = [key for key, count in counts.items() if key[1] and count > 1]
		self.assertEqual(duplicates, [])

	def test_workflow_first_daily_groups_and_key_routes_are_discoverable(self):
		items = _load_sidebar()["items"]
		links = _links_by_label(items)
		for section in ("Front Desk", "Clinical", "Hospital & Services", "Inventory / Pharmacy"):
			self.assertIn(section, _labels(items))
			self.assertGreater(len(_labels_in_section(items, section)), 0)

		expected_routes = {
			"Stock Expiry Monitor": ("Page", "stock-expiry-monitor", "Inventory / Pharmacy"),
			"Appointment Queue": ("Page", "veterinary-appointment-queue", "Front Desk"),
			"Medical History": ("Page", "veterinary-medical-history", "Clinical"),
			"Hospitalisation Dashboard": ("Page", "veterinary-hospitalisation-dashboard", "Hospital & Services"),
			"Kennel Availability Board": ("Page", "kennel-availability-board", "Hospital & Services"),
		}
		for label, (link_type, link_to, section) in expected_routes.items():
			self.assertIn(label, links)
			self.assertEqual(links[label]["link_type"], link_type)
			self.assertEqual(links[label]["link_to"], link_to)
			self.assertEqual(_section_for_label(items, label), section)

	def test_training_centre_is_only_under_help_and_training(self):
		items = _load_sidebar()["items"]
		matches = [
			item
			for item in items
			if item.get("type") == "Link" and item.get("link_to") == "veterinary-training-centre"
		]
		self.assertEqual(len(matches), 1)
		self.assertEqual(matches[0]["label"], "Training Centre")
		self.assertEqual(_section_for_label(items, "Training Centre"), "Help & Training")

	def test_masters_configuration_and_platform_are_separate(self):
		items = _load_sidebar()["items"]
		for label in (
			"Species",
			"Breeds",
			"Symptoms",
			"Diagnoses",
			"Diagnosis Categories",
			"Service Types",
			"Consultation Types",
			"Treatment Items",
			"Treatment Types",
			"Lab Tests",
			"Vaccines",
			"Pet Grooming Service",
		):
			self.assertEqual(_section_for_label(items, label), "Veterinary Masters")

		for label in (
			"Settings",
			"Branch",
			"Care Locations",
			"Kennel",
			"Cost Center",
			"Branch User Assignment",
			"Branch Practitioner Assignment",
			"Notification Preference",
			"Notification Log",
			"Role Bundle",
			"License Profile",
			"Notification Items",
		):
			self.assertEqual(_section_for_label(items, label), "Configuration")

		for label in (
			"Platform Settings",
			"Product Activation",
			"Onboarding",
			"Product Access",
			"Branch Context",
			"Company Context",
		):
			self.assertEqual(_section_for_label(items, label), "Platform")

	def test_coreedge_links_are_only_under_platform(self):
		items = _load_sidebar()["items"]
		coreedge_targets = {
			"CoreEdge Settings",
			"CoreEdge Product Activation",
			"CoreEdge Tenant",
			"CoreEdge Access Decision Log",
			"CoreEdge Branch Session",
			"CoreEdge Context Switch Log",
		}
		for item in items:
			if item.get("type") != "Link" or item.get("link_to") not in coreedge_targets:
				continue
			self.assertEqual(_section_for_label(items, item["label"]), "Platform")

	def test_coreedge_platform_link_visibility_expressions_are_preserved(self):
		links = _links_by_label(_load_sidebar()["items"])
		for label in (
			"Platform Settings",
			"Product Activation",
			"Onboarding",
			"Product Access",
			"Branch Context",
			"Company Context",
		):
			self.assertEqual(links[label].get("display_depends_on"), None)

	def test_consultation_type_is_only_under_veterinary_masters(self):
		items = _load_sidebar()["items"]
		matches = [
			(index, item)
			for index, item in enumerate(items)
			if item.get("link_to") == "Consultation Type"
		]

		self.assertEqual(len(matches), 1)
		index, link = matches[0]
		self.assertEqual(link["label"], "Consultation Types")
		self.assertEqual(_section_for_label(items, "Consultation Types"), "Veterinary Masters")

	def test_patient_link_is_only_under_vetedge_records(self):
		items = _load_sidebar()["items"]
		patient_indexes = [
			index
			for index, item in enumerate(items)
			if item.get("type") == "Link" and item.get("link_to") == "Veterinary Patient"
		]

		self.assertEqual(len(patient_indexes), 1)
		self.assertEqual(_section_for_label(items, "Patients"), "Front Desk")
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

		for label in EXPECTED_WORKFLOW_GROUPS:
			self.assertEqual(sections[label]["collapsible"], 1)
			self.assertEqual(sections[label]["keep_closed"], 1)
			self.assertEqual(sections[label]["show_arrow"], 0)

	def test_sidebar_sections_order(self):
		items = _load_sidebar()["items"]
		top_level = [item.get("label") for item in items if not item.get("child")]
		sections = [item.get("label") for item in items if item.get("type") == "Section Break"]
		self.assertEqual(top_level, EXPECTED_WORKFLOW_GROUPS)
		self.assertEqual(sections, EXPECTED_WORKFLOW_GROUPS)
		self.assertNotIn("Platform Settings", top_level)

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
		self.assertEqual(_section_for_label(items, "Planned Treatment"), "Clinical")
		link = _links_by_label(items)["Planned Treatment"]
		self.assertEqual(link["link_to"], "Planned Treatment")
		self.assertEqual(link["link_type"], "Report")

	def test_stock_expiry_status_report_is_in_collapsed_reports_section(self):
		items = _load_sidebar()["items"]
		labels = [item.get("label") for item in items]
		self.assertEqual(_section_for_label(items, "Stock Usage Summary"), "Inventory / Pharmacy")
		self.assertEqual(_section_for_label(items, "Stock Expiry Status"), "Inventory / Pharmacy")
		self.assertGreater(labels.index("Stock Expiry Status"), labels.index("Stock Usage Summary"))
		link = _links_by_label(items)["Stock Expiry Status"]
		self.assertEqual(link["link_to"], "Stock Expiry Status")
		self.assertEqual(link["link_type"], "Report")
		self.assertIn("Dispensary User", link.get("display_depends_on", ""))

	def test_refined_sidebar_labels(self):
		sidebar = _load_sidebar()
		items = sidebar.get("items", [])
		links = _links_by_label(items)
		labels = [item.get("label") for item in items if item.get("label")]
		sections = [item.get("label") for item in items if item.get("type") == "Section Break"]

		# 1. Executive dashboard label is "Executive Dashboard"
		self.assertIn("Executive Dashboard", links)
		self.assertNotIn("VetEdge Executive Dashboard", links)
		self.assertEqual(links["Executive Dashboard"]["link_to"], "vetedge-executive-dashboard")

		# 2. Workflow-first section labels replace overloaded generic buckets
		for section in EXPECTED_WORKFLOW_GROUPS:
			self.assertIn(section, sections)
		self.assertNotIn("Operations", sections)
		self.assertNotIn("Records", sections)
		self.assertNotIn("Settings", sections)
		self.assertNotIn("VetEdge Masters", labels)

		# 3. Role Bundle label is "Role Bundle"
		self.assertIn("Role Bundle", links)
		self.assertNotIn("VetEdge Role Bundle", links)
		self.assertEqual(links["Role Bundle"]["link_to"], "Veterinary Role Bundle")

		# 4. Configuration link labels remain generic.
		for label in _labels_in_section(items, "Configuration"):
			self.assertFalse(label.startswith("VetEdge "), f"Label '{label}' under Configuration starts with VetEdge")
			self.assertFalse(label.startswith("Veterinary "), f"Label '{label}' under Configuration starts with Veterinary")

		# 5. "link_to" targets remain unchanged and valid
		self.assertEqual(links["Settings"]["link_to"], "Veterinary Settings")
		self.assertEqual(links["Notification Event Registry"]["link_to"], "Veterinary Notification Event Registry")
		self.assertEqual(links["Notification Log"]["link_to"], "Veterinary Notification Log")
		self.assertEqual(links["Notification Preference"]["link_to"], "Veterinary Notification Preference")

	def test_runtime_desktop_icon_label_and_route(self):
		from vetedge.install.dashboard import ensure_vetedge_desktop_icon
		ensure_vetedge_desktop_icon()

		self.assertTrue(frappe.db.exists("Desktop Icon", "VetEdge"))
		doc = frappe.get_doc("Desktop Icon", "VetEdge")

		from vetedge.services.branding import get_branding
		branding = get_branding()
		expected_label = branding.get("app_title") or branding.get("brand_name") or "VetEdge"

		# Desktop icon/app launcher label remains VetEdge
		self.assertEqual(doc.label, expected_label)
		# Desktop icon route points to the intended Veterinary operational landing route
		self.assertEqual(doc.link_type, "Workspace Sidebar")
		self.assertEqual(doc.link_to, "VetEdge")
		self.assertNotEqual(doc.link, "/desk/vetedge-executive-dashboard")
		self.assertNotEqual(doc.link, "/desk/veterinary-patient")

	def test_no_active_vetedge_or_veterinary_desktop_icon_points_to_patient_list(self):
		from vetedge.install.dashboard import ensure_vetedge_desktop_icon
		ensure_vetedge_desktop_icon()

		icons = frappe.get_all(
			"Desktop Icon",
			fields=["name", "label", "app", "hidden", "link", "link_to", "link_type"],
			limit=1000,
		)
		matching_icons = [
			icon
			for icon in icons
			if "vetedge" in " ".join(str(icon.get(field) or "") for field in ("name", "label", "app")).lower()
			or "veterinary" in " ".join(str(icon.get(field) or "") for field in ("name", "label", "app")).lower()
		]

		self.assertGreater(len(matching_icons), 0)
		for icon in matching_icons:
			if icon.hidden:
				continue
			self.assertNotEqual(icon.link, "/desk/veterinary-patient", icon)
			self.assertNotEqual(icon.link_to, "Veterinary Patient", icon)
			if icon.label == "VetEdge":
				self.assertEqual(icon.link_type, "Workspace Sidebar")
				self.assertEqual(icon.link_to, "VetEdge")
				self.assertNotEqual(icon.link, "/desk/vetedge-executive-dashboard")

	def test_canonical_sidebar_sync_updates_live_record(self):
		from vetedge.install.dashboard import ensure_vetedge_workspace_sidebar
		
		# Set an intentionally outdated/scrambled items structure in database doc
		if frappe.db.exists("Workspace Sidebar", "VetEdge"):
			doc = frappe.get_doc("Workspace Sidebar", "VetEdge")
			doc.set("items", [])
			doc.append("items", {
				"type": "Link",
				"label": "Stale Link",
				"link_type": "DocType",
				"link_to": "User"
			})
			doc.save(ignore_permissions=True)
			frappe.db.commit()

		# Run the sync function
		ensure_vetedge_workspace_sidebar()

		# Assert it actually overwrote the stale link and synced from json fixture!
		doc = frappe.get_doc("Workspace Sidebar", "VetEdge")
		labels = [i.label for i in doc.items]
		self.assertNotIn("Stale Link", labels)
		self.assertIn("Patients", labels)

		# Test required EdgeSuite section order exactly.
		top_level = [i.label for i in doc.items if not i.child]
		sections = [i.label for i in doc.items if i.type == "Section Break"]
		# Ensure no extra Platform Settings top-level section appears unless explicitly configured (it is hidden/removed in standard non-coreedge boot/sync)
		self.assertNotIn("Platform Settings", sections)
		self.assertEqual(top_level, EXPECTED_WORKFLOW_GROUPS)
		self.assertEqual(sections, EXPECTED_WORKFLOW_GROUPS)

	def test_bootinfo_sidebar_keys_use_canonical_vetedge_sidebar(self):
		import frappe.boot
		from vetedge.coreedge_adapter import filter_bootinfo_for_coreedge_platform
		from vetedge.install.dashboard import ensure_vetedge_workspace_sidebar

		ensure_vetedge_workspace_sidebar()

		bootinfo = frappe.boot.get_bootinfo()
		filter_bootinfo_for_coreedge_platform(bootinfo)

		for key in ("vetedge", "veterinary"):
			sidebar = bootinfo.workspace_sidebar_item[key]
			items = sidebar.get("items") or []
			first_link = next(item for item in items if item.get("type") == "Link")
			top_level = [item.get("label") for item in items if not item.get("child")]
			patient_items = [item for item in items if item.get("link_to") == "Veterinary Patient"]

			self.assertEqual(sidebar.get("label"), "Veterinary")
			self.assertEqual(first_link["label"], "Executive Dashboard")
			self.assertEqual(first_link["link_to"], "vetedge-executive-dashboard")
			self.assertEqual(top_level, EXPECTED_WORKFLOW_GROUPS)
			self.assertEqual(len(patient_items), 1)
			self.assertGreater(
				[item.get("label") for item in items].index(patient_items[0]["label"]),
				[item.get("label") for item in items].index("Front Desk"),
			)
