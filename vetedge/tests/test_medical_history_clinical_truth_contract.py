from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
LAZY_HISTORY = ROOT / "vetedge" / "services" / "medical_history_lazy.py"
QA_PATCH = ROOT / "vetedge" / "public" / "js" / "vetedge_medical_history_qa_patch.js"


def test_lab_history_requires_completed_workflow_status():
	source = LAZY_HISTORY.read_text()
	assert '"labs": {' in source
	assert '"doctype": "Veterinary Lab Order"' in source
	assert '"required_status": "Completed"' in source
	assert 'if workflow_status != contract["required_status"]:' in source


def test_vaccination_history_requires_administered_workflow_status():
	source = LAZY_HISTORY.read_text()
	assert '"vaccinations": {' in source
	assert '"doctype": "Veterinary Vaccination Record"' in source
	assert '"required_status": "Administered"' in source


def test_docstatus_is_kept_separate_from_workflow_status():
	source = LAZY_HISTORY.read_text()
	assert 'fields=["name", "status", "docstatus"]' in source
	assert 'enriched["workflow_status"] = workflow_status' in source
	assert 'enriched["docstatus"] = docstatus' in source
	assert 'enriched["document_status"] = DOCUMENT_STATUS_LABELS.get' in source
	assert 'docstatus is document-lifecycle metadata' in source


def test_history_rows_are_deduplicated_by_source_record():
	source = LAZY_HISTORY.read_text()
	assert "seen = set()" in source
	assert "if not name or name in seen:" in source
	assert "seen.add(name)" in source


def test_medical_history_ui_explicitly_displays_workflow_status():
	source = QA_PATCH.read_text()
	assert '["labs", "vaccinations"].includes(this.activeHistory)' in source
	assert 'key: "workflow_status"' in source
	assert 'label: __("Workflow Status")' in source
