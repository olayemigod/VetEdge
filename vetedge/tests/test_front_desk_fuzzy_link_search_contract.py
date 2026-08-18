from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SERVICE = ROOT / "vetedge" / "services" / "front_desk_link_search.py"
HOOKS = ROOT / "vetedge" / "hooks.py"
FRONT_DESK = ROOT / "vetedge" / "public" / "js" / "vetedge_front_desk_action_center" / "VetEdgeFrontDeskActionCenter.vue"


def read(path: Path) -> str:
	return path.read_text(encoding="utf-8")


def test_front_desk_link_endpoint_is_overridden_without_changing_edge_link_field_usage():
	hooks = read(HOOKS)
	page = read(FRONT_DESK)

	assert (
		'"vetedge.services.front_desk_action_center.get_front_desk_link_options": '
		'"vetedge.services.front_desk_link_search.get_front_desk_link_options"'
	) in hooks
	assert '<EdgeLinkField :model-value="filters.branch || \'\'"' in page
	assert ':searcher="(query) => linkSearch(\'branch\', query)"' in page
	assert ':searcher="(query) => linkSearch(\'practitioner\', query)"' in page


def test_fuzzy_provider_uses_shared_edgesuite_ranker_with_bounded_candidates():
	content = read(SERVICE)

	assert "from edgesuite_ui.search_ranking import rank_search_records" in content
	assert "CANDIDATE_LIMIT = 100" in content
	assert "RESULT_LIMIT = 20" in content
	assert "page_length=CANDIDATE_LIMIT" in content
	assert 'exact_fields=("value",)' in content
	assert "limit=RESULT_LIMIT" in content
	assert 'fieldname == "branch"' in content
	assert 'fieldname == "practitioner"' in content


def test_fuzzy_provider_preserves_permissions_and_backward_compatibility():
	content = read(SERVICE)

	assert "require_internal_user()" in content
	assert "ensure_appointments_enabled()" in content
	assert "get_assigned_branches(user)" in content
	assert "user_has_global_branch_access(user)" in content
	assert "except ImportError" in content
	assert "_legacy_link_options(fieldname, text)" in content
	assert "frappe.get_list(" in content
	assert 'frappe.get_all(\n\t\t"Has Role"' in content


def test_fuzzy_provider_does_not_add_unbounded_or_generic_doctype_search():
	content = read(SERVICE)

	assert "CANDIDATE_LIMIT = 100" in content
	assert "frappe.db.sql" not in content
	assert "ignore_permissions=True" not in content
	assert "doctype" not in content.lower().split("def get_front_desk_link_options", 1)[1]
