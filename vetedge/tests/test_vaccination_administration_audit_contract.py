from pathlib import Path
from unittest import TestCase


APP_ROOT = Path(__file__).resolve().parents[1]
CONTROLLER = APP_ROOT / "veterinary" / "doctype" / "veterinary_vaccination_record" / "veterinary_vaccination_record.py"
CLIENT_SCRIPT = APP_ROOT / "veterinary" / "doctype" / "veterinary_vaccination_record" / "veterinary_vaccination_record.js"


class VaccinationAdministrationAuditContractTests(TestCase):
	def test_first_administration_stamps_actual_user_and_server_time(self):
		source = CONTROLLER.read_text(encoding="utf-8")

		self.assertIn("def _stamp_administration_audit_fields(doc) -> None:", source)
		self.assertIn('if doc.get("status") != "Administered":', source)
		self.assertIn('if previous and previous.get("status") == "Administered":', source)
		self.assertIn("doc.administered_by = get_current_user()", source)
		self.assertIn("doc.administered_on = now_datetime()", source)

	def test_administration_stamp_runs_before_general_vaccination_validation(self):
		source = CONTROLLER.read_text(encoding="utf-8")
		stamp_call = source.index("\t\t_stamp_administration_audit_fields(self)")
		validation_call = source.index("\t\tvalidate_vaccination_record(self)")

		self.assertLess(stamp_call, validation_call)

	def test_native_form_treats_administration_fields_as_system_controlled(self):
		source = CLIENT_SCRIPT.read_text(encoding="utf-8")

		self.assertIn('frm.set_df_property("administered_by", "read_only", 1);', source)
		self.assertIn('frm.set_df_property("administered_on", "read_only", 1);', source)
		self.assertIn("Automatically recorded from the authorised user", source)
		self.assertIn("Automatically recorded using the server time", source)
