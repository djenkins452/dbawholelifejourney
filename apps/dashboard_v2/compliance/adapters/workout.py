"""
Workout domain adapter — evaluates WorkoutPlan/WorkoutSchedule/WorkoutSession
into canonical ComplianceEvent rows.

Truth hierarchy (WLJ architecture):
1. WorkoutSession (raw data) — checked FIRST as single source of truth
2. WorkoutScheduleLog (derived bridge) — fallback for timeliness/skip info
3. Absence of both → MISSED
"""

import logging
from datetime import timedelta

from apps.dashboard_v2.compliance.constants import (
    ACTUAL_COMPLETED,
    ACTUAL_COMPLETED_LATE,
    ACTUAL_NONE,
    ACTUAL_SKIPPED,
    BUCKET_WORKOUT,
    DOMAIN_WORKOUT,
    FINAL_COMPLETED,
    FINAL_COMPLETED_LATE,
    FINAL_MISSED,
    FINAL_NOT_EXPECTED,
    FINAL_SKIPPED,
    REASON_AFTER_GRACE,
    REASON_COMPLETED_VIA_SESSION,
    REASON_EXPLICIT_SKIP,
    REASON_NOT_COMPLETED,
    REASON_ON_TIME,
    REASON_REST_DAY,
    SOURCE_WORKOUT_SCHEDULE,
    SOURCE_WORKOUT_SCHEDULE_LOG,
    SOURCE_WORKOUT_SESSION,
)

logger = logging.getLogger(__name__)

DAY_NAMES = {0: "Monday", 1: "Tuesday", 2: "Wednesday", 3: "Thursday",
             4: "Friday", 5: "Saturday", 6: "Sunday"}


def evaluate_workout(user, start_date, end_date):
    """
    Produce ComplianceEvent dicts for workout domain.

    One event per expected workout day (non-rest schedule entries).

    Checks WorkoutSession (raw truth) first, then falls back to
    WorkoutScheduleLog (derived bridge) for timeliness and skip info.
    """
    try:
        from apps.health.models import (
            WorkoutPlan,
            WorkoutScheduleLog,
            WorkoutSession,
        )

        active_plan = WorkoutPlan.objects.filter(
            user=user, is_active=True, status="active",
        ).prefetch_related("schedule_entries", "schedule_entries__template").first()

        if not active_plan:
            return []

        schedule_entries = list(active_plan.schedule_entries.all())
        if not schedule_entries:
            return []

        # Build lookup of schedule logs (derived bridge)
        log_qs = WorkoutScheduleLog.objects.filter(
            user=user,
            scheduled_date__gte=start_date,
            scheduled_date__lte=end_date,
            schedule__plan=active_plan,
        )
        log_map = {}
        for log in log_qs:
            key = (log.schedule_id, log.scheduled_date)
            log_map[key] = log

        # Build lookup of completed WorkoutSessions by date (raw truth)
        # A session with completed_at set = workout definitively happened.
        session_qs = WorkoutSession.objects.filter(
            user=user,
            date__gte=start_date,
            date__lte=end_date,
            completed_at__isnull=False,
        ).values_list("date", "id")
        # Map date → first completed session id
        session_map = {}
        for session_date, session_id in session_qs:
            if session_date not in session_map:
                session_map[session_date] = session_id

        events = []
        day = start_date
        while day <= end_date:
            day_of_week = day.weekday()
            for entry in schedule_entries:
                if entry.day_of_week != day_of_week:
                    continue

                if entry.is_rest_day:
                    # Rest day — not expected, not counted
                    continue

                template_name = entry.template.name if entry.template else "Workout"
                day_name = DAY_NAMES.get(day_of_week, "")
                label = f"{template_name} ({day_name})"

                key = (entry.id, day)
                log = log_map.get(key)
                session_id = session_map.get(day)

                event = _build_workout_event(
                    user, day, entry, label, log, session_id,
                )
                events.append(event)

            day += timedelta(days=1)

        return events
    except Exception:
        logger.error("Workout compliance adapter failed", exc_info=True)
        return []


def _build_workout_event(user, day, schedule_entry, label, log, session_id):
    """Build a single ComplianceEvent dict for one workout day.

    Priority:
    1. WorkoutScheduleLog with valid status (has timeliness + skip info)
    2. WorkoutSession with completed_at (raw truth fallback)
    3. Neither → MISSED
    """
    base = {
        "user": user,
        "event_date": day,
        "domain": DOMAIN_WORKOUT,
        "scoring_bucket": BUCKET_WORKOUT,
        "item_type": "WorkoutSchedule",
        "item_id": schedule_entry.id,
        "item_label": label,
        "expected_at": schedule_entry.preferred_time,
        "expected": True,
    }

    # ── Path 1: WorkoutScheduleLog exists (derived bridge with timeliness) ──
    if log:
        base["source_system"] = SOURCE_WORKOUT_SCHEDULE_LOG
        if log.log_status == "completed":
            base.update({
                "actual_status": ACTUAL_COMPLETED,
                "final_status": FINAL_COMPLETED,
                "reason_code": REASON_ON_TIME,
                "reason_detail": {"log_id": log.id, "session_id": log.session_id if hasattr(log, "session_id") else None},
            })
        elif log.log_status == "completed_late":
            base.update({
                "actual_status": ACTUAL_COMPLETED_LATE,
                "final_status": FINAL_COMPLETED_LATE,
                "reason_code": REASON_AFTER_GRACE,
                "reason_detail": {"log_id": log.id},
            })
        elif log.log_status == "skipped":
            base.update({
                "actual_status": ACTUAL_SKIPPED,
                "final_status": FINAL_SKIPPED,
                "reason_code": REASON_EXPLICIT_SKIP,
                "reason_detail": {"log_id": log.id},
            })
        else:
            # Unknown log status — check raw truth before declaring missed
            if session_id:
                base["source_system"] = SOURCE_WORKOUT_SESSION
                base.update({
                    "actual_status": ACTUAL_COMPLETED,
                    "final_status": FINAL_COMPLETED,
                    "reason_code": REASON_COMPLETED_VIA_SESSION,
                    "reason_detail": {"session_id": session_id},
                })
            else:
                base.update({
                    "actual_status": ACTUAL_NONE,
                    "final_status": FINAL_MISSED,
                    "reason_code": REASON_NOT_COMPLETED,
                    "reason_detail": {},
                })

    # ── Path 2: No log, but completed WorkoutSession exists (raw truth) ──
    elif session_id:
        base["source_system"] = SOURCE_WORKOUT_SESSION
        base.update({
            "actual_status": ACTUAL_COMPLETED,
            "final_status": FINAL_COMPLETED,
            "reason_code": REASON_COMPLETED_VIA_SESSION,
            "reason_detail": {"session_id": session_id},
        })

    # ── Path 3: Neither log nor session → genuinely missed ──
    else:
        base["source_system"] = SOURCE_WORKOUT_SCHEDULE
        base.update({
            "actual_status": ACTUAL_NONE,
            "final_status": FINAL_MISSED,
            "reason_code": REASON_NOT_COMPLETED,
            "reason_detail": {},
        })

    return base
