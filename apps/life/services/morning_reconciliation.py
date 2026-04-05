"""
Morning Reconciliation Service — identify yesterday's unresolved routine items.

Surfaces missing execution truth so CoS can ask the user to confirm what
actually happened.  Runs once per day on first dashboard load (morning).

Architecture contract:
  - CoS NEVER infers truth
  - CoS NEVER auto-completes
  - CoS ONLY asks and records user input
  - All updates flow through existing toggle_routine_completion / skip_routine
"""

import logging
from datetime import timedelta

from django.core.cache import cache
from django.utils import timezone

logger = logging.getLogger(__name__)

# Max items to surface per day (sorted by time ascending)
MAX_RECONCILIATION_ITEMS = 5

# Cache key template — one per user per day
_CACHE_KEY = "wlj:reconcile:{user_id}:{date}"

# Cache TTL — 24 hours (auto-expires when date changes)
_CACHE_TTL = 86400


def _reconciliation_cache_key(user_id, date_str):
    return _CACHE_KEY.format(user_id=user_id, date=date_str)


def get_yesterdays_missing_items(user):
    """Find yesterday's routine items that have no completion record.

    Returns a list of dicts suitable for rendering in the reconciliation UI:
    [
        {
            "schedule_id": int,
            "label": str,        # item name
            "routine_name": str,  # parent routine name
            "scheduled_time": str,  # e.g., "6:15 AM"
        },
        ...
    ]

    Filters:
    - Binary routines only (not activity-based)
    - Excludes completed and skipped items
    - Max 5 items, sorted by scheduled_time ascending
    """
    from apps.core.utils import get_user_today
    from apps.life.models import Routine, RoutineLog

    user_today = get_user_today(user)
    yesterday = user_today - timedelta(days=1)
    weekday = yesterday.weekday()

    active_routines = Routine.objects.filter(
        user=user, is_active=True,
    ).prefetch_related('items')

    # Collect applicable binary schedules for yesterday
    applicable = []
    for routine in active_routines:
        for item in routine.items.filter(is_active=True):
            # Binary routines only — activity-based auto-complete via signals
            if getattr(item, 'routine_type', 'binary') == 'activity':
                continue

            if item.specific_date:
                if item.specific_date != yesterday:
                    continue
            elif not item.applies_to_day(weekday):
                continue

            applicable.append((routine, item))

    if not applicable:
        return []

    schedule_ids = [item.id for _, item in applicable]

    # Fetch existing logs for yesterday
    resolved_ids = set(
        RoutineLog.objects.filter(
            schedule_id__in=schedule_ids,
            scheduled_date=yesterday,
            log_status__in=('completed', 'completed_late', 'skipped'),
        ).values_list('schedule_id', flat=True)
    )

    # Missing = applicable but no resolved log
    missing = []
    for routine, item in applicable:
        if item.id in resolved_ids:
            continue
        time_display = (
            item.scheduled_time.strftime('%I:%M %p').lstrip('0')
            if item.scheduled_time else ''
        )
        missing.append({
            'schedule_id': item.id,
            'label': item.name,
            'routine_name': routine.name,
            'scheduled_time': time_display,
            'sort_key': item.scheduled_time or None,
        })

    # Sort by scheduled time ascending, cap at MAX
    missing.sort(key=lambda x: x['sort_key'] or '')
    for m in missing:
        del m['sort_key']

    return missing[:MAX_RECONCILIATION_ITEMS]


def should_show_reconciliation(user):
    """Check if reconciliation should show for this user today.

    Returns True if:
    - It's morning (before noon in user's timezone)
    - Reconciliation hasn't been dismissed/completed today
    - There are missing items from yesterday

    Uses cache to ensure once-per-day idempotency.
    """
    from apps.core.utils import get_user_now, get_user_today

    user_now = get_user_now(user)
    user_today = get_user_today(user)

    # Only show in morning (before noon user time)
    if user_now.hour >= 12:
        return False

    # Check cache — has user already seen/dismissed today?
    cache_key = _reconciliation_cache_key(user.pk, user_today.isoformat())
    if cache.get(cache_key):
        return False

    return True


def mark_reconciliation_shown(user):
    """Mark that reconciliation was shown/completed for today.

    Prevents repeat prompts for the rest of the day.
    """
    from apps.core.utils import get_user_today

    user_today = get_user_today(user)
    cache_key = _reconciliation_cache_key(user.pk, user_today.isoformat())
    cache.set(cache_key, True, _CACHE_TTL)


def get_reconciliation_context(user):
    """Build full reconciliation context for the dashboard.

    Returns dict with:
        show: bool — whether to render the reconciliation section
        items: list — missing items (empty if show=False)
        yesterday_date: str — formatted date string
    """
    if not should_show_reconciliation(user):
        return {'show': False, 'items': [], 'yesterday_date': ''}

    items = get_yesterdays_missing_items(user)
    if not items:
        # Nothing missing — mark as done so we don't recheck
        mark_reconciliation_shown(user)
        return {'show': False, 'items': [], 'yesterday_date': ''}

    from apps.core.utils import get_user_today
    yesterday = get_user_today(user) - timedelta(days=1)

    return {
        'show': True,
        'items': items,
        'yesterday_date': yesterday.strftime('%A, %B %-d'),
    }
