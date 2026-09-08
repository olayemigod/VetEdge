from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
APP = ROOT / "vetedge"


def read(path: str) -> str:
    return (APP / path).read_text(encoding="utf-8")


def test_owner_register_only_exposes_database_native_sort_fields():
    source = read("services/owner_report.py")

    for expected in (
        'SORT_FIELDS = {',
        '"owner": "c.`name`"',
        '"customer_name": "c.`customer_name`"',
        'DEFAULT_SORT = {"field": "customer_name", "direction": "asc"}',
        'column["sortable"] = column.get("fieldname") in SORT_FIELDS',
        'ORDER BY {order_by}',
        '"sorting_mode": "server-allowlist"',
        '"sort": normalized_sort',
    ):
        assert expected in source

    sort_fields = source.split("SORT_FIELDS = {", 1)[1].split("}", 1)[0]
    for derived in ("number_of_pets", "outstanding_amount", "phone", "email"):
        assert f'"{derived}"' not in sort_fields


def test_patient_register_all_displayed_fields_are_server_sortable():
    source = read("services/patient_report.py")

    for field in (
        "patient",
        "patient_name",
        "primary_owner",
        "species",
        "breed",
        "default_branch",
        "registration_status",
        "status",
        "created_on",
    ):
        assert f'"{field}"' in source.split("SORT_FIELDS = {", 1)[1].split("}", 1)[0]

    for expected in (
        'DEFAULT_SORT = {"field": "created_on", "direction": "desc"}',
        'order_by=_order_by(normalized_sort)',
        'column["sortable"] = column.get("fieldname") in SORT_FIELDS',
        '"sorting_mode": "server-allowlist"',
        '"sort": normalized_sort',
    ):
        assert expected in source


def test_master_register_providers_forward_sort_without_affecting_nonadopted_reports():
    registry = read("public/js/vetedge_report_provider_registry.js")

    for expected in (
        "function registerSortableServerReport(reportKey, method, aliases = [])",
        'loadPage: async ({ filters = {}, start = 0, page_length = 50, sort = null })',
        'const payload = await call(method, { filters, start, page_length, sort });',
        '"Owner Register"',
        '"vetedge.services.owner_report.get_owner_register_view"',
        '"Patient Register"',
        '"vetedge.services.patient_report.get_patient_register_view"',
    ):
        assert expected in registry

    generic = registry.split("function registerServerPaginatedReport", 1)[1].split("function registerClinicalReports", 1)[0]
    assert "sort = null" not in generic
    assert "columns: nonSortableColumns(payload.columns)" in generic
