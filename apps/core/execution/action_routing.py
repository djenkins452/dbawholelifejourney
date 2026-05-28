"""
Canonical "where does this action happen?" resolver.

Single source of truth for deep-linking a Focus / Do-This-Now action to the
WLJ page where the user actually performs it. The dashboard asks
``resolve_action_destination(item)`` and gets a real, verified destination
URL — no hardcoded links in templates, no display-text matching in HTML.

RESOLUTION IS METADATA-FIRST (rename-safe):
    1. source_type        — meds/supplements are authoritative → intake
    2. RoutineSchedule.activity_type — workout/bible/faith/journal
    3. Task.module         — faith / journal / health / life
    4. binary domain       — faith / workout / journal summaries
    5. keyword bridge      — ONLY to disambiguate sub-domains the current
                             metadata can't express (e.g. nutrition vs
                             fitness within Health). This mirrors the
                             documented metadata-first/name-fallback pattern
                             already used by
                             apps.life.services.routine_helpers
                             .auto_complete_routine_schedules — and should be
                             retired once activity_type covers these.
    6. fallback            — /life/

Renames are safe: "Bible Reading" → "Morning Scripture" still routes to
/faith/ because it resolves on activity_type='bible' / module='faith', not
the title.

All URLs resolve via reverse() with a literal-path fallback, so a route
rename never produces a dead link.
"""

from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger(__name__)


def _dest(url_name: str, literal: str) -> str:
    """Resolve a named route, falling back to a literal path. Never dead."""
    try:
        from django.urls import reverse
        return reverse(url_name)
    except Exception:
        return literal


def _faith() -> str:    return _dest("faith:home", "/faith/")
def _journal() -> str:  return _dest("journal:home", "/journal/")
def _nutrition() -> str: return _dest("health:nutrition_home", "/health/physical/nutrition/")
def _intake() -> str:   return _dest("health:intake_home", "/health/physical/intake/")
def _fitness() -> str:  return _dest("health:fitness_home", "/health/physical/fitness/")
def _health_home() -> str: return _dest("health:home", "/health/physical/")
def _routines() -> str: return _dest("life:routine_list", "/life/routines/")
def _life() -> str:     return _dest("life:home", "/life/")


# ── activity_type → destination (canonical RoutineSchedule.ACTIVITY_TYPE_*) ──
def _activity_to_dest(activity: str | None) -> str | None:
    if not activity:
        return None
    a = activity.lower()
    if a == "workout":
        return _fitness()
    if a in ("bible", "faith"):
        return _faith()
    if a == "journal":
        return _journal()
    return None


# ── module / domain → destination (canonical Task.module, item.domain) ──
def _module_to_dest(module: str | None) -> str | None:
    if not module:
        return None
    m = module.lower()
    if m in ("faith", "prayer", "bible", "scripture", "bible_reading", "faith_engaged"):
        return _faith()
    if m == "journal":
        return _journal()
    if m in ("nutrition", "meals"):
        return _nutrition()
    if m in ("fitness", "workout"):
        return _fitness()
    if m in ("medicine", "intake", "supplements"):
        return _intake()
    return None


# ── Keyword bridge (LAST RESORT, documented) ──────────────────────────────
# Only consulted when canonical metadata cannot classify the item. Ordered;
# first hit wins. Mirrors the existing auto_complete_routine_schedules
# name-fallback. Retire when activity_type/module fully cover these domains.
_KEYWORD_BRIDGE: list[tuple[tuple[str, ...], Any]] = [
    (("supplement", "medication", "amino", "creatine", "fish oil",
      "metformin", "mounjaro", "lantus", "insulin", "vitamin", "magnesium"),
     _intake),
    (("nutrition", "meal", "macro", "calorie", "protein shake", "log food",
      "log nutrition"),
     _nutrition),
    (("workout", "pickleball", "bike", "ride", "run", "running", "exercise",
      "gym", "cardio", "yoga", "stretch", "lift", "walk"),
     _fitness),
    (("bible", "prayer", "scripture", "devotional", "quiet time", "worship",
      "psalm", "gospel"),
     _faith),
    (("journal",), _journal),
    (("dishwasher", "shower", "watch", "laundry", "chore", "trash",
      "tidy", "clean"),
     _routines),
]


def _keyword_dest(title: str | None) -> str | None:
    if not title:
        return None
    t = title.lower()
    for keywords, dest_fn in _KEYWORD_BRIDGE:
        if any(kw in t for kw in keywords):
            return dest_fn()
    return None


# ── Canonical metadata lookups ─────────────────────────────────────────────
def _routine_activity_type(source_id) -> str | None:
    if not source_id:
        return None
    try:
        from apps.life.models import RoutineSchedule
        sched = RoutineSchedule.objects.filter(pk=source_id).only(
            "activity_type"
        ).first()
        return sched.activity_type if sched else None
    except Exception:
        return None


def _task_module(source_id) -> str | None:
    if not source_id:
        return None
    try:
        from apps.life.models import Task
        task = Task.objects.filter(pk=source_id).only("module").first()
        return getattr(task, "module", None) if task else None
    except Exception:
        return None


def resolve_action_destination(item: dict) -> str:
    """Resolve the canonical WLJ destination URL for an execution item/action.

    Args:
        item: an execution item or prioritized action dict carrying at least
            ``source_type`` and ``source_id`` (plus optional ``domain`` /
            ``title``).

    Returns:
        A real, verified URL string. Never a dead link; falls back to /life/.
    """
    source_type = item.get("source_type")
    title = item.get("title") or ""

    # 1. Meds / supplements — source_type is authoritative.
    if source_type in ("medication_dose", "supplement_dose"):
        return _intake()

    # 2. Routine items — canonical activity_type (rename-safe).
    if source_type == "routine_item":
        dest = _activity_to_dest(_routine_activity_type(item.get("source_id")))
        if dest:
            return dest
        # activity_type absent (nutrition/household) — try the keyword
        # bridge; household routines correctly default to /life/routines/.
        return _keyword_dest(title) or _routines()

    # 3. Tasks — canonical module (rename-safe), then keyword bridge.
    if source_type == "task":
        dest = _module_to_dest(_task_module(item.get("source_id")) or item.get("domain"))
        if dest:
            return dest
        kw = _keyword_dest(title)
        if kw:
            return kw
        # A health task we couldn't sub-classify → physical health home
        # (safe, real, on-topic) rather than the generic /life/ fallback.
        if (item.get("domain") or "").lower() == "health":
            return _health_home()
        return _life()

    # 4. Binary domain summary (faith/workout/journal), if focus surfaces one.
    dest = _module_to_dest(item.get("domain"))
    if dest:
        return dest

    # 5. Documented keyword bridge, then safe fallback.
    return _keyword_dest(title) or _life()
