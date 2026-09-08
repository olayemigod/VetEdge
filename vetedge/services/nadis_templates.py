from __future__ import annotations

"""Authoritative NADIS workbook mapping captured from the supplied VCN templates.

The constants in this module are a source-controlled contract for workbook names,
field identifiers, visible columns and release-critical binary workbook metadata.
They were mapped from the two supplied workbooks rather than inferred from
VetEdge field names.
"""

VACCINATION_TEMPLATE_FILENAME = "Nadis Template Vaccination Report 1.xlsx"
VACCINATION_TEMPLATE_SHA256 = "458e7af8b47c491f5245f5fc6cc8bbe754bbc23ab63829e88bb2083b813c05ba"
VACCINATION_SHEET = "Vaccinations"
VACCINATION_TITLE = "Monthly Vaccination Report"
VACCINATION_DATA_START_ROW = 5
VACCINATION_HEADERS = (
    "PK",
    "Code",
    "Country * ",
    "Admin Division (Level 1) * ",
    "Admin Division (Level 2)",
    "Year",
    "Month",
    "Reason for the vaccination * ",
    "Species * ",
    "Disease * ",
    "Number of animals vaccinated for the species selected * ",
    "Name of Vaccine",
    "Type of Vaccine",
    "Source of Vaccine",
    "Batch number",
    "Vaccine tested at PANVAC",
)
VACCINATION_FIELD_IDS = (
    None,
    None,
    4650,
    4651,
    3433,
    None,
    None,
    3434,
    3435,
    3436,
    3437,
    3438,
    3439,
    3440,
    3441,
    3442,
)
VACCINATION_REQUIRED_COLUMNS = (
    "country",
    "admin_level_1",
    "reason",
    "species",
    "disease",
    "number_vaccinated",
)
VACCINATION_REASONS = (
    "Control/Emergency vaccination",
    "Preventive/Routine vaccination",
)
VACCINATION_VACCINE_TYPES = (
    "Anti-idiotype vaccines",
    "Conjugate vaccines",
    "DNA vaccines",
    "Inactivated vaccines",
)
PANVAC_VALUES = ("No", "Yes")

# Release-critical facts read from the supplied binary workbook. The regulatory
# exporter must preserve these exactly or prove an equivalent Excel contract
# before the file can be described as submission-template faithful.
VACCINATION_BINARY_FIDELITY = {
    "max_row": 851,
    "max_column": 88,
    "hidden_columns": ("A", "CD"),
    "hidden_rows": (2,),
    "row_4_markers": {"B4": 1, "O4": "u"},
    "defined_names": {
        "admin_division_level_1_4651": "Vaccinations!$CD$1:$CD$851",
        "admin_division_level_2_3433": "Vaccinations!$CE$1:$CE$670",
    },
    "validations": (
        {"range": "H5:H239", "formula1": "fd_3434_reason_for_the_vaccination", "allow_blank": False},
        {"range": "I5:I239", "formula1": "fd_3435_species", "allow_blank": False},
        {"range": "C5:C239", "formula1": "fd_4650_country", "allow_blank": False},
        {"range": "P6:P15 P17:P239", "formula1": "fd_3442_vaccine_tested_at_panvac", "allow_blank": False},
        {"range": "D5:D239", "formula1": "admin_division_level_1_4651", "allow_blank": False},
        {"range": "E5:G239", "formula1": "admin_division_level_2_3433", "allow_blank": False},
        {"range": "J5:J239", "formula1": "fd_3436_disease", "allow_blank": False},
        {"range": "M5:M239", "formula1": "fd_3439_type_of_vaccine", "allow_blank": False},
    ),
}

