from __future__ import annotations

import frappe
from frappe.utils import cstr

from vetedge.services.permissions import (
    ELEVATED_ROLES,
    ROLE_BRANCH_MANAGER,
    ROLE_VETEDGE_DOCTOR,
    ROLE_VETEDGE_NURSE,
    ROLE_VETERINARY_NURSE,
    get_assigned_branches,
    get_current_user,
    get_user_roles,
    is_internal_staff_user,
    is_portal_owner_user,
    user_has_global_branch_access,
)


DOCTYPE = "Veterinary Disease Outbreak"
BRANCH_FIELD = "service_branch"

READ_ROLES = {
    ROLE_VETEDGE_DOCTOR,
    ROLE_VETEDGE_NURSE,
    ROLE_VETERINARY_NURSE,
    ROLE_BRANCH_MANAGER,
    "VetEdge Branch Manager",
    *ELEVATED_ROLES,
}
WRITE_ROLES = {
    ROLE_VETEDGE_DOCTOR,
    ROLE_BRANCH_MANAGER,
    "VetEdge Branch Manager",
    *ELEVATED_ROLES,
}


def _allowed_branches(user: str | None) -> list[str] | None:
    """Return None only for explicit global Branch access.

    Ordinary internal users with zero assignments intentionally receive an empty
    list so both native List and direct-document reads fail closed.
    """
    if user_has_global_branch_access(user):
        return None
    return sorted(
        {
            cstr(branch).strip()
            for branch in get_assigned_branches(user)
            if cstr(branch).strip()
        }
    )


def _role_allowed(user: str | None, permission_type: str | None) -> bool:
    roles = get_user_roles(user)
    if permission_type in {"create", "write", "delete", "cancel", "submit"}:
        return bool(roles & WRITE_ROLES)
    return bool(roles & READ_ROLES)


def get_outbreak_query(user: str | None = None) -> str | None:
    user = user or get_current_user()
    if (
        not user
        or user == "Guest"
        or is_portal_owner_user(user)
        or not is_internal_staff_user(user)
        or not _role_allowed(user, "read")
    ):
        return "1=0"

    allowed = _allowed_branches(user)
    if allowed is None:
        return None
    if not allowed:
        return "1=0"

    quoted = ", ".join(frappe.db.escape(branch) for branch in allowed)
    return f"`tab{DOCTYPE}`.`{BRANCH_FIELD}` in ({quoted})"


def has_outbreak_permission(
    doc,
    user: str | None = None,
    permission_type: str | None = None,
) -> bool:
    user = user or get_current_user()
    if (
        not user
        or user == "Guest"
        or is_portal_owner_user(user)
        or not is_internal_staff_user(user)
        or not _role_allowed(user, permission_type)
    ):
        return False

    if user_has_global_branch_access(user):
        return True

    allowed = _allowed_branches(user) or []
    if not allowed:
        return False

    # Frappe may check create permission before a new document has its Branch.
    # Role + at least one assigned Branch is sufficient here because the
    # controller validates the selected Branch before the document can save.
    if permission_type == "create" and not getattr(doc, "name", None):
        return True

    branch = cstr(doc.get(BRANCH_FIELD) if hasattr(doc, "get") else getattr(doc, BRANCH_FIELD, "") or "").strip()
    return bool(branch and branch in allowed)
