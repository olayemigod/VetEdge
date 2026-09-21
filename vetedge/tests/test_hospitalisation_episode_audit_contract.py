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
OPERATIONS_PAGE = (
    ROOT
    / "vetedge"
    / "veterinary"
    / "page"
    / "vetedge_hospitalisation_operations"
    / "vetedge_hospitalisation_operations.js"
)
EPISODE_COMPONENT = (
    ROOT
    / "vetedge"
    / "public"
    / "js"
    / "vetedge_hospitalisation_episode"
    / "VetEdgeHospitalisationEpisode.vue"
)
EPISODE_PAGE = (
    ROOT
    / "vetedge"
    / "veterinary"
    / "page"
    / "vetedge_hospitalisation_episode"
    / "vetedge_hospitalisation_episode.js"
)
SETTINGS_COMPONENT = (
    ROOT
    / "vetedge"
    / "public"
    / "js"
    / "veterinary_settings_center"
    / "VeterinarySettingsCenter.vue"
)
POLICY = ROOT / "vetedge" / "services" / "hospitalisation_episode_policy.py"
POLICY_V2 = ROOT / "vetedge" / "services" / "hospitalisation_episode_policy_v2.py"
EPISODE_SERVICE = ROOT / "vetedge" / "services" / "hospitalisation_episode.py"
OPERATIONS_SERVICE = ROOT / "vetedge" / "services" / "hospitalisation_operations.py"
REPORT_EXCEPTIONS = ROOT / "vetedge" / "services" / "report_exceptions.py"
SETTINGS_PAGE = ROOT / "vetedge" / "services" / "settings_page.py"
MEDICAL_HISTORY = ROOT / "vetedge" / "services" / "medical_history_integrity.py"
CLINICAL_CONTEXT = ROOT / "vetedge" / "services" / "clinical_consultation_context.py"
CLINICAL_WORKSPACE_CONTEXT = ROOT / "vetedge" / "services" / "clinical_workspace_context.py"
HOOKS = ROOT / "vetedge" / "hooks.py"
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
    policy_v2 = read(POLICY_V2)
    episode = read(EPISODE_COMPONENT)

    assert 'return bool(is_enabled("dispensary_flow"))' in policy
    assert 'capabilities["can_preview_stock"] = bool(capabilities.get("can_post_stock") and dispensary_enabled)' in policy
    assert 'capabilities["can_post_stock"] = bool(capabilities.get("can_post_stock") and dispensary_enabled)' in policy
    assert 'signals["pending_stock"] = 0' in policy
    assert 'resolved_stock = 0' in policy
    assert 'source_warehouse = None' in policy
    assert "Hospitalisation stock posting is unavailable" in policy_v2

    assert 'v-if="episode.capabilities?.dispensary_enabled"' in episode
    assert 'v-if="episode.capabilities?.can_preview_stock"' in episode
    assert 'v-if="episode.capabilities?.can_post_stock"' in episode


def test_dispensary_off_suppresses_actionable_operations_and_exception_stock_signals():
    operations = read(OPERATIONS_SERVICE)
    exceptions = read(REPORT_EXCEPTIONS)

    assert "is_hospitalisation_dispensary_enabled" in operations
    assert "dispensary_enabled = is_hospitalisation_dispensary_enabled()" in operations
    assert "dispensary_enabled\n            and cint(row.get(\"stock_affecting\"))" in operations

    assert "is_hospitalisation_dispensary_enabled" in exceptions
    assert "if not is_hospitalisation_dispensary_enabled():" in exceptions
    assert "return []" in exceptions
    assert '"exception_type": "pending_stock"' in exceptions


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


def test_dedicated_vaccination_and_lab_keep_single_billing_stock_authority():
    policy_v2 = read(POLICY_V2)
    hooks = read(HOOKS)

    assert '"billable": 0' in policy_v2
    assert '"stock_affecting": 0' in policy_v2
    assert "timeline reference only" in policy_v2
    assert "create_vaccination_from_consultation" in policy_v2
    assert "create_lab_order_from_consultation" in policy_v2
    assert "create_invoice=0" in policy_v2
    assert "post_stock=0" in policy_v2
    assert (
        '"vetedge.services.hospitalisation_episode.add_hospitalisation_vaccination": '
        '"vetedge.services.hospitalisation_episode_policy_v2.add_hospitalisation_vaccination"'
    ) in hooks
    assert (
        '"vetedge.services.hospitalisation_episode.add_hospitalisation_lab_order": '
        '"vetedge.services.hospitalisation_episode_policy_v2.add_hospitalisation_lab_order"'
    ) in hooks


def test_disabled_policy_shortcuts_apply_access_boundary_before_returning():
    policy_v2 = read(POLICY_V2)
    hooks = read(HOOKS)

    assert "def _require_hospitalisation_access" in policy_v2
    assert "assert_hospitalisation_enabled()" in policy_v2
    assert "base_policy._load_hospitalisation" in policy_v2
    assert "require_vetedge_platform_access" in policy_v2
    for method in (
        "get_hospitalisation_stock_posting_preview",
        "post_hospitalisation_activity_stock",
        "generate_hospitalisation_daily_charges",
        "admit_hospitalisation",
        "get_hospitalisation_discharge_readiness",
        "discharge_hospitalisation",
    ):
        assert f"hospitalisation_episode_policy_v2.{method}" in hooks


