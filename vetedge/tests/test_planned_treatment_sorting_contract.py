from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
APP = ROOT / "vetedge"


def read(path: str) -> str:
    return (APP / path).read_text(encoding="utf-8")


def test_planned_treatment_sorting_is_limited_to_child_native_fields():
    source = read("services/treatment_plan_report.py")

    for expected in (
        'SORT_FIELDS = {',
        '"consultation": "parent"',
        '"item": "item"',
        '"qty": "qty"',
        '"uom": "uom"',
        '"rate": "rate"',
        'DEFAULT_SORT = {"field": "consultation", "direction": "asc"}',
        'field not in SORT_FIELDS or direction not in {"asc", "desc"}',
        'order_by=_order_by(sort)',
        'column["sortable"] = column.get("fieldname") in SORT_FIELDS',
        '"sorting_mode": "server-allowlist"',
        '"sort": normalized_sort',
    ):
        assert expected in source

    sort_fields = source.split("SORT_FIELDS = {", 1)[1].split("}", 1)[0]
    for derived in (
        "consultation_date",
        "service_branch",
        "patient",
        "owner",
        "practitioner",
        "consultation_type",
        "description",
        "amount",
        "consultation_total",
        "patient_total",
        "status",
    ):
        assert f'"{derived}"' not in sort_fields


def test_planned_treatment_provider_passes_sort_without_forcing_all_columns_sortable():
    registry = read("public/js/vetedge_report_provider_registry.js")
    start = registry.index("function registerPlannedTreatment()")
    end = registry.index("function registerConsultationReport()", start)
    block = registry[start:end]

    assert 'loadPage: async ({ filters = {}, start = 0, page_length = 50, sort = null })' in block
    assert '"vetedge.services.treatment_plan_report.get_planned_treatment_view"' in block
    assert "sort," in block
    assert 'columns: nonSortableColumns(payload.columns)' not in block
    assert 'sorting_mode: payload.metadata?.sorting_mode || "server-allowlist"' in block
