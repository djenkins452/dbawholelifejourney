"""
Deterministic idempotency key generation for CalendarEvent.

ONE function. No inline hashing elsewhere.
SHA-256. Fixed-length hex string.

Priority 1 — Source-backed events: hash(user_id, source_type, source_id)
             Stable across title edits, time changes, and all mutable fields.
             The source identity IS the event identity.

Priority 2 — Manual events: hash(user_id, start_utc_seconds, end_utc_seconds,
             source_type, canonical_title)
             Deterministic order. UTC-normalized. Microseconds stripped.
"""

import datetime
import hashlib


def compute_idempotency_key(
    user_id,
    title,
    start_dt,
    end_dt=None,
    source_type='none',
    source_id='',
):
    """
    Compute a deterministic SHA-256 idempotency key.

    Args:
        user_id: int — user's primary key
        title: str — event title (used only for Priority 2 / manual events)
        start_dt: datetime — event start (timezone-aware)
        end_dt: datetime | None — event end (timezone-aware); defaults to start_dt
        source_type: str — e.g. 'task', 'goal', 'habit', 'none'
        source_id: str — PK of source object, or '' for manual events

    Returns:
        str — 64-character hex SHA-256 digest
    """
    if source_id:
        # PRIORITY 1: Source-backed — identity is (user, source_type, source_id).
        # Title, start_dt, end_dt are NOT included. This key is stable
        # across title edits, time changes, and all mutable field updates.
        payload = f"{user_id}:{source_type}:{source_id}"
    else:
        # PRIORITY 2: Manual — include UTC-normalized times + title
        canonical_title = " ".join(title.strip().split()).lower()
        utc_start = start_dt.astimezone(datetime.timezone.utc).replace(microsecond=0)
        start_ts = int(utc_start.timestamp())

        if end_dt:
            utc_end = end_dt.astimezone(datetime.timezone.utc).replace(microsecond=0)
            end_ts = int(utc_end.timestamp())
        else:
            end_ts = start_ts

        payload = f"{user_id}:{start_ts}:{end_ts}:{source_type}:{canonical_title}"

    return hashlib.sha256(payload.encode()).hexdigest()
