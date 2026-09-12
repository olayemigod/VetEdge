from __future__ import annotations

from pathlib import Path
from unittest import TestCase


ROOT = Path(__file__).resolve().parents[1]


class TestClinicalInlineMasterCreationContract(TestCase):
	def test_edgesuite_consultation_keeps_operational_add_buttons(self):
		vue = (ROOT / "public" / "js" / "vetedge_clinical_workspace" / "VetEdgeClinicalWorkspace.vue").read_text()

		self.assertIn('@click="addSymptom">Add Symptom</button>', vue)
		self.assertIn('@click="addDiagnosis">Add Diagnosis</button>', vue)
		self.assertIn('@click="addTreatment">Add Treatment</button>', vue)
		self.assertIn("selectClinicalMaster('symptom', 'symptoms'", vue)
		self.assertIn("selectClinicalMaster('diagnosis', 'diagnoses'", vue)
		self.assertIn('this._createSeed("treatment_item", item)', vue)
		self.assertIn("Create & Select", vue)

	def test_native_consultation_keeps_treatment_picker_safe_and_curated(self):
		js = (
			ROOT
			/ "veterinary"
			/ "doctype"
			/ "veterinary_consultation"
			/ "veterinary_consultation.js"
		).read_text()

		self.assertIn("vetedge.services.treatment_items.get_treatment_item_link_options", js)
		self.assertIn('treatment_grid?.update_docfield_property("item", "only_select", 1)', js)
		self.assertIn("configure_clinical_master_creation", js)
		self.assertNotIn("get_treatment_item_link_options_with_create", js)
		self.assertNotIn("show_treatment_item_create_dialog", js)

	def test_hospitalisation_clinical_item_search_is_separate_from_charge_item_search(self):
		vue = (ROOT / "public" / "js" / "vetedge_hospitalisation_episode" / "VetEdgeHospitalisationEpisode.vue").read_text()

		self.assertIn("optionSearch('clinical_item', query)", vue)
		self.assertIn("optionSearch('item', query)", vue)
		self.assertIn("saveTreatmentMaster", vue)
		self.assertIn("context: 'hospitalisation'", vue)

	def test_backend_does_not_mutate_accounting_documents(self):
		service = (ROOT / "services" / "clinical_master_creation.py").read_text()

		self.assertNotIn('get_doc("Sales Invoice"', service)
		self.assertNotIn("submit()", service)
		self.assertNotIn("cancel()", service)
