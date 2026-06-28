"""
Platform capability: CONFIDENCE (Architecture Law 2).

How much should a consumer trust a piece of truth? A domain-agnostic verdict —
high / medium / low / none — that travels with every truth object alongside its
Freshness verdict. Beth READS confidence (she never invents a hedge); a low-confidence
answer is narrated with appropriate qualification, a none-confidence answer is honest
absence.

Confidence is derived deterministically from the signals that actually erode trust:
- freshness (stale/pending/missing data is less trustworthy than current),
- coverage (an average over 2 of 7 days is weaker than over 7 of 7),
- source (device-synced > manual > estimated/derived).

Implemented once here; consumed by Current Truth (`confidence_from_freshness`) and
History (`confidence_from_coverage`). Composable: `combine()` takes the weakest.
"""
from apps.core.truth.freshness import (CURRENT, MISSING, PARTIAL, PENDING, STALE)

# Canonical verdicts (ordered weakest → strongest for combine()).
NONE = "none"
LOW = "low"
MEDIUM = "medium"
HIGH = "high"

VERDICTS = (NONE, LOW, MEDIUM, HIGH)
_RANK = {NONE: 0, LOW: 1, MEDIUM: 2, HIGH: 3}

# Source reliability ceilings.
SOURCE_CONFIDENCE = {
    "device": HIGH, "synced": HIGH, "api": HIGH,
    "manual": MEDIUM, "user": MEDIUM,
    "estimated": LOW, "derived": LOW, "inferred": LOW,
}


def confidence_from_freshness(freshness):
    """A point/current value's confidence, from its freshness verdict."""
    return {
        CURRENT: HIGH,
        PARTIAL: MEDIUM,     # today, still accruing — directionally right, not final
        STALE: LOW,
        PENDING: NONE,
        MISSING: NONE,
    }.get(freshness, LOW)


def confidence_from_coverage(present, total):
    """A series/aggregate's confidence, from how much of the period has data."""
    if not total or present <= 0:
        return NONE
    ratio = present / total
    if ratio >= 0.8:
        return HIGH
    if ratio >= 0.4:
        return MEDIUM
    return LOW


def confidence_from_source(source):
    """Ceiling implied by where the value came from (unknown source → MEDIUM)."""
    if not source:
        return MEDIUM
    low = str(source).lower()
    for key, verdict in SOURCE_CONFIDENCE.items():
        if key in low:
            return verdict
    return MEDIUM


def combine(*verdicts):
    """The WEAKEST of several confidence verdicts (trust is bounded by its weakest
    input). Empty → NONE."""
    present = [v for v in verdicts if v in _RANK]
    if not present:
        return NONE
    return min(present, key=lambda v: _RANK[v])


def is_at_least(verdict, floor):
    return _RANK.get(verdict, 0) >= _RANK.get(floor, 0)
