from app.models.user import User
from app.schemas.admin import UpdateUserRequest


def _is_visible(actor: User, target: User) -> bool:
    """Soft-deleted users are visible only to superadmin."""
    if not target.is_deleted:
        return True
    return actor.role == "superadmin"


def _can_admin_modify(actor: User, target: User) -> bool:
    """Return True iff `actor` is allowed to PATCH/operate on `target`.

    Rules:
      - superadmin: can modify anyone (including themselves elsewhere is checked separately).
      - admin: cannot modify superadmin, cannot modify themselves.
      - any other role: cannot modify anyone.
    """
    if actor.role == "superadmin":
        return True
    if actor.role != "admin":
        return False
    if target.role == "superadmin":
        return False
    if target.id == actor.id:
        return False
    return True


def _diff_changes(target: User, body: UpdateUserRequest, *, include_limits: bool = False) -> dict:
    changes: dict = {}
    if body.role is not None and body.role != target.role:
        changes["role"] = [target.role, body.role]
    if body.permissions is not None and body.permissions != target.permissions:
        changes["permissions"] = [dict(target.permissions), dict(body.permissions)]
    # Limits are editable only by superadmin for regular users (see update_user);
    # only diff/log them when the caller is actually allowed to apply them.
    if include_limits and body.limits is not None and body.limits != target.limits:
        changes["limits"] = [dict(target.limits), dict(body.limits)]
    if body.is_active is not None and body.is_active != target.is_active:
        changes["is_active"] = [target.is_active, body.is_active]
    return changes
