from __future__ import annotations

"""Authoritative NADIS workbook mapping captured from the supplied VCN templates.

The constants in this module are a source-controlled contract for workbook names,
field identifiers and visible columns. They were mapped from the two supplied
workbooks rather than inferred from VetEdge field names.
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
