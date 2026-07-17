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
SCRIPT_PATH = REPO_ROOT / "tools" / "vetedge_distribution_identity_validator.py"


def load_validator_tool():
	spec = importlib.util.spec_from_file_location("vetedge_distribution_identity_validator", SCRIPT_PATH)
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


class VetEdgeDistributionIdentityValidatorTest(unittest.TestCase):
	@classmethod
	def setUpClass(cls):
		cls.tool = load_validator_tool()

	def fixture_inputs(self, root: Path) -> tuple[Path, Path, Path, Path]:
		source = root / "source"
		contract = root / "contract"
		go_no_go = root / "go_no_go"
		clone_audit = root / "clone_audit.json"
		(source / "vetedge" / "config" / "desktop_icon").mkdir(parents=True)
		(source / "vetedge" / "config" / "workspace_sidebar").mkdir(parents=True)
		(source / "vetedge" / "veterinary" / "doctype" / "veterinary_patient").mkdir(parents=True)
		(source / "vetedge" / "veterinary" / "report" / "stock_expiry_status").mkdir(parents=True)
		(source / "vetedge" / "patches").mkdir(parents=True)
		(source / "hooks.py").write_text("app_name = 'vetedge'\napp_title = 'VetEdge'\n", encoding="utf-8")
		(source / "pyproject.toml").write_text("[project]\nname = 'vetedge'\n", encoding="utf-8")
		(source / "vetedge" / "modules.txt").write_text("VetEdge\n", encoding="utf-8")
		(source / "vetedge" / "config" / "desktop_icon" / "vetedge.json").write_text('{"module_name":"VetEdge"}\n', encoding="utf-8")
		(source / "vetedge" / "config" / "workspace_sidebar" / "vetedge.json").write_text('{"title":"Veterinary Records","route":"/desk/vetedge-executive-dashboard"}\n', encoding="utf-8")
		(source / "vetedge" / "veterinary" / "doctype" / "veterinary_patient" / "veterinary_patient.json").write_text('{"name":"Veterinary Patient","module":"VetEdge"}\n', encoding="utf-8")
		(source / "vetedge" / "veterinary" / "report" / "stock_expiry_status" / "stock_expiry_status.json").write_text('{"report_name":"Stock Expiry Status","module":"VetEdge"}\n', encoding="utf-8")
		(source / "vetedge" / "patches.txt").write_text("vetedge.patches.example\n", encoding="utf-8")

		write_json(
			contract / "blocker_resolution_summary.json",
			{
				"coreedge_contract_defined": True,
				"doctype_identity_policy_defined": True,
				"clone_generation_write_allowed": False,
				"migration_rehearsal_allowed": False,
			},
		)
		(contract / "coreedge_distribution_contract.md").write_text(
			"product_family = veterinary_practice\n"
			"distribution = vetedge\n"
			"distribution = veterinary\n"
			"Separate VetEdge SaaS activation record/path.\n"
			"distribution-aware feature gates\n"
			"Stock Expiry\nFinancial Dashboard\nHospitalisation Dashboard\n"
			"SMS\nEmail\nWhatsApp\nEdgeFinder\nWallet\n",
			encoding="utf-8",
		)
		(contract / "doctype_identity_policy.md").write_text(
			"DocType JSON identity fields must not be treated as client data migration payload.\n"
			"source-tree clone generation process\n"
			"Automatic migration of DocType JSON identity fields remains blocked\n"
			"Patch Log\n",
			encoding="utf-8",
		)
		write_csv(
			contract / "remaining_no_go_items.csv",
			["item_id", "area", "source_blocker", "policy_decision", "status", "still_blocks_migration_rehearsal", "notes"],
			[{"item_id": "NO-GO-001", "area": "CoreEdge/product references", "source_blocker": "", "policy_decision": "", "status": "policy_resolved_code_deferred", "still_blocks_migration_rehearsal": "yes", "notes": ""}],
		)
		write_json(go_no_go / "go_no_go_summary.json", {"migration_allowed": False})
		write_json(
			clone_audit,
			{
				"mode": "dry_run",
				"write_disabled_message": "write mode intentionally disabled for Phase 2A",
				"reference_category_counts": {
					"unknown": {},
					"safe_transform": {"app_source_identifier_reference": 2},
					"dangerous": {"doctype_json_identity": 1},
				},
			},
		)
		return source, contract, go_no_go, clone_audit

	def test_validator_package_is_generated_from_fixture_inputs(self):
		with tempfile.TemporaryDirectory() as tempdir:
			source, contract, go_no_go, clone_audit = self.fixture_inputs(Path(tempdir))
			output = Path(tempdir) / "validator"
			summary = self.tool.generate_distribution_identity_validator(source, contract, go_no_go, output, clone_audit)

			expected = {
				"validator_summary.json",
				"coreedge_distribution_readiness.md",
				"doctype_identity_readiness.md",
				"source_metadata_findings.csv",
				"future_clone_requirements.md",
				"coreedge_gap_register.csv",
				"doctype_identity_gap_register.csv",
				"phase_2k_recommendation.md",
			}
			self.assertEqual({path.name for path in output.iterdir()}, expected)
			self.assertFalse(summary["clone_generated"])
			self.assertFalse(summary["import_behavior_created"])

	def test_coreedge_distribution_contract_rules_are_detected(self):
		with tempfile.TemporaryDirectory() as tempdir:
			source, contract, go_no_go, clone_audit = self.fixture_inputs(Path(tempdir))
			summary = self.tool.generate_distribution_identity_validator(source, contract, go_no_go, Path(tempdir) / "validator", clone_audit)

			self.assertTrue(summary["coreedge_contract_valid"])
			self.assertTrue(summary["coreedge_contract_rules"]["product_family"])
			self.assertTrue(summary["coreedge_contract_rules"]["veterinary_distribution"])

	def test_doctype_identity_policy_blocks_business_data_migration(self):
		with tempfile.TemporaryDirectory() as tempdir:
			source, contract, go_no_go, clone_audit = self.fixture_inputs(Path(tempdir))
			output = Path(tempdir) / "validator"
			summary = self.tool.generate_distribution_identity_validator(source, contract, go_no_go, output, clone_audit)
			text = (output / "doctype_identity_readiness.md").read_text(encoding="utf-8")

			self.assertTrue(summary["doctype_identity_policy_valid"])
			self.assertIn("blocked from automatic business-data migration", text)

	def test_clone_audit_unknown_count_zero_is_accepted(self):
		with tempfile.TemporaryDirectory() as tempdir:
			source, contract, go_no_go, clone_audit = self.fixture_inputs(Path(tempdir))
			summary = self.tool.generate_distribution_identity_validator(source, contract, go_no_go, Path(tempdir) / "validator", clone_audit)

			self.assertEqual(summary["clone_audit"]["unknown_count"], 0)
			self.assertTrue(summary["clone_audit_unknown_count_accepted"])

	def test_safe_transform_is_not_treated_as_write_approval(self):
		with tempfile.TemporaryDirectory() as tempdir:
			source, contract, go_no_go, clone_audit = self.fixture_inputs(Path(tempdir))
			summary = self.tool.generate_distribution_identity_validator(source, contract, go_no_go, Path(tempdir) / "validator", clone_audit)

			self.assertFalse(summary["safe_transform_is_write_approval"])
			self.assertTrue(summary["clone_write_mode_blocked"])

	def test_coreedge_gaps_are_reported(self):
		with tempfile.TemporaryDirectory() as tempdir:
			source, contract, go_no_go, clone_audit = self.fixture_inputs(Path(tempdir))
			output = Path(tempdir) / "validator"
			summary = self.tool.generate_distribution_identity_validator(source, contract, go_no_go, output, clone_audit)
			text = (output / "coreedge_gap_register.csv").read_text(encoding="utf-8")

			self.assertGreaterEqual(summary["coreedge_gap_count"], 5)
			self.assertIn("product_family implementation not yet validated", text)

	def test_doctype_identity_gaps_are_reported(self):
		with tempfile.TemporaryDirectory() as tempdir:
			source, contract, go_no_go, clone_audit = self.fixture_inputs(Path(tempdir))
			output = Path(tempdir) / "validator"
			summary = self.tool.generate_distribution_identity_validator(source, contract, go_no_go, output, clone_audit)
			text = (output / "doctype_identity_gap_register.csv").read_text(encoding="utf-8")

			self.assertGreaterEqual(summary["doctype_identity_gap_count"], 5)
			self.assertIn("DocType JSON identity fields blocked from business migration", text)

	def test_no_sql_shell_import_restore_or_migrate_scripts_are_generated(self):
		with tempfile.TemporaryDirectory() as tempdir:
			source, contract, go_no_go, clone_audit = self.fixture_inputs(Path(tempdir))
			output = Path(tempdir) / "validator"
			self.tool.generate_distribution_identity_validator(source, contract, go_no_go, output, clone_audit)

			self.assertEqual(self.tool.validate_no_forbidden_outputs(output), [])

	def test_no_clone_generation_output_is_created(self):
		with tempfile.TemporaryDirectory() as tempdir:
			source, contract, go_no_go, clone_audit = self.fixture_inputs(Path(tempdir))
			output = Path(tempdir) / "validator"
			self.tool.generate_distribution_identity_validator(source, contract, go_no_go, output, clone_audit)

			self.assertFalse((output / "veterinary").exists())
			self.assertFalse((Path(tempdir) / "veterinary").exists())

	def test_write_mode_fails_intentionally(self):
		result = subprocess.run(
			[
				sys.executable,
				str(SCRIPT_PATH),
				"--source-dir",
				"/tmp/missing-source",
				"--blocker-contract-dir",
				"/tmp/missing-contract",
				"--go-no-go-dir",
				"/tmp/missing-go-no-go",
				"--output-dir",
				"/tmp/validator",
				"--write",
			],
			check=False,
			capture_output=True,
			text=True,
		)

		self.assertNotEqual(result.returncode, 0)
		self.assertIn("write mode intentionally disabled for distribution identity validator", result.stderr)


if __name__ == "__main__":
	unittest.main()
