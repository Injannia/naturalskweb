"""
In-memory blacklist for revoked JWT access tokens.

Stores JTI (JWT ID) strings of invalidated access tokens.
The set grows only until the process restarts; for a multi-process
deployment, replace this with a shared Redis/DB store.
"""

import logging
from datetime import datetime, timezone

logger = logging.getLogger("naturalsk.auth")

# {jti: expiry_timestamp_utc}  — kept so cleanup can remove expired entries
_blacklist: dict[str, float] = {}


def add(jti: str, exp: float) -> None:
    """Add a JTI to the blacklist. exp is the Unix timestamp when the token expires."""
    _blacklist[jti] = exp
    logger.debug("Token blacklisted: jti=%s", jti)


def contains(jti: str) -> bool:
    """Return True if the JTI is present in the blacklist."""
    return jti in _blacklist


def cleanup() -> None:
    """Remove entries whose tokens have already expired (they cannot be replayed anyway)."""
    now = datetime.now(timezone.utc).timestamp()
    expired = [jti for jti, exp in _blacklist.items() if exp < now]
    for jti in expired:
        del _blacklist[jti]
    if expired:
        logger.debug("Token blacklist: removed %d expired entries", len(expired))
