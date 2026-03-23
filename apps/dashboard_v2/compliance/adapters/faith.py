"""
Faith domain adapter — evaluates prayer and Bible reading completion.

Uses the same cross-domain bridge logic as the Execution Truth Engine:
- Prayer can be satisfied by routine items in FAITH_PRAYER_NAMES
- Bible reading can be satisfied by UserReadingProgress or routine items in FAITH_BIBLE_NAMES

Creates up to 2 events per day: one for prayer, one for Bible reading,
only when those activities are expected.
"""

import logging
from datetime import timedelta

from apps.dashboard_v2.compliance.constants import (
    ACTUAL_COMPLETED,
    ACTUAL_NONE,
    BUCKET_FAITH,
    DOMAIN_FAITH,
    FINAL_COMPLETED,
    FINAL_MISSED,
    REASON_ENTRY_EXISTS,
    REASON_NO_ENTRY,
    REASON_NO_PLAN,
    REASON_PLAN_ACTIVE,
    SOURCE_PRAYER_TASK,
    SOURCE_READING_PLAN,
    SOURCE_READING_PROGRESS,
)

logger = logging.getLogger(__name__)


def evaluate_faith(user, start_date, end_date):
    """
    Produce ComplianceEvent dicts for faith domain.

    Creates events for prayer and Bible reading based on user expectations.
    """
    try:
        events = []
        events.extend(_evaluate_prayer(user, start_date, end_date))
        events.extend(_evaluate_bible(user, start_date, end_date))
        return events
    except Exception:
        logger.error("Faith compliance adapter failed", exc_info=True)
        return []


def _evaluate_prayer(user, start_date, end_date):
    """Evaluate prayer completion based on routine items."""
    try:
        from apps.core.execution.execution_truth_engine import FAITH_PRAYER_NAMES
        from apps.life.models import Routine, RoutineLog

        # Find prayer-related routine items
        active_routines = Routine.objects.filter(
            user=user, is_active=True, status="active",
        ).prefetch_related("items")

        prayer_items = []
        for routine in active_routines:
            for item in routine.items.filter(is_active=True):
                if item.name.lower().strip() in FAITH_PRAYER_NAMES:
                    prayer_items.append(item)

        if not prayer_items:
            return []

        # Build log lookup
        schedule_ids = [item.id for item in prayer_items]
        logs = RoutineLog.objects.filter(
            user=user,
            schedule_id__in=schedule_ids,
            scheduled_date__gte=start_date,
            scheduled_date__lte=end_date,
        )
        log_map = {}
        for log in logs:
            log_map.setdefault(log.scheduled_date, []).append(log)

        events = []
        day = start_date
        while day <= end_date:
            day_of_week = day.weekday()

            expected_today = any(
                (item.specific_date == day if item.specific_date else item.applies_to_day(day_of_week))
                for item in prayer_items
            )

            if not expected_today:
                day += timedelta(days=1)
                continue

            # Check if any prayer item was completed
            day_logs = log_map.get(day, [])
            completed = any(
                log.log_status in ("completed", "completed_late")
                for log in day_logs
            )

            events.append({
                "user": user,
                "event_date": day,
                "domain": DOMAIN_FAITH,
                "scoring_bucket": BUCKET_FAITH,
                "item_type": "PrayerRoutine",
                "item_id": prayer_items[0].id,
                "item_label": "Prayer",
                "expected_at": None,
                "expected": True,
                "source_system": SOURCE_PRAYER_TASK,
                "actual_status": ACTUAL_COMPLETED if completed else ACTUAL_NONE,
                "final_status": FINAL_COMPLETED if completed else FINAL_MISSED,
                "reason_code": REASON_ENTRY_EXISTS if completed else REASON_NO_ENTRY,
                "reason_detail": {},
            })

            day += timedelta(days=1)

        return events
    except Exception:
        logger.error("Prayer compliance evaluation failed", exc_info=True)
        return []


def _evaluate_bible(user, start_date, end_date):
    """Evaluate Bible reading based on active reading plans and routine items."""
    try:
        from apps.core.execution.execution_truth_engine import FAITH_BIBLE_NAMES
        from apps.faith.models import UserReadingPlan, UserReadingProgress
        from apps.life.models import Routine, RoutineLog

        # Check for active reading plan
        active_plan = UserReadingPlan.objects.filter(
            user=user, plan_status="active",
        ).first()

        # Check for Bible reading routine items
        active_routines = Routine.objects.filter(
            user=user, is_active=True, status="active",
        ).prefetch_related("items")

        bible_items = []
        for routine in active_routines:
            for item in routine.items.filter(is_active=True):
                if item.name.lower().strip() in FAITH_BIBLE_NAMES:
                    bible_items.append(item)

        if not active_plan and not bible_items:
            return []

        # Check reading progress by date
        progress_dates = set()
        if active_plan:
            progress_qs = UserReadingProgress.objects.filter(
                user_plan=active_plan,
                is_completed=True,
                completed_at__date__gte=start_date,
                completed_at__date__lte=end_date,
            ).values_list("completed_at__date", flat=True)
            progress_dates = set(progress_qs)

        # Check routine log dates for bible items
        bible_log_dates = set()
        if bible_items:
            schedule_ids = [item.id for item in bible_items]
            bible_logs = RoutineLog.objects.filter(
                user=user,
                schedule_id__in=schedule_ids,
                scheduled_date__gte=start_date,
                scheduled_date__lte=end_date,
                log_status__in=("completed", "completed_late"),
            ).values_list("scheduled_date", flat=True)
            bible_log_dates = set(bible_logs)

        events = []
        day = start_date
        while day <= end_date:
            day_of_week = day.weekday()

            # Expected if: active plan exists OR bible routine item applies today
            bible_routine_today = any(
                (item.specific_date == day if item.specific_date else item.applies_to_day(day_of_week))
                for item in bible_items
            ) if bible_items else False

            expected_today = bool(active_plan) or bible_routine_today

            if not expected_today:
                day += timedelta(days=1)
                continue

            completed = (day in progress_dates) or (day in bible_log_dates)

            events.append({
                "user": user,
                "event_date": day,
                "domain": DOMAIN_FAITH,
                "scoring_bucket": BUCKET_FAITH,
                "item_type": "BibleReading",
                "item_id": active_plan.id if active_plan else None,
                "item_label": "Bible Reading",
                "expected_at": None,
                "expected": True,
                "source_system": SOURCE_READING_PROGRESS if (day in progress_dates) else SOURCE_READING_PLAN,
                "actual_status": ACTUAL_COMPLETED if completed else ACTUAL_NONE,
                "final_status": FINAL_COMPLETED if completed else FINAL_MISSED,
                "reason_code": REASON_ENTRY_EXISTS if completed else REASON_NO_ENTRY,
                "reason_detail": {},
            })

            day += timedelta(days=1)

        return events
    except Exception:
        logger.error("Bible reading compliance evaluation failed", exc_info=True)
        return []
