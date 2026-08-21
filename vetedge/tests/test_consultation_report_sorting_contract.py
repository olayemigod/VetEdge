from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
APP = ROOT / "vetedge"


def read(path: str) -> str:
    return (APP / path).read_text(encoding="utf-8")


def test_consultation_sorting_is_server_allowlisted_and_stable():
    source = read("services/consultation_report_sorting.py")

    for expected in (
        'SORT_FIELDS = {',
        '"consultation_datetime": "c.`consultation_datetime`"',
        '"service_branch": "c.`service_branch`"',
        '"owner": "c.`primary_owner`"',
        '"status": "c.`status`"',
        '"payment_status": "c.`payment_status`"',
        'DEFAULT_SORT = {"field": "consultation_datetime", "direction": "desc"}',
        'direction not in {"asc", "desc"}',
        'field not in SORT_FIELDS',
        'return f"{primary} {direction}, c.`name` {direction}"',
        'ORDER BY {order_by}',
        'LIMIT %(limit)s OFFSET %(offset)s',
        '"sorting_mode": "server-allowlist"',
    ):
        assert expected in source

    for forbidden in (
        "ignore_permissions",
        "frappe.db.set_value",
        ".submit()",
        ".cancel()",
    ):
        assert forbidden not in source


def test_page_enriched_consultation_fields_are_not_claimed_sortable():
    source = read("services/consultation_report_sorting.py")

    for field in (
        "patient",
        "invoice",
        "invoice_status",
        "planned_treatment_total",
        "vaccination_count",
        "has_vaccination",
        "outcome_assessment_summary",
    ):
        assert f'"{field}"' in source

    assert 'item["sortable"] = fieldname in SORT_FIELDS and fieldname not in UNSAFE_SORT_FIELDS' in source


def test_consultation_provider_passes_shared_sort_contract_only_to_adopted_endpoint():
    registry = read("public/js/vetedge_report_provider_registry.js")

    for expected in (
        "function registerConsultationReport()",
        'loadPage: async ({ filters = {}, start = 0, page_length = 50, sort = null })',
        '"vetedge.services.consultation_report_sorting.get_consultation_register_view"',
        '{ filters, start, page_length, sort }',
        'sorting_mode: payload.metadata?.sorting_mode || "server-allowlist"',
        "registerConsultationReport();",
    ):
        assert expected in registry

    generic_start = registry.index("function registerServerPaginatedReport")
    generic_end = registry.index("function registerClinicalReports", generic_start)
    generic = registry[generic_start:generic_end]
    assert "sort = null" not in generic
    assert "{ filters, start, page_length, sort }" not in generic
