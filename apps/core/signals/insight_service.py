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
)

logger = logging.getLogger(__name__)


def get_signal_insights(user) -> dict:
    """Get categorized feedback insights for a user.

    Returns:
        {
            "reinforced": [...],  # high yes ratio
            "suppressed": [...],  # high no ratio
            "neutral": [...],     # mixed or insufficient data
        }

    Each entry: {"domain": str, "item": str, "yes": int, "no": int, "ratio": float}
    """
    try:
        from apps.core.signals.models import SignalFeedback
    except ImportError:
        return {"reinforced": [], "suppressed": [], "neutral": []}

    window_start = timezone.now() - timedelta(days=FEEDBACK_WINDOW_DAYS)

    try:
        stats_qs = (
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
        return {"reinforced": [], "suppressed": [], "neutral": []}

    reinforced = []
    suppressed = []
    neutral = []

    for row in stats_qs:
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

    return {
        "reinforced": reinforced,
        "suppressed": suppressed,
        "neutral": neutral,
    }
