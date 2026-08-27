from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
OPERATIONS_COMPONENT = (
    ROOT
    / "vetedge"
    / "public"
    / "js"
    / "vetedge_hospitalisation_operations"
    / "VetEdgeHospitalisationOperations.vue"
)
EPISODE_COMPONENT = (
    ROOT
    / "vetedge"
    / "public"
    / "js"
    / "vetedge_hospitalisation_episode"
    / "VetEdgeHospitalisationEpisode.vue"
)
POLICY = ROOT / "vetedge" / "services" / "hospitalisation_episode_policy.py"
EPISODE_SERVICE = ROOT / "vetedge" / "services" / "hospitalisation_episode.py"
MEDICAL_HISTORY = ROOT / "vetedge" / "services" / "medical_history_integrity.py"
CLINICAL_CONTEXT = ROOT / "vetedge" / "services" / "clinical_consultation_context.py"
CLINICAL_WORKSPACE_CONTEXT = ROOT / "vetedge" / "services" / "clinical_workspace_context.py"
SETTINGS_CONTROLLER = (
    ROOT
    / "vetedge"
    / "veterinary"
    / "doctype"
    / "veterinary_settings"
    / "veterinary_settings.py"
)
SETTINGS_PATCH = ROOT / "vetedge" / "patches" / "add_hospitalisation_episode_policy_settings.py"
DAILY_SETTINGS_PATCH = ROOT / "vetedge" / "patches" / "harden_hospitalisation_daily_charge_settings.py"
PATCHES = ROOT / "vetedge" / "patches.txt"


def read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def test_dispensary_off_is_server_authoritative_and_hides_episode_stock_actions():
    policy = read(POLICY)
    episode = read(EPISODE_COMPONENT)

    assert 'return bool(is_enabled("dispensary_flow"))' in policy
    assert 'capabilities["can_preview_stock"] = bool(capabilities.get("can_post_stock") and dispensary_enabled)' in policy
    assert 'capabilities["can_post_stock"] = bool(capabilities.get("can_post_stock") and dispensary_enabled)' in policy
    assert 'signals["pending_stock"] = 0' in policy
    assert 'resolved_stock = 0' in policy
    assert 'source_warehouse = None' in policy
    assert "Hospitalisation stock posting is unavailable" in policy

    assert 'v-if="episode.capabilities?.dispensary_enabled"' in episode
    assert 'v-if="episode.capabilities?.can_preview_stock"' in episode
    assert 'v-if="episode.capabilities?.can_post_stock"' in episode


def test_charge_editing_setting_preserves_submitted_invoice_immutability():
    policy = read(POLICY)
    patch = read(SETTINGS_PATCH)

    assert '"allow_editing_hospitalisation_charge_items"' in patch
    assert "is_hospitalisation_charge_editing_enabled" in policy
    assert 'frappe.has_permission(HOSPITALISATION_DOCTYPE, ptype="write", doc=doc)' in policy
    assert 'cint(invoice.get("docstatus")) != 0' in policy
    assert "This charge is linked to a submitted or cancelled Sales Invoice." in policy
    assert '"invoice_sync_required"' in policy
    assert "frappe.new_doc" not in policy
    assert "ignore_permissions" not in policy


def test_hospitalisation_clinical_item_contract_uses_real_masters():
    policy = read(POLICY)
    service = read(EPISODE_SERVICE)

    assert "resolved_billable or resolved_type in ITEM_REQUIRED_ACTIVITY_TYPES" in policy
    assert "resolved_stock and not resolved_item" in policy
    assert '"Veterinary Vaccine"' in service
    assert '["default_item", "default_price"]' in service
    assert '"Veterinary Lab Test"' in service
    assert '"linked_item"' in service


def test_direct_hospitalisation_clinical_records_do_not_require_fake_consultation():
    policy = read(POLICY)
    consultation_context = read(CLINICAL_CONTEXT)
    workspace_context = read(CLINICAL_WORKSPACE_CONTEXT)

    assert '_create_direct_hospitalisation_vitals' in policy
    assert '_create_direct_hospitalisation_vaccination' in policy
    assert '_create_direct_hospitalisation_lab_order' in policy
    assert '"doctype": "Veterinary Vital Signs"' in policy
    assert '"doctype": "Veterinary Vaccination Record"' in policy
    assert '"doctype": "Veterinary Lab Order"' in policy

    # Lab and Vaccination consultation links are optional; validators return
    # when no Consultation is supplied. Vitals ownership likewise applies only
    # when a Consultation actually exists.
    assert 'if not consultation:\n        return' in consultation_context
    assert 'def enforce_lab_consultation_context' in consultation_context
    assert 'def enforce_vaccination_consultation_context' in consultation_context
    assert 'if consultation:\n\t\tassert_consultation_write_ownership' in workspace_context


def test_daily_charge_switch_controls_runtime_configuration_and_initial_source():
    policy = read(POLICY)
    settings = read(SETTINGS_CONTROLLER)
    patch = read(SETTINGS_PATCH)
    harden_patch = read(DAILY_SETTINGS_PATCH)
    patches = read(PATCHES)

    assert '"enable_hospitalisation_daily_charges"' in patch
    assert '"default": "1"' in patch
    assert 'is_hospitalisation_daily_charges_enabled' in policy
    assert 'capabilities["can_generate_daily_charges"]' in policy
    assert 'Hospitalisation Daily Charges are disabled' in policy
    assert 'hospitalisation_initial_billing_source' in settings
    assert 'Day 1 Daily Charge cannot be used' in settings

    assert 'hospitalisation_daily_charge_settings' in harden_patch
    assert 'doc.enable_hospitalisation_daily_charges' in harden_patch
    assert 'make_property_setter(' in harden_patch
    assert 'vetedge.patches.harden_hospitalisation_daily_charge_settings' in patches


def test_hospitalisation_history_skips_dedicated_clinical_duplicates():
    history = read(MEDICAL_HISTORY)

    for doctype in (
        '"Veterinary Vital Signs"',
        '"Veterinary Vaccination Record"',
        '"Veterinary Lab Order"',
    ):
        assert doctype in history
    assert "DEDICATED_HOSPITALISATION_CLINICAL_DOCTYPES" in history
    assert "def _is_dedicated_clinical_activity" in history
    assert "if _is_dedicated_clinical_activity(activity):" in history
    assert 'if section == "hospitalisations"' in history


def test_hospitalisation_operations_uses_edgesuite_signature_smart_date_and_four_columns():
    component = read(OPERATIONS_COMPONENT)

    assert "'EdgeSmartDateRange'" in component
    assert "<EdgeSmartDateRange" in component
    assert 'label="Admitted Date"' in component
    assert 'placeholder="e.g. Last 3 weeks, This Month, Last 90 days"' in component
    assert 'date-order="DMY"' in component
    assert '@resolved="onAdmittedDateResolved"' in component
    assert "this.filters.from_date = value.from_date" in component
    assert "this.filters.to_date = value.to_date" in component
    assert 'label="Admitted From"' not in component
    assert 'label="Admitted To"' not in component
    assert "grid-template-columns: repeat(4, minmax(10rem, 1fr));" in component


def test_hospitalisation_exception_action_routes_to_edgesuite_episode():
    component = read(OPERATIONS_COMPONENT)

    assert "item.reference_doctype === 'Veterinary Hospitalisation'" in component
    assert "/desk/vetedge-hospitalisation-episode?name=${encodeURIComponent(item.reference_name)}" in component
    assert "frappe.set_route('Form', 'Veterinary Hospitalisation', item.reference_name)" not in component
