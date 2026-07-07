# ==============================================================================
# File: calendar_engine/services/availability_queries.py
# Project: Whole Life Journey — Calendar Projection Layer
# Description: Canonical truth contract for Availability Blocks (F4). The ONE
#              query every consumer (calendar UI, projection, future planners)
#              uses to answer "when is the user available?".
# Governing doc: docs/WLJ_CALENDAR_PROJECTION_ARCHITECTURE.md
# ==============================================================================
"""AvailabilityQueries — the canonical read for the Availability domain.

Availability Blocks are calendar-native planning constraints. This module is the
single deterministic accessor (Architecture Law F4): UI, the TimeProjection layer,
and any future planner read availability HERE, never by touching the model ad hoc.
"""
from __future__ import annotations

import logging
from typing import List, Tuple

from apps.calendar_engine.models import AvailabilityBlock

logger = logging.getLogger(__name__)


class AvailabilityQueries:
    """Canonical availability truth accessor."""

    @classmethod
    def active(cls, user):
        """Active, non-deleted availability blocks for a user."""
        return AvailabilityBlock.objects.filter(
            user=user, is_active=True, deleted_at__isnull=True,
        )

    @classmethod
    def occurrences_in_range(cls, user, range_start, range_end) -> List[Tuple[AvailabilityBlock, object, object]]:
        """Expand every active block into concrete (block, start, end) occurrences
        overlapping the range. Recurrence + exceptions handled by the model."""
        out: List[Tuple[AvailabilityBlock, object, object]] = []
        for block in cls.active(user):
            try:
                for occ_start, occ_end in block.get_occurrences(range_start, range_end):
                    out.append((block, occ_start, occ_end))
            except Exception:
                logger.debug("Availability expansion failed for block=%s", block.pk)
                continue
        return out

    @classmethod
    def describe(cls, user) -> dict:
        """Deterministic summary of the user's availability constraints."""
        blocks = list(cls.active(user))
        return {
            "count": len(blocks),
            "blocks": [
                {
                    "id": b.pk,
                    "label": b.label,
                    "kind": b.kind,
                    "recurring": b.is_recurring,
                    "frequency": b.frequency,
                }
                for b in blocks
            ],
        }
