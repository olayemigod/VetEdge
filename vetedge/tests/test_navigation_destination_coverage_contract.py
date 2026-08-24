from __future__ import annotations

import ast
import json
from pathlib import Path


PACKAGE_ROOT = Path(__file__).resolve().parents[1]


def _text(relative_path: str) -> str:
	return (PACKAGE_ROOT / relative_path).read_text(encoding="utf-8")


def test_care_location_workspace_backend_is_parseable_and_branch_fail_closed():
	source = _text("services/care_location_workspace.py")
	ast.parse(source)

	assert 'DOCTYPE = "Veterinary Care Location"' in source
	assert "user_has_global_branch_access" in source
	assert "get_assigned_branches" in source
	assert "if allowed == []" in source
	assert "branch_scope_empty" in source
	assert "You do not have an assigned Veterinary Branch for Care Location management." in source
	assert "_assert_branch_access(doc.get(\"branch\"))" in source
	assert "require_vetedge_platform_access" in source
	assert "ignore_permissions=True" not in source
	assert "ignore_permissions = True" not in source


def test_care_location_workspace_is_an_edgesuite_page():
	source = _text("veterinary/page/vetedge_care_locations/vetedge_care_locations.js")

	for component in (
		"EdgeAppShell",
		"EdgePageLayout",
		"EdgePageHeader",
		"EdgeFilterBar",
		"EdgeDataTable",
		"EdgeDocumentForm",
		"EdgeLinkField",
		"EdgeModal",
	):
		assert component in source

	assert "vetedge.services.care_location_workspace.get_care_location_page" in source
	assert "vetedge.services.care_location_workspace.save_care_location_document" in source
	assert "vetedge.services.care_location_workspace.search_care_location_link" in source
	assert 'activeRoute: "/desk/vetedge-care-locations"' in source

	page = json.loads(_text("veterinary/page/vetedge_care_locations/vetedge_care_locations.json"))
	assert page["name"] == "vetedge-care-locations"
	assert page["module"] == "Veterinary"
	assert {row["role"] for row in page["roles"]} >= {
		"System Manager",
		"VetEdge Administrator",
		"Branch Manager",
		"VetEdge Front Desk",
	}


def test_branch_access_workspace_backend_is_parseable_and_permission_aware():
	source = _text("services/branch_access_workspace.py")
	ast.parse(source)

	assert '"user-assignments"' in source
	assert '"practitioner-assignments"' in source
	assert '"Branch User Assignment"' in source
	assert '"Branch Practitioner Assignment"' in source
	assert "get_system_users" in source
	assert "get_veterinary_doctor_users" in source
	assert "user_has_global_branch_access" in source
	assert "get_assigned_branches" in source
	assert "if allowed == []" in source
	assert "require_vetedge_platform_access" in source
	assert "doc.check_permission" in source
	assert "ignore_permissions=True" not in source
	assert "ignore_permissions = True" not in source


def test_branch_access_workspace_is_an_edgesuite_page():
	source = _text("veterinary/page/vetedge_branch_access/vetedge_branch_access.js")
	for component in (
		"EdgeAppShell",
		"EdgePageLayout",
		"EdgePageHeader",
		"EdgeFilterBar",
		"EdgeDataTable",
		"EdgeDocumentForm",
		"EdgeLinkField",
		"EdgeModal",
	):
		assert component in source

	assert "vetedge.services.branch_access_workspace.get_branch_access_page" in source
	assert "vetedge.services.branch_access_workspace.save_branch_access_document" in source
	assert "vetedge.services.branch_access_workspace.search_branch_access_link" in source
	assert 'activeRoute: "/desk/vetedge-branch-access"' in source

	page = json.loads(_text("veterinary/page/vetedge_branch_access/vetedge_branch_access.json"))
	assert page["name"] == "vetedge-branch-access"
	assert page["module"] == "Veterinary"
	assert {row["role"] for row in page["roles"]} >= {
		"System Manager",
		"VetEdge Administrator",
		"Branch Manager",
	}


def test_known_migrated_reports_and_configuration_do_not_stay_on_native_routes():
	source = _text("public/js/vetedge_sidebar_qa_alignment.js")

	for report in (
		"Consultation Register",
		"Patient Register",
		"Owner Register",
		"Lab Order Report",
		"Vaccination Report",
	):
		assert f'"{report}"' in source

	assert "/desk/query-report/" in source
	assert "/desk/vetedge-report-center" in source
	assert 'const CARE_LOCATION_DOCTYPE = "Veterinary Care Location"' in source
	assert 'const CARE_LOCATION_ROUTE = "/desk/vetedge-care-locations"' in source
	assert '"Branch User Assignment": "/desk/vetedge-branch-access?resource=user-assignments"' in source
	assert '"Branch Practitioner Assignment": "/desk/vetedge-branch-access?resource=practitioner-assignments"' in source
	assert '"Training Centre": "/desk/veterinary-training-centre"' in source
	assert '"Settings": "/desk/veterinary-settings-center"' in source
	assert "careLocationTargetFromNativePath" in source
	assert "branchAccessTargetFromNativePath" in source
	assert "navigationCandidate" in source
	assert "event.stopImmediatePropagation" in source
	assert "window.open" not in source


def test_navigation_alignment_preserves_existing_planned_treatment_edgesuite_route():
	source = _text("public/js/vetedge_sidebar_qa_alignment.js")
	assert "movePlannedTreatmentToReports" in source
	assert "/desk/vetedge-treatment-plan-report" in source
