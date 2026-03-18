"""
Data migration: run one-time workout minutes audit on deploy.

Logs record-level evidence of the current 7-day workout total for all
active users, so we can verify the fix landed correctly and explain
the previous 174-minute value.
"""
import logging
from datetime import timedelta

from django.db import migrations
from django.utils import timezone

logger = logging.getLogger("wlj.health.audit")


def audit_workout_minutes(apps, schema_editor):
    """Log workout-minutes evidence for all users with recent workouts."""
    WorkoutSession = apps.get_model("health", "WorkoutSession")
    User = apps.get_model("users", "User")

    now = timezone.now()
    cutoff_7d = now - timedelta(days=7)

    user_ids = (
        WorkoutSession.objects.filter(
            date__gte=cutoff_7d.date(),
        )
        .values_list("user_id", flat=True)
        .distinct()
    )

    for user_id in user_ids:
        user = User.objects.filter(id=user_id).first()
        if not user:
            continue

        # Canonical (status='active', completed_at set)
        canonical = WorkoutSession.objects.filter(
            user_id=user_id,
            date__gte=cutoff_7d.date(),
            status="active",
            completed_at__isnull=False,
        )
        canonical_min = sum(s.duration_minutes or 0 for s in canonical)

        # All (no filters except date)
        all_sessions = WorkoutSession.objects.filter(
            user_id=user_id,
            date__gte=cutoff_7d.date(),
        )
        all_min = sum(s.duration_minutes or 0 for s in all_sessions)

        inflation = all_min - canonical_min

        evidence = []
        for s in canonical.order_by("date"):
            source = "healthkit" if s.sync_id else "manual"
            evidence.append(
                f"ID={s.id} date={s.date} type={s.workout_type or '—'} "
                f"dur={s.duration_minutes}min source={source}"
            )

        logger.info(
            "WORKOUT_AUDIT user=%s canonical=%dmin(%d sessions) "
            "all=%dmin(%d sessions) inflation=%dmin | %s",
            getattr(user, "email", user_id),
            canonical_min,
            canonical.count(),
            all_min,
            all_sessions.count(),
            inflation,
            " | ".join(evidence) if evidence else "no sessions",
        )


class Migration(migrations.Migration):
    dependencies = [
        ("health", "0063_behavior_system"),
    ]

    operations = [
        migrations.RunPython(audit_workout_minutes, migrations.RunPython.noop),
    ]
