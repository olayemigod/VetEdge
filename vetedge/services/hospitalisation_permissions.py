from __future__ import annotations

import frappe
from frappe.utils import cstr

from vetedge.services.permissions import (
    get_assigned_branches,
    get_current_user,
    is_internal_staff_user,
    is_portal_owner_user,
    user_has_global_branch_access,
)


DOCTYPE = "Veterinary Hospitalisation"
BRANCH_FIELD = "service_branch"


def _allowed_branches(user: str | None) -> list[str] | None:
    """Return None only for explicit global Branch access; otherwise a bounded set.

    An empty list is intentionally fail-closed for ordinary internal users.
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


def get_hospitalisation_query(user: str | None = None) -> str | None:
    user = user or get_current_user()
    if (
        not user
        or user == "Guest"
        or is_portal_owner_user(user)
        or not is_internal_staff_user(user)
    ):
        return "1=0"

    allowed = _allowed_branches(user)
    if allowed is None:
        return None
    if not allowed:
        return "1=0"

    quoted = ", ".join(frappe.db.escape(branch) for branch in allowed)
    return f"`tab{DOCTYPE}`.`{BRANCH_FIELD}` in ({quoted})"


def has_hospitalisation_permission(
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
    ):
        return False

    if user_has_global_branch_access(user):
        return True

    allowed = _allowed_branches(user) or []
    if not allowed:
        return False

    branch = cstr(doc.get(BRANCH_FIELD) if hasattr(doc, "get") else getattr(doc, BRANCH_FIELD, "") or "").strip()
    return bool(branch and branch in allowed)
