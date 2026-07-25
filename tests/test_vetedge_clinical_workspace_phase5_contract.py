from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def read(path: str) -> str:
	return (ROOT / path).read_text(encoding="utf-8")


def test_pending_dispensary_completion_is_blocked_server_side():
	hooks = read("vetedge/hooks.py")
	provider = read("vetedge/services/clinical_workspace_phase5.py")

	assert "clinical_workspace_phase5.enforce_pending_dispensary_completion_invariant" in hooks
	assert 'doc.get("status") or "") == "Completed"' in provider
	assert 'doc.get("dispensary_status") or "") == DISPENSARY_PENDING' in provider
	assert "Dispensary confirmation is required before this consultation can be completed" in provider


def test_workspace_reuses_existing_dispensary_stock_engine():
	provider = read("vetedge/services/clinical_workspace_phase5.py")
	frontend = read("vetedge/public/js/vetedge_clinical_workspace_phase5.js")

	assert "confirm_dispensary_issue" in provider
	assert "get_branch_dispensary_warehouse" in provider
	assert "require_vetedge_platform_access" in provider
	assert "get_dispensary_workspace_context" in provider
	assert "confirm_workspace_dispensary" in provider
	assert "Review Dispensary" in frontend
	assert "Confirm Dispensary Issue" in frontend
	assert "status:Completed" in frontend
	assert "status:Ready for Treatment" in frontend
	assert "Open Stock Entry" in frontend


def test_medical_history_uses_four_vital_trends_and_date_grouping():
	shared = read("vetedge/public/js/vetedge_medical_history_ui.js")
	standalone = read("vetedge/veterinary/page/veterinary_medical_history/veterinary_medical_history.js")
	clinical = read("vetedge/public/js/vetedge_clinical_workspace_phase5.js")
	base_component = read("vetedge/public/js/vetedge_clinical_workspace/VetEdgeClinicalWorkspace.vue")

	for fieldname in ("temperature", "weight", "heart_rate", "respiratory_rate"):
		assert f"fieldname: '{fieldname}'" in shared
	assert "groupTimelineByDate" in shared
	assert "vetedge-history-day" in shared
	assert "data-vital-metric" in shared
	assert "VetEdgeMedicalHistoryUI.render" in standalone
	assert "openDateGroupedMedicalHistory" in clinical
	assert "Latest Vitals and Billing Context" in base_component


def test_treatment_additions_are_newest_first_and_default_fee_is_last():
	provider = read("vetedge/services/clinical_workspace_phase5.py")
	frontend = read("vetedge/public/js/vetedge_clinical_workspace_phase5.js")

	assert "_sort_treatment_order_rows" in provider
	assert "DEFAULT_CONSULTATION_SOURCE_DETAIL" in provider
	assert "1 if _is_default_consultation_row(row) else 0" in provider
	assert "rows.unshift(added)" in frontend
	assert "refreshTreatmentDisplayOrder" in frontend
	assert "return leftDefault ? 1 : -1" in frontend


def test_phase5_installs_before_workspace_mounts():
	loader = read("vetedge/veterinary/page/vetedge_clinical_workspace/vetedge_clinical_workspace.js")

	install = loader.index("VetEdgeClinicalWorkspacePhase5?.install")
	mount = loader.index("runtime.createEdgeApp(window.VetEdgeClinicalWorkspace)")
	assert install < mount
	assert "vetedge_medical_history_ui.js" in loader
	assert "vetedge_clinical_workspace_phase5.js" in loader
