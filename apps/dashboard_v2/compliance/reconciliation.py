"""
Reconciliation Engine — generic obligation-aware dedupe across ALL domains.

Two-pass identity assignment:
    Pass 1: Native domain events (workout, journal, faith, medication, task)
            get their obligation_type + stable identity. Workout events
            register their identity so routine items can match.
    Pass 2: Routine events resolve bridge type (structural field first,
            name-matching fallback) and adopt the native domain's identity.

Obligation Key Format:
    {obligation_type}:{user_id}:{date}:{obligation_identity}

Reconciliation Rules (domain-agnostic):
    1. Group events by obligation_key (non-empty only)
    2. Pick best outcome as primary (status precedence)
    3. Prefer native-domain event as primary (workout > routine)
    4. Suppress siblings with typed suppression reason
    5. If completion exists, override sibling misses
    6. Conservative: empty key = no reconciliation
    7. Cross-domain collision guard: log and skip
"""

import logging
from collections import defaultdict

from django.conf import settings

from apps.dashboard_v2.compliance.constants import (
    DOMAIN_FAITH,
    DOMAIN_JOURNAL,
    DOMAIN_MEDICATION,
    DOMAIN_ROUTINE,
    DOMAIN_TASK,
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
    OBLIGATION_MEDICATION,
    OBLIGATION_ROUTINE,
    OBLIGATION_SUPPRESSION_MAP,
    OBLIGATION_TASK,
    OBLIGATION_WORKOUT,
    SUPPRESSED_DUPLICATE,
)

logger = logging.getLogger(__name__)

_STATUS_PRECEDENCE = {
    FINAL_COMPLETED: 0,
    FINAL_COMPLETED_LATE: 1,
    FINAL_SKIPPED: 2,
    FINAL_RESCHEDULED: 3,
    FINAL_OVERDUE: 4,
    FINAL_MISSED: 5,
}

_DOMAIN_PRIORITY = {
    DOMAIN_WORKOUT: 0, DOMAIN_JOURNAL: 0, DOMAIN_FAITH: 0,
    DOMAIN_MEDICATION: 0, DOMAIN_TASK: 0,
    DOMAIN_ROUTINE: 1,
}


def reconcile_events(event_dicts, user):
    """Run obligation reconciliation. Modifies dicts in-place."""
    _assign_obligation_keys(event_dicts, user)

    groups = defaultdict(list)
    for ev in event_dicts:
        key = ev.get("obligation_key", "")
        if key:
            groups[key].append(ev)

    for key, group in groups.items():
        if len(group) < 2:
            continue
        if not _validate_group(key, group):
            continue
        _reconcile_group(group)

    return event_dicts


def _assign_obligation_keys(event_dicts, user):
    """
    Two-pass obligation key assignment.

    Pass 1: Native domains — collect identity anchors (especially workout IDs).
    Pass 2: Routine items — resolve bridge type and adopt native identity.
    """
    user_id = user.id
    structural_map = _build_structural_obligation_map(user)

    # Collected anchors: date_str → workout identity
    workout_anchors = {}

    # ── Pass 1: Native domain events ──
    for ev in event_dicts:
        _init_obligation_fields(ev)
        domain = ev.get("domain", "")
        if domain == DOMAIN_ROUTINE:
            continue  # Defer to pass 2

        event_date = ev.get("event_date")
        if not event_date:
            continue

        date_str = str(event_date)
        item_id = ev.get("item_id")

        if domain == DOMAIN_WORKOUT:
            ev["obligation_type"] = OBLIGATION_WORKOUT
            ev["obligation_identity"] = f"ws_{item_id}" if item_id else "ws_0"
            workout_anchors[date_str] = ev["obligation_identity"]

        elif domain == DOMAIN_JOURNAL:
            ev["obligation_type"] = OBLIGATION_JOURNAL
            ev["obligation_identity"] = "entry"

        elif domain == DOMAIN_FAITH:
            item_type = ev.get("item_type", "")
            if item_type == "PrayerRoutine":
                ev["obligation_type"] = OBLIGATION_FAITH_PRAYER
                ev["obligation_identity"] = "prayer"
            elif item_type == "BibleReading":
                ev["obligation_type"] = OBLIGATION_FAITH_BIBLE
                ev["obligation_identity"] = "bible"

        elif domain == DOMAIN_MEDICATION:
            ev["obligation_type"] = OBLIGATION_MEDICATION
            expected_at = ev.get("expected_at")
            time_str = expected_at.strftime("%H%M") if expected_at else "0000"
            ev["obligation_identity"] = f"ms_{item_id}_{time_str}"

        elif domain == DOMAIN_TASK:
            ev["obligation_type"] = OBLIGATION_TASK
            ev["obligation_identity"] = f"task_{item_id}" if item_id else "unknown"

        _build_key(ev, user_id)

    # ── Pass 2: Routine events ──
    for ev in event_dicts:
        domain = ev.get("domain", "")
        if domain != DOMAIN_ROUTINE:
            continue

        _init_obligation_fields(ev)
        event_date = ev.get("event_date")
        if not event_date:
            continue

        date_str = str(event_date)
        item_id = ev.get("item_id")

        bridge_type = _get_routine_bridge_type(ev, item_id, structural_map)

        if bridge_type == OBLIGATION_WORKOUT:
            ev["obligation_type"] = OBLIGATION_WORKOUT
            # Use the workout anchor collected in pass 1, or DB lookup fallback
            if date_str in workout_anchors:
                ev["obligation_identity"] = workout_anchors[date_str]
            else:
                ws_id = _find_workout_schedule_for_day(ev.get("user"), event_date)
                ev["obligation_identity"] = f"ws_{ws_id}" if ws_id else f"rs_{item_id}"

        elif bridge_type == OBLIGATION_JOURNAL:
            ev["obligation_type"] = OBLIGATION_JOURNAL
            ev["obligation_identity"] = "entry"

        elif bridge_type == OBLIGATION_FAITH_PRAYER:
            ev["obligation_type"] = OBLIGATION_FAITH_PRAYER
            ev["obligation_identity"] = "prayer"

        elif bridge_type == OBLIGATION_FAITH_BIBLE:
            ev["obligation_type"] = OBLIGATION_FAITH_BIBLE
            ev["obligation_identity"] = "bible"

        else:
            ev["obligation_type"] = OBLIGATION_ROUTINE
            ev["obligation_identity"] = f"rs_{item_id}" if item_id else "unknown"

        _build_key(ev, user_id)


