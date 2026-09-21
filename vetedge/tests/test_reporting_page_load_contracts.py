from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path
from unittest import TestCase


APP_ROOT = Path(__file__).resolve().parents[1]
REPORT_CENTER_JS = APP_ROOT / "veterinary" / "page" / "vetedge_report_center" / "vetedge_report_center.js"
REGULATORY_JS = APP_ROOT / "veterinary" / "page" / "vetedge_regulatory_reporting" / "vetedge_regulatory_reporting.js"
REGULATORY_PAGE_JSON = APP_ROOT / "veterinary" / "page" / "vetedge_regulatory_reporting" / "vetedge_regulatory_reporting.json"
REGULATORY_NAV = APP_ROOT / "install" / "regulatory_reporting.py"


class ReportingPageLoadContractTests(TestCase):
	def _assert_javascript_parses(self, path: Path) -> None:
		node = shutil.which("node")
		if not node:
			self.skipTest("node is unavailable for JavaScript syntax validation")
		result = subprocess.run(
			[node, "--check", str(path)],
			capture_output=True,
			text=True,
			check=False,
		)
		self.assertEqual(
			result.returncode,
			0,
			msg=f"{path.name} must parse before Frappe can mount the page:\n{result.stderr}",
		)

	def test_report_center_javascript_parses(self):
		self._assert_javascript_parses(REPORT_CENTER_JS)

	def test_report_center_loader_closes_without_extra_parenthesis(self):
		source = REPORT_CENTER_JS.read_text(encoding="utf-8")
		self.assertNotIn("\t})));", source)
		self.assertTrue(source.rstrip().endswith("}));\n};"))

	def test_regulatory_reporting_javascript_parses(self):
		self._assert_javascript_parses(REGULATORY_JS)

	def test_regulatory_reporting_mounts_into_frappe_jquery_page_body(self):
		source = REGULATORY_JS.read_text(encoding="utf-8")
		self.assertNotIn("wrapper.page.body.appendChild", source)
		self.assertIn("$(wrapper.page.body).append(mount)", source)
		self.assertIn("wrapper.vue_app.mount(mount)", source)

	def test_regulatory_scope_fields_use_edgesuite_link_searcher_contract(self):
		source = REGULATORY_JS.read_text(encoding="utf-8")
		self.assertIn('searcher: this.searchCompanies', source)
		self.assertIn('searcher: this.searchBranches', source)
		self.assertIn('selectedLabel: this.filters.company || ""', source)
		self.assertIn('selectedLabel: this.filters.branch || ""', source)
		self.assertNotIn('search: this.searchCompanies', source)
		self.assertNotIn('search: this.searchBranches', source)
		self.assertIn('ignore_user_permissions: 0', source)
		self.assertIn('report_name: "Vaccination Report", field: "branch"', source)

	def test_regulatory_navigation_targets_standard_page_and_outbreak_register(self):
		navigation = REGULATORY_NAV.read_text(encoding="utf-8")
		page = json.loads(REGULATORY_PAGE_JSON.read_text(encoding="utf-8"))

		self.assertEqual(page["name"], "vetedge-regulatory-reporting")
		self.assertEqual(page["page_name"], "vetedge-regulatory-reporting")
		self.assertEqual(page["standard"], "Yes")
		self.assertIn('REGULATORY_PAGE = "vetedge-regulatory-reporting"', navigation)
		self.assertIn('_link("VCN / NADIS Reports", "Page", REGULATORY_PAGE', navigation)
		self.assertIn('_link("Disease Outbreak Register", "DocType", OUTBREAK_DOCTYPE', navigation)
