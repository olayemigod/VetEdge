from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_branch_scoped_reporting_must_not_fail_open_without_assignments():
    source = (ROOT / "services/report_visibility.py").read_text(encoding="utf-8")

    unsafe = "assigned_branches = _allowed_branches_for_user(user)\n\tif not assigned_branches:\n\t\treturn"
    assert unsafe not in source
    assert 'title=_("Branch Assignment Required")' in source
    assert "No Veterinary Branch is assigned to this user" in source
    assert "frappe.PermissionError" in source


def test_branch_scope_preserves_authoritative_default_and_restriction_rules():
    source = (ROOT / "services/report_visibility.py").read_text(encoding="utf-8")
    for expected in (
        "normalize_report_filters",
        "normalize_dashboard_filters",
        "_apply_branch_default_and_restriction",
        "get_assigned_branches",
        "user_has_global_branch_access",
        "selected_branch not in assigned_branches",
        "filters.branch = default_branch",
        "if user_default and user_default in assigned_branches",
        "if len(assigned_branches) == 1",
        "return sorted(assigned_branches)[0]",
    ):
        assert expected in source


def test_global_branch_access_remains_outside_branch_scoped_fail_closed_gate():
    source = (ROOT / "services/report_visibility.py").read_text(encoding="utf-8")
    assert "if not user or user_has_global_branch_access(user):\n\t\treturn False" in source
