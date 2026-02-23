"""
Phase 2 — Deadline Surfacing Engine.

ISE-driven deadline snapshot computation. No deadline computation inside
send_message(). build_cos_context() reads the latest snapshot.

Runs every 5 minutes via ISE. Only executes if:
- pending commitments exist, OR
- future goal deadlines exist, OR
- scheduled blocks in next 7 days exist.

If snapshot >10 minutes old, raises SAME anomaly STALE_DEADLINE_SNAPSHOT.

Project: Whole Life Journey
Path: apps/core/blueprint/deadline_engine.py
"""

import logging
from datetime import timedelta

from django.utils import timezone

logger = logging.getLogger(__name__)


def compute_deadline_snapshot(user):
    """
    Compute a DeadlineSnapshot for a user.

    Queries all pending commitments, goal deadlines, and scheduled blocks.
    Categorizes into due_24h, due_72h, due_7d buckets.
    Detects collision flags (pairs with <2h gap, days with >3 hard deadlines).

    Args:
        user: User instance.

    Returns:
        DeadlineSnapshot instance (saved to DB).
    """
    from apps.core.blueprint.models import (
        Commitment,
        DeadlineSnapshot,
    )

    now = timezone.now()
    h24 = now + timedelta(hours=24)
    h72 = now + timedelta(hours=72)
    d7 = now + timedelta(days=7)

    due_24h = []
    due_72h = []
    due_7d = []
    all_deadlines = []  # (datetime, label) for collision detection

    # --- Pending commitments ---
    pending = Commitment.pending_for_user(user)
    for c in pending:
        item = {
            'type': 'commitment',
            'id': c.pk,
            'text': c.normalized_text,
            'deadline': c.time_boundary.isoformat(),
            'commitment_type': c.commitment_type,
        }
        all_deadlines.append((c.time_boundary, c.normalized_text))

        if c.time_boundary <= h24:
            due_24h.append(item)
        elif c.time_boundary <= h72:
            due_72h.append(item)
        elif c.time_boundary <= d7:
            due_7d.append(item)

    # --- Goal deadlines ---
    try:
        from apps.purpose.models import Goal
        goals = Goal.objects.filter(
            user=user,
            is_completed=False,
            deadline__isnull=False,
            deadline__gte=now,
            deadline__lte=d7,
        )
        for g in goals:
            item = {
                'type': 'goal',
                'id': g.pk,
                'text': g.title,
                'deadline': g.deadline.isoformat(),
            }
            all_deadlines.append((g.deadline, g.title))

            if g.deadline <= h24:
                due_24h.append(item)
            elif g.deadline <= h72:
                due_72h.append(item)
            else:
                due_7d.append(item)
    except Exception:
        pass  # Goals module may not be available

    # --- Scheduled blocks in next 7 days ---
    try:
        from apps.core.blueprint.models import ArchitecturePlan
        for day_offset in range(7):
            target_date = (now + timedelta(days=day_offset)).date()
            plan = ArchitecturePlan.get_active_for_date(user, target_date)
            if not plan:
                continue
            for block in plan.blocks.filter(is_locked=True):
                if block.end_time:
                    import datetime as dt_module
                    block_dt = dt_module.datetime.combine(
                        target_date, block.end_time,
                        tzinfo=timezone.get_current_timezone(),
                    )
                    if block_dt > now and block_dt <= d7:
                        item = {
                            'type': 'block',
                            'id': block.pk,
                            'text': block.title,
                            'deadline': block_dt.isoformat(),
                            'tier': block.tier,
                        }
                        all_deadlines.append((block_dt, block.title))

                        if block_dt <= h24:
                            due_24h.append(item)
                        elif block_dt <= h72:
                            due_72h.append(item)
                        else:
                            due_7d.append(item)
    except Exception:
        pass

    # --- Collision detection ---
    collision_flags = _detect_collisions(all_deadlines)

    # Save snapshot
    snapshot = DeadlineSnapshot.objects.create(
        user=user,
        due_24h=due_24h,
        due_72h=due_72h,
        due_7d=due_7d,
        collision_flags=collision_flags,
    )

    return snapshot


def _detect_collisions(deadlines):
    """
    Detect deadline collisions.

    Flags:
    - Pairs of deadlines with <2h gap
    - Days with >3 hard deadlines

    Args:
        deadlines: list of (datetime, label) tuples.

    Returns:
        list of collision flag dicts.
    """
    flags = []
    sorted_dl = sorted(deadlines, key=lambda x: x[0])

    # Pair collisions (<2h gap)
    for i in range(len(sorted_dl) - 1):
        dt1, label1 = sorted_dl[i]
        dt2, label2 = sorted_dl[i + 1]
        gap = (dt2 - dt1).total_seconds() / 3600
        if gap < 2:
            flags.append({
                'type': 'pair_collision',
                'items': [label1, label2],
                'gap_hours': round(gap, 1),
            })

    # Daily overload (>3 deadlines on same day)
    from collections import Counter
    day_counts = Counter()
    for dt, label in sorted_dl:
        day_counts[dt.date()] += 1
    for day, count in day_counts.items():
        if count > 3:
            flags.append({
                'type': 'daily_overload',
                'date': day.isoformat(),
                'deadline_count': count,
            })

    return flags


def should_compute_snapshot(user):
    """
    Check if deadline snapshot computation should run for this user.

    Only executes if:
    - pending commitments exist, OR
    - future goal deadlines exist, OR
    - scheduled blocks in next 7 days exist.

    Args:
        user: User instance.

    Returns:
        bool — True if computation is needed.
    """
    from apps.core.blueprint.models import Commitment

    # Check pending commitments
    if Commitment.pending_for_user(user).exists():
        return True

    # Check future goal deadlines
    try:
        from apps.purpose.models import Goal
        if Goal.objects.filter(
            user=user,
            is_completed=False,
            deadline__isnull=False,
            deadline__gte=timezone.now(),
        ).exists():
            return True
    except Exception:
        pass

    # Check scheduled blocks in next 7 days
    try:
        from apps.core.blueprint.models import ArchitecturePlan
        for day_offset in range(7):
            target_date = (timezone.now() + timedelta(days=day_offset)).date()
            plan = ArchitecturePlan.get_active_for_date(user, target_date)
            if plan and plan.blocks.exists():
                return True
    except Exception:
        pass

    return False


def check_stale_snapshot(user):
    """
    Check if the latest snapshot is stale (>10 minutes old).

    If stale, raises SAME anomaly STALE_DEADLINE_SNAPSHOT.

    Args:
        user: User instance.

    Returns:
        dict or None — anomaly dict if stale, None otherwise.
    """
    from apps.core.blueprint.models import DeadlineSnapshot

    snapshot = DeadlineSnapshot.latest_for_user(user)
    if snapshot is None or snapshot.is_stale():
        return {
            "anomaly_type": "STALE_DEADLINE_SNAPSHOT",
            "severity": "P2",
            "engine_name": "ECC",
            "summary": (
                f"Deadline snapshot for user {user.pk} is "
                f"{'missing' if snapshot is None else 'stale (>10 min old)'}"
            ),
            "evidence": {
                "user_id": user.pk,
                "snapshot_age_minutes": (
                    round((timezone.now() - snapshot.computed_at).total_seconds() / 60, 1)
                    if snapshot else None
                ),
            },
            "suggested_actions": [
                {"action": "recompute_deadline_snapshot", "label": "Recompute deadline snapshot"},
            ],
        }
    return None
