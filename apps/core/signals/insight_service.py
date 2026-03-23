"""
Phase 5 — Signal Insight Service: Read-only visibility into adaptive learning.

Provides a categorized view of what the system is learning from user feedback.
No control. No editing. No tuning.

Uses the same thresholds and recency window as the presenter's adaptive layer
to ensure what the user sees here matches what the system actually does.
"""

import logging
from datetime import timedelta

from django.db.models import Count, Q
from django.utils import timezone

from apps.core.signals.signal_presenter import (
    ADAPTIVE_MIN_FEEDBACK,
    ADAPTIVE_REINFORCE_RATIO,
    ADAPTIVE_SUPPRESS_RATIO,
    FEEDBACK_WINDOW_DAYS,
    ITEM_LABELS,
    PATTERN_MIN_FEEDBACK,
    PATTERN_REINFORCE_RATIO,
    PATTERN_SUPPRESS_RATIO,
)

logger = logging.getLogger(__name__)


def get_signal_insights(user) -> dict:
    """Get categorized feedback insights for a user.

    Returns:
        {
            "reinforced": [...],  # high yes ratio (signal-level)
            "suppressed": [...],  # high no ratio (signal-level)
            "neutral": [...],     # mixed or insufficient data
            "patterns": [...],    # cross-day pattern-level insights (Phase 5.2)
        }

    Each entry: {"domain": str, "item": str, "yes": int, "no": int, "ratio": float}
    """
    try:
        from apps.core.signals.models import SignalFeedback
    except ImportError:
        return {"reinforced": [], "suppressed": [], "neutral": [], "patterns": []}

    window_start = timezone.now() - timedelta(days=FEEDBACK_WINDOW_DAYS)

    try:
        stats_rows = list(
            SignalFeedback.objects
            .filter(
                user=user,
                signal_type="possible_completion",
                created_at__gte=window_start,
            )
            .values("domain", "item")
            .annotate(
                yes_count=Count("id", filter=Q(response="yes")),
                no_count=Count("id", filter=Q(response="no")),
            )
        )
    except Exception:
        logger.error("Insight service: failed to query feedback", exc_info=True)
        return {"reinforced": [], "suppressed": [], "neutral": [], "patterns": []}

    reinforced = []
    suppressed = []
    neutral = []

    for row in stats_rows:
        yes = row["yes_count"]
        no = row["no_count"]
        total = yes + no

        if total == 0:
            continue

        ratio = yes / total
        item_key = row["item"] or ""
        label = ITEM_LABELS.get(item_key, item_key or row["domain"])

        entry = {
            "domain": row["domain"],
            "item": item_key,
            "label": label,
            "yes": yes,
            "no": no,
            "ratio": round(ratio, 2),
        }

        if total >= ADAPTIVE_MIN_FEEDBACK and ratio >= ADAPTIVE_REINFORCE_RATIO:
            reinforced.append(entry)
        elif (
            total >= ADAPTIVE_MIN_FEEDBACK
            and no >= ADAPTIVE_MIN_FEEDBACK
            and (no / total) >= ADAPTIVE_SUPPRESS_RATIO
        ):
            suppressed.append(entry)
        else:
            neutral.append(entry)

    # Pattern-level insights (cross-day, same data, Phase 5.2 thresholds)
    patterns = _classify_patterns(stats_rows)

    return {
        "reinforced": reinforced,
        "suppressed": suppressed,
        "neutral": neutral,
        "patterns": patterns,
    }


def _classify_patterns(stats_rows: list) -> list:
    """Classify feedback data using pattern-level thresholds (Phase 5.2).

    Uses higher thresholds than signal-level:
    - Minimum 5 feedback records (vs 3)
    - Suppression ratio 80% (vs 75%)
    - Reinforcement ratio 75% (same)

    Returns list of pattern dicts with status field.
    """
    patterns = []

    for row in stats_rows:
        yes = row["yes_count"]
        no = row["no_count"]
        total = yes + no

        if total < PATTERN_MIN_FEEDBACK:
            continue

        ratio = yes / total
        item_key = row["item"] or ""
        domain = row["domain"]
        label = ITEM_LABELS.get(item_key, item_key or domain)

        # Determine pattern status
        if ratio >= PATTERN_REINFORCE_RATIO:
            status = "reinforced"
        elif no >= PATTERN_MIN_FEEDBACK and (no / total) >= PATTERN_SUPPRESS_RATIO:
            status = "suppressed"
        else:
            status = "neutral"

        patterns.append({
            "pattern": f"{domain}:{item_key}",
            "domain": domain,
            "item": item_key,
            "label": label,
            "yes": yes,
            "no": no,
            "ratio": round(ratio, 2),
            "status": status,
        })

    return patterns
