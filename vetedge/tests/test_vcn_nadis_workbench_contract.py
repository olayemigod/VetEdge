from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_regulatory_workbench_is_edgesuite_native_and_uses_dedicated_official_exports():
    page = (ROOT / "veterinary/page/vetedge_regulatory_reporting/vetedge_regulatory_reporting.js").read_text(encoding="utf-8")

    for expected in (
        'frappe.require("edgeui.bundle.js"',
        '"EdgeAppShell"',
        '"EdgePageLayout"',
        '"EdgePageHeader"',
        '"EdgeLinkField"',
        'validate_nadis_vaccination_export',
        'download_nadis_vaccination_workbook',
        'validate_nadis_outbreak_export',
        'download_nadis_outbreak_workbook',
        '__("NADIS Monthly Vaccination Report")',
        '__("NADIS Disease Outbreak Report")',
        '__("Download Official Excel")',
        'label: __("Company")',
        'doctype: "Company"',
        'company: frappe.defaults?.get_user_default?.("Company")',
        'canManageOutbreak: Boolean(',
        'frappe.user?.has_role?.("VetEdge Administrator")',
        '__("Administrator Managed")',
    ):
        assert expected in page

    for forbidden in (
        "ignore_permissions",
        "Sales Invoice",
        "Payment Entry",
        "Stock Entry",
    ):
        assert forbidden not in page


def test_regulatory_navigation_is_idempotent_and_runs_after_standard_sidebar_sync():
    navigation = (ROOT / "install/regulatory_reporting.py").read_text(encoding="utf-8")
    install = (ROOT / "install/__init__.py").read_text(encoding="utf-8")

    for expected in (
        'REGULATORY_PAGE = "vetedge-regulatory-reporting"',
        'SECTION_LABEL = "Regulatory Reporting"',
        'LINK_LABEL = "VCN / NADIS Reports"',
        'getattr(item, "link_type", None) == "Page"',
        'getattr(item, "link_to", None) == REGULATORY_PAGE',
        'getattr(item, "label", None) == "Configuration"',
        'frappe.cache.delete_key("bootinfo")',
    ):
        assert expected in navigation

    assert "ensure_financial_dashboard()\n\tensure_regulatory_reporting_navigation()" in install


def test_vaccination_reason_extends_existing_guarded_edgesuite_editor():
    extension = (ROOT / "services/nadis_vaccination_editor.py").read_text(encoding="utf-8")
    state = (ROOT / "services/clinical_record_state_v2.py").read_text(encoding="utf-8")
    mutations = (ROOT / "services/mutation_security.py").read_text(encoding="utf-8")

    assert 'FIELDNAME = "vaccination_reason"' in extension
    assert 'safe_after_invoice.add(FIELDNAME)' in extension
    assert "extend_vaccination_editor_config(clinical_record_editor.RECORD_CONFIG)" in state
    assert 'fields.get("vaccination_reason")' in state
    assert "extend_vaccination_editor_config(clinical_record_editor.RECORD_CONFIG)" in mutations

    for protected in (
        '"administered_by"',
        '"administered_on"',
        '"batch_no"',
        '"expiry_date"',
        '"billing_item"',
        '"amount"',
        '"linked_invoice"',
        '"stock_entry_reference"',
    ):
        assert protected in mutations


def test_outbreak_native_access_is_admin_only_until_fail_closed_read_hooks_are_added():
    outbreak = (ROOT / "veterinary/doctype/veterinary_disease_outbreak/veterinary_disease_outbreak.json").read_text(encoding="utf-8")

    assert '"role": "System Manager"' in outbreak
    assert '"role": "VetEdge Administrator"' in outbreak
    assert '"role": "VetEdge Doctor"' not in outbreak
    assert '"role": "Veterinary Nurse"' not in outbreak
    assert '"role": "Branch Manager"' not in outbreak
