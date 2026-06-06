"""Wire the production-evidence France-mission 289.9 lb weight milestone.

Phase 1 trust fix (2026-06-03). The production dashboard surfaced:

    France 2027 Family 10K Mission
    Goal Weight of 289.9
    weight = 288.8  →  milestone still showed incomplete

This migration converts the SPECIFIC known broken row into an
objective weight milestone (metric=weight_lb, target=289.9,
operator=lte) and runs an initial evaluation so the milestone
converges against current weight without waiting for the next
WeightEntry save.

Targeting is deliberately narrow:
  - parent goal.title icontains "France"
  - milestone.title icontains "289.9"

This uniquely matches "Goal Weight of 289.9" inside the France 2027
mission and only that. No email / user filter — environment-agnostic.
No regex title parsing. No broad milestone conversion.

Reversible: the reverse function unwires only rows it owns
(objective_metric=weight_lb + objective_target_value=289.9).
"""

from decimal import Decimal

from django.db import migrations


def _wire_france_289_9_milestone(apps, schema_editor):
    GoalMilestone = apps.get_model("purpose", "GoalMilestone")

    candidates = GoalMilestone.objects.filter(
        goal__title__icontains="France",
        title__icontains="289.9",
    )

    affected_user_ids = set()
    for milestone in candidates:
        milestone.objective_metric = "weight_lb"
        milestone.objective_target_value = Decimal("289.9")
        milestone.objective_operator = "lte"
        milestone.save(update_fields=[
            "objective_metric",
            "objective_target_value",
            "objective_operator",
            "updated_at",
        ])
        affected_user_ids.add(milestone.goal.user_id)

    # Initial bidirectional evaluation — does NOT wait for the next
    # WeightEntry save. Uses the runtime service so the latest
    # WeightEntry can be read against the live user object.
    if not affected_user_ids:
        return
    try:
        from django.contrib.auth import get_user_model
        from apps.purpose.services.objective_weight_milestones import (
            evaluate_weight_milestones,
        )
        User = get_user_model()
        for user in User.objects.filter(pk__in=affected_user_ids):
            evaluate_weight_milestones(user)
    except Exception:
        # Best-effort. The WeightEntry signal will converge on the
        # next save; recompute_objective_milestones is the manual
        # repair path if needed.
        pass


def _unwire_france_289_9_milestone(apps, schema_editor):
    GoalMilestone = apps.get_model("purpose", "GoalMilestone")
    GoalMilestone.objects.filter(
        objective_metric="weight_lb",
        objective_target_value=Decimal("289.9"),
    ).update(
        objective_metric=None,
        objective_target_value=None,
        objective_operator=None,
    )


class Migration(migrations.Migration):
    dependencies = [
        ("purpose", "0017_objective_weight_milestone"),
    ]
    operations = [
        migrations.RunPython(
            _wire_france_289_9_milestone,
            _unwire_france_289_9_milestone,
        ),
    ]
