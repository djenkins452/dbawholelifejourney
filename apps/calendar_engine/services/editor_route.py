# ==============================================================================
# File: calendar_engine/services/editor_route.py
# Project: Whole Life Journey — Calendar Projection Layer
# Description: Resolve a projected time block to where it is TRULY edited — the
#              owning domain's editor. The Calendar edits ONLY calendar-native
#              objects (manual events + availability); everything else routes out.
# Governing doc: docs/WLJ_CALENDAR_PROJECTION_ARCHITECTURE.md
# ==============================================================================
"""Editor routing for the Calendar Projection Layer.

The Calendar Projection Law: *editing from the Calendar always edits the owning
domain.* This module maps a projected block's ``source_type`` (+ its source id)
to the owning domain's editor URL. Calendar-native blocks (manual events and
availability blocks) are edited in place; every other block navigates to the
domain that owns the object.

Crash-safe: an unresolvable route degrades to ``None`` (the surface then treats
the block as non-navigable) — this module never raises into a request/render path.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Optional

logger = logging.getLogger(__name__)


# Calendar-native source types — edited INSIDE the calendar, not routed out.
NATIVE_SOURCE_TYPES = frozenset({"none", "", "availability"})


@dataclass(frozen=True)
class EditorRoute:
    """Where a projected block is edited.

    ``edit_in_place`` is True only for calendar-native blocks (manual events,
    availability). For everything else, ``url`` is the owning domain's editor and
    the surface should navigate there — never edit the projection/cache.
    """

    edit_in_place: bool = False
    url: Optional[str] = None
    label: Optional[str] = None
    owner: Optional[str] = None  # human-readable owning domain, for tooltip/debug

    def as_dict(self) -> dict:
        return {
            "edit_in_place": self.edit_in_place,
            "url": self.url,
            "label": self.label,
            "owner": self.owner,
        }


# source_type → (url_name, pk_kwarg | None, label, owner)
# pk_kwarg None means the URL takes no argument (a domain landing page). These
# are the honest fallbacks for sources whose owning-object pk isn't the stored
# source_id (schedule→intake, schedule→plan, plan→slug) — see the governing doc.
_ROUTE_MAP: dict[str, tuple[str, Optional[str], str, str]] = {
    "task":             ("life:task_update",         "pk", "Edit task",        "Tasks"),
    "life_event":       ("life:event_update",        "pk", "Edit event",       "Calendar"),
    "goal":             ("purpose:goal_detail",      "pk", "Open goal",        "Goals"),
    "goal_milestone":   ("purpose:milestone_update", "pk", "Edit milestone",   "Goals"),
    "habit":            ("purpose:habit_goal_detail","pk", "Open habit",       "Habits"),
    "medicine_schedule":("health:intake_home",       None, "Open medications", "Medicine"),
    "workout_schedule": ("health:workout_list",      None, "Open workouts",    "Workouts"),
    "faith_routine":    ("faith:reading_plans",      None, "Open reading plans","Faith"),
}


def _safe_reverse(url_name: str, pk_kwarg: Optional[str], source_id) -> Optional[str]:
    """reverse() the editor URL, crash-safe. Returns None on any failure so a bad
    name/id degrades to a non-navigable block rather than a 500 or broken link."""
    try:
        from django.urls import reverse
        if pk_kwarg is None:
            return reverse(url_name)
        if source_id in (None, "", "0"):
            return None
        try:
            pk = int(source_id)
        except (TypeError, ValueError):
            return None
        return reverse(url_name, kwargs={pk_kwarg: pk})
    except Exception:
        logger.debug("editor_route reverse failed for %s (%s)", url_name, source_id)
        return None


def resolve_editor_route(
    source_type: Optional[str],
    source_id=None,
    *,
    is_availability: bool = False,
) -> EditorRoute:
    """Resolve a projected block to its owning-domain editor.

    - Calendar-native (``none``/empty, or ``is_availability``) → ``edit_in_place``.
    - Any other source → the owning domain's editor URL (navigate out).
    - Unresolvable → an empty route (non-navigable). Never raises.
    """
    st = (source_type or "none").strip().lower()

    if is_availability or st == "availability":
        return EditorRoute(edit_in_place=True, label="Edit availability",
                           owner="Calendar")
    if st in ("none", ""):
        return EditorRoute(edit_in_place=True, label="Edit event",
                           owner="Calendar")

    spec = _ROUTE_MAP.get(st)
    if not spec:
        return EditorRoute()  # unknown source → non-navigable, never edits cache

    url_name, pk_kwarg, label, owner = spec
    url = _safe_reverse(url_name, pk_kwarg, source_id)
    if not url:
        return EditorRoute(owner=owner, label=label)  # owner known, link unresolved
    return EditorRoute(edit_in_place=False, url=url, label=label, owner=owner)
