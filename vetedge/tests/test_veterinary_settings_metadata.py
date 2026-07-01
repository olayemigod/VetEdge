import json
import unittest
from pathlib import Path


SETTINGS_JSON = (
    Path(__file__).resolve().parents[1]
    / "veterinary"
    / "doctype"
    / "veterinary_settings"
    / "veterinary_settings.json"
)


class TestVeterinarySettingsMetadata(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.data = json.loads(SETTINGS_JSON.read_text())
        cls.fields = {field["fieldname"]: field for field in cls.data["fields"]}

    def test_json_field_inventory_is_consistent(self):
        field_order = self.data["field_order"]

        self.assertEqual(len(field_order), len(set(field_order)))
        self.assertEqual(set(field_order), set(self.fields))
        self.assertEqual(len(self.data["fields"]), len(self.fields))

    def test_requested_section_labels_exist(self):
        section_labels = {
            field.get("label")
            for field in self.data["fields"]
            if field.get("fieldtype") == "Section Break"
        }

        expected_sections = {
            "Clinic & Defaults",
            "Consultation & Clinical Workflow",
            "Appointments & Queue",
            "Billing & Payment",
            "Pharmacy, Dispensary & Stock",
            "Hospitalisation",
            "Grooming & Boarding",
            "Lab Results",
            "General Notification Settings",
            "Email Notification Settings",
            "SMS Notification Settings",
            "WhatsApp Notification Settings",
            "Reports & Dashboards",
            "Advanced / System",
        }
        self.assertTrue(expected_sections.issubset(section_labels))

    def test_top_level_section_order(self):
        expected_order = [
            "general_section",
            "consultation_section",
            "lab_results_section",
            "appointments_section",
            "billing_core_section",
            "treatment_inventory_section",
            "hospitalisation_section",
            "pet_services_section",
            "notifications_section",
            "email_notification_settings_section",
            "sms_notification_settings_section",
            "whatsapp_notification_settings_section",
            "advanced_reports_section",
            "security_branch_section",
        ]
        field_order = self.data["field_order"]

        actual_indexes = [field_order.index(fieldname) for fieldname in expected_order]
        self.assertEqual(actual_indexes, sorted(actual_indexes))

    def test_key_settings_fields_remain_present(self):
        expected_fields = {
            "auto_add_default_consultation_billing_item",
            "allow_editing_consultation_billing_item",
            "consultation_payment_gate",
            "enable_veterinary_hospitalisation",
            "hospitalisation_payment_gate",
            "hospitalisation_daily_charge_settings",
            "enable_notifications",
            "enable_email_notifications",
            "enable_sms_notifications",
            "enable_whatsapp_notifications",
            "enable_stock_expiry_monitor",
            "expiry_reminder_days",
            "enforce_strict_expiry_control",
            "enable_dispensary_flow",
            "enable_billing_sessions",
            "default_payment_gate_mode",
            "allow_doctor_lab_result_entry",
            "allow_doctor_lab_result_upload",
            "require_lab_result_review",
            "allow_lab_result_edit_after_review",
        }

        self.assertTrue(expected_fields.issubset(self.fields))

    def test_guardrail_defaults_are_unchanged(self):
        expected_defaults = {
            "consultation_payment_gate": "Full Payment Required",
            "hospitalisation_payment_gate": "Partial Payment Gate",
            "expiry_reminder_days": "30,60,90",
            "enable_internal_expiry_notifications": "1",
            "enforce_cost_center_on_billing": "1",
            "enable_billing_sessions": "1",
            "payment_backend_mode": "stub",
            "notification_backend_mode": "local",
            "enable_appointment_sms_notifications": "1",
            "auto_add_default_consultation_billing_item": "1",
            "allow_editing_consultation_billing_item": "1",
            "allow_doctor_lab_result_entry": "1",
            "allow_doctor_lab_result_upload": "0",
            "require_lab_result_review": "1",
            "allow_lab_result_edit_after_review": "0",
        }

        for fieldname, expected_default in expected_defaults.items():
            self.assertEqual(self.fields[fieldname].get("default"), expected_default)

    def test_larger_sections_are_collapsible(self):
        collapsible_sections = {
            "registration_billing_section",
            "vitals_section",
            "vaccination_section",
            "lab_results_section",
            "appointments_section",
            "billing_core_section",
            "treatment_inventory_section",
            "hospitalisation_section",
            "pet_services_section",
            "notifications_section",
            "email_notification_settings_section",
            "sms_notification_settings_section",
            "whatsapp_notification_settings_section",
            "advanced_reports_section",
            "security_branch_section",
        }

        for fieldname in collapsible_sections:
            self.assertEqual(self.fields[fieldname].get("collapsible"), 1)

    def test_common_sections_stay_open(self):
        open_sections = {
            "general_section",
            "consultation_section",
        }

        for fieldname in open_sections:
            self.assertNotEqual(self.fields[fieldname].get("collapsible"), 1)

    def test_notification_backend_mode_remains_documented(self):
        field = self.fields["notification_backend_mode"]

        self.assertEqual(field.get("label"), "Notification Backend Mode")
        self.assertIn("local", field.get("options", ""))
        self.assertIn("processedge_core", field.get("options", ""))
        self.assertIn("provider-agnostic backend", field.get("description", "").lower())


if __name__ == "__main__":
    unittest.main()
