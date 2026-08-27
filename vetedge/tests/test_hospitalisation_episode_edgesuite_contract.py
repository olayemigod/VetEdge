from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
PAGE_DIR = ROOT / "vetedge" / "veterinary" / "page" / "vetedge_hospitalisation_episode"
PAGE_JS = PAGE_DIR / "vetedge_hospitalisation_episode.js"
PAGE_JSON = PAGE_DIR / "vetedge_hospitalisation_episode.json"
BUNDLE = ROOT / "vetedge" / "public" / "js" / "vetedge_hospitalisation_episode.bundle.js"
COMPONENT = (
    ROOT
    / "vetedge"
    / "public"
    / "js"
    / "vetedge_hospitalisation_episode"
    / "VetEdgeHospitalisationEpisode.vue"
)
OPERATIONS_COMPONENT = (
    ROOT
    / "vetedge"
    / "public"
    / "js"
    / "vetedge_hospitalisation_operations"
    / "VetEdgeHospitalisationOperations.vue"
)
SERVICE = ROOT / "vetedge" / "services" / "hospitalisation_episode.py"
POLICY = ROOT / "vetedge" / "services" / "hospitalisation_episode_policy.py"
POLICY_V2 = ROOT / "vetedge" / "services" / "hospitalisation_episode_policy_v2.py"
HOSPITALISATION_SERVICE = ROOT / "vetedge" / "services" / "hospitalisation.py"
MEDICAL_HISTORY = ROOT / "vetedge" / "services" / "medical_history_integrity.py"
HOOKS = ROOT / "vetedge" / "hooks.py"
PATCH = ROOT / "vetedge" / "patches" / "add_hospitalisation_episode_policy_settings.py"
PATCHES = ROOT / "vetedge" / "patches.txt"


def read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def test_hospitalisation_episode_page_and_bundle_exist():
    assert PAGE_JS.exists()
    assert PAGE_JSON.exists()
    assert BUNDLE.exists()
    assert COMPONENT.exists()

    page = read(PAGE_JS)
    bundle = read(BUNDLE)
    component = read(COMPONENT)

    assert "vetedge_hospitalisation_episode.bundle.js" in page
    assert "new URLSearchParams(window.location.search" in page
    assert "params.get('name')" in page
    assert "mountVetEdgeHospitalisationEpisode" in page
    assert "VetEdgeHospitalisationEpisode.vue" in bundle
    assert "applyWorkspaceSafety" in bundle
    assert "<EdgeAppShell" in component
    assert "<EdgePageLayout" in component
    assert "Open Native Form" in component


def test_hospitalisation_episode_preserves_shared_edgesuite_navigation_shell():
    component = read(COMPONENT)

    assert ".edge-sidebar" not in component
    assert ".edge-shell-sidebar" not in component
    assert ".edge-shell-body" not in component
    assert "display: none !important" not in component


def test_hospitalisation_operations_drills_into_edgesuite_episode_with_query_preserved():
    component = read(OPERATIONS_COMPONENT)
    page = read(PAGE_JS)

    assert "/app/vetedge-hospitalisation-episode?name=${encodeURIComponent(name)}" in component
    assert "openHospitalisationEpisode" in component
    assert "/desk/vetedge-hospitalisation-episode" not in component
    assert "frappe.set_route('Form', 'Veterinary Hospitalisation', row.hospitalisation)" not in component
    assert "canonicalizeHospitalisationEpisodeRoute" in page
    assert "/app/vetedge-hospitalisation-episode" in page


def test_hospitalisation_episode_service_is_permission_and_branch_aware():
    service = read(SERVICE)

    for contract in (
        "require_internal_user()",
        'doc.check_permission("write" if write else "read")',
        "validate_hospitalisation_branch_access(doc)",
        "_assert_not_stale",
        "get_hospitalisation_episode",
        "save_hospitalisation_episode_context",
        "add_hospitalisation_activity",
        "add_hospitalisation_vitals",
        "add_hospitalisation_vaccination",
        "add_hospitalisation_lab_order",
        "search_hospitalisation_episode_options",
        "perform_hospitalisation_episode_action",
    ):
        assert contract in service

    assert "ignore_permissions" not in service


def test_hospitalisation_episode_reuses_authoritative_hospitalisation_services():
    service = read(SERVICE)

    for contract in (
        "service.admit_hospitalisation(name)",
        "service.get_hospitalisation_discharge_readiness(name)",
        "service.get_hospitalisation_stock_posting_preview",
        "service.assign_hospitalisation_care_location",
        "service.release_hospitalisation_care_location",
        "service.post_hospitalisation_activity_stock",
        "service.build_hospitalisation_charge_items(name)",
        "service.sync_hospitalisation_charges_to_invoice",
        "service.check_hospitalisation_payment_gate(name)",
        "service.discharge_hospitalisation",
        "force=False",
    ):
        assert contract in service


def test_hospitalisation_episode_uses_bounded_context_searches():
    service = read(SERVICE)

    assert "_bounded_limit(page_length)" in service
    assert 'if field == "care_location"' in service
    assert '"branch": doc.get("service_branch")' in service
    assert 'if field == "practitioner"' in service
    assert 'if field == "vaccine"' in service
    assert 'if field == "lab_test"' in service
    assert 'if field == "item"' in service


