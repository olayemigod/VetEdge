from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
ADAPTER = ROOT / "vetedge" / "services" / "appointment_link_search.py"
HOOKS = ROOT / "vetedge" / "hooks.py"
APPOINTMENT = ROOT / "vetedge" / "services" / "appointment_edgeui.py"
FLOW = ROOT / "vetedge" / "public" / "js" / "vetedge_resource_center" / "VetEdgeAppointmentFlow.vue"


def read(path: Path) -> str:
	return path.read_text(encoding="utf-8")


def test_appointment_link_search_is_overridden_without_changing_ui_contract():
	hooks = read(HOOKS)
	flow = read(FLOW)

	assert (
		'"vetedge.services.appointment_edgeui.search_appointment_link": '
		'"vetedge.services.appointment_link_search.search_appointment_link"'
	) in hooks
	assert 'frappe.call("vetedge.services.appointment_edgeui.search_appointment_link"' in flow
	assert '<EdgeLinkField' in flow


def test_adapter_reuses_shared_ranker_and_original_permission_provider():
	content = read(ADAPTER)

	assert "from edgesuite_ui.search_ranking import rank_search_records" in content
	assert "appointment_edgeui.search_appointment_link(" in content
	assert "CANDIDATE_POOL_MAX = 100" in content
	assert 'exact_fields=("identifiers",)' in content
	assert 'search_fields=("label", "description", "search_text")' in content
	assert '"microchip_id"' in content
	assert '"mobile_no"' in content
	assert '"email_id"' in content
	assert "except (ImportError, ModuleNotFoundError)" in content


def test_existing_provider_retains_business_filters_and_permissions():
	content = read(APPOINTMENT)

	for contract in (
		'frappe.has_permission(doctype, "read")',
		'filters["disabled"] = ["!=", 1]',
		'filters["status"] = ["!=", "Deceased"]',
		'filters["primary_owner"] = context["owner"]',
		'filters["default_branch"] = ["in", ["", context["branch"]]]',
		'_permission_filtered_branches()',
		'filters["species"] = context["species"]',
		'get_veterinary_doctor_users(',
	):
		assert contract in content


def test_adapter_keeps_pagination_and_old_edgesuite_fallback_safe():
	content = read(ADAPTER)

	assert "if not query or start_value or not _shared_ranker():" in content
	assert "page_length=limit" in content
	assert "candidate_limit = min(CANDIDATE_POOL_MAX" in content
	assert 'txt=""' in content
