from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPT_PATH = REPO_ROOT / "tools" / "create_veterinary_clone.py"
SNAPSHOT_PATH = REPO_ROOT / "tests" / "fixtures" / "veterinary_clone_audit_snapshot.json"


def load_clone_tool():
	spec = importlib.util.spec_from_file_location("create_veterinary_clone", SCRIPT_PATH)
	module = importlib.util.module_from_spec(spec)
	assert spec.loader is not None
	sys.modules[spec.name] = module
	spec.loader.exec_module(module)
	return module


def write(path: Path, text: str) -> Path:
	path.parent.mkdir(parents=True, exist_ok=True)
	path.write_text(text, encoding="utf-8")
	return path


class CloneAuditToolTest(unittest.TestCase):
	@classmethod
	def setUpClass(cls):
		cls.tool = load_clone_tool()

	def replacement_count(self, reports: dict, rule: str) -> int:
		return reports[rule].count

	def test_transformation_preview_rules_use_small_fixture_tree(self):
		with tempfile.TemporaryDirectory() as tempdir:
			root = Path(tempdir)
			write(root / "pyproject.toml", '[project]\nname = "vetedge"\n')
			write(
				root / "vetedge" / "hooks.py",
				"\n".join(
					[
						'app_name = "vetedge"',
						'app_title = "VetEdge"',
						'app_logo_url = "/assets/vetedge/images/vetedge-app-icon.png"',
						'app_home = "/desk/vetedge-executive-dashboard"',
					]
				),
			)
			write(root / "vetedge" / "services" / "billing.py", "from vetedge.services.stock import get_item\n")
			write(
				root / "vetedge" / "public" / "js" / "portal.js",
				'frappe.call({ method: "vetedge.services.owner_portal.create_owner_appointment_request" });\n',
			)
			write(root / "vetedge" / "templates" / "portal.html", '<link href="/assets/vetedge/css/owner_portal.css">\n')
			write(root / "vetedge" / "workspace_sidebar" / "vetedge.json", '{"link_to": "vetedge-executive-dashboard"}\n')

			files, skipped = self.tool.build_inventory(root)
			reports = self.tool.preview_text_replacements(files, root)

			self.assertEqual(skipped, [])
			self.assertEqual(self.replacement_count(reports, "pyproject_project_name"), 1)
			self.assertEqual(self.replacement_count(reports, "hooks_app_identity"), 4)
			self.assertEqual(self.replacement_count(reports, "python_dotted_imports"), 1)
			self.assertEqual(self.replacement_count(reports, "js_frappe_method_strings"), 1)
			self.assertEqual(self.replacement_count(reports, "asset_urls"), 2)
			self.assertEqual(self.replacement_count(reports, "executive_dashboard_route"), 2)

	def test_protected_clinical_labels_and_stock_expiry_are_preserved(self):
		with tempfile.TemporaryDirectory() as tempdir:
			root = Path(tempdir)
			write(root / "notes.md", "Veterinary Patient\nVeterinary Consultation\nStock Expiry Status\n")

			files, _skipped = self.tool.build_inventory(root)
			classified = self.tool.classify_remaining_references(files, root)
			preserved = {(item["category"], item["text"]) for item in classified["preserve"]}

			self.assertIn(("protected_clinical_domain_name", "Veterinary Patient"), preserved)
			self.assertIn(("protected_clinical_domain_name", "Stock Expiry Status"), preserved)
			self.assertEqual(classified["dangerous"], [])

	def test_dangerous_and_manual_review_classification(self):
		with tempfile.TemporaryDirectory() as tempdir:
			root = Path(tempdir)
			write(root / "vetedge" / "patches.txt", "vetedge.patches.rename_desktop_icon\n")
			write(root / "vetedge" / "install" / "__init__.py", '"VetEdge Doctor"\n')
			write(root / "vetedge" / "www" / "portal.html", '<a href="/vetedge_guest_booking">Book</a>\n')
			write(
				root / "vetedge" / "public" / "js" / "api.js",
				'frappe.call({ method: "vetedge.services.billing.create_consultation_invoice" });\n',
			)

			files, _skipped = self.tool.build_inventory(root)
			classified = self.tool.classify_remaining_references(files, root)

			self.assertTrue(any(item["category"] == "patch_lineage" for item in classified["dangerous"]))
			self.assertTrue(any(item["category"] == "portal_route" for item in classified["dangerous"]))
			self.assertTrue(any(item["category"] == "whitelisted_method_reference" for item in classified["dangerous"]))
			self.assertTrue(any(item["category"] == "role_name" for item in classified["manual_review"]))

	def test_generated_and_cache_files_are_skipped(self):
		with tempfile.TemporaryDirectory() as tempdir:
			root = Path(tempdir)
			write(root / "vetedge" / "__pycache__" / "module.py", "from vetedge.services import billing\n")
			write(root / "node_modules" / "pkg" / "index.js", "vetedge\n")
			write(root / "dist" / "bundle.js", "vetedge\n")
			write(root / "vetedge" / "services" / "module.pyc", "compiled vetedge\n")
			kept = write(root / "vetedge" / "services" / "module.py", "from vetedge.services import billing\n")

			files, skipped = self.tool.build_inventory(root)

			self.assertEqual(files, [kept])
			skipped_paths = {item["path"] for item in skipped}
			self.assertIn("vetedge/services/module.pyc", skipped_paths)
			self.assertTrue(all("__pycache__" not in str(path) for path in files))
			self.assertTrue(all("node_modules" not in str(path) for path in files))
			self.assertTrue(all("dist" not in str(path) for path in files))

	def test_write_mode_fails_intentionally(self):
		result = subprocess.run(
			[
				sys.executable,
				str(SCRIPT_PATH),
				"--source-dir",
				str(REPO_ROOT),
				"--output-dir",
				str(REPO_ROOT.parent / "veterinary"),
				"--write",
			],
			check=False,
			capture_output=True,
			text=True,
		)

		self.assertNotEqual(result.returncode, 0)
		self.assertIn("write mode intentionally disabled for Phase 2A", result.stderr)

	def test_full_repo_audit_matches_golden_safety_snapshot(self):
		snapshot = json.loads(SNAPSHOT_PATH.read_text(encoding="utf-8"))
		report = self.tool.build_audit_report(REPO_ROOT, REPO_ROOT.parent / "veterinary")
		layer_counts = report["reference_layer_counts"]
		category_counts = report["reference_category_counts"]

		for layer, (minimum, maximum) in snapshot["layer_count_ranges"].items():
			self.assertGreaterEqual(layer_counts[layer], minimum, layer)
			self.assertLessEqual(layer_counts[layer], maximum, layer)

		for check in snapshot["required_static_checks"]:
			self.assertTrue(report["static_checks"]["sidebar"][check], check)
		self.assertTrue(report["static_checks"]["dashboard_shell"]["fallback_present"])

		for term in ("Veterinary Patient", "Veterinary Financial Dashboard", "Stock Expiry Status"):
			self.assertIn(term, report["protected_terms"])

		for category in snapshot["required_dangerous_categories"]:
			self.assertIn(category, category_counts["dangerous"])
			self.assertGreater(category_counts["dangerous"][category], 0)

		self.assertEqual(report["audit_status"]["unknown_threshold"], snapshot["unknown_threshold"])
		self.assertTrue(report["audit_status"]["unknown_within_threshold"])

	def test_audit_status_fails_when_unknown_references_exceed_threshold(self):
		with tempfile.TemporaryDirectory() as tempdir:
			root = Path(tempdir)
			write(root / "notes.md", "VetEdge Mystery Reference\n")
			registry = {
				"unknown_threshold": 0,
				"classifications": [],
				"protected_clinical_domain_names": [],
			}

			report = self.tool.build_audit_report(root, root.parent / "veterinary", registry=registry)

			self.assertEqual(report["reference_layer_counts"]["unknown"], 1)
			self.assertFalse(report["audit_status"]["unknown_within_threshold"])
			self.assertIn("Unknown references exceed approved threshold", report["audit_status"]["failure_reason"])


if __name__ == "__main__":
	unittest.main()
