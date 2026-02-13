"""
Duplicate detection for lab results.

Uses SHA-256 fingerprinting to detect exact duplicates.
"""

import hashlib
import logging

from apps.medical.models import LabResult

logger = logging.getLogger(__name__)


def compute_fingerprint(user_id, canonical_test_id, raw_test_name,
                        collected_at, value_text, unit, provider=""):
    """
    Compute deterministic fingerprint for a lab result.

    fingerprint = sha256(
        user_id + (canonical_test_id OR normalized_raw_test_name) +
        collected_at_iso + value_normalized + unit_normalized + provider
    )
    """
    parts = [
        str(user_id),
        str(canonical_test_id) if canonical_test_id else raw_test_name.strip().lower(),
        collected_at.isoformat() if collected_at else "",
        value_text.strip().lower() if value_text else "",
        unit.strip().lower() if unit else "",
        provider.strip().lower() if provider else "",
    ]
    raw = "|".join(parts)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def is_duplicate(fingerprint: str, user_id) -> bool:
    """
    Check if an active result with this fingerprint already exists for this user.

    Uses application-level check (not DB constraint) for clear reporting.
    Only checks active records — soft-deleted results should not block re-import.
    """
    return LabResult.objects.filter(
        user_id=user_id,
        fingerprint=fingerprint,
    ).exists()


def check_batch_duplicates(candidates: list[dict], user_id) -> tuple[list[dict], list[dict]]:
    """
    Check a batch of candidates for duplicates.

    Args:
        candidates: list of dicts with fingerprint info
        user_id: the user's ID

    Returns:
        (unique_candidates, duplicate_candidates)
    """
    # Get all existing active fingerprints for this user in one query.
    # Only checks active records — soft-deleted results should not block re-import.
    existing_fps = set(
        LabResult.objects.filter(user_id=user_id)
        .values_list("fingerprint", flat=True)
    )

    unique = []
    duplicates = []
    seen_fps = set()

    for candidate in candidates:
        fp = candidate.get("fingerprint", "")
        if fp in existing_fps or fp in seen_fps:
            duplicates.append(candidate)
        else:
            unique.append(candidate)
            seen_fps.add(fp)

    return unique, duplicates
