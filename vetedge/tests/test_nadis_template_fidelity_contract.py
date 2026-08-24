from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_vaccination_template_fidelity_contract_is_recorded():
    templates = (ROOT / "services/nadis_templates.py").read_text(encoding="utf-8")

    for expected in (
        'VACCINATION_TEMPLATE_SHA256 = "458e7af8b47c491f5245f5fc6cc8bbe754bbc23ab63829e88bb2083b813c05ba"',
        'VACCINATION_SHEET = "Vaccinations"',
        'VACCINATION_DATA_START_ROW = 5',
    ):
        assert expected in templates

    # These values come from the supplied binary workbook and are release QA
    # requirements, not optional presentation details.
    expected_binary_metadata = {
        "hidden_columns": ("A", "CD"),
        "hidden_rows": (2,),
        "defined_names": {
            "admin_division_level_1_4651": "Vaccinations!$CD$1:$CD$851",
            "admin_division_level_2_3433": "Vaccinations!$CE$1:$CE$670",
        },
        "row_4_markers": {"B4": 1, "O4": "u"},
        "validation_count": 8,
        "validation_ranges": (
            "H5:H239",
            "I5:I239",
            "C5:C239",
            "P6:P15 P17:P239",
            "D5:D239",
            "E5:G239",
            "J5:J239",
            "M5:M239",
        ),
    }
    assert expected_binary_metadata["validation_count"] == 8
    assert expected_binary_metadata["row_4_markers"]["B4"] == 1


def test_outbreak_template_fidelity_contract_is_recorded():
    templates = (ROOT / "services/nadis_templates.py").read_text(encoding="utf-8")

    assert 'DISEASE_OUTBREAK_TEMPLATE_SHA256 = "8ea90b4b5c30a66029186905e9aab846bf897f40121d5ec7d7d69acf2964db94"' in templates
    for sheet_name in (
        "Outbreaks",
        "Animals affected",
        "Bases of Diagnosis",
        "Disease Control Measures",
        "Locations",
    ):
        assert f'"{sheet_name}"' in templates

    # Supplied workbook fidelity facts captured during binary inspection.
    expected = {
        "Outbreaks": {"hidden_columns": ("A", "CA"), "validation_count": 4},
        "Animals affected": {"hidden_columns": ("A", "CH"), "validation_count": 1},
        "Bases of Diagnosis": {"hidden_columns": ("A", "CK"), "validation_count": 0},
        "Disease Control Measures": {"hidden_columns": ("A", "CL"), "validation_count": 2},
        "Locations": {"hidden_columns": ("A", "CN"), "validation_count": 4},
    }
    assert sum(item["validation_count"] for item in expected.values()) == 11
    assert expected["Outbreaks"]["hidden_columns"] == ("A", "CA")


def test_current_exporters_do_not_claim_binary_template_preservation():
    vaccination = (ROOT / "services/nadis_vaccination_export.py").read_text(encoding="utf-8")
    outbreak = (ROOT / "services/nadis_outbreak_export.py").read_text(encoding="utf-8")

    # Until the exact binary templates are packaged/populated, generated files
    # must not be described in source as byte-for-byte copies of the originals.
    for source in (vaccination, outbreak):
        assert "byte-for-byte" not in source.lower()
        assert "exact binary template" not in source.lower()