DISEASE_OUTBREAK_TEMPLATE_FILENAME = "NadisTemplate Disease Outbreak Report.xlsx"
DISEASE_OUTBREAK_TEMPLATE_SHA256 = "8ea90b4b5c30a66029186905e9aab846bf897f40121d5ec7d7d69acf2964db94"
OUTBREAK_DATA_START_ROW = 5
OUTBREAK_SHEETS = (
    "Outbreaks",
    "Animals affected",
    "Bases of Diagnosis",
    "Disease Control Measures",
    "Locations",
)
OUTBREAK_SHEET_DEFINITIONS = {
    "Outbreaks": {
        "title": "Disease outbreak detail",
        "field_ids": (None, None, None, 5518, 3210, 3211, 3212, 3213, 3214, 3220, 3221, 3215, 3713, 3216, 3219, 3222, 3223),
        "headers": (
            "PK",
            "Code",
            "Country",
            "Admin Level 1",
            "Year * ",
            "Month",
            "Disease * ",
            "Serotype",
            "New or Follow up outbreak",
            "Number of New outbreaks * ",
            "Total number of outbreaks",
            "Date of start of outbreak",
            "Date reported to Vet",
            "Date investigated * ",
            "Date of final diagnosis * ",
            "Source of infection",
            "Outbreak status",
        ),
        "date_hint_columns": (12, 13, 14, 15),
    },
    "Animals affected": {
        "title": "Disease outbreak detail > Animals affected",
        "field_ids": (None, None, 4579, 4605, 4581, 4582, 4583, 4585, 4586, 4587, 4588),
        "headers": (
            "PK",
            "parent",
            "Species * ",
            "Age Group",
            "Sex",
            "Number susceptible",
            "Number of cases * ",
            "Number of death",
            "Number slaughtered",
            "Number destroyed",
            "Number vaccinated around the outbreak",
        ),
    },
    "Bases of Diagnosis": {
        "title": "Disease outbreak detail > Bases of Diagnosis",
        "field_ids": (None, None, 1359),
        "headers": ("PK", "parent", "Basis of diagnosis"),
    },
    "Disease Control Measures": {
        "title": "Disease outbreak detail > Disease Control Measures",
        "field_ids": (None, None, 1394, 4606),
        "headers": ("PK", "parent", "Disease control measure * ", "Flag * "),
    },
    "Locations": {
        "title": "Disease outbreak detail > Locations",
        "field_ids": (None, None, 1344, 1343, 1346, 1345, None),
        "headers": (
            "PK",
            "parent",
            "Name of locality * ",
            "Epidemiological unit type",
            "Production system",
            "Location coordinate",
            None,
        ),
        "subheaders": (None, None, None, None, None, "Latitude", "Longitude"),
    },
}
OUTBREAK_TYPES = ("Follow up outbreak", "New outbreak")
OUTBREAK_STATUSES = ("Continuing", "Resolved")
DIAGNOSIS_BASES = (
    "Advanced laboratory test(s)",
    "Basic laboratory test(s)",
    "Clinical",
    "Owner's claim",
    "Post-mortem",
)
CONTROL_MEASURE_FLAGS = ("Applied", "Not Applicable", "Planned")
EPIDEMIOLOGICAL_UNIT_TYPES = ("Farm", "Not Applicable", "Quarantine facility", "Village")
PRODUCTION_SYSTEMS = (
    "All",
    "Extensive (Pastoralist & Transhumance)",
    "Intensive",
    "Mixed / semi-extensive / semi-intensive",
)
ANIMAL_SEX_VALUES = ("All", "Female", "Male", "Unknown")

OUTBREAK_BINARY_FIDELITY = {
    "defined_names": {
        # The supplied workbook carries a malformed external-style sheet name in
        # this defined-name formula. Preserve/verify the binary behavior rather
        # than silently normalizing it in a regulatory export.
        "admin_level_1_5518": "[1]Worksheet!$CB$1:$CB$780",
    },
    "sheets": {
        "Outbreaks": {
            "max_row": 931,
            "max_column": 85,
            "hidden_columns": ("A", "CA"),
            "hidden_rows": (2,),
            "date_hints": {"L4": "(dd/mm/yyyy)", "M4": "(dd/mm/yyyy)", "N4": "(dd/mm/yyyy)", "O4": "(dd/mm/yyyy)"},
            "validations": (
                {"range": "P7:P8", "formula1": "CU7:CU11"},
                {"range": "P6", "formula1": "CU5:CU9"},
                {"range": "P9:P10 P11", "formula1": "CU8:CU17"},
                {"range": "P12:P252", "formula1": "CU10:CU19"},
            ),
        },
        "Animals affected": {
            "max_row": 191,
            "max_column": 88,
            "hidden_columns": ("A", "CH"),
            "hidden_rows": (2,),
            "validations": (
                {"range": "D5:D236", "formula1": 'INDIRECT(SUBSTITUTE(C5," ","_"))'},
            ),
        },
        "Bases of Diagnosis": {
            "max_row": 5,
            "max_column": 89,
            "hidden_columns": ("A", "CK"),
            "hidden_rows": (2,),
            "validations": (),
        },
        "Disease Control Measures": {
            "max_row": 141,
            "max_column": 91,
            "hidden_columns": ("A", "CL"),
            "hidden_rows": (2,),
            "validations": (
                {"range": "D5:D11 D15:D251", "formula1": "CP5:CP8"},
                {"range": "D12:D14", "formula1": "CP12:CP14"},
            ),
        },
        "Locations": {
            "max_row": 87,
            "max_column": 93,
            "hidden_columns": ("A", "CN"),
            "hidden_rows": (2,),
            "validations": (
                {"range": "E5:E7", "formula1": "CS5:CS8"},
                {"range": "E8", "formula1": "CS8:CS9"},
                {"range": "E9:E10 E11", "formula1": "CS9:CS14"},
                {"range": "E12:E252", "formula1": "CS11:CS16"},
            ),
        },
    },
}
