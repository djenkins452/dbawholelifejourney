"""Backfill RoutineLog entries for structured workout sessions that were
logged on or after 2026-04-15 but missed routine auto-complete because
their duration_minutes was 0/null.

Before this deploy, `handle_workout_session_completed` (Block 2) required
total duration_minutes ≥ WORKOUT_COMPLETION_THRESHOLD_MINUTES to trigger
the workout→routine bridge. Structured strength sessions routinely leave
duration_minutes at 0, so any user whose workout was logged as sets/reps
had their routine stay unchecked despite the domain showing "Completed".

The fix in this release qualifies a session via logged exercises OR
duration threshold. This migration replays the bridge for recent
completed sessions that now qualify but previously didn't, so users
don't need to re-save each workout manually.

Scope:
  - Only sessions completed on or after 2026-04-15 (14-day lookback
    from this deploy date 2026-04-18 is generous but bounded).
  - Only sessions with:
      * completed_at IS NOT NULL
      * status != 'deleted'
      * at least one WorkoutExercise row (the new qualifying criterion)
      * no existing RoutineLog already covering that day's workout
        routine (idempotency — preserves the "first-workout-wins" rule)
  - Uses the canonical `auto_complete_routine_schedules` helper so the
    backfill produces identical log rows to the live path — no drift.
"""

from datetime import date, timedelta

from django.db import migrations


CUTOFF_DATE = date(2026, 4, 15)


def backfill(apps, schema_editor):
    # Import at migration-run time so the real helper (with signals etc.)
    # is used. We intentionally do NOT use apps.get_model() for RoutineLog
    # because auto_complete_routine_schedules needs the live manager + utils.
    from apps.health.models import WorkoutSession
    from apps.life.services.routine_helpers import (
        auto_complete_routine_schedules,
    )

    # Iterate completed structured-work sessions on/after cutoff.
    # Distinct by (user, date) — we only need to fire once per user-day;
    # the helper is idempotent (first-workout-wins) so extra calls are
    # safe but wasteful.
    sessions = (
        WorkoutSession.objects
        .filter(
            completed_at__isnull=False,
            date__gte=CUTOFF_DATE,
            workout_exercises__isnull=False,
        )
        .exclude(status="deleted")
        .order_by("user_id", "date", "started_at", "completed_at", "pk")
        .distinct()
    )

    seen_user_days = set()
    replayed = 0
    for s in sessions.iterator():
        key = (s.user_id, s.date)
        if key in seen_user_days:
            continue
        seen_user_days.add(key)

        try:
            auto_complete_routine_schedules(
                user=s.user,
                keyword="workout",
                source="workout",
                completion_time=s.started_at or s.completed_at,
                source_object_id=s.pk,
                target_date=s.date,
            )
            replayed += 1
        except Exception:
            # A failed backfill for one user-day must not block the
            # migration — the signal-level fix will cover them on next save.
            continue

    # Optional visibility into how many user-days were replayed.
    # Printed during migrate output; no-op if captured silently.
    print(
        f"[0086_backfill_structured_workout_routine_logs] "
        f"Replayed routine auto-complete for {replayed} user-day(s) "
        f"with logged exercises since {CUTOFF_DATE.isoformat()}."
    )


def noop_reverse(apps, schema_editor):
    # Reversing this migration would require tracking which RoutineLog
    # rows it created — not worth the bookkeeping. The rows are safe to
    # keep; worst case they represent a completed routine the user
    # actually did.
    pass


class Migration(migrations.Migration):

    dependencies = [
        ("health", "0085_update_intake_help_text"),
        ("life", "0053_alter_task_depends_on_key"),
    ]

    operations = [
        migrations.RunPython(backfill, noop_reverse),
    ]