def _init_obligation_fields(ev):
    """Set defaults for obligation fields."""
    ev.setdefault("obligation_type", "")
    ev.setdefault("obligation_identity", "")
    ev.setdefault("obligation_key", "")
    ev.setdefault("is_primary", True)
    ev.setdefault("suppression_reason", "")


def _build_key(ev, user_id):
    """Build composite obligation_key from type + identity."""
    if ev["obligation_type"] and ev["obligation_identity"]:
        date_str = str(ev.get("event_date", ""))
        ev["obligation_key"] = (
            f"{ev['obligation_type']}:{user_id}:{date_str}:"
            f"{ev['obligation_identity']}"
        )


def _build_structural_obligation_map(user):
    """RoutineSchedule.id → obligation_type from DB field."""
    try:
        from apps.life.models import RoutineSchedule
        qs = RoutineSchedule.objects.filter(
            routine__user=user, routine__is_active=True,
            routine__status="active", is_active=True,
        ).exclude(obligation_type="").values_list("id", "obligation_type")
        return dict(qs)
    except Exception:
        return {}


def _get_routine_bridge_type(ev, item_id, structural_map):
    """
    Determine obligation type a routine item bridges to.

    Priority:
    1. RoutineSchedule.obligation_type (structural — preferred)
    2. Name-based matching (DEPRECATED fallback)
    """
    if item_id and item_id in structural_map:
        return structural_map[item_id]

    # DEPRECATED fallback — TODO: remove when all rows have obligation_type
    from apps.core.execution.execution_truth_engine import (
        FAITH_BIBLE_NAMES, FAITH_PRAYER_NAMES, JOURNAL_NAMES, WORKOUT_NAMES,
    )
    raw_name = ev.get("item_label", "").split("(")[0].strip().lower()
    if raw_name in WORKOUT_NAMES:
        return OBLIGATION_WORKOUT
    elif raw_name in JOURNAL_NAMES:
        return OBLIGATION_JOURNAL
    elif raw_name in FAITH_PRAYER_NAMES:
        return OBLIGATION_FAITH_PRAYER
    elif raw_name in FAITH_BIBLE_NAMES:
        return OBLIGATION_FAITH_BIBLE
    return None


def _find_workout_schedule_for_day(user, event_date):
    """Find WorkoutSchedule.id for a day from the active plan."""
    try:
        from apps.health.models import WorkoutPlan
        plan = WorkoutPlan.objects.filter(
            user=user, is_active=True, status="active",
        ).prefetch_related("schedule_entries").first()
        if not plan:
            return None
        entry = plan.schedule_entries.filter(
            day_of_week=event_date.weekday(), is_rest_day=False,
        ).first()
        return entry.id if entry else None
    except Exception:
        return None


def _validate_group(key, group):
    """H4 safety: skip reconciliation if obligation_types are mixed."""
    types = {ev.get("obligation_type") for ev in group}
    if len(types) > 1:
        logger.warning(
            "Compliance reconciliation: key %s has mixed types %s — skipping",
            key, types,
        )
        return False
    return True


def _reconcile_group(group):
    """Determine which event in an obligation group is score-bearing."""
    obligation_type = group[0].get("obligation_type", "")
    _debug = getattr(settings, "COMPLIANCE_DEBUG", False)

    if _debug:
        labels = [f"{e.get('domain')}:{e.get('item_label')}={e.get('final_status')}"
                  for e in group]
        logger.info("Reconcile [%s]: %s", obligation_type, labels)

    def sort_key(ev):
        return (
            _STATUS_PRECEDENCE.get(ev.get("final_status", ""), 99),
            _DOMAIN_PRIORITY.get(ev.get("domain", ""), 2),
        )

    group.sort(key=sort_key)

    primary = group[0]
    primary["is_primary"] = True
    primary["suppression_reason"] = ""

    best_status = primary.get("final_status")
    best_is_positive = best_status in (FINAL_COMPLETED, FINAL_COMPLETED_LATE)
    linked_suppression = OBLIGATION_SUPPRESSION_MAP.get(
        obligation_type, SUPPRESSED_DUPLICATE
    )

    for ev in group[1:]:
        ev["is_primary"] = False
        ev_status = ev.get("final_status")

        if best_is_positive and ev_status in (FINAL_MISSED, FINAL_OVERDUE):
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

        if _debug:
            logger.info("  Suppressed: %s (%s→%s, %s)",
                        ev.get("item_label"), ev_status,
                        ev.get("final_status"), ev.get("suppression_reason"))
