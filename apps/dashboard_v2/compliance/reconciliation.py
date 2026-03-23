"""
Reconciliation Engine — resolves duplicate obligations after event generation.

Architecture:
    adapters generate raw events → reconcile() groups by obligation → one
    score-bearing event per obligation → rollups read only is_primary=True.

The reconciler runs in-memory on event dicts BEFORE persistence, assigning
obligation_key, is_primary, and suppression_reason fields. This keeps the
write path as a single bulk_create with no post-hoc updates.

Obligation Key Strategy:
    - workout + routine linkage:
        key = "workout:{user_id}:{date}" for both the WorkoutSchedule event
        and any RoutineSchedule event whose name is in WORKOUT_NAMES
    - journal + routine linkage:
        key = "journal:{user_id}:{date}"
    - faith + routine linkage:
        key = "faith_prayer:{user_id}:{date}" / "faith_bible:{user_id}:{date}"
    - all others: empty string (no grouping)

Reconciliation Rules:
    1. Group events by obligation_key (non-empty keys only)
    2. Within each group, pick the best outcome as primary (precedence below)
    3. Suppress siblings with clear reason
    4. If no completion exists in group, pick the domain-native event as primary
    5. Conservative: empty key = no reconciliation

Final Status Precedence (best → worst):
    completed > completed_late > skipped > rescheduled > overdue > missed
"""

import logging
from collections import defaultdict

from apps.dashboard_v2.compliance.constants import (
    BUCKET_ROUTINE,
    DOMAIN_ROUTINE,
    DOMAIN_WORKOUT,
    FINAL_COMPLETED,
    FINAL_COMPLETED_LATE,
    FINAL_MISSED,
    FINAL_OVERDUE,
    FINAL_RESCHEDULED,
    FINAL_SKIPPED,
    SUPPRESSED_BY_LINKED_WORKOUT,
    SUPPRESSED_DUPLICATE,
)

logger = logging.getLogger(__name__)

# Precedence: lower index = better outcome
_STATUS_PRECEDENCE = {
    FINAL_COMPLETED: 0,
    FINAL_COMPLETED_LATE: 1,
    FINAL_SKIPPED: 2,
    FINAL_RESCHEDULED: 3,
    FINAL_OVERDUE: 4,
    FINAL_MISSED: 5,
}


def reconcile_events(event_dicts, user):
    """
    Run obligation reconciliation on a list of ComplianceEvent dicts.

    Modifies dicts in-place, adding:
        - obligation_key
        - is_primary
        - suppression_reason

    Args:
        event_dicts: list of dicts ready for ComplianceEvent(**d)
        user: User instance (for obligation key generation)

    Returns:
        The same list, modified in-place.
    """
    # Step 1: Assign obligation keys
    _assign_obligation_keys(event_dicts, user)

    # Step 2: Group by obligation_key and reconcile
    groups = defaultdict(list)
    for ev in event_dicts:
        key = ev.get("obligation_key", "")
        if key:
            groups[key].append(ev)

    for key, group in groups.items():
        if len(group) < 2:
            # Single event in group — nothing to reconcile
            continue
        _reconcile_group(group)

    return event_dicts


def _assign_obligation_keys(event_dicts, user):
    """
    Assign deterministic obligation_key to events that may represent
    the same real-world commitment.
    """
    from apps.core.execution.execution_truth_engine import (
        JOURNAL_NAMES,
        WORKOUT_NAMES,
    )

    user_id = user.id

    for ev in event_dicts:
        # Default: no grouping
        ev.setdefault("obligation_key", "")
        ev.setdefault("is_primary", True)
        ev.setdefault("suppression_reason", "")

        domain = ev.get("domain", "")
        event_date = ev.get("event_date")

        if not event_date:
            continue

        date_str = str(event_date)

        # ── Workout domain events get a workout obligation key ──
        if domain == DOMAIN_WORKOUT:
            ev["obligation_key"] = f"workout:{user_id}:{date_str}"

        # ── Routine items that represent workouts get the same key ──
        elif domain == DOMAIN_ROUTINE:
            item_label = ev.get("item_label", "")
            # Strip time suffix: "Chest Workout (5:30 AM)" → "Chest Workout"
            raw_name = item_label.split("(")[0].strip()

            if raw_name.lower() in WORKOUT_NAMES:
                ev["obligation_key"] = f"workout:{user_id}:{date_str}"


def _reconcile_group(group):
    """
    Given a group of events sharing an obligation_key, determine which
    is score-bearing and suppress the rest.

    Strategy:
    1. Find the best outcome (by precedence)
    2. Prefer the domain-native event as primary when outcomes tie
    3. Suppress all others with clear reason
    """
    # Sort by: best final_status first, then prefer workout domain (native)
    def sort_key(ev):
        status_rank = _STATUS_PRECEDENCE.get(ev.get("final_status", ""), 99)
        # Prefer workout-domain event as primary (it's the "real" completion)
        domain_rank = 0 if ev.get("domain") == DOMAIN_WORKOUT else 1
        return (status_rank, domain_rank)

    group.sort(key=sort_key)

    primary = group[0]
    primary["is_primary"] = True
    primary["suppression_reason"] = ""

    best_status = primary.get("final_status")
    best_is_positive = best_status in (FINAL_COMPLETED, FINAL_COMPLETED_LATE)

    for ev in group[1:]:
        ev["is_primary"] = False

        # Determine suppression reason
        ev_status = ev.get("final_status")
        if best_is_positive and ev_status in (FINAL_MISSED, FINAL_OVERDUE):
            # The key case: workout completed but routine item missed
            ev["suppression_reason"] = SUPPRESSED_BY_LINKED_WORKOUT
            # Override the final_status to reflect the linked completion
            ev["final_status"] = best_status
            ev["reason_code"] = "satisfied_by_linked_workout"
            ev["reason_detail"] = {
                **ev.get("reason_detail", {}),
                "satisfied_by_domain": primary.get("domain"),
                "satisfied_by_label": primary.get("item_label"),
                "original_status": ev_status,
            }
        else:
            ev["suppression_reason"] = SUPPRESSED_DUPLICATE
