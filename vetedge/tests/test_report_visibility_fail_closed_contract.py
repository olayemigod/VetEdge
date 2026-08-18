from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_branch_scoped_reporting_must_not_fail_open_without_assignments():
    source = (ROOT / "services/report_visibility.py").read_text(encoding="utf-8")

    # Branch-scoped users with no assignments must never fall through to an
    # unfiltered report/dashboard query. The shared visibility layer must
    # either deny access or inject an impossible branch scope.
    unsafe = "assigned_branches = _allowed_branches_for_user(user)\n\tif not assigned_branches:\n\t\treturn"
    assert unsafe not in source

    assert (
        "No branch is assigned" in source
        or "frappe.PermissionError" in source
        or "filters.branch =" in source
    )


def test_branch_scope_remains_server_authoritative():
    source = (ROOT / "services/report_visibility.py").read_text(encoding="utf-8")
    assert "normalize_report_filters" in source
    assert "normalize_dashboard_filters" in source
    assert "_apply_branch_default_and_restriction" in source
    assert "get_assigned_branches" in source
    assert "user_has_global_branch_access" in source
