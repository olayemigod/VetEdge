from __future__ import annotations

import ast
import json
from pathlib import Path
from unittest import TestCase


APP_ROOT = Path(__file__).resolve().parents[1]
HOOKS_PATH = APP_ROOT / "hooks.py"
DESKTOP_ICON_PATH = APP_ROOT / "desktop_icon" / "vetedge.json"
WORKSPACE_SIDEBAR_PATH = APP_ROOT / "workspace_sidebar" / "vetedge.json"
VETERINARY_ROOT = APP_ROOT / "veterinary"


def _hooks_assignment(name: str) -> list[str]:
	module = ast.parse(HOOKS_PATH.read_text())
	for node in module.body:
		if isinstance(node, ast.Assign):
			for target in node.targets:
				if isinstance(target, ast.Name) and target.id == name:
					return ast.literal_eval(node.value)
	return []


def _literal_assignments() -> dict:
	values = {}
	module = ast.parse(HOOKS_PATH.read_text())
	for node in module.body:
		if not isinstance(node, ast.Assign):
			continue
		for target in node.targets:
			if isinstance(target, ast.Name):
				try:
					values[target.id] = ast.literal_eval(node.value)
				except (ValueError, TypeError):
					pass
	return values


def _resolve_names(value, values: dict):
	if isinstance(value, ast.Name):
		return values[value.id]
	if isinstance(value, ast.Constant):
		return value.value
	if isinstance(value, ast.Dict):
		return {
			_resolve_names(key, values): _resolve_names(val, values)
			for key, val in zip(value.keys, value.values)
		}
	if isinstance(value, ast.List):
		return [_resolve_names(item, values) for item in value.elts]
	raise AssertionError(f"Unsupported hooks expression: {ast.dump(value)}")


