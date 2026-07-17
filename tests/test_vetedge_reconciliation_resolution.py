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
SCRIPT_PATH = REPO_ROOT / "tools" / "vetedge_reconciliation_resolution.py"


def load_resolution_tool():
	spec = importlib.util.spec_from_file_location("vetedge_reconciliation_resolution", SCRIPT_PATH)
	module = importlib.util.module_from_spec(spec)
	assert spec.loader is not None
	sys.modules[spec.name] = module
	spec.loader.exec_module(module)
	return module


def write_json(path: Path, payload: object) -> None:
	path.parent.mkdir(parents=True, exist_ok=True)
	path.write_text(json.dumps(payload, sort_keys=True), encoding="utf-8")


def write_csv(path: Path, columns: list[str], rows: list[dict[str, str]]) -> None:
	path.parent.mkdir(parents=True, exist_ok=True)
	with path.open("w", newline="", encoding="utf-8") as handle:
		writer = csv.DictWriter(handle, fieldnames=columns)
		writer.writeheader()
		for row in rows:
			writer.writerow(row)


class VetEdgeReconciliationResolutionTest(unittest.TestCase):
	@classmethod
	def setUpClass(cls):
		cls.tool = load_resolution_tool()

	def fixture_review_package(self, root: Path) -> Path:
		review = root / "review"
		write_json(
			review / "reconciliation_summary.json",
			{"readiness_status": "needs_review", "readiness_score": 0},
		)
		write_csv(
			review / "reconciliation_matrix.csv",
			["area", "source", "category", "doctype", "source_count", "sample_count", "excluded", "redacted", "risk_level", "review_required", "reviewer_notes"],
			[
				{"area": "roles/permissions", "source": "fixture", "category": "requires_manual_review", "doctype": "Role", "source_count": "2", "sample_count": "0", "excluded": "true", "redacted": "false", "risk_level": "high", "review_required": "true", "reviewer_notes": "VetEdge Doctor"},
				{"area": "email templates", "source": "fixture", "category": "requires_manual_review", "doctype": "Email Template", "source_count": "1", "sample_count": "0", "excluded": "false", "redacted": "false", "risk_level": "medium", "review_required": "true", "reviewer_notes": ""},
			],
		)
		write_csv(
			review / "manual_review_items.csv",
			["area", "reason", "reviewer_notes"],
			[
				{"area": "email templates", "reason": "review branding", "reviewer_notes": ""},
				{"area": "CoreEdge/product references", "reason": "platform mapping", "reviewer_notes": ""},
				{"area": "roles", "reason": "role mapping", "reviewer_notes": ""},
			],
		)
		write_csv(
			review / "dangerous_exclusions.csv",
			["doctype", "category", "reason", "reviewer_notes"],
			[
				{"doctype": "Patch Log", "category": "dangerous_do_not_auto_migrate", "reason": "patch lineage", "reviewer_notes": ""},
				{"doctype": "GL Entry", "category": "baseline_dangerous_or_dependency", "reason": "ledger", "reviewer_notes": ""},
			],
		)
		(review / "warnings.md").write_text(
			'activities_tab is not queryable as a column.\nVeterinary License Profile could not be sampled.\n',
			encoding="utf-8",
		)
		(review / "cutover_questions.md").write_text("- [ ] Which client/site is being migrated?\n", encoding="utf-8")
		return review

	def test_resolution_package_is_generated_from_fixture_review_inputs(self):
		with tempfile.TemporaryDirectory() as tempdir:
			review = self.fixture_review_package(Path(tempdir))
			output = Path(tempdir) / "resolution"
			summary = self.tool.generate_resolution(review, output)

			expected = {
				"resolution_summary.json",
				"role_permission_mapping.md",
				"portal_route_mapping.md",
				"email_branding_review.md",
				"coreedge_mapping.md",
				"hospitalisation_metadata_review.md",
				"manual_review_resolution.csv",
				"future_import_contract_draft.md",
				"unresolved_blockers.md",
			}
			self.assertEqual({path.name for path in output.iterdir()}, expected)
			self.assertFalse(summary["import_behavior_created"])
			self.assertFalse(summary["clone_generated"])

	def test_role_mapping_file_is_generated(self):
		with tempfile.TemporaryDirectory() as tempdir:
			review = self.fixture_review_package(Path(tempdir))
			output = Path(tempdir) / "resolution"
			self.tool.generate_resolution(review, output)

			text = (output / "role_permission_mapping.md").read_text(encoding="utf-8")
			self.assertIn("VetEdge Doctor", text)
			self.assertIn("Veterinary Doctor", text)

	def test_portal_route_mapping_file_is_generated(self):
		with tempfile.TemporaryDirectory() as tempdir:
			review = self.fixture_review_package(Path(tempdir))
			output = Path(tempdir) / "resolution"
			self.tool.generate_resolution(review, output)

			text = (output / "portal_route_mapping.md").read_text(encoding="utf-8")
			self.assertIn("/vetedge_portal", text)
			self.assertIn("/veterinary_portal", text)

	def test_coreedge_mapping_file_is_generated(self):
		with tempfile.TemporaryDirectory() as tempdir:
			review = self.fixture_review_package(Path(tempdir))
			output = Path(tempdir) / "resolution"
			self.tool.generate_resolution(review, output)

			text = (output / "coreedge_mapping.md").read_text(encoding="utf-8")
			self.assertIn("product_family", text)
			self.assertIn("veterinary_practice", text)

	def test_hospitalisation_warning_is_carried_into_metadata_review(self):
		with tempfile.TemporaryDirectory() as tempdir:
			review = self.fixture_review_package(Path(tempdir))
			output = Path(tempdir) / "resolution"
			self.tool.generate_resolution(review, output)

			text = (output / "hospitalisation_metadata_review.md").read_text(encoding="utf-8")
			self.assertIn("activities_tab", text)
			self.assertIn("fix sampler metadata filtering", text)

	def test_dangerous_exclusions_remain_excluded_and_contract_is_non_executable(self):
		with tempfile.TemporaryDirectory() as tempdir:
			review = self.fixture_review_package(Path(tempdir))
			output = Path(tempdir) / "resolution"
			self.tool.generate_resolution(review, output)

			contract = (output / "future_import_contract_draft.md").read_text(encoding="utf-8")
			self.assertIn("non-executable", contract)
			self.assertIn("Patch Log", contract)
			self.assertIn("GL Entry", contract)
			self.assertEqual(self.tool.validate_no_forbidden_outputs(output), [])

	def test_write_mode_fails_intentionally(self):
		result = subprocess.run(
			[
				sys.executable,
				str(SCRIPT_PATH),
				"--review-package-dir",
				"/tmp/missing-review",
				"--output-dir",
				"/tmp/resolution",
				"--write",
			],
			check=False,
			capture_output=True,
			text=True,
		)

		self.assertNotEqual(result.returncode, 0)
		self.assertIn("write mode intentionally disabled for reconciliation resolution", result.stderr)


if __name__ == "__main__":
	unittest.main()
