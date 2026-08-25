from pathlib import Path
from types import SimpleNamespace
from unittest import TestCase
from unittest.mock import patch

import frappe

from vetedge.services import clinical_workspace, dispensary, registration_billing


ROOT = Path(__file__).resolve().parents[2]


def read(relative_path: str) -> str:
    return ROOT.joinpath(relative_path).read_text(encoding="utf-8")


class TestPhase5ConsultationContinuity(TestCase):
    def test_billing_core_defers_registration_payment_until_consultation_gate(self):
        patient = frappe._dict(
            name="VP-001",
            default_branch="Main",
            registration_status=registration_billing.AWAITING_PAYMENT_STATUS,
            registration_invoice="SINV-REG-001",
        )
        rule = registration_billing.RegistrationBillingRule(
            enabled=True,
            branch="Main",
            registration_item="REG-ITEM",
            registration_fee=5000,
            auto_create_invoice=True,
            require_payment_before_first_consultation=True,
        )

        with (
            patch.object(registration_billing.frappe.db, "get_value", return_value=patient),
            patch.object(registration_billing, "get_registration_rule", return_value=rule),
            patch.object(registration_billing, "is_first_consultation_for_patient", return_value=True),
            patch.object(registration_billing, "use_billing_core_for_registration", return_value=True),
            patch.object(registration_billing.frappe, "throw") as throw,
        ):
            registration_billing.validate_registration_payment_before_first_consultation("VP-001")

        throw.assert_not_called()

    def test_legacy_registration_gate_still_blocks_unpaid_first_consultation(self):
        patient = frappe._dict(
            name="VP-001",
            default_branch="Main",
            registration_status=registration_billing.AWAITING_PAYMENT_STATUS,
            registration_invoice="SINV-REG-001",
        )
        rule = registration_billing.RegistrationBillingRule(
            enabled=True,
            branch="Main",
            registration_item="REG-ITEM",
            registration_fee=5000,
            auto_create_invoice=True,
            require_payment_before_first_consultation=True,
        )
        invoice = SimpleNamespace(
            name="SINV-REG-001",
            docstatus=0,
            status="Draft",
            outstanding_amount=5000,
        )

        with (
            patch.object(registration_billing.frappe.db, "get_value", return_value=patient),
            patch.object(registration_billing, "get_registration_rule", return_value=rule),
            patch.object(registration_billing, "is_first_consultation_for_patient", return_value=True),
            patch.object(registration_billing, "use_billing_core_for_registration", return_value=False),
            patch.object(registration_billing, "get_active_registration_invoice_name", return_value=invoice.name),
            patch.object(registration_billing.frappe, "get_doc", return_value=invoice),
            patch.object(registration_billing, "update_patient_registration_payment_status"),
            patch.object(registration_billing.frappe, "throw", side_effect=frappe.ValidationError),
        ):
            self.assertRaises(
                frappe.ValidationError,
                registration_billing.validate_registration_payment_before_first_consultation,
                "VP-001",
            )

    def test_clinical_route_key_keeps_patient_scoped_new_consultations_distinct(self):
        content = read(
            "vetedge/veterinary/page/vetedge_clinical_workspace/vetedge_clinical_workspace.js"
        )

        assert "const patient = String(params.get('patient') || '').trim();" in content
        assert "patient," in content
        assert "`new:${patient || '-'}`" in content

    def test_mounted_clinical_route_reopens_new_patient_when_view_state_was_discarded(self):
        content = read(
            "vetedge/veterinary/page/vetedge_clinical_workspace/vetedge_clinical_workspace.js"
        )

        assert "function mountedClinicalStateMatchesRoute(view, requested)" in content
        assert "if (!view.detail?.open || view.detail?.name) return false;" in content
        assert "return String(view.form?.patient || '') === requested.patient;" in content
        assert "const stateMismatch = !mountedClinicalStateMatchesRoute(view, requested);" in content
        assert "const needsRouteSync = routeChanged || stateMismatch;" in content
        assert "else if (requested.isNew) await view.startNewConsultation?.();" in content

    def test_resource_center_drops_stale_new_patient_route_option_on_list_return(self):
        content = read(
            "vetedge/veterinary/page/vetedge_resource_center/vetedge_resource_center.js"
        )

        assert "function clearStalePatientCreateRouteOption()" in content
        assert "resource !== 'patients' || params.get('new') === '1'" in content
        assert "delete routeOptions.new;" in content
        assert content.index("clearStalePatientCreateRouteOption();") < content.index("wrapper.vue_app?.refresh")

    def test_billing_core_retains_registration_session_continuity_for_consultation(self):
        content = read("vetedge/services/billing_core.py")

        assert "find_registration_billing_session_for_consultation" in content
        assert 'if source_doctype == "Veterinary Consultation":' in content
        assert "registration_session = find_registration_billing_session_for_consultation(identity)" in content
        assert 'source_doctype == "Veterinary Consultation" and charge_doctype == "Veterinary Patient"' in content

    def test_clinical_patient_link_keeps_id_as_value_and_uses_readable_title(self):
        content = read(
            "vetedge/public/js/vetedge_clinical_workspace/VetEdgeClinicalWorkspace.vue"
        )

        assert ':model-value="form.patient"' in content
        assert ':selected-label="form.patient_label"' in content
        assert 'patient_label: ""' in content
        assert 'patient_label: values.patient_label || payload?.patient_label || values.patient || ""' in content
        assert 'this.form.patient_label = context?.patient?.label || context?.patient?.name || value;' in content
        assert 'active-route="/desk/vetedge-clinical-workspace"' in content
        assert "/app/vetedge-clinical-workspace" not in content

    def test_non_stock_treatment_does_not_require_dispensary_without_explicit_override(self):
        doc = frappe._dict(planned_treatments=[frappe._dict(item="SERVICE-001", treatment_type=None)])

        with (
            patch.object(dispensary, "get_dispensary_settings", return_value=SimpleNamespace(enabled=True)),
            patch.object(dispensary, "get_treatment_type_requires_dispensary", return_value=False),
            patch.object(dispensary, "get_treatment_item_defaults", return_value=None),
            patch.object(
                dispensary,
                "get_item_stock_profile",
                return_value=SimpleNamespace(is_stock_item=False),
            ),
        ):
            self.assertFalse(dispensary.consultation_requires_dispensary(doc))

    def test_disabled_dispensary_never_requires_dispensary(self):
        doc = frappe._dict(planned_treatments=[frappe._dict(item="MED-001")])

        with patch.object(
            dispensary,
            "get_dispensary_settings",
            return_value=SimpleNamespace(enabled=False),
        ):
            self.assertFalse(dispensary.consultation_requires_dispensary(doc))

    def test_pending_dispensary_action_is_hidden_when_not_required(self):
        doc = SimpleNamespace(status="In Progress", has_permission=lambda permission: True)

        with patch.object(clinical_workspace, "consultation_requires_dispensary", return_value=False):
            actions = clinical_workspace._status_actions(doc)

        self.assertNotIn("status:Pending Dispensary", [row["key"] for row in actions])

    def test_pending_dispensary_action_is_available_when_required(self):
        doc = SimpleNamespace(status="In Progress", has_permission=lambda permission: True)

        with patch.object(clinical_workspace, "consultation_requires_dispensary", return_value=True):
            actions = clinical_workspace._status_actions(doc)

        self.assertIn("status:Pending Dispensary", [row["key"] for row in actions])
