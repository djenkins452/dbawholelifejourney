"""Phase 1 objective WEIGHT milestone evaluator.

Bidirectional. The GoalMilestone table has historically been a
text-only manual-toggle checkbox; this module adds a thin evaluator
for the exactly-one supported case
(``objective_metric="weight_lb"``, ``objective_operator="lte"``) so a
weight-loss milestone auto-completes when current weight ≤ target and
auto-uncompletes if the weight later climbs above target.

Scope is deliberately tiny — Phase 1 plan. No registries, no
abstractions. Future PRs will generalize to body_fat / steps /
A1C / BP. Until then, every other milestone keeps its existing
manual + one-way behavior.

Fail-soft: the public surface NEVER raises into the caller (see the
WeightEntry signal handler that drives this evaluator on every weight
write).
"""

from decimal import Decimal
import logging
import re
from typing import Optional

from django.utils import timezone

logger = logging.getLogger(__name__)

# Conservative weight-target parse for TITLE-FORM milestones — the SAME
# heuristic goal_pace (`_nearest_weight_milestone`) uses to DISPLAY these as the
# "next milestone": the title must mention weight/lb and carry a plausible
# body-weight number (80–500 lb). Anything else (e.g. "Run first 10K") parses to
# None and is left as a manual achievement milestone.
_WEIGHT_TITLE_NUM = re.compile(r"(\d{2,3}(?:\.\d+)?)")


def _parse_weight_target_from_title(title) -> Optional[Decimal]:
    tl = (title or "").lower()
    if "weight" not in tl and "lb" not in tl:
        return None
    hit = _WEIGHT_TITLE_NUM.search(title or "")
    if not hit:
        return None
    val = float(hit.group(1))
    if 80 <= val <= 500:
        return Decimal(str(val))
    return None


def _latest_weight_lb(user) -> Optional[Decimal]:
    """Return the user's latest active WeightEntry value as Decimal lbs,
    or None when no entry exists.

    Reads the same canonical source ``HealthProfile.get_weight_progress``
    uses — most recent active row by ``recorded_at``.
    """
    from apps.health.models import WeightEntry

    entry = (
        WeightEntry.objects
        .filter(user=user, status="active")
        .order_by("-recorded_at")
        .first()
    )
    if entry is None:
        return None
    # Decimal round-trip through str() avoids float precision drift
    # — important for 289.9 boundary correctness.
    return Decimal(str(entry.value_in_lb))


def evaluate_weight_milestones(user, emit: bool = True) -> int:
    """Re-evaluate every objective weight milestone for ``user``.

    Bidirectional convergence:
      - If ``current_weight <= target`` and milestone is NOT completed,
        set ``completed=True`` + ``completed_date=today``.
      - If ``current_weight > target`` and milestone IS completed,
        set ``completed=False`` + ``completed_date=None``.

    Idempotent: when the resulting state matches the current row, the
    function performs no DB save (no ``updated_at`` churn, no signal
    re-fire). Achievement milestones (``objective_metric=None``) are
    filtered out at the query level and are never touched.

    Args:
        user: Django User instance.

    Returns:
        int — number of milestone rows actually mutated.
    """
    from apps.purpose.models import GoalMilestone

    current = _latest_weight_lb(user)
    if current is None:
        return 0

    # LifeGoal.status: "active" is the live working state. We don't
    # touch milestones on goals that have been released or completed
    # so historical state stays intact.
    qs = GoalMilestone.objects.filter(
        goal__user=user,
        goal__status="active",
        objective_metric="weight_lb",
        objective_operator="lte",
    ).select_related("goal")

    changed = 0
    for milestone in qs:
        target = milestone.objective_target_value
        if target is None:
            continue
        should_complete = current <= target
        if should_complete == milestone.completed:
            continue  # No state change — idempotent skip.

        milestone.completed = should_complete
        milestone.completed_date = (
            timezone.localdate() if should_complete else None
        )
        milestone.save(update_fields=[
            "completed", "completed_date", "updated_at",
        ])
        changed += 1
        logger.info(
            "OBJECTIVE_WEIGHT_MILESTONE user=%s milestone=%s "
            "current=%s target=%s op=lte → completed=%s",
            user.id, milestone.id, current, target, should_complete,
        )
        # A FALSE→TRUE transition is a mission-significant ACHIEVEMENT — emit the
        # domain event so the Significant Event Pipeline reacts in the moment
        # (recognize → notify → re-plan) instead of waiting for the 3-hour CoS
        # Event Engine scheduler. Un-completions (TRUE→FALSE) are not events.
        if should_complete and emit:
            _emit_milestone_achieved(user, milestone, current, target)

    # ── Title-form weight milestones (objective_metric IS NULL) ─────────
    # A weight milestone written only as a TITLE ("Reach 284.9 lb", "Goal
    # Weight of 289.9") is the common production shape — most rungs were never
    # wired to the objective_* columns (only ONE France rung was, via migration
    # 0018). goal_pace already PARSES these titles to DISPLAY them as the "next
    # milestone", but the evaluator never COMPLETED them — so a rung you
    # actually crossed showed as "next" forever and the mission froze (France
    # stuck at 1/12). Complete them ONE-WAY (achievement: never auto-uncomplete,
    # to respect a manual toggle) using the SAME conservative parse goal_pace
    # uses, and emit the significant event so the full propagation chain fires.
    # Non-weight achievements ("Run first 10K") parse to None → left manual
    # (Phase-1 back-compat contract preserved).
    for milestone in GoalMilestone.objects.filter(
            goal__user=user, goal__status="active",
            objective_metric__isnull=True, completed=False).select_related("goal"):
        target = _parse_weight_target_from_title(milestone.title)
        if target is None or current > target:
            continue
        milestone.completed = True
        milestone.completed_date = timezone.localdate()
        milestone.save(update_fields=["completed", "completed_date", "updated_at"])
        changed += 1
        logger.info(
            "TITLE_WEIGHT_MILESTONE user=%s milestone=%s current=%s target=%s "
            "→ completed (title-form, one-way)",
            user.id, milestone.id, current, target,
        )
        if emit:
            _emit_milestone_achieved(user, milestone, current, target)

    return changed


