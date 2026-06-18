import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
CONSULTATION_JS = ROOT / "vetedge" / "veterinary" / "doctype" / "veterinary_consultation" / "veterinary_consultation.js"


class TestConsultationClientAssets(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.source = CONSULTATION_JS.read_text(encoding="utf-8")

    def test_medical_history_button_exists(self):
        self.assertIn("View Medical History", self.source)
        self.assertIn("show_medical_history_dialog", self.source)

    def test_medical_history_popup_uses_existing_backend(self):
        self.assertIn("vetedge.services.medical_history.get_patient_medical_history_view", self.source)
        self.assertIn("Veterinary Medical History", self.source)

    def test_medical_history_popup_handles_missing_patient(self):
        self.assertIn("Select a patient/animal before viewing medical history.", self.source)

    def test_medical_history_popup_is_read_only_and_sanitized(self):
        self.assertIn("sanitize_consultation_history_rich_text", self.source)
        self.assertIn("script, style, iframe, object, embed, link, meta", self.source)
        self.assertNotIn("frappe.set_route(\"Form\", \"Veterinary Medical History\"", self.source)

    def test_assessment_precedes_treatment_plan_in_popup(self):
        self.assertLess(
            self.source.index("history_rich_block(__(\"Assessment\")"),
            self.source.index("history_treatment_plan_block(row)"),
        )


if __name__ == "__main__":
    unittest.main()
