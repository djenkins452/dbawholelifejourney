# ==============================================================================
# File: apps/health/services/weight_queries.py
# Layer 1 — Canonical WEIGHT retrieval BY POINT IN TIME (mirrors sleep_queries).
# `on_date(user, target_date)` returns the authoritative weight for a specific day —
# the LATEST reading recorded that day, in the user's local timezone — or None when
# there is no reading. Never inferred, never a nearest-day substitute.
# ==============================================================================
from datetime import datetime, time, timedelta


def on_date(user, target_date):
    """The authoritative weight (lb) recorded on `target_date` (user-local day), or
    None. Uses a local-day datetime range so a late-evening reading is dated correctly."""
    from django.utils import timezone as djtz
    from apps.health.models import WeightEntry
    try:
        from apps.core.utils import _get_user_tz
        tz = _get_user_tz(user)
    except Exception:
        tz = djtz.get_current_timezone()
    start = djtz.make_aware(datetime.combine(target_date, time.min), tz)
    end = start + timedelta(days=1)
    e = (WeightEntry.objects.filter(user=user, recorded_at__gte=start, recorded_at__lt=end)
         .order_by("-recorded_at").first())
    if e is None:
        return None
    return {
        "date": target_date,
        "value_lb": round(float(e.value_in_lb), 1),
        "recorded_at": e.recorded_at,
        "unit": "lb",
    }
