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
CLINICAL_LOADER = (
	REPOSITORY_ROOT
	/ "vetedge"
	/ "veterinary"
	/ "page"
	/ "vetedge_clinical_workspace"
	/ "vetedge_clinical_workspace.js"
)
CLINICAL_BUNDLE = REPOSITORY_ROOT / "vetedge" / "public" / "js" / "vetedge_clinical_workspace.bundle.js"
MODAL_PRESENTER = REPOSITORY_ROOT / "vetedge" / "public" / "js" / "vetedge_edge_modal_presenter.bundle.js"
BILLING_EDGE = REPOSITORY_ROOT / "vetedge" / "public" / "js" / "vetedge_billing_edgesuite.bundle.js"
CLINICAL_WORKFLOW = REPOSITORY_ROOT / "vetedge" / "public" / "js" / "vetedge_clinical_workflow_modal.bundle.js"
CANCELLATION_SERVICE = REPOSITORY_ROOT / "vetedge" / "services" / "consultation_cancellation.py"


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


def test_stock_expiry_loader_uses_standalone_edgesuite_ui_runtime():
	content = STOCK_EXPIRY_LOADER.read_text(encoding="utf-8")

	assert "edgeui.bundle.js" in content
	assert "window.EdgeSuiteUI || window.EdgeUI" in content
	assert "vetedge_stock_expiry_monitor.bundle.js" in content
	assert content.index("edgeui.bundle.js") < content.index(
		"vetedge_stock_expiry_monitor.bundle.js"
	)
	assert "coreedge" not in content.lower()


def test_stock_expiry_bundle_uses_shared_runtime_without_coreedge():
	content = STOCK_EXPIRY_BUNDLE.read_text(encoding="utf-8")

	assert "window.EdgeSuiteUI || window.EdgeUI" in content
	assert "runtime.createEdgeApp" in content
	assert "coreedge" not in content.lower()


def test_clinical_loader_installs_edgesuite_modal_layers_before_workspace():
	content = CLINICAL_LOADER.read_text(encoding="utf-8")
	for asset in (
		"vetedge_edge_modal_presenter.bundle.js",
		"vetedge_billing_edgesuite.bundle.js",
		"vetedge_clinical_workflow_modal.bundle.js",
		"vetedge_clinical_workspace.bundle.js",
	):
		assert asset in content
	assert content.index("vetedge_edge_modal_presenter.bundle.js") < content.index(
		"vetedge_billing_edgesuite.bundle.js"
	)
	assert content.index("vetedge_billing_edgesuite.bundle.js") < content.index(
		"vetedge_clinical_workspace.bundle.js"
	)
	assert content.index("vetedge_clinical_workflow_modal.bundle.js") < content.index(
		"vetedge_clinical_workspace.bundle.js"
	)


def test_clinical_modal_presenter_is_edgesuite_native_and_nested_safe():
	content = MODAL_PRESENTER.read_text(encoding="utf-8")
	for contract in (
		"EdgeModal",
		"EdgeLinkField",
		"edge-multiselect",
		"stack: []",
		"runFooterAction",
		"closeOnSuccess",
		"window.VetEdgeEdgeModalPresenter",
	):
		assert contract in content
	assert "frappe.ui.Dialog" not in content


def test_clinical_related_service_actions_stay_in_edgesuite_modals():
	content = CLINICAL_BUNDLE.read_text(encoding="utf-8")
	for contract in (
		"VetEdgeEdgeModalPresenter.open",
		"vetedge.services.lab.create_lab_order_from_consultation",
		"vetedge.services.vaccination.create_vaccination_from_consultation",
		"vetedge.services.hospitalisation.create_hospitalisation_from_consultation",
		"get_active_lab_tests_for_picker",
		"get_vaccination_billing_defaults",
		"frappe.desk.search.search_link",
	):
		assert contract in content
	assert 'frappe.set_route("List", doctype)' not in content


def test_billing_replaces_native_dialog_with_edgesuite_presenter():
	content = BILLING_EDGE.read_text(encoding="utf-8")
	for contract in (
		"VetEdgeEdgeModalPresenter",
		"get_billing_modal_state",
		"create_or_update_modal_invoice",
		"submit_modal_invoice",
		"record_modal_invoice_payment",
		"window.vetedgeBillingModal",
	):
		assert contract in content
	assert "new frappe.ui.Dialog" not in content


def test_completed_consultation_uses_governed_resolution_workflow():
	frontend = CLINICAL_WORKFLOW.read_text(encoding="utf-8")
	backend = CANCELLATION_SERVICE.read_text(encoding="utf-8")
	for contract in (
		"Reverse / Resolve Consultation",
		"get_consultation_cancellation_preflight",
		"record_consultation_cancellation_resolution",
		"approve_consultation_cancellation_resolution",
		"retain_payment_and_cancel_consultation",
		"execute_consultation_reschedule_resolution",
		"complete_consultation_cancellation_resolution_manually",
		"RESOLUTION_ROLES",
		"REFERENCE_TYPES",
		"Completion Evidence / Note",
	):
		assert contract in frontend
	for contract in (
		"def get_consultation_cancellation_preflight",
		"def cancel_consultation_safely",
		"def record_consultation_cancellation_resolution",
		"def retain_payment_and_cancel_consultation",
		"def execute_consultation_reschedule_resolution",
		"def complete_consultation_cancellation_resolution_manually",
		"Submitted invoices, payments, stock entries, and billing history from the original consultation remain unchanged.",
	):
		assert contract in backend
	assert 'status = "In Progress"' not in frontend
