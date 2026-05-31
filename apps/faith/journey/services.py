"""
Journey services — small helpers that keep view code thin.

Includes:
- get_active_journey(user) — the user's currently active UserJourney, if any
- get_or_create_journey(user, path_slug) — start or resume a journey
- get_current_day(user_journey) — the user's current JourneyDay
- get_progress_for_day(user_journey, journey_day) — fetch/create per-day progress
- mark_day_complete(user, user_journey, journey_day, ...) — completion + advancement
- parse_reference(ref) — turn "Leviticus 1:5" into (book_name, book_order, chapter, verse_start, verse_end)

All functions are deterministic and isolated. No imports of reading-plan code.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from typing import Optional

from django.db import transaction
from django.utils import timezone

logger = logging.getLogger(__name__)

from apps.faith.journey.models import (
    JourneyArc,
    JourneyDay,
    JourneyPath,
    UserJourney,
    UserJourneyDayProgress,
)


# ---------------------------------------------------------------------------
# Bible book order (Genesis=1 ... Revelation=66) for annotation reuse.
# Keeps Journey's per-day verse parsing aligned with BibleHighlight.book_order.
# ---------------------------------------------------------------------------
BOOK_ORDER: dict[str, int] = {
    # Old Testament
    "Genesis": 1, "Exodus": 2, "Leviticus": 3, "Numbers": 4, "Deuteronomy": 5,
    "Joshua": 6, "Judges": 7, "Ruth": 8, "1 Samuel": 9, "2 Samuel": 10,
    "1 Kings": 11, "2 Kings": 12, "1 Chronicles": 13, "2 Chronicles": 14,
    "Ezra": 15, "Nehemiah": 16, "Esther": 17, "Job": 18, "Psalms": 19,
    "Psalm": 19, "Proverbs": 20, "Ecclesiastes": 21, "Song of Solomon": 22,
    "Song of Songs": 22, "Isaiah": 23, "Jeremiah": 24, "Lamentations": 25,
    "Ezekiel": 26, "Daniel": 27, "Hosea": 28, "Joel": 29, "Amos": 30,
    "Obadiah": 31, "Jonah": 32, "Micah": 33, "Nahum": 34, "Habakkuk": 35,
    "Zephaniah": 36, "Haggai": 37, "Zechariah": 38, "Malachi": 39,
    # New Testament
    "Matthew": 40, "Mark": 41, "Luke": 42, "John": 43, "Acts": 44,
    "Romans": 45, "1 Corinthians": 46, "2 Corinthians": 47, "Galatians": 48,
    "Ephesians": 49, "Philippians": 50, "Colossians": 51,
    "1 Thessalonians": 52, "2 Thessalonians": 53, "1 Timothy": 54,
    "2 Timothy": 55, "Titus": 56, "Philemon": 57, "Hebrews": 58, "James": 59,
    "1 Peter": 60, "2 Peter": 61, "1 John": 62, "2 John": 63, "3 John": 64,
    "Jude": 65, "Revelation": 66,
}


@dataclass
class ParsedReference:
    book_name: str
    book_order: int
    chapter: int
    verse_start: int
    verse_end: Optional[int]

    def display(self) -> str:
        if self.verse_end and self.verse_end != self.verse_start:
            return f"{self.book_name} {self.chapter}:{self.verse_start}-{self.verse_end}"
        return f"{self.book_name} {self.chapter}:{self.verse_start}"


_REFERENCE_RE = re.compile(
    r"^\s*"
    r"(?P<book>(?:\d\s+)?[A-Za-z][A-Za-z\s]*?)"   # "1 Samuel" or "Leviticus"
    r"\s+(?P<chapter>\d+)"
    r"(?::(?P<verse_start>\d+)(?:-(?P<verse_end>\d+))?)?"
    r"\s*$"
)


def parse_reference(ref: str) -> ParsedReference:
    """Parse a reference string like 'Leviticus 1:5' or '1 Samuel 17:1-11'.

    Raises ValueError on malformed input or unknown book.
    """
    m = _REFERENCE_RE.match(ref)
    if not m:
        raise ValueError(f"Could not parse reference: {ref!r}")
    book_raw = " ".join(m.group("book").split())  # collapse whitespace
    if book_raw not in BOOK_ORDER:
        raise ValueError(f"Unknown Bible book: {book_raw!r}")
    chapter = int(m.group("chapter"))
    verse_start = int(m.group("verse_start") or 1)
    verse_end = int(m.group("verse_end")) if m.group("verse_end") else None
    return ParsedReference(
        book_name=book_raw,
        book_order=BOOK_ORDER[book_raw],
        chapter=chapter,
        verse_start=verse_start,
        verse_end=verse_end,
    )


# ---------------------------------------------------------------------------
# Journey state helpers
# ---------------------------------------------------------------------------

def get_active_journey(user) -> Optional[UserJourney]:
    """Return the user's single active UserJourney, or None."""
    return (
        UserJourney.objects
        .filter(user=user, journey_status="active")
        .select_related("journey_path", "current_arc")
        .first()
    )


@transaction.atomic
def get_or_create_journey(user, path_slug: str) -> UserJourney:
    """Start the named journey if the user isn't on one; otherwise return existing.

    Phase 1 enforces "one active journey per user" at the service layer.
    """
    existing = get_active_journey(user)
    if existing and existing.journey_path.slug == path_slug:
        return existing
    if existing:
        # The user has a different active journey; do not silently switch.
        raise ValueError(
            "User already has an active journey on a different path. "
            "Pause or abandon the current journey before starting another."
        )

    path = JourneyPath.objects.get(slug=path_slug)
    first_arc = path.arcs.order_by("order").first()
    if first_arc is None:
        raise ValueError(f"Journey path '{path_slug}' has no arcs authored yet.")

    uj = UserJourney.objects.create(
        user=user,
        journey_path=path,
        current_arc=first_arc,
        current_day_number=_min_day_number(first_arc),
        journey_status="active",
        preferred_difficulty=path.difficulty_default,
    )
    return uj


