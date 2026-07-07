# ==============================================================================
# File: calendar_engine/services/time_projection.py
# Project: Whole Life Journey — Calendar Projection Layer
# Description: The Calendar's single read contract — "What occupies my time?"
#              Projects each domain's truth into time via a provider registry.
#              The Calendar owns TIME, not OBJECTS.
# Governing doc: docs/WLJ_CALENDAR_PROJECTION_ARCHITECTURE.md
# ==============================================================================
"""TimeProjection — the Calendar Projection Layer's read contract.

`TimeProjection.for_range(user, start, end)` returns a `ProjectionResult` split
into three lanes:

    committed    — items with a REAL execution time (they occupy the timeline)
    due          — due-dated items with NO execution time (never on the timeline,
                   never given a fabricated window)
    constraints  — availability blocks (planning constraints)

Every rendered calendar item is a `ProjectedBlock` — a read-only DTO that also
carries `editor_route`, the deep link to the OWNING domain's editor. The calendar
never edits the projection/cache for non-native objects.

Sources register as `TimeProvider`s (framework-first): adding a domain to the
calendar is one registration, never a change to the calendar core. Today:
  - CalendarCacheProvider — the materialized `CalendarEvent` cache (compat seam;
    a future per-domain LIVE provider can replace it per source_type with no UI
    change).
  - AvailabilityProvider  — the calendar-native `AvailabilityBlock` model (live).
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import List, Optional

from django.utils import timezone

from apps.calendar_engine.models import CalendarEvent
from apps.calendar_engine.services.editor_route import resolve_editor_route

logger = logging.getLogger(__name__)

# Lanes
LANE_COMMITTED = "committed"
LANE_DUE = "due"
LANE_CONSTRAINT = "constraint"


@dataclass
class ProjectedBlock:
    """The surface-agnostic answer to "what occupies this slice of time."

    Read-only. Never an owner of truth — `source_type`/`source_id` point at the
    owning domain object, and `editor_route` says where to edit it.
    """

    lane: str
    origin: str                 # 'calendar_native' | 'task' | 'medicine' | ...
    title: str
    start_dt: object            # aware datetime (UTC-normalized; serialized local)
    end_dt: object
    source_type: str = "none"
    source_id: str = ""
    event_id: Optional[int] = None      # cache/native row id (for native editing)
    event_kind: str = "manual"
    is_all_day: bool = False
    is_protected: bool = False
    status: str = "scheduled"
    domain: Optional[str] = None
    domain_color: str = "#6b7280"
    is_occurrence: bool = False
    editor_route: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        local_start = timezone.localtime(self.start_dt)
        local_end = timezone.localtime(self.end_dt)
        return {
            "id": self.event_id,
            "lane": self.lane,
            "origin": self.origin,
            "title": self.title,
            "start_dt": local_start.isoformat(),
            "end_dt": local_end.isoformat(),
            "is_all_day": self.is_all_day,
            "event_kind": self.event_kind,
            "source_type": self.source_type,
            "source_id": self.source_id,
            "is_protected": self.is_protected,
            "status": self.status,
            "domain": self.domain,
            "domain_color": self.domain_color,
            "is_occurrence": self.is_occurrence,
            "duration_minutes": int((local_end - local_start).total_seconds() / 60),
            "editor_route": self.editor_route,
        }


@dataclass
class ProjectionResult:
    committed: List[ProjectedBlock] = field(default_factory=list)
    due: List[ProjectedBlock] = field(default_factory=list)
    constraints: List[ProjectedBlock] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "committed": [b.to_dict() for b in self.committed],
            "due": [b.to_dict() for b in self.due],
            "constraints": [b.to_dict() for b in self.constraints],
        }

    @property
    def all_blocks(self) -> List[ProjectedBlock]:
        return self.committed + self.due + self.constraints


# ──────────────────────────────────────────────────────────
# Provider contract
# ──────────────────────────────────────────────────────────

class TimeProvider:
    """A source of time. Returns ProjectedBlocks for a range. Stateless.

    Implementations MUST be crash-safe (return [] on failure) and MUST NOT compute
    heavy analytics or call the LLM on the request path (F5 / request-path safety).
    """

    name = "base"

    def blocks_for_range(self, user, range_start, range_end) -> List[ProjectedBlock]:
        raise NotImplementedError


_PROVIDERS: List[TimeProvider] = []


def register_provider(provider: TimeProvider) -> None:
    """Register a TimeProvider. Adding a domain to the calendar is one call."""
    _PROVIDERS.append(provider)


def _classify_lane(event_kind: str, source_type: str) -> str:
    if source_type == "availability":
        return LANE_CONSTRAINT
    if event_kind == CalendarEvent.KIND_DEADLINE_MARKER:
        return LANE_DUE
    return LANE_COMMITTED


def _origin_for(source_type: str) -> str:
    if source_type in ("none", "", "life_event"):
        return "calendar_native"
    return source_type


# ──────────────────────────────────────────────────────────
# CalendarCacheProvider — reads the materialized CalendarEvent cache
# ──────────────────────────────────────────────────────────

class CalendarCacheProvider(TimeProvider):
    """Reads the existing materialized `CalendarEvent` cache (manual events + the
    projected rows kept in sync by services/projection.py).

    This is the compatibility seam. It preserves exact parity with the legacy
    range read. A future per-domain LIVE provider can take over any `source_type`
    (reading `Task`/`MedicineQueries`/… directly) with ZERO UI change — this
    provider just stops emitting that source_type.
    """

    name = "calendar_cache"

    def _block_from_event(self, event, start_dt, end_dt, *, is_occurrence=False) -> ProjectedBlock:
        source_type = event.source_type or "none"
        lane = _classify_lane(event.event_kind, source_type)
        route = resolve_editor_route(source_type, event.source_id)
        # Deadline markers are titled "Due: <task>" — the due lane shows the bare
        # object name (no fabricated time), so strip the projection prefix.
        title = event.title
        return ProjectedBlock(
            lane=lane,
            origin=_origin_for(source_type),
            title=title,
            start_dt=start_dt,
            end_dt=end_dt,
            source_type=source_type,
            source_id=event.source_id or "",
            event_id=event.pk,
            event_kind=event.event_kind,
            is_all_day=event.is_all_day,
            is_protected=event.is_protected,
            status=event.status,
            domain=event.domain.name if event.domain else None,
            domain_color=event.domain.color if event.domain else "#6b7280",
            is_occurrence=is_occurrence,
            editor_route=route.as_dict(),
        )

    def blocks_for_range(self, user, range_start, range_end) -> List[ProjectedBlock]:
        try:
            return self._blocks(user, range_start, range_end)
        except Exception:
            logger.error("CalendarCacheProvider failed for user=%s", getattr(user, "id", None),
                         exc_info=True)
            return []

    def _blocks(self, user, range_start, range_end) -> List[ProjectedBlock]:
        blocks: List[ProjectedBlock] = []

        # Direct (non-recurring-occurrence) events overlapping the range.
        direct = CalendarEvent.objects.filter(
            user=user,
            status=CalendarEvent.STATUS_SCHEDULED,
            start_dt__lt=range_end,
            end_dt__gt=range_start,
        ).select_related("domain")

        direct_title_dates = set()
        for event in direct:
            block = self._block_from_event(event, event.start_dt, event.end_dt)
            blocks.append(block)
            local = timezone.localtime(event.start_dt)
            direct_title_dates.add((event.title.strip().lower(), local.date().isoformat()))

        # Recurring occurrences (base row expanded dynamically), deduped against
        # any direct event already covering the same title+date.
        recurring = (
            CalendarEvent.objects.filter(
                user=user,
                status=CalendarEvent.STATUS_SCHEDULED,
                recurrence__isnull=False,
            )
            .select_related("domain", "recurrence")
            .exclude(pk__in=direct.values_list("pk", flat=True))
        )
        for event in recurring:
            try:
                occurrences = event.recurrence.get_occurrences(range_start, range_end)
            except Exception:
                logger.debug("Recurrence expansion failed for event=%s", event.pk)
                continue
            for occ_start, occ_end in occurrences:
                occ_date = timezone.localtime(occ_start).date().isoformat()
                if (event.title.strip().lower(), occ_date) in direct_title_dates:
                    continue
                blocks.append(
                    self._block_from_event(event, occ_start, occ_end, is_occurrence=True)
                )

        return blocks


# ──────────────────────────────────────────────────────────
# TimeProjection — the read contract the calendar UI consumes
# ──────────────────────────────────────────────────────────

class TimeProjection:
    """The Calendar's single read contract: what occupies my time?"""

    @staticmethod
    def for_range(user, range_start, range_end) -> ProjectionResult:
        result = ProjectionResult()
        for provider in _PROVIDERS:
            try:
                for block in provider.blocks_for_range(user, range_start, range_end):
                    if block.lane == LANE_DUE:
                        result.due.append(block)
                    elif block.lane == LANE_CONSTRAINT:
                        result.constraints.append(block)
                    else:
                        result.committed.append(block)
            except Exception:
                logger.error("TimeProvider %s failed", getattr(provider, "name", "?"),
                             exc_info=True)
                continue

        result.committed.sort(key=lambda b: b.start_dt)
        result.due.sort(key=lambda b: b.start_dt)
        result.constraints.sort(key=lambda b: b.start_dt)
        return result


