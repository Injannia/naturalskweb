"""Daily-quota policy helpers.

Limits apply only to regular users. Admins and superadmins have unlimited
daily usage — quota checks are bypassed for them and the API reports their
limit as the sentinel -1 (rendered as ∞ by the frontend).
"""
from app.models.user import User

UNLIMITED_ROLES = ("admin", "superadmin")

# Sentinel limit value meaning "no cap". Frontend shows ∞ for limit < 0.
UNLIMITED = -1


def has_unlimited_quota(user: User) -> bool:
    """True when the user's role is exempt from daily quotas."""
    return user.role in UNLIMITED_ROLES
