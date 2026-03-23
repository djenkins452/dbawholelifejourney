"""
Reconciliation Engine — generic obligation-aware dedupe across ALL domains.

Architecture:
    adapters generate raw events → reconcile() groups by obligation_key →
    one score-bearing event per obligation → rollups read only is_primary=True.

The reconciler runs in-memory on event dicts BEFORE persistence.

Obligation Key Format:
    {obligation_type}:{user_id}:{date}:{obligation_identity}

    Examples:
    - workout:42:2026-03-23:sched_7       (WorkoutSchedule #7)
    - journal:42:2026-03-23:daily          (daily journal obligation)
    - faith_prayer:42:2026-03-23:sched_15  (RoutineSchedule #15)
    - faith_bible:42:2026-03-23:plan_3     (UserReadingPlan #3)
    - medication:42:2026-03-23:sched_8_0800 (MedicineSchedule #8 at 08:00)

Identity Assignment Strategy:
    Each domain adapter emits obligation_type + obligation_identity.
    Routine items that bridge to another domain (workout, journal, faith)
    get that domain's obligation_type + a matching identity so they group
    together with the native domain event.

    The name-matching (WORKOUT_NAMES, JOURNAL_NAMES, FAITH_*_NAMES) is
    used ONCE at key-assignment time to classify routine items, then the
    RoutineSchedule.id becomes the stable identity for the routine side.

Reconciliation Rules (domain-agnostic):
    1. Group events by obligation_key (non-empty keys only)
    2. Pick best outcome as primary (status precedence)
    3. Prefer the native-domain event as primary (workout > routine, etc.)
    4. Suppress siblings with typed suppression reason
    5. If completion exists, override sibling misses to reflect linked completion
    6. Conservative: empty key = no reconciliation
"""

import logging
from collections import defaultdict