# ──────────────────────────────────────────────────────────
# AvailabilityProvider — reads the calendar-native AvailabilityBlock model (live)
# ──────────────────────────────────────────────────────────

class AvailabilityProvider(TimeProvider):
    """Reads Availability Blocks LIVE via the canonical AvailabilityQueries truth
    contract (not the legacy cache). This is the first live provider — proof that
    the registry lets a domain project into time without a materialized row."""

    name = "availability"

    # Muted, non-completion colors — availability is a constraint, not a task.
    _COLOR = {"unavailable": "#94a3b8", "available": "#34d399"}

    def blocks_for_range(self, user, range_start, range_end) -> List[ProjectedBlock]:
        try:
            from apps.calendar_engine.services.availability_queries import AvailabilityQueries
            # Availability is calendar-native but edited on its own management
            # page (not the single-event modal), so route there directly.
            try:
                from django.urls import reverse
                route_dict = {
                    "edit_in_place": False,
                    "url": reverse("calendar_engine:availability"),
                    "label": "Edit availability",
                    "owner": "Calendar",
                }
            except Exception:
                route_dict = resolve_editor_route("availability", is_availability=True).as_dict()
            blocks: List[ProjectedBlock] = []
            for block, occ_start, occ_end in AvailabilityQueries.occurrences_in_range(
                user, range_start, range_end,
            ):
                blocks.append(ProjectedBlock(
                    lane=LANE_CONSTRAINT,
                    origin="availability",
                    title=block.label,
                    start_dt=occ_start,
                    end_dt=occ_end,
                    source_type="availability",
                    source_id=str(block.pk),
                    event_id=block.pk,
                    event_kind="availability",
                    status="scheduled",
                    domain=block.get_kind_display(),
                    domain_color=self._COLOR.get(block.kind, "#94a3b8"),
                    is_occurrence=block.is_recurring,
                    editor_route=route_dict,
                ))
            return blocks
        except Exception:
            logger.error("AvailabilityProvider failed for user=%s",
                         getattr(user, "id", None), exc_info=True)
            return []


# Register the default providers. Order is display-independent (lanes are sorted).
register_provider(CalendarCacheProvider())
register_provider(AvailabilityProvider())
