"""
Journal domain adapter — evaluates JournalEntry existence against
routine-based expectations.

Truth hierarchy (WLJ architecture):
1. JournalEntry (raw data) — single source of truth for completion
2. JournalSignal (derived) — NOT used for completion (used for trends/mood)
3. Absence of entry → MISSED

Expected logic: User has a routine item with a name in the journal name set
(from execution_truth_engine). If no journal routine exists, journaling is
not expected and no events are created.
"""

import logging
from datetime import timedelta

from apps.dashboard_v2.compliance.constants import (
    ACTUAL_COMPLETED,
    ACTUAL_NONE,
    BUCKET_JOURNAL,
    DOMAIN_JOURNAL,
    FINAL_COMPLETED,
    FINAL_MISSED,
    REASON_COMPLETED_VIA_JOURNAL,
    REASON_NOT_COMPLETED,
    SOURCE_JOURNAL_ENTRY,
)

logger = logging.getLogger(__name__)


def evaluate_journal(user, start_date, end_date):
    """
    Produce ComplianceEvent dicts for journal domain.

    Only creates events for days where journaling is expected
    (has an active routine item matching journal names).
    """
    try:
        from apps.core.execution.execution_truth_engine import JOURNAL_NAMES
        from apps.journal.models import JournalEntry
        from apps.life.models import Routine

        # Find journal-related routine items
        active_routines = Routine.objects.filter(
            user=user, is_active=True, status="active",
        ).prefetch_related("items")

        journal_items = []
        for routine in active_routines:
            for item in routine.items.filter(is_active=True):
                if item.name.lower().strip() in JOURNAL_NAMES:
                    journal_items.append(item)

        if not journal_items:
            return []

        # Build lookup of journal entries by date
        entries = JournalEntry.objects.filter(
            user=user,
            entry_date__gte=start_date,
            entry_date__lte=end_date,
        ).values_list("entry_date", flat=True)
        entry_dates = set(entries)

        events = []
        day = start_date
        while day <= end_date:
            day_of_week = day.weekday()

            # Check if any journal routine item applies to this day
            expected_today = any(
                (item.specific_date == day if item.specific_date else item.applies_to_day(day_of_week))
                for item in journal_items
            )

            if not expected_today:
                day += timedelta(days=1)
                continue

            has_entry = day in entry_dates

            events.append({
                "user": user,
                "event_date": day,
                "domain": DOMAIN_JOURNAL,
                "scoring_bucket": BUCKET_JOURNAL,
                "item_type": "JournalEntry",
                "item_id": None,
                "item_label": "Daily Journal",
                "expected_at": None,
                "expected": True,
                "source_system": SOURCE_JOURNAL_ENTRY,
                "actual_status": ACTUAL_COMPLETED if has_entry else ACTUAL_NONE,
                "final_status": FINAL_COMPLETED if has_entry else FINAL_MISSED,
                "reason_code": REASON_COMPLETED_VIA_JOURNAL if has_entry else REASON_NOT_COMPLETED,
                "reason_detail": {},
            })

            day += timedelta(days=1)

        return events
    except Exception:
        logger.error("Journal compliance adapter failed", exc_info=True)
        return []
