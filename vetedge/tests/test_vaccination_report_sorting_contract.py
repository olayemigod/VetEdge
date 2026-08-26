from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
APP = ROOT / "vetedge"


def read(path: str) -> str:
    return (APP / path).read_text(encoding="utf-8")


def test_vaccination_sorting_is_server_allowlisted_and_stable():
    source = read("services/vaccination_report.py")

    for expected in (
        'SORT_FIELDS = {',
        '"vaccination_record": "name"',
        '"owner": "primary_owner"',
        '"vaccine": "vaccine"',
        '"service_branch": "service_branch"',
        '"administered_by": "administered_by"',
        '"administered_on": "administered_on"',
        '"next_due_date": "next_due_date"',
        '"status": "status"',
        'DEFAULT_SORT = {"field": "administered_on", "direction": "desc"}',
        'field not in SORT_FIELDS or direction not in {"asc", "desc"}',
        'return f"{source} {direction}, name {direction}"',
        'order_by=_order_by(normalized_sort)',
        '"sorting_mode": "server-allowlist"',
        '"sort": normalized_sort',
    ):
        assert expected in source


def test_vaccination_derived_due_state_and_patient_display_are_not_claimed_sortable():
    source = read("services/vaccination_report.py")
    sort_fields = source.split("SORT_FIELDS = {", 1)[1].split("}", 1)[0]

    assert '"fieldname": "due_status"' in source
    assert '"fieldname": "patient"' in source
    assert '"due_status"' not in sort_fields
    assert '"patient"' not in sort_fields
    assert 'column["sortable"] = column.get("fieldname") in SORT_FIELDS' in source


def test_vaccination_provider_passes_shared_sort_contract():
    registry = read("public/js/vetedge_report_provider_registry.js")

    for expected in (
        "function registerVaccinationReport()",
        '"vetedge.services.vaccination_report.get_vaccination_report_view"',
        'loadPage: async ({ filters = {}, start = 0, page_length = 50, sort = null })',
        "sort,",
        'sorting_mode: payload.metadata?.sorting_mode || "server-allowlist"',
        "registerVaccinationReport();",
    ):
        assert expected in registry