def test_hospitalisation_episode_ui_uses_server_facade_for_mutations():
    component = read(COMPONENT)

    for api in (
        "hospitalisation_episode.get_hospitalisation_episode",
        "hospitalisation_episode.save_hospitalisation_episode_context",
        "hospitalisation_episode.add_hospitalisation_activity",
        "hospitalisation_episode.add_hospitalisation_vitals",
        "hospitalisation_episode.add_hospitalisation_vaccination",
        "hospitalisation_episode.add_hospitalisation_lab_order",
        "hospitalisation_episode.perform_hospitalisation_episode_action",
    ):
        assert api in component

    # Accounting and stock truth stay on the backend. The Vue workspace must
    # not construct ERPNext financial or stock documents itself.
    assert "frappe.new_doc('Sales Invoice'" not in component
    assert 'frappe.new_doc("Sales Invoice"' not in component
    assert "frappe.new_doc('Stock Entry'" not in component
    assert 'frappe.new_doc("Stock Entry"' not in component


def test_hospitalisation_episode_exposes_authoritative_daily_charge_action():
    component = read(COMPONENT)
    service = read(SERVICE)

    assert "Generate Daily Charges" in component
    assert '@click="generateDailyCharges"' in component
    assert "runAction('generate_daily_charges'" in component
    assert '"generate_daily_charges"' in service
    assert "service.generate_hospitalisation_daily_charges(" in service

    # Daily charging remains server-owned. The Episode UI must not create
    # or mutate ERPNext invoices directly.
    assert "frappe.new_doc('Sales Invoice'" not in component
    assert 'frappe.new_doc("Sales Invoice"' not in component


def test_hospitalisation_episode_billing_actions_match_native_operational_parity():
    component = read(COMPONENT)
    service = read(SERVICE)
    hospitalisation = read(HOSPITALISATION_SERVICE)

    assert "Check Payment Gate" in component
    assert '@click="checkPaymentGate"' in component
    assert "runAction('check_payment_gate'" in component
    assert 'elif action == "check_payment_gate"' in service
    assert "service.check_hospitalisation_payment_gate(name)" in service

    assert "View Charge Summary" in component
    assert '@click="viewChargeSummary"' in component
    assert "def get_hospitalisation_charge_summary" in hospitalisation
    assert "const rows = this.episode.charge_items || []" in component
    assert "this.applyEpisode(await call(API.detail" in component
    assert "vetedge.services.hospitalisation.get_hospitalisation_charge_summary" not in component

    # The parity actions consume authoritative, permission-aware Episode data;
    # the EdgeSuite workspace still does not construct accounting documents.
    assert "frappe.new_doc('Sales Invoice'" not in component
    assert 'frappe.new_doc("Sales Invoice"' not in component


def test_hospitalisation_episode_policy_is_routed_through_frappe_overrides():
    hooks = read(HOOKS)

    legacy_contracts = (
        '"vetedge.services.hospitalisation_episode.get_hospitalisation_episode": "vetedge.services.hospitalisation_episode_policy.get_hospitalisation_episode"',
        '"vetedge.services.hospitalisation_episode.add_hospitalisation_activity": "vetedge.services.hospitalisation_episode_policy.add_hospitalisation_activity"',
        '"vetedge.services.hospitalisation_episode.add_hospitalisation_vitals": "vetedge.services.hospitalisation_episode_policy.add_hospitalisation_vitals"',
    )
    hardened_contracts = (
        '"vetedge.services.hospitalisation_episode.add_hospitalisation_vaccination": "vetedge.services.hospitalisation_episode_policy_v2.add_hospitalisation_vaccination"',
        '"vetedge.services.hospitalisation_episode.add_hospitalisation_lab_order": "vetedge.services.hospitalisation_episode_policy_v2.add_hospitalisation_lab_order"',
        '"vetedge.services.hospitalisation_episode.perform_hospitalisation_episode_action": "vetedge.services.hospitalisation_episode_policy_v2.perform_hospitalisation_episode_action"',
        '"vetedge.services.hospitalisation.get_hospitalisation_stock_posting_preview": "vetedge.services.hospitalisation_episode_policy_v2.get_hospitalisation_stock_posting_preview"',
        '"vetedge.services.hospitalisation.post_hospitalisation_activity_stock": "vetedge.services.hospitalisation_episode_policy_v2.post_hospitalisation_activity_stock"',
        '"vetedge.services.hospitalisation.generate_hospitalisation_daily_charges": "vetedge.services.hospitalisation_episode_policy_v2.generate_hospitalisation_daily_charges"',
        '"vetedge.services.hospitalisation.admit_hospitalisation": "vetedge.services.hospitalisation_episode_policy_v2.admit_hospitalisation"',
        '"vetedge.services.hospitalisation.get_hospitalisation_discharge_readiness": "vetedge.services.hospitalisation_episode_policy_v2.get_hospitalisation_discharge_readiness"',
        '"vetedge.services.hospitalisation.discharge_hospitalisation": "vetedge.services.hospitalisation_episode_policy_v2.discharge_hospitalisation"',
    )
    for contract in (*legacy_contracts, *hardened_contracts):
        assert contract in hooks


