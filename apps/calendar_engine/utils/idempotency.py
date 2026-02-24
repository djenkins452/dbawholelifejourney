"""
Deterministic idempotency key generation for CalendarEvent.

Every CalendarEvent must have an idempotency_key computed from:
    SHA-256(user_id:normalized_title:start_dt.isoformat())

This key is NOT random. It is deterministic and reproducible.
"""

import hashlib


def compute_idempotency_key(user_id, title, start_dt):
    """
    Compute a deterministic SHA-256 idempotency key.

    Args:
        user_id: int — the user's primary key
        title: str — the event title (will be normalized)
        start_dt: datetime — the event start (must be timezone-aware)

    Returns:
        str — 64-character hex SHA-256 digest
    """
    normalized_title = " ".join(title.strip().split()).lower()
    return hashlib.sha256(
        f"{user_id}:{normalized_title}:{start_dt.isoformat()}".encode()
    ).hexdigest()
