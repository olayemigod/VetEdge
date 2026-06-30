from __future__ import annotations

import csv
import importlib.util
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPT_PATH = REPO_ROOT / "tools" / "vetedge_staging_review_package.py"


def load_review_tool():
	spec = importlib.util.spec_from_file_location("vetedge_staging_review_package", SCRIPT_PATH)
	module = importlib.util.module_from_spec(spec)
	assert spec.loader is not None
	sys.modules[spec.name] = module
	spec.loader.exec_module(module)
	return module


def write_json(path: Path, payload: object) -> None:
	path.parent.mkdir(parents=True, exist_ok=True)
	path.write_text(json.dumps(payload, sort_keys=True), encoding="utf-8")


class VetEdgeStagingReviewPackageTest(unittest.TestCase):
	@classmethod
	def setUpClass(cls):
		cls.tool = load_review_tool()

	def fixture_dirs(self, root: Path) -> tuple[Path, Path, Path, Path]:
		audit = root / "audit.json"
		package = root / "package"
		rehearsal = root / "rehearsal"
		output = root / "review"
		write_json(
			audit,
			{
				"category_counts": {"directly_portable": 1, "requires_manual_review": 2},
				"doctypes": [
					{"doctype": "Veterinary Patient", "category": "directly_portable", "record_count": 3},
					{"doctype": "Patch Log", "category": "dangerous_do_not_auto_migrate", "record_count": 9},
					{"doctype": "Email Template", "category": "requires_manual_review", "record_count": 2},
				],
			},
		)
		write_json(package / "manifest.json", {"mode": "manifest_templates_samples_only", "doctype_file_counts": {"directly_portable": 1}})
		write_json(
			rehearsal / "rehearsal_summary.json",
			{
				"allowed_sample_doctype_count": 1,
				"excluded_doctype_count": 1,
				"business_data_mutated": False,
				"import_behavior_included": False,
			},
		)
		write_json(rehearsal / "redaction_report.json", {"count": 2, "redactions": [{"fieldname": "owner_email"}]})
		write_json(
			rehearsal / "excluded_doctypes.json",
			[{"doctype": "Patch Log", "category": "dangerous_do_not_auto_migrate", "reason": "Patch lineage"}],
		)
		write_json(
			rehearsal / "validation_warnings.json",
			{
				"warnings": [
					'Veterinary Hospitalisation fell back to name-only sampling because metadata referenced "activities_tab", which is not queryable as a column.',
					"Veterinary License Profile and Veterinary Settings could not be sampled as row tables in this context.",
				]
			},
		)
		(rehearsal / "samples").mkdir(parents=True)
		(rehearsal / "samples" / "Veterinary Patient.jsonl").write_text('{"name":"VP-001"}\n', encoding="utf-8")
		return audit, package, rehearsal, output

	def test_review_package_can_be_generated_from_fixture_inputs(self):
		with tempfile.TemporaryDirectory() as tempdir:
			audit, package, rehearsal, output = self.fixture_dirs(Path(tempdir))
			summary = self.tool.generate_review_package(audit, package, rehearsal, output)

			expected = {
				"README.md",
				"review_checklist.md",
				"reconciliation_summary.json",
				"reconciliation_matrix.csv",
				"warnings.md",
				"manual_review_items.csv",
				"dangerous_exclusions.csv",
				"cutover_questions.md",
			}
			self.assertEqual({path.name for path in output.iterdir()}, expected)
			self.assertEqual(summary["redaction_count"], 2)

	def test_readme_contains_staging_notice(self):
		with tempfile.TemporaryDirectory() as tempdir:
			audit, package, rehearsal, output = self.fixture_dirs(Path(tempdir))
			self.tool.generate_review_package(audit, package, rehearsal, output)

			readme = (output / "README.md").read_text(encoding="utf-8")
			self.assertIn("STAGING REVIEW ONLY — NOT AN IMPORT PACKAGE", readme)
			self.assertIn("No import behavior is included", readme)

	def test_reconciliation_matrix_includes_dangerous_exclusions(self):
		with tempfile.TemporaryDirectory() as tempdir:
			audit, package, rehearsal, output = self.fixture_dirs(Path(tempdir))
			self.tool.generate_review_package(audit, package, rehearsal, output)

			with (output / "reconciliation_matrix.csv").open(newline="", encoding="utf-8") as handle:
				rows = list(csv.DictReader(handle))
			patch_row = next(row for row in rows if row["doctype"] == "Patch Log")
			self.assertEqual(patch_row["excluded"], "true")
			self.assertEqual(patch_row["risk_level"], "high")

	def test_phase_2f_warnings_are_carried_forward(self):
		with tempfile.TemporaryDirectory() as tempdir:
			audit, package, rehearsal, output = self.fixture_dirs(Path(tempdir))
			self.tool.generate_review_package(audit, package, rehearsal, output)

			warnings = (output / "warnings.md").read_text(encoding="utf-8")
			self.assertIn("activities_tab", warnings)
			self.assertIn("Veterinary License Profile", warnings)

	def test_manual_review_items_are_included(self):
		with tempfile.TemporaryDirectory() as tempdir:
			audit, package, rehearsal, output = self.fixture_dirs(Path(tempdir))
			self.tool.generate_review_package(audit, package, rehearsal, output)

			with (output / "manual_review_items.csv").open(newline="", encoding="utf-8") as handle:
				rows = list(csv.DictReader(handle))
			areas = {row["area"] for row in rows}
			self.assertIn("email templates", areas)
			self.assertIn("CoreEdge/product references", areas)

	def test_no_import_scripts_sql_or_shell_files_are_generated(self):
		with tempfile.TemporaryDirectory() as tempdir:
			audit, package, rehearsal, output = self.fixture_dirs(Path(tempdir))
			self.tool.generate_review_package(audit, package, rehearsal, output)

			self.assertEqual(self.tool.validate_no_forbidden_outputs(output), [])

	def test_missing_input_files_fail_safely(self):
		result = subprocess.run(
			[
				sys.executable,
				str(SCRIPT_PATH),
				"--audit-json",
				"/tmp/missing-audit.json",
				"--migration-package-dir",
				"/tmp/missing-package",
				"--rehearsal-dir",
				"/tmp/missing-rehearsal",
				"--output-dir",
				"/tmp/review",
			],
			check=False,
			capture_output=True,
			text=True,
		)

		self.assertNotEqual(result.returncode, 0)
		self.assertIn("Required input file not found", result.stderr)

	def test_write_mode_fails_intentionally(self):
		result = subprocess.run(
			[
				sys.executable,
				str(SCRIPT_PATH),
				"--audit-json",
				"/tmp/missing-audit.json",
				"--migration-package-dir",
				"/tmp/missing-package",
				"--rehearsal-dir",
				"/tmp/missing-rehearsal",
				"--output-dir",
				"/tmp/review",
				"--write",
			],
			check=False,
			capture_output=True,
			text=True,
		)

		self.assertNotEqual(result.returncode, 0)
		self.assertIn("write mode intentionally disabled for staging review package", result.stderr)


if __name__ == "__main__":
	unittest.main()
