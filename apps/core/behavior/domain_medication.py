"""
Medication domain adapter for the behavior score contract.

Reads from existing Medicine/MedicineSchedule/MedicineLog models.
No model changes — all data already exists.

Fairness rule: today's future doses (scheduled_time > now) are excluded
from expected count. You can't miss a dose that isn't due yet.
"""

import logging

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
    from apps.health.models import Intake, IntakeLog
    from apps.health.medicine_utils import get_expected_dose_entries

    active_medicines = list(
        Intake.objects.filter(
            user=user,
            intake_status=Intake.STATUS_ACTIVE,
            intake_type=Intake.INTAKE_TYPE_MEDICATION,
        ).prefetch_related("schedules")
    )

    if not active_medicines:
        return None

    # D5 / Canon §5 — single expected-dose author. Use the ONE canonical
    # enumerator (active intakes, day-of-week, future-dose-today fairness)
    # instead of re-walking schedules here. (Also drops a latent crash when a
    # schedule has no scheduled_time: the helper guards `scheduled_time` before
    # comparing.)
    expected = len(
        get_expected_dose_entries(
            user, start_date, end_date, active_medicines=active_medicines
        )
    )

    if expected == 0:
        return None

    # Count actual logs — split taken from late
    # Filter to active medicines only so logs from discontinued medicines
    # don't inflate the taken count beyond expected.
    logs = IntakeLog.objects.filter(
        user=user,
        intake__in=active_medicines,
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
