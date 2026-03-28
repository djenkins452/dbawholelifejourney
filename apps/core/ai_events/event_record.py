# ==============================================================================
# File: apps/core/ai_events/event_record.py
# Project: Whole Life Journey — Django 5.x Personal Wellness/Journaling App
# Description: Canonical event record dataclass for cross-domain event access
# Owner: Danny Jenkins (admin@wholelifejourney.com)
# Created: 2026-03-28
# ==============================================================================
"""
EventRecord — the standardized container for event-level truth.

Every domain adapter returns a list of EventRecord instances.
The EventResolver merges and sorts them for cross-domain timelines.

This is NOT a Django model. It creates no tables. It is a pure
data transfer object for read-only event access.
"""

from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional


@dataclass(frozen=True)
class EventRecord:
    """
    Immutable record of a single event from a domain model.

    Attributes:
        domain: Source domain (e.g., 'medication', 'routine', 'workout')
        event_type: Specific event type (e.g., 'dose_taken', 'dose_missed',
                    'routine_completed', 'workout_completed')
        timestamp: When the event happened or was expected (timezone-aware)
        label: Human-readable description (e.g., 'Lantus SoloStar 9:00 AM')
        status: Event outcome ('completed', 'missed', 'skipped', 'late', 'pending')
        detail: Domain-specific extra data (frozen after creation)
        source_model: Django model class name (e.g., 'MedicineLog')
        source_id: Primary key of the source record
    """
    domain: str
    event_type: str
    timestamp: datetime
    label: str
    status: str
    detail: dict = field(default_factory=dict)
    source_model: Optional[str] = None
    source_id: Optional[int] = None

    def __post_init__(self):
        """Validate required fields."""
        if not self.domain:
            raise ValueError("EventRecord.domain is required")
        if not self.event_type:
            raise ValueError("EventRecord.event_type is required")
        if not self.label:
            raise ValueError("EventRecord.label is required")
        if not self.status:
            raise ValueError("EventRecord.status is required")
