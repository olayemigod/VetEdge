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
SCRIPT_PATH = REPO_ROOT / "tools" / "vetedge_blocker_resolution_contract.py"


def load_contract_tool():
	spec = importlib.util.spec_from_file_location("vetedge_blocker_resolution_contract", SCRIPT_PATH)
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


class VetEdgeBlockerResolutionContractTest(unittest.TestCase):
	@classmethod
	def setUpClass(cls):
		cls.tool = load_contract_tool()

	def fixture_inputs(self, root: Path) -> tuple[Path, Path, Path]:
		go_no_go = root / "go_no_go"
		resolution = root / "resolution"
		clone_audit = root / "clone_audit.json"
		write_json(
			go_no_go / "go_no_go_summary.json",
			{
				"migration_allowed": False,
				"clone_generated": False,
				"import_behavior_created": False,
				"business_data_mutated": False,
			},
		)
		write_csv(
			go_no_go / "blockers_register.csv",
			[
				"blocker_id",
				"area",
				"description",
				"source_file",
				"severity",
				"required_decision",
				"owner",
				"status",
				"target_resolution",
				"notes",
			],
			[
				{
					"blocker_id": "BLK-001",
					"area": "CoreEdge/product references",
					"description": "CoreEdge/product references need platform decision.",
					"source_file": "coreedge_mapping.md",
					"severity": "high",
					"required_decision": "Approve distribution mapping.",
					"owner": "CoreEdge/platform owner",
					"status": "open",
					"target_resolution": "",
					"notes": "",
				},
				{
					"blocker_id": "BLK-002",
					"area": "DocType JSON identity fields",
					"description": "DocType JSON identity fields remain blocked from automatic migration.",
					"source_file": "future_import_contract_draft.md",
					"severity": "high",
					"required_decision": "Block system identity migration.",
					"owner": "Technical lead",
					"status": "open",
					"target_resolution": "",
					"notes": "",
				},
			],
		)
		write_csv(
			go_no_go / "risk_register.csv",
			["risk_id", "area", "risk", "impact", "likelihood", "mitigation", "owner", "status"],
			[{"risk_id": "RISK-001", "area": "CoreEdge", "risk": "activation mismatch", "impact": "high", "likelihood": "medium", "mitigation": "", "owner": "", "status": "open"}],
		)
		(go_no_go / "required_decisions.md").write_text("# Required Decisions\n", encoding="utf-8")
		(resolution / "coreedge_mapping.md").parent.mkdir(parents=True, exist_ok=True)
		(resolution / "coreedge_mapping.md").write_text("product_family = veterinary_practice\n", encoding="utf-8")
		(resolution / "future_import_contract_draft.md").write_text("non-executable\n", encoding="utf-8")
		write_json(clone_audit, {"category_counts": {"unknown": 0}, "unknown_threshold": 0})
		return go_no_go, resolution, clone_audit

	def test_blocker_resolution_package_is_generated_from_fixture_inputs(self):
		with tempfile.TemporaryDirectory() as tempdir:
			go_no_go, resolution, clone_audit = self.fixture_inputs(Path(tempdir))
			output = Path(tempdir) / "contract"
			summary = self.tool.generate_blocker_resolution_contract(go_no_go, resolution, output, clone_audit)

			expected = {
				"blocker_resolution_summary.json",
				"coreedge_distribution_contract.md",
				"doctype_identity_policy.md",
				"clone_generation_policy.md",
				"migration_policy.md",
				"app_lineage_policy.md",
				"role_route_branding_policy.md",
				"remaining_no_go_items.csv",
				"phase_2j_signoff.md",
			}
			self.assertEqual({path.name for path in output.iterdir()}, expected)
			self.assertFalse(summary["clone_generated"])
			self.assertFalse(summary["import_behavior_created"])
			self.assertFalse(summary["business_data_mutated"])

	def test_coreedge_distribution_contract_includes_product_family_and_distribution_rules(self):
		with tempfile.TemporaryDirectory() as tempdir:
			go_no_go, resolution, clone_audit = self.fixture_inputs(Path(tempdir))
			output = Path(tempdir) / "contract"
			self.tool.generate_blocker_resolution_contract(go_no_go, resolution, output, clone_audit)
			text = (output / "coreedge_distribution_contract.md").read_text(encoding="utf-8")

			self.assertIn("product_family = veterinary_practice", text)
			self.assertIn("distribution = vetedge", text)
			self.assertIn("distribution = veterinary", text)

	def test_doctype_identity_policy_blocks_automatic_migration(self):
		with tempfile.TemporaryDirectory() as tempdir:
			go_no_go, resolution, clone_audit = self.fixture_inputs(Path(tempdir))
			output = Path(tempdir) / "contract"
			self.tool.generate_blocker_resolution_contract(go_no_go, resolution, output, clone_audit)
			text = (output / "doctype_identity_policy.md").read_text(encoding="utf-8")

			self.assertIn("must not be treated as client data migration payload", text)
			self.assertIn("Automatic migration of DocType JSON identity fields remains blocked", text)

	def test_clone_generation_policy_defines_upstream_downstream(self):
		with tempfile.TemporaryDirectory() as tempdir:
			go_no_go, resolution, clone_audit = self.fixture_inputs(Path(tempdir))
			output = Path(tempdir) / "contract"
			self.tool.generate_blocker_resolution_contract(go_no_go, resolution, output, clone_audit)
			text = (output / "clone_generation_policy.md").read_text(encoding="utf-8")

			self.assertIn("VetEdge remains the upstream source", text)
			self.assertIn("Veterinary becomes a downstream generated app", text)

	def test_existing_client_policy_says_do_not_uninstall_vetedge_from_production_first(self):
		with tempfile.TemporaryDirectory() as tempdir:
			go_no_go, resolution, clone_audit = self.fixture_inputs(Path(tempdir))
			output = Path(tempdir) / "contract"
			self.tool.generate_blocker_resolution_contract(go_no_go, resolution, output, clone_audit)
			text = (output / "migration_policy.md").read_text(encoding="utf-8")

			self.assertIn("Do not uninstall VetEdge from production first", text)

	def test_role_route_branding_mappings_are_included(self):
		with tempfile.TemporaryDirectory() as tempdir:
			go_no_go, resolution, clone_audit = self.fixture_inputs(Path(tempdir))
			output = Path(tempdir) / "contract"
			self.tool.generate_blocker_resolution_contract(go_no_go, resolution, output, clone_audit)
			text = (output / "role_route_branding_policy.md").read_text(encoding="utf-8")

			self.assertIn("VetEdge Administrator", text)
			self.assertIn("Veterinary Administrator", text)
			self.assertIn("/vetedge_portal", text)
			self.assertIn("/veterinary_portal", text)

	def test_app_lineage_policy_blocks_blind_patch_migration(self):
		with tempfile.TemporaryDirectory() as tempdir:
			go_no_go, resolution, clone_audit = self.fixture_inputs(Path(tempdir))
			output = Path(tempdir) / "contract"
			self.tool.generate_blocker_resolution_contract(go_no_go, resolution, output, clone_audit)
			text = (output / "app_lineage_policy.md").read_text(encoding="utf-8")

			self.assertIn("Patch Log must not be migrated blindly", text)
			self.assertIn("VetEdge patches remain VetEdge lineage", text)

	def test_no_sql_shell_import_restore_or_migrate_scripts_are_generated(self):
		with tempfile.TemporaryDirectory() as tempdir:
			go_no_go, resolution, clone_audit = self.fixture_inputs(Path(tempdir))
			output = Path(tempdir) / "contract"
			self.tool.generate_blocker_resolution_contract(go_no_go, resolution, output, clone_audit)

			self.assertEqual(self.tool.validate_no_forbidden_outputs(output), [])

	def test_no_clone_write_or_import_behavior_is_created(self):
		with tempfile.TemporaryDirectory() as tempdir:
			go_no_go, resolution, clone_audit = self.fixture_inputs(Path(tempdir))
			output = Path(tempdir) / "contract"
			summary = self.tool.generate_blocker_resolution_contract(go_no_go, resolution, output, clone_audit)

			self.assertFalse(summary["clone_generation_write_allowed"])
			self.assertFalse(summary["migration_rehearsal_allowed"])
			self.assertFalse(summary["import_behavior_created"])

	def test_write_mode_fails_intentionally(self):
		result = subprocess.run(
			[
				sys.executable,
				str(SCRIPT_PATH),
				"--go-no-go-dir",
				"/tmp/missing-go-no-go",
				"--resolution-dir",
				"/tmp/missing-resolution",
				"--output-dir",
				"/tmp/contract",
				"--write",
			],
			check=False,
			capture_output=True,
			text=True,
		)

		self.assertNotEqual(result.returncode, 0)
		self.assertIn("write mode intentionally disabled for blocker resolution contract", result.stderr)


if __name__ == "__main__":
	unittest.main()
