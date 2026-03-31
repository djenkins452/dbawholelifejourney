"""
Medication domain adapter for the behavior score contract.

Reads from existing Medicine/MedicineSchedule/MedicineLog models.
No model changes — all data already exists.

Fairness rule: today's future doses (scheduled_time > now) are excluded
from expected count. You can't miss a dose that isn't due yet.
"""

import logging
from datetime import timedelta

from apps.core.behavior.status_engine import build_behavior_output

logger = logging.getLogger(__name__)


def calculate_medicine_behavior_output(user, start_date, end_date):
    """
    Produce the standardized behavior output contract for medication.

    Splits taken/late (existing MedicineLog.log_status), applies strict
    accountability scoring (completed=1.0, late=0.7, skipped=0.0, missed=0.0).

    Today's future doses (scheduled after current time) are excluded from
    expected count — you can't miss a dose that isn't due yet.

    Args:
        user: User instance
        start_date: date
        end_date: date

    Returns:
        dict matching behavior output contract, or None if no medicines
    """
    from apps.core.utils import get_user_now, get_user_today
    from apps.health.models import Medicine, MedicineLog

    active_medicines = Medicine.objects.filter(
        user=user,
        medicine_status=Medicine.STATUS_ACTIVE,
    ).prefetch_related("schedules")

    if not active_medicines.exists():
        return None

    user_today = get_user_today(user)
    user_now = get_user_now(user)
    current_time = user_now.time()

    # Count expected doses by iterating each day and checking schedules.
    # For today: only count doses whose scheduled_time has passed.
    expected = 0
    day = start_date
    while day <= end_date:
        day_of_week = day.weekday()
        is_today = (day == user_today)
        for medicine in active_medicines:
            for schedule in medicine.schedules.filter(is_active=True):
                if schedule.applies_to_day(day_of_week):
                    if is_today and schedule.scheduled_time > current_time:
                        # Future dose today — not due yet, skip
                        continue
                    expected += 1
        day += timedelta(days=1)

    if expected == 0:
        return None

    # Count actual logs — split taken from late
    # Filter to active medicines only so logs from discontinued medicines
    # don't inflate the taken count beyond expected.
    logs = MedicineLog.objects.filter(
        user=user,
        medicine__in=active_medicines,
        scheduled_date__gte=start_date,
        scheduled_date__lte=end_date,
    )
    completed = logs.filter(log_status="taken").count()
    late = logs.filter(log_status="late").count()
    skipped = logs.filter(log_status="skipped").count()
    explicit_missed = logs.filter(log_status="missed").count()

    # Missed = expected minus all accounted-for interactions
    accounted = completed + late + skipped + explicit_missed
    unlogged = max(0, expected - accounted)
    missed = explicit_missed + unlogged

    return build_behavior_output(
        domain='medication',
        expected=expected,
        completed=completed,
        late=late,
        skipped=skipped,
        missed=missed,
    )
