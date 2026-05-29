"""Shared Pydantic field types."""
from datetime import datetime, timezone
from typing import Annotated

from pydantic import PlainSerializer


def _utc_iso(dt: datetime) -> str:
    """Serialize a (possibly naive) UTC datetime as ISO-8601 with a 'Z' suffix.

    SQLite hands datetimes back naive, but they represent UTC. Without an
    explicit designator on the wire the frontend's ``new Date(iso)`` parses
    them as *local* time, shifting every displayed/compared timestamp by the
    client's UTC offset. Tagging them with 'Z' makes the contract
    unambiguous so every consumer reads true UTC.
    """
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    else:
        dt = dt.astimezone(timezone.utc)
    return dt.isoformat().replace("+00:00", "Z")


# A datetime that always serializes to JSON as UTC ISO-8601 with a 'Z' suffix.
UtcDatetime = Annotated[datetime, PlainSerializer(_utc_iso, return_type=str, when_used="json")]
