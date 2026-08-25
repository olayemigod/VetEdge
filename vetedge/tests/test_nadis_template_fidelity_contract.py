from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_vaccination_template_fidelity_contract_is_recorded():
    templates = (ROOT / "services/nadis_templates.py").read_text(encoding="utf-8")

    for expected in (
        'VACCINATION_TEMPLATE_SHA256 = "458e7af8b47c491f5245f5fc6cc8bbe754bbc23ab63829e88bb2083b813c05ba"',
        'VACCINATION_SHEET = "Vaccinations"',
        'VACCINATION_DATA_START_ROW = 5',
        'VACCINATION_BINARY_FIDELITY = {',
        '"hidden_columns": ("A", "CD")',
        '"hidden_rows": (2,)',
        '"row_4_markers": {"B4": 1, "O4": "u"}',
        '"admin_division_level_1_4651": "Vaccinations!$CD$1:$CD$851"',
        '"admin_division_level_2_3433": "Vaccinations!$CE$1:$CE$670"',
        '"range": "H5:H239", "formula1": "fd_3434_reason_for_the_vaccination"',
        '"range": "P6:P15 P17:P239", "formula1": "fd_3442_vaccine_tested_at_panvac"',
        '"range": "E5:G239", "formula1": "admin_division_level_2_3433"',
    ):
        assert expected in templates


def test_outbreak_template_fidelity_contract_is_recorded():
    templates = (ROOT / "services/nadis_templates.py").read_text(encoding="utf-8")

    for expected in (
        'DISEASE_OUTBREAK_TEMPLATE_SHA256 = "8ea90b4b5c30a66029186905e9aab846bf897f40121d5ec7d7d69acf2964db94"',
        'OUTBREAK_BINARY_FIDELITY = {',
        '"admin_level_1_5518": "[1]Worksheet!$CB$1:$CB$780"',
        '"hidden_columns": ("A", "CA")',
        '"date_hints": {"L4": "(dd/mm/yyyy)", "M4": "(dd/mm/yyyy)", "N4": "(dd/mm/yyyy)", "O4": "(dd/mm/yyyy)"}',
        '"range": "D5:D236", "formula1": \'INDIRECT(SUBSTITUTE(C5," ","_"))\'',
        '"hidden_columns": ("A", "CL")',
        '"range": "D5:D11 D15:D251", "formula1": "CP5:CP8"',
        '"hidden_columns": ("A", "CN")',
        '"range": "E12:E252", "formula1": "CS11:CS16"',
    ):
        assert expected in templates


def test_both_exporters_populate_sha256_verified_official_templates_without_rebuilding_workbooks():
    vaccination = (ROOT / "services/nadis_vaccination_export.py").read_text(encoding="utf-8")
    outbreak = (ROOT / "services/nadis_outbreak_export.py").read_text(encoding="utf-8")

    for source, filename_constant in (
        (vaccination, "VACCINATION_TEMPLATE_FILENAME"),
        (outbreak, "DISEASE_OUTBREAK_TEMPLATE_FILENAME"),
    ):
        assert "load_verified_template_bytes" in source
        assert f"load_verified_template_bytes({filename_constant})" in source
        assert "populate_official_template" in source
        assert "Workbook()" not in source
        assert "create_sheet(" not in source
        assert "DataValidation(" not in source
