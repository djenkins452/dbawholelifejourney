"""Converge TITLE-FORM weight milestones that have already been crossed.

Production capability gap (2026-07-02). The objective weight-milestone evaluator
only completed milestones wired to the `objective_*` columns. Migration 0018
wired exactly ONE France rung (289.9) — deliberately narrow. Every other weight
rung (e.g. "Reach 284.9 lb") stayed TITLE-FORM (`objective_metric IS NULL`), so
it could never auto-complete even when the weight was clearly below target. The
dashboard reads milestone completion LIVE, so it faithfully showed the mission
frozen at 1/12 with an already-achieved rung still displayed as "next".

`evaluate_weight_milestones` has now been generalized to complete title-form
weight milestones one-way (achievement). This migration runs that generalized
evaluator ONCE for every user who has an incomplete title-form weight milestone,
so already-crossed rungs converge immediately — without waiting for the next
WeightEntry save.

`emit=False`: this is a backfill of PAST achievements, not a real-time event —
converge the truth silently (the dashboard + Beth read it live and are correct
on the next render). Genuinely NEW crossings notify event-driven via the
Significant Event Pipeline. Reverse is a no-op: a milestone you actually reached
is true, and prior completed-state is not recoverable.
"""

from django.db import migrations


def _converge_title_form_milestones(apps, schema_editor):
    HistoricalMilestone = apps.get_model("purpose", "GoalMilestone")

    user_ids = list(
        HistoricalMilestone.objects.filter(
            goal__status="active",
            objective_metric__isnull=True,
            completed=False,
        )
        .values_list("goal__user_id", flat=True)
        .distinct()
    )
    if not user_ids:
        return

    # Use the RUNTIME service so it reads the live WeightEntry against the real
    # user object (same pattern migration 0018 used). Best-effort: the
    # WeightEntry signal + goal_pace reads will converge later if this is skipped.
    try:
        from django.contrib.auth import get_user_model
        from apps.purpose.services.objective_weight_milestones import (
            evaluate_weight_milestones,
        )
    except Exception:
        return

    User = get_user_model()
    for user in User.objects.filter(pk__in=user_ids):
        try:
            evaluate_weight_milestones(user, emit=False)
        except Exception:
            # Never let one user's data abort the deploy migration.
            continue


class Migration(migrations.Migration):
    dependencies = [
        ("purpose", "0018_wire_france_289_9_milestone"),
    ]
    operations = [
        migrations.RunPython(
            _converge_title_form_milestones,
            migrations.RunPython.noop,
        ),
    ]
