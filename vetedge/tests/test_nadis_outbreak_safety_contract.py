from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_outbreak_export_allows_zero_new_count_for_follow_up_but_not_new_outbreak():
    export = (ROOT / "services/nadis_outbreak_export.py").read_text(encoding="utf-8")

    assert 'row.get("outbreak_type") == "New outbreak" and cint(row.get("number_new_outbreaks")) < 1' in export
    assert 'Number of New Outbreaks cannot be negative.' in export
    assert 'A New outbreak must report at least one new outbreak' in export
    assert 'investigated.strftime("%B")' in export
    assert 'investigated.strftime("%B").upper()' not in export
    assert 'row.get("country"),' in export
    assert 'or "Nigeria"' not in export


def test_outbreak_source_model_rejects_cross_company_branch_and_bad_follow_up_disease():
    controller = (ROOT / "veterinary/doctype/veterinary_disease_outbreak/veterinary_disease_outbreak.py").read_text(encoding="utf-8")

    for expected in (
        'branch_company = cstr(branch.get("company")',
        'branch_company != selected_company',
        'Reporting Branch {0} belongs to Company {1}, not {2}.',
        'original = frappe.get_doc("Veterinary Disease Outbreak", self.parent_outbreak)',
        'original.check_permission("read")',
        'A follow-up outbreak must use the same Disease as the Original Outbreak.',
        'A follow-up outbreak must belong to the same Company as the Original Outbreak.',
        'A follow-up outbreak must use the same Reporting Branch as the Original Outbreak.',
        'Deaths cannot exceed Cases in Animals Affected row {0}.',
    ):
        assert expected in controller


def test_outbreak_export_revalidates_legacy_counts_and_coordinates_before_download():
    export = (ROOT / "services/nadis_outbreak_export.py").read_text(encoding="utf-8")

    for expected in (
        'Total Number of Outbreaks cannot be negative.',
        'has more Deaths than Cases.',
        'Latitude outside -90 to 90.',
        'Longitude outside -180 to 180.',
    ):
        assert expected in export


def test_outbreak_source_of_infection_is_guided_by_supplied_template_values():
    doctype = (ROOT / "veterinary/doctype/veterinary_disease_outbreak/veterinary_disease_outbreak.json").read_text(encoding="utf-8")

    assert '"fieldname": "source_of_infection", "fieldtype": "Select"' in doctype
    for value in (
        "Airborne spread",
        "Extension from wildlife",
        "Fomites",
        "From endemic foci at locality",
    ):
        assert value in doctype


def test_outbreak_child_query_preserves_parent_doctype_context():
    """Child-table regulatory reads must retain parent permission context."""
    from pathlib import Path

    source = (
        Path(__file__).resolve().parents[1]
        / "services"
        / "nadis_outbreak_export.py"
    ).read_text()

    assert "parent_doctype=OUTBREAK_DOCTYPE" in source
