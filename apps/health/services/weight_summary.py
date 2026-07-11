# ==============================================================================
# File: apps/health/services/weight_summary.py
# Project: Whole Life Journey - Django 5.x Personal Wellness/Journaling App
# Description: Deterministic Weight overview facts — the SINGLE source shared by the
#              Weight page stats and the assistant's Current Context page summary.
# Owner: Danny Jenkins (admin@wholelifejourney.com)
# ==============================================================================
"""One deterministic Weight summary, consumed by BOTH the Weight page (WeightListView)
and the Current Context page-summary provider, so the assistant can never contradict the
numbers on screen (one source of truth — no re-derivation, no drift).

Request-path-safe: a handful of aggregate reads over the user's own WeightEntry rows.
"""
from datetime import timedelta

from django.utils import timezone

from apps.health.models import WeightEntry

# The rolling window for the "(30d)" stats the page shows. Genuine 30 DAYS (the label's
# promise), computed once here so page + assistant agree.
WINDOW_DAYS = 30


def build_weight_summary(user, *, point_date=None):
    """Deterministic Weight facts for `user`, or {} when there are no entries.

    Returns: current_lb/current_at, first_lb/first_at, total_change_lb, count,
    avg_30d_lb/low_30d_lb/high_30d_lb + window_count/window_days, and (optional)
    point_lb/point_at for a selected chart point. All weights are lb, rounded to 0.1.
    USER-SCOPED (the default manager already excludes soft-deleted rows)."""
    qs = WeightEntry.objects.filter(user=user)
    latest = qs.order_by("-recorded_at").first()
    if latest is None:
        return {}
    oldest = qs.order_by("recorded_at").first()
    count = qs.count()

    current_lb = round(float(latest.value_in_lb), 1)
    first_lb = round(float(oldest.value_in_lb), 1)
    single = oldest.pk == latest.pk

    window_start = timezone.now() - timedelta(days=WINDOW_DAYS)
    win_vals = [float(e.value_in_lb) for e in qs.filter(recorded_at__gte=window_start)]

    facts = {
        "current_lb": current_lb,
        "current_at": latest.recorded_at,
        "first_lb": first_lb,
        "first_at": oldest.recorded_at,
        "count": count,
        "total_change_lb": None if single else round(current_lb - first_lb, 1),
        "window_days": WINDOW_DAYS,
        "window_count": len(win_vals),
        "avg_30d_lb": round(sum(win_vals) / len(win_vals), 1) if win_vals else None,
        "low_30d_lb": round(min(win_vals), 1) if win_vals else None,
        "high_30d_lb": round(max(win_vals), 1) if win_vals else None,
    }

    # Optional selected point — a deterministic lookup of the entry on that calendar date.
    if point_date:
        pt = qs.filter(recorded_at__date=point_date).order_by("-recorded_at").first()
        if pt is not None:
            facts["point_lb"] = round(float(pt.value_in_lb), 1)
            facts["point_at"] = pt.recorded_at
    return facts