class TestNavigationAssets(TestCase):
	def test_app_launcher_identity_and_route(self):
		module = ast.parse(HOOKS_PATH.read_text())
		assignments = _literal_assignments()
		for node in module.body:
			if isinstance(node, ast.Assign):
				for target in node.targets:
					if isinstance(target, ast.Name) and target.id == "add_to_apps_screen":
						assignments[target.id] = _resolve_names(node.value, assignments)

		self.assertEqual(assignments["app_title"], "VetEdge")
		self.assertEqual(assignments["app_home"], "/app/vetedge")
		self.assertNotEqual(assignments["app_home"], "/desk/vetedge-executive-dashboard")
		self.assertNotEqual(assignments["app_home"], "/desk/veterinary-patient")
		self.assertEqual(assignments["add_to_apps_screen"][0]["title"], "VetEdge")
		self.assertEqual(assignments["add_to_apps_screen"][0]["route"], "/app/vetedge")
		self.assertNotEqual(assignments["add_to_apps_screen"][0]["route"], "/desk/vetedge-executive-dashboard")
		self.assertNotEqual(assignments["add_to_apps_screen"][0]["route"], "/desk/veterinary-patient")

	def test_desktop_icon_fixture_uses_supported_launcher_route(self):
		icon = json.loads(DESKTOP_ICON_PATH.read_text())

		self.assertEqual(icon["label"], "VetEdge")
		self.assertEqual(icon["link_type"], "Workspace Sidebar")
		self.assertEqual(icon["link_to"], "VetEdge")
		self.assertNotEqual(icon.get("link"), "/desk/vetedge-executive-dashboard")
		self.assertNotEqual(icon["link"], "/desk/veterinary-patient")
		self.assertNotEqual(icon["link_to"], "Veterinary Patient")

	def test_no_active_launcher_source_uses_patient_list_route(self):
		assignments = _literal_assignments()
		module = ast.parse(HOOKS_PATH.read_text())
		for node in module.body:
			if isinstance(node, ast.Assign):
				for target in node.targets:
					if isinstance(target, ast.Name) and target.id == "add_to_apps_screen":
						assignments[target.id] = _resolve_names(node.value, assignments)

		launcher_sources = list(assignments["add_to_apps_screen"])
		launcher_sources.append(json.loads(DESKTOP_ICON_PATH.read_text()))
		for source in launcher_sources:
			identity = " ".join(str(source.get(field) or "") for field in ("name", "title", "label", "app")).lower()
			if "vetedge" not in identity and "veterinary" not in identity:
				continue
			self.assertNotEqual(source.get("route"), "/desk/veterinary-patient", source)
			self.assertNotEqual(source.get("link"), "/desk/veterinary-patient", source)
			self.assertNotEqual(source.get("link_to"), "Veterinary Patient", source)

	def test_workspace_sidebar_fixture_canonical_top_level_order(self):
		items = json.loads(WORKSPACE_SIDEBAR_PATH.read_text())["items"]
		top_level = [item.get("label") for item in items if not item.get("child")]
		self.assertEqual(
			top_level,
			[
				"Executive Dashboard",
				"Dashboards",
				"Training Centre",
				"Veterinary Records",
				"Hospitalisation",
				"Pet Grooming",
				"Pet Boarding",
				"Veterinary Masters",
				"Reports",
				"Billing",
				"Setup",
			],
		)
		self.assertNotIn("Platform Settings", top_level)

	def test_required_desk_assets_are_registered_and_exist(self):
		asset_paths = _hooks_assignment("app_include_css") + _hooks_assignment("app_include_js")

		expected_assets = {
			"/assets/vetedge/css/dashboard_shell.css",
			"/assets/vetedge/css/veterinary_unread_badge.css",
			"/assets/vetedge/js/dashboard_shell.js",
			"/assets/vetedge/js/invoice_summary_dialog.js",
			"/assets/vetedge/js/billing_modal.js",
			"/assets/vetedge/js/report_pdf_patch.js",
			"/assets/vetedge/js/report_visibility.js",
			"/assets/vetedge/js/veterinary_unread_badge.js",
		}

		for asset in expected_assets:
			self.assertIn(asset, asset_paths)
			relative = asset.removeprefix("/assets/vetedge/")
			self.assertTrue((APP_ROOT / "public" / relative).exists(), asset)

	def test_dashboard_page_routes_and_shell_assets_exist(self):
		expected_pages = {
			"veterinary_financial_dashboard": ("veterinary-financial-dashboard", "financial"),
			"veterinary_hospitalisation_dashboard": ("veterinary-hospitalisation-dashboard", "hospitalisation"),
		}

		for folder, (page_name, dashboard_key) in expected_pages.items():
			with self.subTest(page=page_name):
				page_root = VETERINARY_ROOT / "page" / folder
				page_json = json.loads((page_root / f"{folder}.json").read_text())
				page_js = (page_root / f"{folder}.js").read_text()
				self.assertEqual(page_json["name"], page_name)
				self.assertEqual(page_json["page_name"], page_name)
				self.assertEqual(page_json["module"], "Veterinary")
				self.assertIn("/assets/vetedge/js/dashboard_shell.js", page_js)
				self.assertIn(f'key: "{dashboard_key}"', page_js)

	def test_dashboard_sidebar_placements(self):
		items = json.loads(WORKSPACE_SIDEBAR_PATH.read_text())["items"]
		labels = [item.get("label") for item in items]
		links = {
			item.get("label"): item
			for item in items
			if item.get("type") == "Link"
		}

		self.assertGreater(labels.index("Financial Dashboard"), labels.index("Dashboards"))
		self.assertLess(labels.index("Financial Dashboard"), labels.index("Veterinary Records"))
		self.assertEqual(links["Financial Dashboard"]["link_to"], "veterinary-financial-dashboard")
		self.assertEqual(links["Financial Dashboard"]["link_type"], "Page")

		self.assertGreater(labels.index("Hospitalisation Dashboard"), labels.index("Hospitalisation"))
		self.assertLess(labels.index("Hospitalisation Dashboard"), labels.index("Pet Grooming"))
		self.assertEqual(links["Hospitalisation Dashboard"]["link_to"], "veterinary-hospitalisation-dashboard")
		self.assertEqual(links["Hospitalisation Dashboard"]["link_type"], "Page")

	def test_training_centre_page_and_sidebar_link_exist(self):
		page_root = VETERINARY_ROOT / "page" / "veterinary_training_centre"
		page_json = json.loads((page_root / "veterinary_training_centre.json").read_text())
		page_js = (page_root / "veterinary_training_centre.js").read_text()
		items = json.loads(WORKSPACE_SIDEBAR_PATH.read_text())["items"]
		links = {
			item.get("label"): item
			for item in items
			if item.get("type") == "Link"
		}

		self.assertEqual(page_json["name"], "veterinary-training-centre")
		self.assertEqual(page_json["page_name"], "veterinary-training-centre")
		self.assertEqual(page_json["title"], "Veterinary Training Centre")
		self.assertIn("vetedge.services.training_centre.get_training_modules", page_js)
		self.assertIn("vetedge.services.training_centre.get_training_module_content", page_js)
		self.assertIn("Training Centre", links)
		self.assertEqual(links["Training Centre"]["link_to"], "veterinary-training-centre")
		self.assertEqual(links["Training Centre"]["link_type"], "Page")
		self.assertIn("Training Centre", [item.get("label") for item in items if not item.get("child")])
		labels = [item.get("label") for item in items]
		training_section_index = next(
			index for index, item in enumerate(items)
			if item.get("label") == "Training Centre" and item.get("type") == "Section Break"
		)
		training_link_index = next(
			index for index, item in enumerate(items)
			if item.get("label") == "Training Centre" and item.get("type") == "Link"
		)
		self.assertGreater(training_link_index, training_section_index)
		self.assertLess(training_link_index, labels.index("Veterinary Records"))

	def test_no_duplicate_dashboard_top_level_sections(self):
		items = json.loads(WORKSPACE_SIDEBAR_PATH.read_text())["items"]
		top_level = [item.get("label") for item in items if not item.get("child")]
		self.assertEqual(top_level.count("Veterinary Financial Dashboard"), 0)
		self.assertEqual(top_level.count("Hospitalisation Dashboard"), 0)
		self.assertEqual(top_level.count("Veterinary Hospitalisation Dashboard"), 0)

	def test_dashboard_shell_renders_chart_table_fallbacks(self):
		source = (APP_ROOT / "public" / "js" / "dashboard_shell.js").read_text()

		self.assertIn("renderChartTable", source)
		self.assertIn("chart.empty_state", source)
		self.assertIn("chart.rows", source)
		self.assertIn("chart.columns", source)
		self.assertIn("!frappe.Chart", source)
		self.assertIn("VetEdge dashboard chart failed to render", source)
