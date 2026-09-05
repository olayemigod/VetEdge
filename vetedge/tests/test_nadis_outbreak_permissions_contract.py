from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_outbreak_native_permissions_are_hooked_fail_closed():
    hooks = (ROOT / "hooks.py").read_text(encoding="utf-8")
    permissions = (ROOT / "services/outbreak_permissions.py").read_text(encoding="utf-8")

    assert '"Veterinary Disease Outbreak": "vetedge.services.outbreak_permissions.get_outbreak_query"' in hooks
    assert '"Veterinary Disease Outbreak": "vetedge.services.outbreak_permissions.has_outbreak_permission"' in hooks

    for expected in (
        'return "1=0"',
        'user_has_global_branch_access(user)',
        'get_assigned_branches(user)',
        'if not allowed:',
        'frappe.db.escape(branch)',
        'BRANCH_FIELD = "service_branch"',
        'permission_type == "create"',
        'branch and branch in allowed',
    ):
        assert expected in permissions


def test_outbreak_roles_separate_read_from_write_authority():
    permissions = (ROOT / "services/outbreak_permissions.py").read_text(encoding="utf-8")
    doctype = (ROOT / "veterinary/doctype/veterinary_disease_outbreak/veterinary_disease_outbreak.json").read_text(encoding="utf-8")

    assert 'READ_ROLES = {' in permissions
    assert 'WRITE_ROLES = {' in permissions
    assert 'ROLE_VETEDGE_DOCTOR' in permissions
    assert 'ROLE_BRANCH_MANAGER' in permissions
    assert 'ROLE_VETERINARY_NURSE' in permissions

    assert '"role": "VetEdge Doctor"' in doctype
    assert '"role": "Branch Manager"' in doctype
    assert '"role": "Veterinary Nurse"' in doctype

    # Nurse remains read/report only in DocType role permissions.
    nurse_entry = doctype.split('{"email": 1, "export": 1, "print": 1, "read": 1, "report": 1, "role": "Veterinary Nurse"', 1)
    assert len(nurse_entry) == 2


def test_outbreak_filter_normalizer_blocks_zero_assignment_and_cross_branch_scope():
    permissions = (ROOT / "services/outbreak_permissions.py").read_text(encoding="utf-8")

    for expected in (
        'def normalize_outbreak_report_filters(',
        'No Veterinary Branch is assigned to this user.',
        'selected not in allowed',
        'You are not permitted to report Disease Outbreak data for Branch',
        'result["branch"] = default_branch if default_branch in allowed else sorted(allowed)[0]',
    ):
        assert expected in permissions
