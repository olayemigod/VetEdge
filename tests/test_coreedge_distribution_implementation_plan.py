from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPT_PATH = REPO_ROOT / "tools" / "coreedge_distribution_implementation_plan.py"


def load_plan_tool():
	spec = importlib.util.spec_from_file_location("coreedge_distribution_implementation_plan", SCRIPT_PATH)
	module = importlib.util.module_from_spec(spec)
	assert spec.loader is not None
	sys.modules[spec.name] = module
	spec.loader.exec_module(module)
	return module


def write_json(path: Path, payload: object) -> None:
	path.parent.mkdir(parents=True, exist_ok=True)
	path.write_text(json.dumps(payload, sort_keys=True), encoding="utf-8")


class CoreEdgeDistributionImplementationPlanTest(unittest.TestCase):
	@classmethod
	def setUpClass(cls):
		cls.tool = load_plan_tool()
		cls.tempdir = tempfile.TemporaryDirectory()
		root = Path(cls.tempdir.name)
		cls.coreedge, cls.vetedge, cls.validator, cls.contract = cls.fixture_inputs(root)
		cls.output = root / "plan"
		cls.summary = cls.tool.generate_implementation_plan(cls.coreedge, cls.vetedge, cls.validator, cls.contract, cls.output)

	@classmethod
	def tearDownClass(cls):
		cls.tempdir.cleanup()

	@staticmethod
	def fixture_inputs(root: Path) -> tuple[Path, Path, Path, Path]:
		coreedge = root / "coreedge"
		vetedge = root / "vetedge"
		validator = root / "validator"
		contract = root / "contract"
		(coreedge / "coreedge" / "api").mkdir(parents=True)
		(coreedge / "coreedge" / "doctype" / "coreedge_product_activation").mkdir(parents=True)
		(vetedge / "vetedge" / "services").mkdir(parents=True)
		(coreedge / "coreedge" / "api" / "runtime_access.py").write_text(
			"PRODUCT = 'vetedge'\n# feature_gate activation product_code\n",
			encoding="utf-8",
		)
		(coreedge / "coreedge" / "services" / "branding.py").parent.mkdir(parents=True)
		(coreedge / "coreedge" / "services" / "branding.py").write_text(
			"# branding Email SMS WhatsApp wallet notification\n",
			encoding="utf-8",
		)
		(coreedge / "coreedge" / "doctype" / "coreedge_product_activation" / "coreedge_product_activation.json").write_text(
			'{"name":"CoreEdge Product Activation","fields":[{"fieldname":"product_code"}]}',
			encoding="utf-8",
		)
		(vetedge / "vetedge" / "services" / "coreedge_adapter.py").write_text(
			"PRODUCT = 'VetEdge'\n",
			encoding="utf-8",
		)
		write_json(
			validator / "validator_summary.json",
			{"coreedge_contract_valid": True, "doctype_identity_policy_valid": True},
		)
		(contract / "coreedge_distribution_contract.md").parent.mkdir(parents=True, exist_ok=True)
		(contract / "coreedge_distribution_contract.md").write_text("product_family = veterinary_practice\n", encoding="utf-8")
		return coreedge, vetedge, validator, contract

	def test_implementation_package_is_generated(self):
		expected = {
			"implementation_plan_summary.json",
			"coreedge_source_inventory.csv",
			"product_family_distribution_design.md",
			"activation_model_design.md",
			"feature_gate_design.md",
			"shared_services_design.md",
			"branding_and_identity_design.md",
			"adapter_contract_design.md",
			"required_coreedge_changes.csv",
			"required_vetedge_adapter_changes.csv",
			"test_plan.md",
			"migration_impact_assessment.md",
			"phase_2l_recommendation.md",
		}
		self.assertEqual({path.name for path in self.output.iterdir()}, expected)
		self.assertFalse(self.summary["clone_generated"])
		self.assertFalse(self.summary["import_behavior_created"])

	def test_product_family_distribution_design_is_present(self):
		text = (self.output / "product_family_distribution_design.md").read_text(encoding="utf-8")

		self.assertIn("product_family = veterinary_practice", text)
		self.assertIn("distribution = vetedge", text)
		self.assertIn("distribution = veterinary", text)

	def test_activation_model_design_is_present(self):
		text = (self.output / "activation_model_design.md").read_text(encoding="utf-8")

		self.assertIn("VetEdge SaaS activation", text)
		self.assertIn("Veterinary white-label activation", text)
		self.assertIn("product_family", text)
		self.assertIn("distribution", text)

	def test_feature_gate_design_includes_required_dashboards_and_stock_expiry(self):
		text = (self.output / "feature_gate_design.md").read_text(encoding="utf-8")

		self.assertIn("Stock Expiry", text)
		self.assertIn("Financial Dashboard", text)
		self.assertIn("Hospitalisation Dashboard", text)

	def test_required_changes_csv_is_generated(self):
		text = (self.output / "required_coreedge_changes.csv").read_text(encoding="utf-8")

		self.assertEqual(self.summary["required_coreedge_change_count"], 6)
		self.assertIn("COREEDGE-001", text)

	def test_test_plan_is_generated(self):
		text = (self.output / "test_plan.md").read_text(encoding="utf-8")

		self.assertIn("CoreEdge product family/distribution resolver tests", text)
		self.assertIn("no regression for current VetEdge access gates", text)

	def test_no_sql_shell_import_restore_or_migrate_scripts_are_generated(self):
		self.assertEqual(self.tool.validate_no_forbidden_outputs(self.output), [])

	def test_write_mode_fails_intentionally(self):
		result = subprocess.run(
			[
				sys.executable,
				str(SCRIPT_PATH),
				"--coreedge-dir",
				"/tmp/missing-coreedge",
				"--vetedge-dir",
				"/tmp/missing-vetedge",
				"--output-dir",
				"/tmp/plan",
				"--write",
			],
			check=False,
			capture_output=True,
			text=True,
		)

		self.assertNotEqual(result.returncode, 0)
		self.assertIn("write mode intentionally disabled for CoreEdge distribution implementation planning", result.stderr)


if __name__ == "__main__":
	unittest.main()
