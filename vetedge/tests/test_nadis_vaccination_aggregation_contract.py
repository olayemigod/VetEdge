from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_vaccination_export_counts_distinct_patients_per_nadis_group():
    export = (ROOT / "services/nadis_vaccination_export.py").read_text(encoding="utf-8")

    for expected in (
        '"patient": patient',
        'patients_by_group: dict[tuple, set[str]] = defaultdict(set)',
        'patients_by_group[key].add(row["patient"])',
        '"number_vaccinated": len(distinct_patients)',
        '"distinct_animal_count": sum(row["number_vaccinated"] for row in aggregated)',
        'VetEdge reports the distinct animal count to avoid double-counting.',
    ):
        assert expected in export


def test_vaccination_export_populates_verified_official_template_instead_of_rebuilding_it():
    export = (ROOT / "services/nadis_vaccination_export.py").read_text(encoding="utf-8")

    for expected in (
        "load_verified_template_bytes",
        "populate_official_template",
        'sheet_rows={VACCINATION_SHEET: _template_rows(rows)}',
        'visible_column_counts={VACCINATION_SHEET: VISIBLE_COLUMN_COUNT}',
        "clear_through_row=VACCINATION_DATA_START_ROW + MAX_TEMPLATE_DATA_ROWS - 1",
    ):
        assert expected in export

    assert "Workbook()" not in export
    assert "DataValidation(" not in export
    assert 'sheet["B4"] = 1' not in export
    assert 'sheet["O4"] = "u"' not in export


def test_vaccine_master_uses_controlled_nadis_vaccine_type():
    vaccine = (ROOT / "veterinary/doctype/veterinary_vaccine/veterinary_vaccine.json").read_text(encoding="utf-8")

    assert '"fieldname": "nadis_vaccine_type"' in vaccine
    assert '"fieldtype": "Select"' in vaccine
    for value in (
        "Anti-idiotype vaccines",
        "Conjugate vaccines",
        "DNA vaccines",
        "Inactivated vaccines",
    ):
        assert value in vaccine
