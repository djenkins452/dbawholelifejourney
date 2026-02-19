"""
Phase 5 — Governance Display Filter.

Controls what intelligence items are shown to the user per day.
This is separate from noise_budget.py (which caps generation).
This caps what actually gets DISPLAYED.

Rules:
    - Max 6 items per day across all channels
    - At-risk non-negotiables always included (priority slot)
    - 48-hour repeat suppression (same dedupe_key within 48h)
    - Non-negotiable items get priority slots

Public API:
    - filter_for_display(user, items) -> list
    - get_display_count_today(user) -> int
    - record_display(user, item_type, item_id) -> None
"""

import logging
from datetime import timedelta

from django.utils import timezone

logger = logging.getLogger(__name__)

# Display budget
MAX_DISPLAY_PER_DAY = 6
REPEAT_SUPPRESSION_HOURS = 48
PRIORITY_SLOTS = 2  # Reserved for non-negotiable at-risk items


def filter_for_display(user, items):
    """
    Filter a list of displayable items through the governance display budget.

    Items should be dicts with at minimum:
        - 'id': unique identifier
        - 'type': 'insight', 'guidance', 'briefing', 'notification'
        - 'dedupe_key': string for suppression (optional)
        - 'is_non_negotiable_risk': bool (optional, gets priority)
        - 'severity': 'critical', 'warning', 'info' (optional)

    Returns:
        list of items that pass the display filter (max MAX_DISPLAY_PER_DAY).
    """
    if not items:
        return []

    # Get today's display count
    displayed_today = get_display_count_today(user)
    remaining = max(0, MAX_DISPLAY_PER_DAY - displayed_today)

    if remaining == 0:
        # Only allow critical items if budget exhausted
        return [i for i in items if i.get('severity') == 'critical'][:2]

    # Get recent dedupe keys for suppression
    recent_keys = _get_recent_display_keys(user)

    # Split into priority (non-negotiable at-risk) and regular
    priority_items = []
    regular_items = []

    for item in items:
        # 48h suppression check
        dedupe = item.get('dedupe_key', '')
        if dedupe and dedupe in recent_keys:
            continue

        if item.get('is_non_negotiable_risk') or item.get('severity') == 'critical':
            priority_items.append(item)
        else:
            regular_items.append(item)

    # Allocate: priority items first, then fill with regular
    result = []
    priority_count = min(len(priority_items), PRIORITY_SLOTS, remaining)
    result.extend(priority_items[:priority_count])
    remaining -= priority_count

    regular_count = min(len(regular_items), remaining)
    result.extend(regular_items[:regular_count])

    return result


def get_display_count_today(user):
    """Get how many items have been displayed to the user today."""
    try:
        from apps.core.ai_state.state_engine import get_state_value
        count = get_state_value(user, 'governance.display_count_today', 0)
        return int(count) if count else 0
    except Exception:
        return 0


def record_display(user, item_type, item_id, dedupe_key=''):
    """
    Record that an item was displayed to the user.

    Args:
        user: Django User instance.
        item_type: str — 'insight', 'guidance', etc.
        item_id: int or str — ID of the item.
        dedupe_key: str — for 48h repeat suppression.
    """
    try:
        from apps.core.ai_state.state_engine import set_state_value, get_state_value

        # Increment today's count
        current = get_state_value(user, 'governance.display_count_today', 0)
        set_state_value(user, 'governance.display_count_today', int(current or 0) + 1)

        # Record dedupe key with timestamp for 48h suppression
        if dedupe_key:
            recent = get_state_value(user, 'governance.recent_display_keys', {}) or {}
            recent[dedupe_key] = timezone.now().isoformat()

            # Prune old keys (>48h)
            cutoff = timezone.now() - timedelta(hours=REPEAT_SUPPRESSION_HOURS)
            pruned = {
                k: v for k, v in recent.items()
                if _parse_iso(v) and _parse_iso(v) > cutoff
            }
            set_state_value(user, 'governance.recent_display_keys', pruned)

    except Exception as e:
        logger.debug("Display record failed: %s", e)


def reset_daily_display_count(user):
    """Reset the daily display count (called at start of day)."""
    try:
        from apps.core.ai_state.state_engine import set_state_value
        set_state_value(user, 'governance.display_count_today', 0)
    except Exception:
        pass


# =============================================================================
# HELPERS
# =============================================================================


def _get_recent_display_keys(user):
    """Get dedupe keys displayed in the last 48 hours."""
    try:
        from apps.core.ai_state.state_engine import get_state_value
        recent = get_state_value(user, 'governance.recent_display_keys', {}) or {}
        cutoff = timezone.now() - timedelta(hours=REPEAT_SUPPRESSION_HOURS)
        return {
            k for k, v in recent.items()
            if _parse_iso(v) and _parse_iso(v) > cutoff
        }
    except Exception:
        return set()


def _parse_iso(iso_str):
    """Parse ISO datetime string, returning None on failure."""
    try:
        from django.utils.dateparse import parse_datetime
        return parse_datetime(iso_str)
    except Exception:
        return None