def test_hardened_policy_keeps_dedicated_clinical_billing_and_stock_single_sourced():
    policy = read(POLICY_V2)

    assert '"billable": 0' in policy
    assert '"stock_affecting": 0' in policy
    assert "timeline reference only" in policy
    assert "create_vaccination_from_consultation" in policy
    assert "create_lab_order_from_consultation" in policy
    assert "create_invoice=0" in policy
    assert "post_stock=0" in policy


def test_hardened_policy_does_not_mutate_stock_history_for_disabled_dispensary():
    policy = read(POLICY_V2)

    assert "def _readiness_without_disabled_stock" in policy
    assert 'result["pending_stock_activities"] = []' in policy
    assert "_normalize_unposted_stock_flags_when_dispensary_disabled" not in policy
    assert "source_warehouse = None" not in policy


def test_hospitalisation_episode_policy_preserves_admission_and_accounting_safety():
    policy = read(POLICY)
    hardened = read(POLICY_V2)
    hospitalisation = read(HOSPITALISATION_SERVICE)

    # The pre-existing admission policy remains authoritative. A clinic that
    # requires consultation linkage does not silently become a direct-admission
    # clinic merely because the EdgeSuite Episode workspace exists.
    assert 'allow_direct_admission=cint(value("allow_direct_hospitalisation_admission", 0))' in hospitalisation
    assert "Hospitalisation should be created from a Consultation" in hospitalisation

    # Charge editing is confined to the Hospitalisation charge sheet while
    # submitted/cancelled ERPNext invoices remain immutable.
    assert "update_hospitalisation_charge_item" in policy
    assert "This charge is linked to a submitted or cancelled Sales Invoice." in policy
    assert '"invoice_sync_required"' in policy
    assert "Sync Charges to Invoice" in policy
    assert "ignore_permissions" not in policy
    assert "frappe.new_doc" not in policy

    # Disabled policy branches are not weaker permission/platform paths.
    assert "def _require_hospitalisation_access" in hardened
    assert "assert_hospitalisation_enabled()" in hardened
    assert "require_vetedge_platform_access" in hardened


def test_hospitalisation_episode_policy_settings_patch_is_registered_and_idempotent():
    patch = read(PATCH)
    patches = read(PATCHES)

    assert "create_custom_fields(" in patch
    assert "update=True" in patch
    assert '"enable_hospitalisation_daily_charges"' in patch
    assert '"allow_editing_hospitalisation_charge_items"' in patch
    assert patch.count('"fieldname": "hospitalisation"') == 3
    assert '"Veterinary Vital Signs"' in patch
    assert '"Veterinary Vaccination Record"' in patch
    assert '"Veterinary Lab Order"' in patch
    assert "vetedge.patches.add_hospitalisation_episode_policy_settings" in patches


def test_direct_admission_clinical_records_are_authoritative_and_linked():
    policy = read(POLICY)

    for contract in (
        "_create_direct_hospitalisation_vitals",
        '"doctype": "Veterinary Vital Signs"',
        "_create_direct_hospitalisation_vaccination",
        '"doctype": "Veterinary Vaccination Record"',
        "_create_direct_hospitalisation_lab_order",
        '"doctype": "Veterinary Lab Order"',
        "_link_record_to_hospitalisation",
        "_link_activity_rows",
    ):
        assert contract in policy

    # Source clinical documents are created through ordinary permission-aware
    # document insertion; the new policy layer must not bypass permissions.
    assert "record.insert()" in policy
    assert "order.insert()" in policy
    assert "ignore_permissions" not in policy


def test_hospitalisation_medical_history_has_permission_aware_episode_timeline():
    history = read(MEDICAL_HISTORY)

    for contract in (
        "get_hospitalisation_history",
        "require_internal_user()",
        "can_access_medical_history",
        'frappe.has_permission(HOSPITALISATION_DOCTYPE, "read")',
        '"event_type": "Admission"',
        '"event_type": "Discharge"',
        'if section == "hospitalisations"',
        'result["hospitalisations"] = get_hospitalisation_history(',
        "HOSPITALISATION_HISTORY_MAX_LIMIT = 100",
    ):
        assert contract in history


def test_hospitalisation_episode_ui_reflects_clinic_policy_capabilities():
    component = read(COMPONENT)
    policy = read(POLICY)

    for contract in (
        "dispensary_enabled",
        "daily_charges_enabled",
        "can_generate_daily_charges",
        "allow_charge_item_editing",
        "update_hospitalisation_charge_item",
    ):
        assert contract in policy

    assert "Dispensary Flow" in component
    assert "Daily charges are off" in component
    assert "Edit Hospitalisation Charge" in component
    assert "Draft invoice linked" in component
    assert "Sync Charges to Invoice afterwards" in component
    assert "hospitalisation_episode_policy.update_hospitalisation_charge_item" in component
