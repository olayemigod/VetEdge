from __future__ import annotations

import ast
import json
from pathlib import Path
from unittest import TestCase


APP_ROOT = Path(__file__).resolve().parents[1]
HOOKS_PATH = APP_ROOT / "hooks.py"
DESKTOP_ICON_PATH = APP_ROOT / "desktop_icon" / "vetedge.json"
WORKSPACE_SIDEBAR_PATH = APP_ROOT / "workspace_sidebar" / "vetedge.json"


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
		self.assertEqual(assignments["app_home"], "/desk/vetedge-executive-dashboard")
		self.assertNotEqual(assignments["app_home"], "/desk/veterinary-patient")
		self.assertEqual(assignments["add_to_apps_screen"][0]["title"], "VetEdge")
		self.assertEqual(assignments["add_to_apps_screen"][0]["route"], "/desk/vetedge-executive-dashboard")
		self.assertNotEqual(assignments["add_to_apps_screen"][0]["route"], "/desk/veterinary-patient")

	def test_desktop_icon_fixture_uses_supported_launcher_route(self):
		icon = json.loads(DESKTOP_ICON_PATH.read_text())

		self.assertEqual(icon["label"], "VetEdge")
		self.assertEqual(icon["link_type"], "External")
		self.assertEqual(icon["link"], "/desk/vetedge-executive-dashboard")
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
