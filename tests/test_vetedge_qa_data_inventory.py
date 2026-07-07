from __future__ import annotations

import importlib.util
import subprocess
import sys
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPT_PATH = REPO_ROOT / "tools" / "vetedge_qa_data_inventory.py"


def load_inventory_tool():
	spec = importlib.util.spec_from_file_location("vetedge_qa_data_inventory", SCRIPT_PATH)
	module = importlib.util.module_from_spec(spec)
	assert spec.loader is not None
	sys.modules[spec.name] = module
	spec.loader.exec_module(module)
	return module


class VetEdgeQaDataInventoryTest(unittest.TestCase):
	@classmethod
	def setUpClass(cls):
		cls.tool = load_inventory_tool()

	def test_scenario_result_marks_found_with_samples_and_counts(self):
		definition = self.tool.ScenarioDefinition(
			"sample_case",
			"Sample Case",
			"Veterinary Consultation",
			"consultations",
		)

		result = self.tool.build_scenario_result(
			definition,
			["VCON-001", "VCON-002", "VCON-003"],
			include_counts=True,
			include_samples=True,
			sample_limit=2,
		)

		self.assertEqual(result.status, "found")
		self.assertEqual(result.candidate_count, 3)
		self.assertEqual(result.samples, ["VCON-001", "VCON-002"])
		self.assertIn("Candidate records for QA only", " ".join(result.notes))

	def test_scenario_result_marks_missing_without_records(self):
		definition = self.tool.ScenarioDefinition(
			"missing_case",
			"Missing Case",
			"Veterinary Lab Order",
			"lab",
		)

		result = self.tool.build_scenario_result(definition, [], include_counts=True, include_samples=True)

		self.assertEqual(result.status, "missing")
		self.assertEqual(result.candidate_count, 0)
		self.assertEqual(result.samples, [])

	def test_missing_optional_doctype_is_not_applicable(self):
		definition = self.tool.ScenarioDefinition(
			"support_journal_entry",
			"Journal Entry evidence",
			"Journal Entry",
			"erpnext_support",
		)

		result = self.tool.build_scenario_result(definition, [], doctype_exists=False, include_counts=True)

		self.assertEqual(result.status, "not_applicable")
		self.assertEqual(result.candidate_count, 0)
		self.assertIn("not installed", " ".join(result.notes))

	def test_report_shape_is_read_only_and_summarizes_statuses(self):
		found = self.tool.build_scenario_result(
			self.tool.ScenarioDefinition("found_case", "Found", "Veterinary Consultation", "consultations"),
			["VCON-001"],
		)
		missing = self.tool.build_scenario_result(
			self.tool.ScenarioDefinition("missing_case", "Missing", "Veterinary Lab Order", "lab"),
			[],
		)
		not_applicable = self.tool.build_scenario_result(
			self.tool.ScenarioDefinition("na_case", "N/A", "Journal Entry", "erpnext_support"),
			[],
			doctype_exists=False,
		)

		report = self.tool.build_report(
			"vetedge.local",
			[found, missing, not_applicable],
			generated_at="2026-07-07T00:00:00+00:00",
		)

		self.assertEqual(report["mode"], self.tool.MODE)
		self.assertEqual(report["site"], "vetedge.local")
		self.assertFalse(report["business_records_mutated"])
		self.assertEqual(report["destructive_operations"], [])
		self.assertEqual(report["summary"], {"found": 1, "missing": 1, "not_applicable": 1})
		self.assertIn("found_case", report["scenarios"])

	def test_inventory_contains_required_phase_10f_groups(self):
		groups = {definition.group for definition in self.tool.SCENARIOS}

		for group in (
			"consultations",
			"cancellation_resolutions",
			"lab",
			"vaccination",
			"hospitalisation",
			"grooming",
			"boarding",
			"appointments",
			"erpnext_support",
		):
			self.assertIn(group, groups)

	def test_negative_sample_limit_fails(self):
		result = subprocess.run(
			[
				sys.executable,
				str(SCRIPT_PATH),
				"--site",
				"vetedge.local",
				"--sample-limit",
				"-1",
			],
			check=False,
			capture_output=True,
			text=True,
		)

		self.assertNotEqual(result.returncode, 0)
		self.assertIn("--sample-limit must be non-negative", result.stderr)


if __name__ == "__main__":
	unittest.main()
