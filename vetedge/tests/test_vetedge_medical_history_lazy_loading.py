from pathlib import Path
from unittest import TestCase

REPO_ROOT = Path(__file__).resolve().parents[2]
BUNDLE = REPO_ROOT / "vetedge" / "public" / "js" / "veterinary_medical_history.bundle.js"
LOADER = REPO_ROOT / "vetedge" / "veterinary" / "page" / "veterinary_medical_history" / "veterinary_medical_history.js"
LEGACY_COMPONENT = REPO_ROOT / "vetedge" / "public" / "js" / "veterinary_medical_history" / "VeterinaryMedicalHistory.vue"
LAZY_SERVICE = REPO_ROOT / "vetedge" / "services" / "medical_history_lazy.py"
LEGACY_SERVICE = REPO_ROOT / "vetedge" / "services" / "medical_history.py"


class TestVetEdgeMedicalHistoryLazyLoading(TestCase):
	def read(self, path: Path) -> str:
		return path.read_text(encoding="utf-8")

	def test_edgesuite_bundle_loads_summary_section_and_single_trend(self):
		bundle = self.read(BUNDLE)

		self.assertIn("get_patient_medical_history_summary", bundle)
		self.assertIn("get_patient_medical_history_section", bundle)
		self.assertIn("get_patient_vitals_trend", bundle)
		self.assertIn("HISTORY_SECTION_LIMIT = 50", bundle)
		self.assertIn("TREND_LIMIT = 100", bundle)
		self.assertIn("ensureHistorySection", bundle)
		self.assertIn("ensureTrend", bundle)

	def test_edgesuite_load_does_not_call_legacy_full_history_endpoint(self):
		bundle = self.read(BUNDLE)
		legacy_component = self.read(LEGACY_COMPONENT)

		self.assertIn("get_patient_medical_history_view", legacy_component)
		self.assertNotIn("get_patient_medical_history_view", bundle)
		load_block = bundle[bundle.index("async load()") : bundle.index("async ensureHistorySection")]
		self.assertIn("SUMMARY_API", load_block)
		self.assertIn("Promise.all", load_block)
		self.assertIn("this.activeHistory", load_block)
		self.assertIn("this.activeTrend", load_block)

	def test_history_tabs_fetch_only_when_opened_and_cache_loaded_sections(self):
		bundle = self.read(BUNDLE)

		self.assertIn("async activeHistory(value)", bundle)
		self.assertIn("await this.ensureHistorySection(value)", bundle)
		self.assertIn("this.loadedHistorySections?.[section]", bundle)
		self.assertIn("this.loadedHistorySections = { ...this.loadedHistorySections, [section]: true }", bundle)
		self.assertIn("counter.textContent", bundle)
		self.assertIn(": '—'", bundle)

	def test_vitals_tabs_fetch_only_selected_trend_and_cache_it(self):
		bundle = self.read(BUNDLE)

		self.assertIn("async activeTrend(value)", bundle)
		self.assertIn("await this.ensureTrend(value)", bundle)
		self.assertIn("this.loadedTrends?.[fieldname]", bundle)
		self.assertIn("[fieldname]: response.message || []", bundle)

	def test_medical_history_reuses_lazy_instance_before_dom_reset(self):
		loader = self.read(LOADER)
		bundle = self.read(BUNDLE)

		reuse_index = loader.index("if (wrapper.vue_app?.refresh)")
		reset_index = loader.index("$(page.body).empty()")
		self.assertLess(reuse_index, reset_index)
		self.assertIn("VETEDGE_MEDICAL_HISTORY_REFRESH_MAX_AGE_MS = 15000", loader)
		self.assertIn("wrapper.vue_app.refresh({ maxAgeMs: VETEDGE_MEDICAL_HISTORY_REFRESH_MAX_AGE_MS })", loader)
		self.assertIn("async refresh(options = {})", bundle)
		self.assertIn("lastLazyLoadAt", bundle)
		self.assertIn("patientChanged", bundle)

	def test_lazy_service_preserves_medical_history_permissions_and_caps_sections(self):
		service = self.read(LAZY_SERVICE)

		self.assertIn("require_internal_user()", service)
		self.assertIn("can_access_medical_history", service)
		self.assertIn("validate_patient_context(patient)", service)
		self.assertIn("MEDICAL_HISTORY_SECTION_MAX_LIMIT = 100", service)
		self.assertIn("SECTION_READERS", service)
		self.assertNotIn("ignore_permissions", service)

	def test_legacy_full_endpoint_remains_available_for_backward_compatibility(self):
		legacy = self.read(LEGACY_SERVICE)

		self.assertIn("def get_patient_medical_history_view(", legacy)
		for section in ("consultations", "vitals", "diagnoses", "symptoms", "treatments", "labs", "vaccinations", "trends"):
			self.assertIn(f'\"{section}\"', legacy)

	def test_lazy_bundle_adds_no_background_polling(self):
		self.assertNotIn("setInterval(", self.read(BUNDLE))
		self.assertNotIn("setInterval(", self.read(LOADER))