def _min_day_number(arc: JourneyArc) -> int:
    """Earliest available day_number in an arc (handles incremental authoring)."""
    first = arc.days.order_by("day_number").first()
    return first.day_number if first else 1


def get_current_day(user_journey: UserJourney) -> Optional[JourneyDay]:
    """Return the user's current JourneyDay if it exists in the current arc."""
    if not user_journey.current_arc:
        return None
    return (
        user_journey.current_arc.days
        .filter(day_number=user_journey.current_day_number)
        .first()
    )


def get_day_in_arc(arc_slug: str, day_number: int) -> Optional[JourneyDay]:
    """Lookup a specific day by arc slug + day number (for review routes)."""
    return (
        JourneyDay.objects
        .filter(arc__slug=arc_slug, day_number=day_number)
        .select_related("arc", "arc__journey_path")
        .first()
    )


def get_progress_for_day(user_journey: UserJourney, journey_day: JourneyDay) -> UserJourneyDayProgress:
    """Fetch or create the per-day progress record."""
    progress, _ = UserJourneyDayProgress.objects.get_or_create(
        user_journey=user_journey,
        journey_day=journey_day,
        defaults={"user": user_journey.user},
    )
    return progress


@transaction.atomic
def mark_day_complete(
    user_journey: UserJourney,
    journey_day: JourneyDay,
    reflection_notes: str = "",
    application_committed: bool = False,
) -> UserJourneyDayProgress:
    """Mark a day complete and advance current_day_number / current_arc as needed."""
    progress = get_progress_for_day(user_journey, journey_day)
    progress.is_completed = True
    progress.completed_at = timezone.now()
    progress.reflection_notes = reflection_notes
    progress.application_committed = application_committed
    progress.difficulty_at_completion = user_journey.preferred_difficulty
    progress.save()

    # Advance only when completing the currently-displayed day.
    if journey_day.arc_id == user_journey.current_arc_id and journey_day.day_number == user_journey.current_day_number:
        next_day = (
            journey_day.arc.days
            .filter(day_number__gt=journey_day.day_number)
            .order_by("day_number")
            .first()
        )
        arc_just_completed = False
        if next_day is not None:
            user_journey.current_day_number = next_day.day_number
        else:
            # End of arc. Try to move to next arc in the path.
            arc_just_completed = True
            next_arc = (
                journey_day.arc.journey_path.arcs
                .filter(order__gt=journey_day.arc.order)
                .order_by("order")
                .first()
            )
            if next_arc is not None and next_arc.days.exists():
                user_journey.current_arc = next_arc
                user_journey.current_day_number = _min_day_number(next_arc)
            else:
                # No more arcs available — mark journey complete.
                user_journey.journey_status = "completed"
                user_journey.completed_at = timezone.now()

        user_journey.last_engaged_at = timezone.now()
        user_journey.save()

        # Fire arc.completed signal AFTER the save commits so subscribers see consistent state.
        if arc_just_completed:
            from apps.faith.journey.signals import emit_arc_completed
            emit_arc_completed(user_journey.user, user_journey=user_journey, arc=journey_day.arc)

    # ── Routine bridge ───────────────────────────────────────────────
    # Auto-complete the matching "Bible Reading" routine schedule for
    # today so Daily Rhythm / "Do This Next" reflects the completion
    # immediately. Mirrors the legacy MarkDayCompleteView pattern at
    # apps/faith/views.py:1424-1437.
    #
    # Domain-agnostic: uses activity_type='bible'/'faith' (preferred)
    # and name__icontains fallback — works for ANY journey path with
    # no hardcoded plan name. Idempotent: auto_complete_routine_schedules
    # short-circuits if a RoutineLog already exists for today.
    try:
        from apps.life.services.routine_helpers import auto_complete_routine_schedules
        auto_complete_routine_schedules(
            user_journey.user, 'bible', 'bible',
            source_object_id=progress.pk,
        )
        auto_complete_routine_schedules(
            user_journey.user, 'faith', 'faith',
            source_object_id=progress.pk,
        )
    except Exception:
        logger.warning(
            "journey: failed to auto-complete Bible Reading routine "
            "(user=%s progress=%s) — dashboard may show stale state",
            user_journey.user_id, progress.pk, exc_info=True,
        )

    # Fire intelligence chain for parity with legacy reading-plan flow.
    try:
        from apps.core.ai_orchestrator.intelligence_hook import fire_intelligence
        fire_intelligence(
            user_journey.user, "faith", progress.pk, "complete_reading",
        )
    except Exception:
        logger.warning(
            "journey: fire_intelligence failed (user=%s progress=%s)",
            user_journey.user_id, progress.pk, exc_info=True,
        )

    return progress


# ---------------------------------------------------------------------------
# Navigation guard
# ---------------------------------------------------------------------------

def can_view_day(user_journey: UserJourney, journey_day: JourneyDay) -> bool:
    """Past + current days are viewable; future days are locked.

    A day is viewable if:
      - it's in an arc the user has reached (arc.order <= current_arc.order), AND
      - if it's in the current arc, day_number <= current_day_number
    """
    if not user_journey.current_arc:
        return False
    if journey_day.arc.journey_path_id != user_journey.journey_path_id:
        return False
    if journey_day.arc.order < user_journey.current_arc.order:
        return True
    if journey_day.arc.order == user_journey.current_arc.order:
        return journey_day.day_number <= user_journey.current_day_number
    return False
