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


def test_vaccination_export_preserves_known_row4_markers_and_controlled_dropdowns():
    export = (ROOT / "services/nadis_vaccination_export.py").read_text(encoding="utf-8")

    for expected in (
        'sheet.row_dimensions[2].hidden = True',
        'sheet["B4"] = 1',
        'sheet["O4"] = "u"',
        'sheet.column_dimensions["CD"].hidden = True',
        'Anti-idiotype vaccines,Conjugate vaccines,DNA vaccines,Inactivated vaccines',
        'reason_validation.add(f"H{VACCINATION_DATA_START_ROW}:H239")',
        'vaccine_type_validation.add(f"M{VACCINATION_DATA_START_ROW}:M239")',
        'panvac_validation.add(f"P{VACCINATION_DATA_START_ROW}:P239")',
    ):
        assert expected in export


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
