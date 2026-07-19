"""The Mirror — a spiritual biography, composed from truth WLJ already owns.

NOT analytics. NOT a dashboard. A gentle, honest reflection of a life being
formed: journeys walked, prayers He's answered, what a person keeps bringing to
Him, verses returned to, milestones marked — so someone can look back and
recognize God's work for themselves.

Architectural honesty (non-negotiable):
  • Deterministic and read-only. WLJ owns the truth; this only reflects it.
  • It NEVER claims what God did ("God changed you"). It speaks in grounded,
    observational language ("Looking back…", "You've returned to…", "He answered
    prayers you named…") and lets the person draw the conclusion.
  • The full aggregation is HEAVY (it reads across a person's whole history), so
    it is computed in a BACKGROUND task and cached. The request path only ever
    reads the cache (get_cached_mirror) — never computes inline.
"""

from __future__ import annotations

import datetime as _dt
from typing import Any, Optional

from django.core.cache import cache
from django.db.models import Count
from django.utils import timezone

_CACHE_KEY = "wlj:faith:mirror:{uid}"
_CACHE_TTL = 60 * 60 * 12  # 12h — a reflection doesn't need to be minute-fresh


def cache_key(user_id: int) -> str:
    return _CACHE_KEY.format(uid=user_id)


def get_cached_mirror(user) -> Optional[dict[str, Any]]:
    """Request-path-safe read. Returns the cached reflection or None (never computes)."""
    return cache.get(cache_key(user.id))


def compute_and_cache(user) -> dict[str, Any]:
    """Compute the reflection and cache it. Called from the background task."""
    data = compute_mirror(user)
    cache.set(cache_key(user.id), data, _CACHE_TTL)
    return data


def _iso(dt) -> Optional[str]:
    return dt.isoformat() if dt else None


def _when(dt) -> str:
    """A gentle display like 'March 2025' (or '' if unknown). Handles date/datetime."""
    if not dt:
        return ""
    if isinstance(dt, _dt.datetime) and timezone.is_aware(dt):
        dt = timezone.localtime(dt)
    return dt.strftime("%B %Y")


def compute_mirror(user) -> dict[str, Any]:
    """The heavy aggregation. Runs in a Celery worker, not on the request path."""
    from apps.faith.models import (
        FaithMilestone,
        PrayerRequest,
        SavedVerse,
        UserReadingPlan,
    )

    now = timezone.now()

    # ── When the walk began (earliest durable trace) ──
    began_dt = None
    candidates = []
    first_plan = UserReadingPlan.objects.filter(user=user).order_by("started_at").values_list("started_at", flat=True).first()
    if first_plan:
        candidates.append(first_plan)
    first_prayer = PrayerRequest.objects.filter(user=user).order_by("created_at").values_list("created_at", flat=True).first()
    if first_prayer:
        candidates.append(first_prayer)
    try:
        from apps.faith.journey.models import UserJourney
        first_journey = UserJourney.objects.filter(user=user).order_by("started_at").values_list("started_at", flat=True).first()
        if first_journey:
            candidates.append(first_journey)
    except Exception:
        pass
    if candidates:
        began_dt = min(candidates)
    began = None
    if began_dt:
        months = max(0, int((now - began_dt).days / 30.44))
        began = {"iso": _iso(began_dt), "months": months}

    # ── Journeys finished — in order (what prepared the heart for what came next) ──
    journeys = []
    for up in (
        UserReadingPlan.objects.filter(user=user, plan_status="completed")
        .select_related("template").order_by("completed_at")
    ):
        journeys.append({
            "title": up.template.title,
            "when_iso": _iso(up.completed_at),
            "when": _when(up.completed_at),
            "kind": "Reading plan",
        })
    try:
        from apps.faith.journey.models import UserJourney
        for uj in (
            UserJourney.objects.filter(user=user, journey_status="completed")
            .select_related("journey_path").order_by("completed_at")
        ):
            journeys.append({
                "title": uj.journey_path.name,
                "when_iso": _iso(uj.completed_at),
                "when": _when(uj.completed_at),
                "kind": "Guided journey",
            })
    except Exception:
        pass
    journeys.sort(key=lambda j: j["when_iso"] or "")

    # ── Prayers He's answered ──
    answered_qs = PrayerRequest.objects.filter(user=user, is_answered=True).order_by("-answered_at")
    answered = {
        "count": answered_qs.count(),
        "recent": [
            {
                "title": p.title,
                "subject": (p.person_or_situation or "").strip(),
                "when_iso": _iso(p.answered_at),
                "when": _when(p.answered_at),
                "answer": (getattr(p, "answer_notes_plain", "") or "").strip()[:160],
            }
            for p in answered_qs[:4]
        ],
    }

    # ── What you keep bringing to Him (recurring prayer subjects) ──
    recurring = []
    for row in (
        PrayerRequest.objects.filter(user=user)
        .exclude(person_or_situation="")
        .values("person_or_situation")
        .annotate(c=Count("id"))
        .filter(c__gte=2)
        .order_by("-c")[:4]
    ):
        recurring.append({"subject": row["person_or_situation"].strip(), "count": row["c"]})

    # ── Verses you've returned to ──
    verses = [
        {"reference": v.reference, "text": (v.text or "").strip()[:180]}
        for v in SavedVerse.objects.filter(user=user).order_by("-created_at")[:5]
    ]

    # ── Milestones you've marked ──
    milestones = [
        {"title": m.title, "when_iso": _iso(getattr(m, "date", None)), "when": _when(getattr(m, "date", None)), "type": m.milestone_type}
        for m in FaithMilestone.objects.filter(user=user).order_by("date")[:8]
    ]

    has_content = bool(journeys or answered["count"] or recurring or verses or milestones)

    return {
        "generated_at": _iso(now),
        "began": began,
        "journeys": journeys,
        "answered_prayers": answered,
        "recurring_prayers": recurring,
        "verses": verses,
        "milestones": milestones,
        "has_content": has_content,
        # Honest gap note: longitudinal journal-theme analysis (how a theme
        # changed over time) is deferred to a later phase — it needs heavier NLP
        # over the journal corpus and will slot into this same cached payload.
    }
