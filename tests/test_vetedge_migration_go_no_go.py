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
SCRIPT_PATH = REPO_ROOT / "tools" / "vetedge_migration_go_no_go.py"


def load_gate_tool():
	spec = importlib.util.spec_from_file_location("vetedge_migration_go_no_go", SCRIPT_PATH)
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


class VetEdgeMigrationGoNoGoTest(unittest.TestCase):
	@classmethod
	def setUpClass(cls):
		cls.tool = load_gate_tool()

	def fixture_resolution_dir(self, root: Path) -> Path:
		resolution = root / "resolution"
		write_json(
			resolution / "resolution_summary.json",
			{
				"source_readiness_status": "needs_review",
				"source_readiness_score": 0,
				"blocked_items": ["CoreEdge/product references", "DocType JSON identity fields"],
			},
		)
		write_csv(
			resolution / "manual_review_resolution.csv",
			["area", "status", "resolution", "owner", "notes"],
			[{"area": "CoreEdge/product references", "status": "blocked", "resolution": "", "owner": "", "notes": ""}],
		)
		(resolution / "unresolved_blockers.md").write_text(
			"- CoreEdge/product references need platform decision.\n- DocType JSON identity fields remain blocked from automatic migration.\n",
			encoding="utf-8",
		)
		(resolution / "future_import_contract_draft.md").write_text("non-executable\n", encoding="utf-8")
		return resolution

	def test_go_no_go_package_is_generated_from_fixture_resolution_inputs(self):
		with tempfile.TemporaryDirectory() as tempdir:
			resolution = self.fixture_resolution_dir(Path(tempdir))
			output = Path(tempdir) / "gate"
			summary = self.tool.generate_go_no_go(resolution, output)

			expected = {
				"go_no_go_summary.json",
				"migration_gate.md",
				"signoff_template.md",
				"blockers_register.csv",
				"risk_register.csv",
				"required_decisions.md",
				"cutover_readiness_checklist.md",
				"rollback_readiness_checklist.md",
				"future_rehearsal_scope.md",
			}
			self.assertEqual({path.name for path in output.iterdir()}, expected)
			self.assertFalse(summary["migration_allowed"])
			self.assertFalse(summary["clone_generated"])
			self.assertFalse(summary["import_behavior_created"])

	def test_unresolved_blockers_cause_migration_allowed_false(self):
		with tempfile.TemporaryDirectory() as tempdir:
			resolution = self.fixture_resolution_dir(Path(tempdir))
			output = Path(tempdir) / "gate"
			self.tool.generate_go_no_go(resolution, output)
			summary = json.loads((output / "go_no_go_summary.json").read_text(encoding="utf-8"))

			self.assertFalse(summary["migration_allowed"])
			self.assertIn("not allowed", summary["reason"])

	def test_signoff_template_includes_required_roles(self):
		with tempfile.TemporaryDirectory() as tempdir:
			resolution = self.fixture_resolution_dir(Path(tempdir))
			output = Path(tempdir) / "gate"
			self.tool.generate_go_no_go(resolution, output)
			text = (output / "signoff_template.md").read_text(encoding="utf-8")

			for role in self.tool.SIGNOFF_ROLES:
				self.assertIn(role, text)

	def test_blockers_register_includes_required_blockers(self):
		with tempfile.TemporaryDirectory() as tempdir:
			resolution = self.fixture_resolution_dir(Path(tempdir))
			output = Path(tempdir) / "gate"
			self.tool.generate_go_no_go(resolution, output)
			with (output / "blockers_register.csv").open(newline="", encoding="utf-8") as handle:
				rows = list(csv.DictReader(handle))
			areas = {row["area"] for row in rows}

			self.assertIn("CoreEdge/product references", areas)
			self.assertIn("DocType JSON identity fields", areas)

	def test_risk_register_includes_patch_and_submitted_financial_stock_risks(self):
		with tempfile.TemporaryDirectory() as tempdir:
			resolution = self.fixture_resolution_dir(Path(tempdir))
			output = Path(tempdir) / "gate"
			self.tool.generate_go_no_go(resolution, output)
			text = (output / "risk_register.csv").read_text(encoding="utf-8")

			self.assertIn("patch lineage confusion", text)
			self.assertIn("submitted financial/stock link damage", text)

	def test_cutover_and_rollback_checklists_are_generated(self):
		with tempfile.TemporaryDirectory() as tempdir:
			resolution = self.fixture_resolution_dir(Path(tempdir))
			output = Path(tempdir) / "gate"
			self.tool.generate_go_no_go(resolution, output)

			self.assertTrue((output / "cutover_readiness_checklist.md").exists())
			self.assertTrue((output / "rollback_readiness_checklist.md").exists())

	def test_no_sql_shell_import_restore_or_migrate_scripts_are_generated(self):
		with tempfile.TemporaryDirectory() as tempdir:
			resolution = self.fixture_resolution_dir(Path(tempdir))
			output = Path(tempdir) / "gate"
			self.tool.generate_go_no_go(resolution, output)

			self.assertEqual(self.tool.validate_no_forbidden_outputs(output), [])

	def test_write_mode_fails_intentionally(self):
		result = subprocess.run(
			[
				sys.executable,
				str(SCRIPT_PATH),
				"--resolution-dir",
				"/tmp/missing-resolution",
				"--output-dir",
				"/tmp/gate",
				"--write",
			],
			check=False,
			capture_output=True,
			text=True,
		)

		self.assertNotEqual(result.returncode, 0)
		self.assertIn("write mode intentionally disabled for migration go/no-go gate", result.stderr)


if __name__ == "__main__":
	unittest.main()