def _emit_milestone_achieved(user, milestone, current, target_value=None) -> None:
    """Fire ``purpose.milestone.completed`` on a milestone achievement.

    Fail-soft: this evaluator runs on the weight-write request path AND inside
    read-path pace computations (cos_intelligence), so emission must never raise.
    The event only fires on the real FALSE→TRUE transition (the evaluator is
    idempotent — subsequent calls find ``completed=True`` and skip), so it is
    emitted exactly once per achievement.
    """
    try:
        from apps.core.events.domain_events import EventTypes, safe_emit_event

        # objective-form carries the target on the row; title-form passes it in.
        target = milestone.objective_target_value
        if target is None:
            target = target_value
        safe_emit_event(
            EventTypes.PURPOSE_MILESTONE_COMPLETED,
            user,
            {
                "milestone_id": milestone.id,
                "goal_id": milestone.goal_id,
                "title": milestone.title,
                "metric": "weight_lb",
                "target_value": float(target) if target is not None else None,
                "target_date": (milestone.target_date.isoformat()
                                if milestone.target_date else None),
                "current_weight": float(current),
                "achieved_date": (milestone.completed_date
                                  or timezone.localdate()).isoformat(),
            },
            source="objective_weight_milestones",
        )
    except Exception:
        logger.warning(
            "objective_weight_milestone emit failed (milestone=%s)",
            getattr(milestone, "id", "?"), exc_info=True,
        )


def recompute_objective_milestones(user) -> int:
    """Operational repair utility — re-evaluate every objective
    milestone for ``user`` from canonical data.

    Same philosophy as a SAE rebuild: if milestone truth ever drifts
    out of sync with canonical data (manual DB edit, missed signal,
    data backfill, etc.), this function deterministically converges
    the milestone state to whatever the raw data says it should be.

    Phase 1 covers only weight milestones; future phases will extend
    this dispatcher to call additional evaluators (body fat, steps,
    A1C, BP) without changing this entry point.

    Returns the number of rows mutated.

    Fail-soft via the underlying evaluator — never raises into the
    caller. Safe to call from views, tasks, management commands, or
    future endpoints.
    """
    try:
        # Repair = converge truth silently (emit=False); re-announcing an old
        # achievement during a repair sweep would be misleading.
        return evaluate_weight_milestones(user, emit=False)
    except Exception:
        logger.warning(
            "recompute_objective_milestones failed for user=%s",
            getattr(user, "id", "?"), exc_info=True,
        )
        return 0
