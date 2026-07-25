from __future__ import annotations

import ast
import json
from pathlib import Path

REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
HOOKS_PATH = REPOSITORY_ROOT / "vetedge" / "hooks.py"
TSCONFIG_PATH = REPOSITORY_ROOT / "tsconfig.json"
STOCK_EXPIRY_LOADER = (
	REPOSITORY_ROOT
	/ "vetedge"
	/ "veterinary"
	/ "page"
	/ "stock_expiry_monitor"
	/ "stock_expiry_monitor.js"
)
STOCK_EXPIRY_BUNDLE = (
	REPOSITORY_ROOT
	/ "vetedge"
	/ "public"
	/ "js"
	/ "vetedge_stock_expiry_monitor.bundle.js"
)
EDGEUI_PAGE_LOADERS = (
	STOCK_EXPIRY_LOADER,
	REPOSITORY_ROOT / "vetedge" / "veterinary" / "page" / "vetedge_executive_dashboard" / "vetedge_executive_dashboard.js",
	REPOSITORY_ROOT / "vetedge" / "veterinary" / "page" / "vetedge_resource_center" / "vetedge_resource_center.js",
	REPOSITORY_ROOT / "vetedge" / "veterinary" / "page" / "vetedge_document_workspace" / "vetedge_document_workspace.js",
	REPOSITORY_ROOT / "vetedge" / "veterinary" / "page" / "vetedge_master_workspace" / "vetedge_master_workspace.js",
	REPOSITORY_ROOT / "vetedge" / "veterinary" / "page" / "vetedge_pricing_master_workspace" / "vetedge_pricing_master_workspace.js",
	REPOSITORY_ROOT / "vetedge" / "veterinary" / "page" / "vetedge_clinical_workspace" / "vetedge_clinical_workspace.js",
	REPOSITORY_ROOT / "vetedge" / "veterinary" / "page" / "vetedge_front_desk_action_center" / "vetedge_front_desk_action_center.js",
)


def _get_required_apps() -> list[str]:
	tree = ast.parse(HOOKS_PATH.read_text(encoding="utf-8"))

	for node in tree.body:
		if not isinstance(node, ast.Assign):
			continue

		if not any(
			isinstance(target, ast.Name) and target.id == "required_apps"
			for target in node.targets
		):
			continue

		value = ast.literal_eval(node.value)
		assert isinstance(value, list)
		return value

	raise AssertionError("required_apps is not declared in vetedge/hooks.py")


def test_vetedge_requires_edgesuite_ui_but_not_coreedge():
	required_apps = _get_required_apps()

	assert "edgesuite_ui" in required_apps
	assert "coreedge" not in required_apps


def test_typescript_config_aliases_vue_to_edgesuite_ui_not_coreedge():
	config = json.loads(TSCONFIG_PATH.read_text(encoding="utf-8"))
	paths = config.get("compilerOptions", {}).get("paths", {})
	vue_paths = paths.get("vue", [])

	assert vue_paths == ["../edgesuite_ui/edgesuite_ui/public/js/edgeui/vue-bridge.js"]
	assert "coreedge" not in json.dumps(config).lower()


def test_all_vetedge_page_loaders_use_collision_safe_edgesuite_ui_runtime():
	for loader in EDGEUI_PAGE_LOADERS:
		assert loader.exists(), loader
		content = loader.read_text(encoding="utf-8")
		assert "edgesuite_ui.bundle.js" in content, loader
		assert "window.EdgeSuiteUI" in content, loader
		assert "createEdgeApp" in content, loader
		assert "frappe.require('edgeui.bundle.js'" not in content, loader
		assert 'frappe.require("edgeui.bundle.js"' not in content, loader


def test_stock_expiry_loader_orders_shared_runtime_before_product_bundle():
	content = STOCK_EXPIRY_LOADER.read_text(encoding="utf-8")

	assert content.index("edgesuite_ui.bundle.js") < content.index(
		"vetedge_stock_expiry_monitor.bundle.js"
	)
	assert "coreedge" not in content.lower()


def test_stock_expiry_bundle_uses_shared_runtime_without_coreedge():
	content = STOCK_EXPIRY_BUNDLE.read_text(encoding="utf-8")

	assert "window.EdgeSuiteUI || window.EdgeUI" in content
	assert "runtime.createEdgeApp" in content
	assert "coreedge" not in content.lower()
