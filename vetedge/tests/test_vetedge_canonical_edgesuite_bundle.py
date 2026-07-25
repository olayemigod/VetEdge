from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]

LOADERS = (
	ROOT / "vetedge" / "veterinary" / "page" / "stock_expiry_monitor" / "stock_expiry_monitor.js",
	ROOT / "vetedge" / "veterinary" / "page" / "vetedge_executive_dashboard" / "vetedge_executive_dashboard.js",
	ROOT / "vetedge" / "veterinary" / "page" / "vetedge_resource_center" / "vetedge_resource_center.js",
	ROOT / "vetedge" / "veterinary" / "page" / "vetedge_document_workspace" / "vetedge_document_workspace.js",
	ROOT / "vetedge" / "veterinary" / "page" / "vetedge_master_workspace" / "vetedge_master_workspace.js",
	ROOT / "vetedge" / "veterinary" / "page" / "vetedge_pricing_master_workspace" / "vetedge_pricing_master_workspace.js",
	ROOT / "vetedge" / "veterinary" / "page" / "vetedge_clinical_workspace" / "vetedge_clinical_workspace.js",
	ROOT / "vetedge" / "veterinary" / "page" / "vetedge_front_desk_action_center" / "vetedge_front_desk_action_center.js",
)


def test_all_edgesuite_page_loaders_use_collision_safe_bundle():
	for path in LOADERS:
		assert path.exists(), path
		content = path.read_text(encoding="utf-8")
		assert "edgesuite_ui.bundle.js" in content, path
		assert "frappe.require('edgeui.bundle.js'" not in content, path
		assert 'frappe.require("edgeui.bundle.js"' not in content, path


def test_loaders_validate_the_standalone_runtime_before_mounting():
	for path in LOADERS:
		content = path.read_text(encoding="utf-8")
		assert "EdgeSuiteUI" in content, path
		assert "createEdgeApp" in content, path
		assert "failed to load" in content.lower() or "unavailable" in content.lower(), path