def test_dispensary_off_readiness_does_not_rewrite_historical_stock_rows():
    policy_v2 = read(POLICY_V2)

    assert "def _readiness_without_disabled_stock" in policy_v2
    assert 'result["pending_stock_activities"] = []' in policy_v2
    assert 'action != "Post Stock Usage"' in policy_v2
    assert "stock_affecting = 0" not in policy_v2
    assert "source_warehouse = None" not in policy_v2
    assert "_normalize_unposted_stock_flags_when_dispensary_disabled" not in policy_v2


def test_daily_charge_switch_controls_runtime_configuration_and_initial_source():
    policy = read(POLICY)
    policy_v2 = read(POLICY_V2)
    settings = read(SETTINGS_CONTROLLER)
    settings_page = read(SETTINGS_PAGE)
    settings_component = read(SETTINGS_COMPONENT)
    patch = read(SETTINGS_PATCH)
    harden_patch = read(DAILY_SETTINGS_PATCH)
    patches = read(PATCHES)

    assert '"enable_hospitalisation_daily_charges"' in patch
    assert '"default": "1"' in patch
    assert 'is_hospitalisation_daily_charges_enabled' in policy
    assert 'capabilities["can_generate_daily_charges"]' in policy
    assert 'Hospitalisation Daily Charges are disabled' in policy_v2
    assert 'hospitalisation_initial_billing_source' in settings
    assert 'Day 1 Daily Charge cannot be used' in settings

    assert 'hospitalisation_daily_charge_settings' in harden_patch
    assert 'doc.enable_hospitalisation_daily_charges' in harden_patch
    assert 'make_property_setter(' in harden_patch
    assert 'vetedge.patches.harden_hospitalisation_daily_charge_settings' in patches

    # The EdgeSuite Settings Center is metadata-driven, so the Property Setter
    # hides the table without a Hospitalisation-specific alternate settings UI.
    assert '"depends_on": field.depends_on or ""' in settings_page
    assert "isVisible(field) { return evaluateCondition(field.depends_on, this.values); }" in settings_component


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
    assert ":deep(.edge-smart-date__picker)" in component
    assert "inset-inline-end: 0" in component
    assert "if (hadAppliedRange) this.applyFilters();" in component


def test_hospitalisation_operations_sorting_is_server_side_and_allowlisted():
    component = read(OPERATIONS_COMPONENT)
    service = read(OPERATIONS_SERVICE)

    assert ':sort="sort"' in component
    assert '@sort-change="onSortChange"' in component
    assert "sort: JSON.stringify(this.sort || DEFAULT_SORT)" in component
    assert "def _normalize_sort" in service
    assert "SORTABLE_PARENT_FIELDS" in service
    assert "order_by=_order_by(sort)" in service
    assert '"sorting_strategy": "server-parent-fields"' in service
    assert '"latest_activity_datetime", "label": _("Latest Activity"), "fieldtype": "Datetime", "sortable": False' in service
    assert '"pending_stock_count", "label": _("Pending Stock"), "fieldtype": "Int", "sortable": False' in service
    assert '"pending_charge_amount", "label": _("Pending Charges"), "fieldtype": "Currency", "sortable": False' in service
    assert '"missing_price_count", "label": _("Missing Prices"), "fieldtype": "Int", "sortable": False' in service


def test_hospitalisation_exception_and_list_actions_use_record_path_segment():
    component = read(OPERATIONS_COMPONENT)
    operations_page = read(OPERATIONS_PAGE)
    episode_page = read(EPISODE_PAGE)

    # Both Vue actions share the same method, which the Frappe Page wrapper
    # replaces with a route-safe implementation after mount and on repeat visits.
    assert "item.reference_doctype === 'Veterinary Hospitalisation'" in component
    assert "this.openHospitalisationEpisode(item.reference_name)" in component
    assert "this.openHospitalisationEpisode(row.hospitalisation)" in component
    assert "function openHospitalisationEpisodeRoute" in operations_page
    assert "view.openHospitalisationEpisode = openHospitalisationEpisodeRoute" in operations_page
    assert "frappe.set_route('vetedge-hospitalisation-episode', hospitalisation)" in operations_page
    assert "/desk/vetedge-hospitalisation-episode/${encodeURIComponent(hospitalisation)}" in operations_page
    assert "{ name: hospitalisation }" not in operations_page
    assert "frappe.set_route('Form', 'Veterinary Hospitalisation', item.reference_name)" not in component

    # The Hospitalisation identifier is a Frappe route segment so it cannot be
    # lost as transient route_options. Query-string support remains only for
    # older links already in browser history.
    assert "hospitalisationEpisodeDeskUrl" in episode_page
    assert "/desk/vetedge-hospitalisation-episode/${encodeURIComponent(name)}" in episode_page
    assert "window.frappe?.get_route?.()" in episode_page
    assert "pathParts" in episode_page
    assert "params.get('name')" in episode_page
    assert "window.frappe?.route_options?.name" in episode_page
    assert "canonicalizeHospitalisationEpisodeRoute" in episode_page
