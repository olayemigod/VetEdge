from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]


def test_remaining_link_providers_route_through_shared_adapter():
	hooks = (ROOT / "vetedge" / "hooks.py").read_text()
	assert (
		'"vetedge.services.clinical_workspace.get_clinical_link_options": '
		'"vetedge.services.remaining_link_search.get_clinical_link_options"'
	) in hooks
	assert (
		'"vetedge.services.pricing_master_workspace.get_pricing_master_link_options": '
		'"vetedge.services.remaining_link_search.get_pricing_master_link_options"'
	) in hooks


def test_remaining_adapter_uses_shared_ranker_and_bounded_candidates():
	source = (ROOT / "vetedge" / "services" / "remaining_link_search.py").read_text()
	assert "from edgesuite_ui.search_ranking import rank_search_records" in source
	assert "CANDIDATE_LIMIT = 100" in source
	assert 'exact_fields=("value",)' in source
	assert 'search_fields=("label", "description")' in source
	assert "clinical_workspace.get_clinical_link_options" in source
	assert "pricing_master_workspace.get_pricing_master_link_options" in source


def test_remaining_search_anchors_provider_queries_before_ranking():
	source = (ROOT / "vetedge" / "services" / "remaining_link_search.py").read_text()
	assert "_query_anchors" in source
	assert "MAX_ANCHORS = 4" in source
	assert "_collect_tuple_candidates" in source
	assert "_pricing_rows" in source
	assert "remaining = CANDIDATE_LIMIT - len(rows)" in source
	assert 'or_filters={fieldname: ["like", f"%{anchor}%"] for fieldname in search_fields}' in source


def test_clinical_adapter_preserves_curated_treatment_and_practitioner_sources():
	source = (ROOT / "vetedge" / "services" / "remaining_link_search.py").read_text()
	assert "get_veterinary_doctor_users" in source
	assert "get_treatment_item_link_options" in source
	assert "_require_clinical_context" in source
	assert "_validate_branch" in source


def test_pricing_adapter_preserves_resource_filters_and_read_permission():
	source = (ROOT / "vetedge" / "services" / "remaining_link_search.py").read_text()
	assert "pricing_master_workspace._require_resource" in source
	assert 'frappe.has_permission(options, "read")' in source
	assert 'config.get("link_filters")' in source
	assert "frappe.get_list" in source
