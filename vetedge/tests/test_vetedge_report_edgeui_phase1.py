from __future__ import annotations

from pathlib import Path

try:
	from frappe.tests.utils import FrappeTestCase
except ImportError:
	FrappeTestCase = None

ROOT = Path(__file__).resolve().parents[2]


def read(*parts: str) -> str:
	return ROOT.joinpath(*parts).read_text(encoding="utf-8")


def test_report_assets_are_loaded_before_visibility_bridge():
	hooks = read("vetedge", "hooks.py")
	assert "vetedge_report_edgeui.css" in hooks
	assert "vetedge_report_edgeui.js" in hooks
	assert hooks.index("vetedge_report_edgeui.js") < hooks.index("report_visibility.js")
	for preserved in (
		'"on_update_after_submit"',
		'"Stock Entry"',
		'"Veterinary Appointment"',
		'"*/5 * * * *"',
		'before_request = ["vetedge.services.portal_access.block_owner_portal_desk_access"]',
	):
		assert preserved in hooks


def test_shared_report_surface_uses_edgesuite_runtime_without_private_imports():
	content = read("vetedge", "public", "js", "vetedge_report_edgeui.js")
	for contract in (
		"runtime.createEdgeApp(root)",
		"runtime.components?.EdgePageHeader",
		"runtime.components?.EdgeDashboardLayout",
		"runtime.components?.EdgeStatCard",
		"runtime.components?.EdgeStatusBadge",
		"runtime.components?.EdgeEmptyState",
		"patchSummaryRenderer",
		"report.show_and_render_summary",
		"frappe.require(\"edgeui.bundle.js\"",
		"report.export_report()",
		"report.print_report()",
	):
		assert contract in content
	for forbidden in (
		"coreedge/public",
		"../../../../../coreedge",
		"innerHTML =",
		"frappe.db.set_value",
	):
		assert forbidden not in content


def test_priority_reports_register_business_facing_edgesuite_surfaces():
	reports = {
		"branch_performance_report": (
			"Branch Performance Report",
			"Management Report",
			"Branch Performance",
		),
		"consultation_register": (
			"Consultation Register",
			"Clinical Operations",
			"Consultation Register",
		),
		"planned_treatment": (
			"Planned Treatment",
			"Clinical Planning",
			"Planned Treatment",
		),
	}
	for folder, expected in reports.items():
		content = read("vetedge", "veterinary", "report", folder, f"{folder}.js")
		for contract in expected:
			assert contract in content
		assert "vetedgeReportVisibility?.apply" in content
		assert "vetedgeReportEdgeUI?.attach" in content
		assert content.index("vetedgeReportVisibility?.apply") < content.index("vetedgeReportEdgeUI?.attach")
		assert "frappe.datetime.month_start()" in content


def test_report_surface_styles_native_query_report_without_replacing_table():
	content = read("vetedge", "public", "css", "vetedge_report_edgeui.css")
	for selector in (
		".vetedge-edgeui-report-page .page-form",
		".vetedge-report-edgeui-host",
		".vetedge-report-edgeui-card.is-clickable",
		".vetedge-edgeui-report-page .datatable-container",
		".vetedge-report-edgeui-recommendations",
	):
		assert selector in content
	assert "display: none" not in content


def test_priority_report_metadata_is_read_only_and_actionable():
	content = read("vetedge", "services", "report_metadata_edgeui.py")
	logic = read("vetedge", "services", "reporting_logic_v3.py")
	for contract in (
		'register_report(\n\t\t"Branch Performance Report"',
		'"consultation_count"',
		'"revenue_total"',
		'"outstanding_total"',
		'register_report(\n\t\t"Planned Treatment"',
		'"planned_value"',
		'"average_line_value"',
		'"Pending / Active"',
	):
		assert contract in content
	assert "register_edgeui_report_definitions()" in logic
	for forbidden in (
		"frappe.db.set_value",
		".save(",
		".submit(",
		".insert(",
		"ignore_permissions",
	):
		assert forbidden not in content


if FrappeTestCase is not None:
	class TestVetEdgePriorityReportMetadata(FrappeTestCase):
		def test_branch_performance_cards_use_existing_report_rows(self):
			from vetedge.services.report_insights import build_report_summary
			from vetedge.services.report_metadata_edgeui import register_edgeui_report_definitions

			register_edgeui_report_definitions()
			rows = [
				{
					"branch": "Main",
					"consultation_count": 4,
					"appointment_count": 6,
					"revenue_total": 120000,
					"outstanding_total": 20000,
					"lab_order_count": 3,
					"vaccination_count": 2,
				},
				{
					"branch": "Annex",
					"consultation_count": 2,
					"appointment_count": 3,
					"revenue_total": 45000,
					"outstanding_total": 5000,
					"lab_order_count": 1,
					"vaccination_count": 4,
				},
			]
			summary = build_report_summary(
				"Branch Performance Report",
				rows,
				{"from_date": "2026-07-01", "to_date": "2026-07-31"},
			)
			cards = {row.get("id"): row for row in summary if row.get("id")}
			self.assertEqual(cards["branches"]["value"], 2)
			self.assertEqual(cards["consultations"]["value"], 6)
			self.assertEqual(cards["appointments"]["value"], 9)
			self.assertEqual(cards["revenue"]["value"], 165000)
			self.assertEqual(cards["outstanding"]["value"], 25000)

		def test_planned_treatment_cards_use_planned_lines_only(self):
			from vetedge.services.report_insights import build_report_summary
			from vetedge.services.report_metadata_edgeui import register_edgeui_report_definitions

			register_edgeui_report_definitions()
			rows = [
				{"amount": 10000, "status": "In Progress"},
				{"amount": 5000, "status": "Ready for Treatment"},
				{"amount": 15000, "status": "Completed"},
			]
			summary = build_report_summary(
				"Planned Treatment",
				rows,
				{"from_date": "2026-07-01", "to_date": "2026-07-31"},
			)
			cards = {row.get("id"): row for row in summary if row.get("id")}
			self.assertEqual(cards["planned_lines"]["value"], 3)
			self.assertEqual(cards["planned_value"]["value"], 30000)
			self.assertEqual(cards["average_line_value"]["value"], 10000)
			self.assertEqual(cards["pending"]["value"], 2)
			self.assertEqual(cards["completed"]["value"], 1)
