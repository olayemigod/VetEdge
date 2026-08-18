from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SERVICE = ROOT / "vetedge" / "services" / "master_link_search.py"
HOOKS = ROOT / "vetedge" / "hooks.py"
MASTER = ROOT / "vetedge" / "services" / "master_workspace.py"


def read(path: Path) -> str:
	return path.read_text(encoding="utf-8")


def test_master_link_endpoint_is_overridden_without_replacing_master_workspace():
	hooks = read(HOOKS)
	master = read(MASTER)

	assert (
		'"vetedge.services.master_workspace.get_master_link_options": '
		'"vetedge.services.master_link_search.get_master_link_options"'
	) in hooks
	assert "def get_master_link_options(" in master


def test_master_fuzzy_provider_uses_shared_ranker_and_alias_fields():
	content = read(SERVICE)

	assert "from edgesuite_ui.search_ranking import rank_search_records" in content
	assert "CANDIDATE_LIMIT = 100" in content
	assert "RESULT_LIMIT_MAX = 50" in content
	assert "page_length=CANDIDATE_LIMIT" in content
	assert 'exact_fields=("value",)' in content
	assert 'search_fields=("label", "description")' in content
	assert 'alias_fields=("aliases",)' in content


def test_master_fuzzy_provider_preserves_link_permissions_and_resource_filters():
	content = read(SERVICE)

	assert "_require_master(resource)" in content
	assert 'field.fieldtype != "Link"' in content
	assert "frappe.has_permission(options, \"read\")" in content
	assert 'config.get("link_filters")' in content
	assert "frappe.get_list(" in content
	assert "ignore_permissions=True" not in content


def test_master_fuzzy_provider_has_backward_compatible_fallback():
	content = read(SERVICE)

	assert "except ImportError" in content
	assert "_legacy_link_options(resource, fieldname, query, page_length)" in content
	assert "from vetedge.services.master_workspace import get_master_link_options" in content