from apps.dashboard_v2.compliance.constants import (
    DOMAIN_FAITH,
    DOMAIN_JOURNAL,
    DOMAIN_ROUTINE,
    DOMAIN_WORKOUT,
    FINAL_COMPLETED,
    FINAL_COMPLETED_LATE,
    FINAL_MISSED,
    FINAL_OVERDUE,
    FINAL_RESCHEDULED,
    FINAL_SKIPPED,
    OBLIGATION_FAITH_BIBLE,
    OBLIGATION_FAITH_PRAYER,
    OBLIGATION_JOURNAL,
    OBLIGATION_SUPPRESSION_MAP,
    OBLIGATION_WORKOUT,
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

# Domain priority for choosing primary event within a group (native > bridge)
_DOMAIN_PRIORITY = {
    DOMAIN_WORKOUT: 0,
    DOMAIN_JOURNAL: 0,
    DOMAIN_FAITH: 0,
    DOMAIN_ROUTINE: 1,  # Routine is the bridge — prefer native domain
}


def reconcile_events(event_dicts, user):
    """
    Run obligation reconciliation on a list of ComplianceEvent dicts.

    Modifies dicts in-place. Returns the same list.
    """
    _assign_obligation_keys(event_dicts, user)

    groups = defaultdict(list)
    for ev in event_dicts:
        key = ev.get("obligation_key", "")
        if key:
            groups[key].append(ev)

    for key, group in groups.items():
        if len(group) < 2:
            continue
        _reconcile_group(group)

    return event_dicts


def _assign_obligation_keys(event_dicts, user):
    """
    Assign obligation_type, obligation_identity, and obligation_key
    to each event dict.

    Strategy:
    - Native domain events (workout, journal, faith, medication, task)
      get their own obligation type + stable ID.
    - Routine items that bridge to another domain get THAT domain's
      obligation type so they group together for reconciliation.
    """
    from apps.core.execution.execution_truth_engine import (
        FAITH_BIBLE_NAMES,
        FAITH_PRAYER_NAMES,
        JOURNAL_NAMES,
        WORKOUT_NAMES,
    )

    user_id = user.id

    for ev in event_dicts:
        ev.setdefault("obligation_type", "")
        ev.setdefault("obligation_identity", "")
        ev.setdefault("obligation_key", "")
        ev.setdefault("is_primary", True)
        ev.setdefault("suppression_reason", "")

        domain = ev.get("domain", "")
        event_date = ev.get("event_date")
        if not event_date:
            continue

        date_str = str(event_date)
        item_id = ev.get("item_id")

        # ── Native domain identity assignment ──

        if domain == DOMAIN_WORKOUT:
            ev["obligation_type"] = OBLIGATION_WORKOUT
            # WorkoutSchedule has unique_together(plan, day_of_week), so
            # there's at most one workout obligation per day. Use "daily"
            # as identity to match routine workout items for that day.
            ev["obligation_identity"] = "daily"

        elif domain == DOMAIN_JOURNAL:
            ev["obligation_type"] = OBLIGATION_JOURNAL
            ev["obligation_identity"] = "daily"

        elif domain == DOMAIN_FAITH:
            item_type = ev.get("item_type", "")
            if item_type == "PrayerRoutine":
                ev["obligation_type"] = OBLIGATION_FAITH_PRAYER
                ev["obligation_identity"] = "daily"
            elif item_type == "BibleReading":
                ev["obligation_type"] = OBLIGATION_FAITH_BIBLE
                ev["obligation_identity"] = "daily"

        elif domain == DOMAIN_ROUTINE:
            # Check if this routine item bridges to another domain
            raw_name = _extract_raw_name(ev.get("item_label", ""))
            name_lower = raw_name.lower()

            if name_lower in WORKOUT_NAMES:
                ev["obligation_type"] = OBLIGATION_WORKOUT
                ev["obligation_identity"] = "daily"

            elif name_lower in JOURNAL_NAMES:
                ev["obligation_type"] = OBLIGATION_JOURNAL
                ev["obligation_identity"] = "daily"

            elif name_lower in FAITH_PRAYER_NAMES:
                ev["obligation_type"] = OBLIGATION_FAITH_PRAYER
                ev["obligation_identity"] = "daily"

            elif name_lower in FAITH_BIBLE_NAMES:
                ev["obligation_type"] = OBLIGATION_FAITH_BIBLE
                ev["obligation_identity"] = "daily"

        # Build composite key
        if ev["obligation_type"] and ev["obligation_identity"]:
            ev["obligation_key"] = (
                f"{ev['obligation_type']}:{user_id}:{date_str}:"
                f"{ev['obligation_identity']}"
            )


def _extract_raw_name(label):
    """Strip time suffix from label: 'Workout (5:30 AM)' → 'Workout'."""
    return label.split("(")[0].strip()


def _reconcile_group(group):
    """
    Given events sharing an obligation_key, determine which is score-bearing.

    Domain-agnostic: uses obligation_type for suppression reason mapping.
    """
    obligation_type = group[0].get("obligation_type", "")

    def sort_key(ev):
        status_rank = _STATUS_PRECEDENCE.get(ev.get("final_status", ""), 99)
        domain_rank = _DOMAIN_PRIORITY.get(ev.get("domain", ""), 2)
        return (status_rank, domain_rank)

    group.sort(key=sort_key)

    primary = group[0]
    primary["is_primary"] = True
    primary["suppression_reason"] = ""

    best_status = primary.get("final_status")
    best_is_positive = best_status in (FINAL_COMPLETED, FINAL_COMPLETED_LATE)

    # Get the typed suppression reason for this obligation domain
    linked_suppression = OBLIGATION_SUPPRESSION_MAP.get(
        obligation_type, SUPPRESSED_DUPLICATE
    )

    for ev in group[1:]:
        ev["is_primary"] = False
        ev_status = ev.get("final_status")

        if best_is_positive and ev_status in (FINAL_MISSED, FINAL_OVERDUE):
            # Linked completion satisfies the missed sibling
            ev["suppression_reason"] = linked_suppression
            ev["final_status"] = best_status
            ev["reason_code"] = "satisfied_by_linked"
            ev["reason_detail"] = {
                **ev.get("reason_detail", {}),
                "satisfied_by_domain": primary.get("domain"),
                "satisfied_by_label": primary.get("item_label"),
                "original_status": ev_status,
            }
        else:
            ev["suppression_reason"] = SUPPRESSED_DUPLICATE
