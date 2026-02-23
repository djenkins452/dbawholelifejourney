"""
Phase 5 — Protective Action Engine.

Turns forecast/pressure/deadline signals into USER-FACING protective
recommendations and alerts. Advisory-only v1 — never auto-modifies
schedule or commitments.

Deterministic only. No LLM calls.

Core functions:
    - compute_protective_recommendations(user, now_local, horizon_days=7)
    - schedule_deadline_alerts(user, now_local)
    - apply_overload_triggers(user, pressure_snapshot)
    - expire_superseded_recommendations(user)
    - deliver_due_alerts(now=None)
    - run_protective_sweep()

Project: Whole Life Journey
Path: apps/core/blueprint/protective_engine.py
"""

import datetime as dt
import logging

from django.utils import timezone

from apps.core.blueprint.protective_models import (
    ProtectiveActionLog,
    ProtectiveAlert,
    ProtectiveRecommendation,
)

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

# CPI thresholds
CPI_ELEVATED = 60
CPI_HIGH = 80
CPI_CRITICAL = 90

# Density threshold for overloaded days
DENSITY_OVERLOADED = 0.85

# Minimum free gap (minutes) to suggest a time block
MIN_FREE_GAP_MINUTES = 30

# Breach probability threshold for renegotiation prompt
BREACH_PROB_THRESHOLD = 0.6

# Collision thresholds
COLLISION_HARD_DEADLINE_DAY_MAX = 3
COLLISION_GAP_HOURS = 2

# Alert timing offsets (before deadline)
ALERT_OFFSETS = {
    ProtectiveAlert.TYPE_DEADLINE_24H: dt.timedelta(hours=24),
    ProtectiveAlert.TYPE_DEADLINE_4H: dt.timedelta(hours=4),
    ProtectiveAlert.TYPE_DEADLINE_1H: dt.timedelta(hours=1),
}

# Supersede window (hours)
SUPERSEDE_WINDOW_HOURS = 12

# DNE throttle defaults (per user per day)
DNE_MAX_ALERTS_PER_HOUR = 3
DNE_MAX_ALERTS_PER_DAY = 10

# Day boundaries for available minutes calculation
DAY_START_HOUR = 7
DAY_END_HOUR = 22
AVAILABLE_MINUTES_PER_DAY = (DAY_END_HOUR - DAY_START_HOUR) * 60  # 900

# Human-language load status labels
LOAD_STATUS_MAP = {
    'normal': 'Normal',
    'elevated': 'Elevated',
    'high': 'High',
    'critical': 'Critical',
}


def get_load_status_label(cpi):
    """Map CPI to human-language load status label."""
    if cpi >= CPI_CRITICAL:
        return 'Critical'
    elif cpi >= CPI_HIGH:
        return 'High'
    elif cpi >= CPI_ELEVATED:
        return 'Elevated'
    return 'Normal'


# ---------------------------------------------------------------------------
# 1) Protective Recommendations
# ---------------------------------------------------------------------------

def compute_protective_recommendations(user, now_local=None, horizon_days=7):
    """
    Generate protective recommendations when risk thresholds are crossed.

    Deterministic: same inputs → same outputs.
    Advisory only: no auto-changes to schedule/commitments.

    Returns:
        list[ProtectiveRecommendation] — Newly created recommendations.
    """
    if now_local is None:
        now_local = timezone.now()

    created = []

    # Get latest pressure snapshot
    pressure = _get_latest_pressure(user)
    if not pressure:
        return created

    cpi = pressure.pressure_index

    # --- TIME_BLOCK_SUGGESTION ---
    # If CPI > 60 AND there's a free gap >= 30 min in next 48h
    if cpi > CPI_ELEVATED:
        highest_risk_item = _find_highest_risk_item(user, now_local)
        if highest_risk_item:
            has_gap = _has_free_gap(user, now_local, hours_ahead=48)
            if has_gap:
                rec = _create_recommendation(
                    user=user,
                    rec_type=ProtectiveRecommendation.TYPE_TIME_BLOCK,
                    title="Block time for what matters most",
                    message=(
                        f"Your schedule is busier than usual. "
                        f"Consider blocking time for: {highest_risk_item['label']}. "
                        f"You have an open slot in the next couple of days."
                    ),
                    call_to_action={
                        'A': {'text': 'Suggest times for me', 'action_key': 'suggest_times'},
                        'B': {'text': "I'll handle it", 'action_key': 'dismiss'},
                    },
                    priority=70 if cpi > CPI_HIGH else 50,
                    related_type=highest_risk_item.get('object_type', ''),
                    related_id=highest_risk_item.get('object_id'),
                    risk_start=now_local,
                    risk_end=now_local + dt.timedelta(hours=48),
                    metadata={
                        'cpi': cpi,
                        'risk_item': highest_risk_item['label'],
                        'has_free_gap': True,
                    },
                )
                if rec:
                    created.append(rec)

    # --- EARLY_RENEGOTIATION_PROMPT ---
    # Commitment due within 24h AND breach_probability > 0.6
    urgent_commitments = _get_urgent_commitments(user, now_local, hours=24)
    breach_prob = pressure.breach_risk_score

    for commitment in urgent_commitments:
        if breach_prob > BREACH_PROB_THRESHOLD:
            rec = _create_recommendation(
                user=user,
                rec_type=ProtectiveRecommendation.TYPE_RENEGOTIATION,
                title=f"Deadline approaching: {_truncate(commitment['text'], 60)}",
                message=(
                    f"You have a commitment due soon and your schedule is tight. "
                    f"What would you like to do?"
                ),
                call_to_action={
                    'A': {'text': "I have a plan — I'm on it", 'action_key': 'confirm_plan'},
                    'B': {'text': 'Renegotiate the deadline', 'action_key': 'renegotiate'},
                    'C': {'text': 'Cancel this commitment', 'action_key': 'cancel'},
                },
                priority=80,
                related_type='Commitment',
                related_id=commitment['id'],
                risk_start=now_local,
                risk_end=commitment.get('time_boundary', now_local + dt.timedelta(hours=24)),
                metadata={
                    'cpi': cpi,
                    'breach_probability': breach_prob,
                    'commitment_id': commitment['id'],
                    'commitment_text': commitment['text'],
                },
            )
            if rec:
                created.append(rec)

    # --- CAPACITY_WARNING ---
    # Density > 0.85 in next 72h
    overloaded_days = _count_overloaded_days(user, now_local, days=3)
    if overloaded_days >= 1:
        if overloaded_days == 1:
            severity = 'gentle'
            title = "Heads up — tomorrow looks packed"
            message = "One of your upcoming days is very full. You might want to protect some breathing room."
            priority = 40
        elif overloaded_days == 2:
            severity = 'warning'
            title = "Your next few days are heavy"
            message = "Two of your upcoming days are very full. Consider moving what can wait."
            priority = 60
        else:
            severity = 'red_alert'
            title = "Your schedule needs attention"
            message = (
                "Three or more upcoming days are packed. "
                "This level of load is hard to sustain — something should give."
            )
            priority = 85

        rec = _create_recommendation(
            user=user,
            rec_type=ProtectiveRecommendation.TYPE_CAPACITY_WARNING,
            title=title,
            message=message,
            call_to_action={
                'A': {'text': 'Show me what I can move', 'action_key': 'show_flexible'},
                'B': {'text': "I know — I'll manage", 'action_key': 'dismiss'},
            },
            priority=priority,
            risk_start=now_local,
            risk_end=now_local + dt.timedelta(days=3),
            metadata={
                'cpi': cpi,
                'overloaded_days': overloaded_days,
                'severity': severity,
                'density_threshold': DENSITY_OVERLOADED,
            },
        )
        if rec:
            created.append(rec)

    # --- DEADLINE_FOCUS_PLAN ---
    # >3 hard deadlines/day OR two deadlines <2h apart
    collision_info = _check_deadline_collisions(user, now_local)
    if collision_info['has_collisions']:
        top_deadlines = collision_info['top_deadlines'][:3]
        deadline_list = ', '.join(d['label'] for d in top_deadlines)
        rec = _create_recommendation(
            user=user,
            rec_type=ProtectiveRecommendation.TYPE_FOCUS_PLAN,
            title="Multiple deadlines converging",
            message=(
                f"You have several deadlines close together. "
                f"Focus on these first: {deadline_list}."
            ),
            call_to_action={
                'A': {'text': 'Help me prioritize', 'action_key': 'prioritize'},
                'B': {'text': 'I have it sorted', 'action_key': 'dismiss'},
            },
            priority=75,
            risk_start=now_local,
            risk_end=now_local + dt.timedelta(days=2),
            metadata={
                'cpi': cpi,
                'collision_count': collision_info['collision_count'],
                'top_deadlines': [d['label'] for d in top_deadlines],
            },
        )
        if rec:
            created.append(rec)

    return created


# ---------------------------------------------------------------------------
# 2) Deadline Alerts
# ---------------------------------------------------------------------------

def schedule_deadline_alerts(user, now_local=None):
    """
    Schedule 24h/4h/1h pre-deadline alerts for pending commitments
    and goal milestones.

    Only schedules alerts for deadlines that are still pending/not completed.
    Respects existing alerts (no duplicates).

    Returns:
        list[ProtectiveAlert] — Newly created alerts.
    """
    if now_local is None:
        now_local = timezone.now()

    created = []

    # Pending commitments with time boundaries
    try:
        from apps.core.blueprint.models import Commitment
        pending = Commitment.pending_for_user(user)
        for commitment in pending:
            if not commitment.time_boundary:
                continue
            if commitment.time_boundary <= now_local:
                continue

            for alert_type, offset in ALERT_OFFSETS.items():
                alert_time = commitment.time_boundary - offset
                if alert_time <= now_local:
                    continue  # Already past this alert window

                # Check for existing pending alert of same type for same object
                existing = ProtectiveAlert.pending_for_object(
                    user, 'Commitment', commitment.id,
                ).filter(alert_type=alert_type).exists()
                if existing:
                    continue

                # Build message
                message, cta = _build_deadline_alert_message(
                    alert_type, commitment.normalized_text, commitment.time_boundary,
                )

                alert = ProtectiveAlert.objects.create(
                    user=user,
                    alert_type=alert_type,
                    message=message,
                    call_to_action=cta,
                    scheduled_for=alert_time,
                    related_object_type='Commitment',
                    related_object_id=commitment.id,
                    metadata={
                        'commitment_text': _truncate(commitment.normalized_text, 100),
                        'deadline': commitment.time_boundary.isoformat(),
                    },
                )
                created.append(alert)

                # Audit log
                ProtectiveActionLog.objects.create(
                    user=user,
                    event_type=ProtectiveActionLog.EVENT_AUTO_DECISION,
                    object_type='ProtectiveAlert',
                    object_id=alert.id,
                    rationale=f"Scheduled {alert_type} alert for commitment deadline",
                    metadata={'alert_type': alert_type, 'scheduled_for': alert_time.isoformat()},
                )

    except Exception as e:
        logger.debug("Phase 5: Deadline alert scheduling error: %s", e)

    return created


def cancel_alerts_for_object(user, object_type, object_id, reason='deadline_moved'):
    """
    Cancel all pending alerts for a specific object (e.g., when renegotiated).

    Returns:
        int — Number of alerts cancelled.
    """
    pending = ProtectiveAlert.pending_for_object(user, object_type, object_id)
    count = pending.count()

    for alert in pending:
        alert.delivery_status = ProtectiveAlert.DELIVERY_CANCELLED
        alert.save(update_fields=['delivery_status'])

        ProtectiveActionLog.objects.create(
            user=user,
            event_type=ProtectiveActionLog.EVENT_ALERT_CANCELLED,
            object_type='ProtectiveAlert',
            object_id=alert.id,
            rationale=f"Alert cancelled: {reason}",
            metadata={'reason': reason, 'original_scheduled_for': alert.scheduled_for.isoformat()},
        )

    return count


# ---------------------------------------------------------------------------
# 3) Overload Triggers → InterventionLog
# ---------------------------------------------------------------------------

def apply_overload_triggers(user, pressure_snapshot=None):
    """
    Create InterventionLog entries when CPI crosses overload thresholds.

    - CPI > 80: Level 2 (Ping) — "High load risk"
    - CPI > 90: Level 3 (Interrupt) — "Critical overload risk"

    IMPORTANT: Does NOT change EscalationState. Advisory only.

    Returns:
        InterventionLog or None
    """
    if pressure_snapshot is None:
        pressure_snapshot = _get_latest_pressure(user)

    if not pressure_snapshot:
        return None

    cpi = pressure_snapshot.pressure_index

    if cpi <= CPI_HIGH:
        return None

    try:
        from apps.core.blueprint.models import InterventionLog

        if cpi > CPI_CRITICAL:
            level = InterventionLog.LEVEL_INTERRUPT
            message = (
                "You're at maximum capacity right now. "
                "Something needs to come off your plate to protect "
                "what matters most."
            )
            trigger = 'critical_overload_risk'
        else:
            level = InterventionLog.LEVEL_PING
            message = (
                "Your load is getting heavy this week. "
                "Consider deferring non-essential items and "
                "protecting your recovery time."
            )
            trigger = 'high_load_risk'

        # Deduplication: don't create if same trigger exists in last 6 hours
        six_hours_ago = timezone.now() - dt.timedelta(hours=6)
        existing = InterventionLog.objects.filter(
            user=user,
            trigger_type=trigger,
            created_at__gte=six_hours_ago,
        ).exists()
        if existing:
            return None

        intervention = InterventionLog.objects.create(
            user=user,
            level=level,
            trigger_type=trigger,
            message=message,
            evidence={
                'pressure_index': cpi,
                'density_score': pressure_snapshot.density_score,
                'breach_risk_score': pressure_snapshot.breach_risk_score,
                'computed_at': pressure_snapshot.computed_at.isoformat(),
            },
            delivered_via='in_app',
        )

        # Audit log
        ProtectiveActionLog.objects.create(
            user=user,
            event_type=ProtectiveActionLog.EVENT_AUTO_DECISION,
            object_type='InterventionLog',
            object_id=intervention.id,
            rationale=f"Overload trigger: {trigger} (load index {cpi})",
            metadata={'cpi': cpi, 'level': level},
        )

        return intervention

    except Exception as e:
        logger.debug("Phase 5: Overload trigger error: %s", e)
        return None


# ---------------------------------------------------------------------------
# 4) Supersede / Expire
# ---------------------------------------------------------------------------

def expire_superseded_recommendations(user):
    """
    Expire old recommendations that have been superseded by newer ones.

    If a new recommendation of the same type for the same related object
    was created within 12 hours, mark the older one 'expired'.
    Never deletes — only status changes.

    Returns:
        int — Number of recommendations expired.
    """
    expired_count = 0
    active_recs = ProtectiveRecommendation.objects.filter(
        user=user,
        status=ProtectiveRecommendation.STATUS_ACTIVE,
    ).order_by('-created_at')

    seen = {}  # (type, related_type, related_id) -> newest rec

    for rec in active_recs:
        key = (rec.recommendation_type, rec.related_object_type, rec.related_object_id)

        if key in seen:
            newest = seen[key]
            time_diff = (newest.created_at - rec.created_at).total_seconds() / 3600
            if time_diff <= SUPERSEDE_WINDOW_HOURS:
                rec.status = ProtectiveRecommendation.STATUS_EXPIRED
                rec.save(update_fields=['status', 'updated_at'])
                expired_count += 1

                ProtectiveActionLog.objects.create(
                    user=user,
                    event_type=ProtectiveActionLog.EVENT_RECOMMENDATION_EXPIRED,
                    object_type='ProtectiveRecommendation',
                    object_id=rec.id,
                    rationale=(
                        f"Superseded by recommendation #{newest.id} "
                        f"(same type within {SUPERSEDE_WINDOW_HOURS}h)"
                    ),
                    metadata={
                        'superseded_by': newest.id,
                        'hours_apart': round(time_diff, 1),
                    },
                )
        else:
            seen[key] = rec

    return expired_count


# ---------------------------------------------------------------------------
# 5) Alert Delivery
# ---------------------------------------------------------------------------

def deliver_due_alerts(now=None):
    """
    Deliver all pending alerts that are due.

    Respects DNE throttle limits. Alerts that exceed the throttle are
    marked as suppressed_by_throttle with audit logs.

    Returns:
        dict — {delivered: int, suppressed: int, errors: int}
    """
    if now is None:
        now = timezone.now()

    due_alerts = ProtectiveAlert.pending_due(now).order_by('scheduled_for')

    delivered = 0
    suppressed = 0
    errors = 0

    # Track throttle per user
    user_counts = {}

    for alert in due_alerts:
        user_id = alert.user_id

        try:
            # Check throttle
            if user_id not in user_counts:
                user_counts[user_id] = _count_recent_deliveries(alert.user, now)

            hourly, daily = user_counts[user_id]

            if hourly >= DNE_MAX_ALERTS_PER_HOUR or daily >= DNE_MAX_ALERTS_PER_DAY:
                alert.delivery_status = ProtectiveAlert.DELIVERY_SUPPRESSED
                alert.save(update_fields=['delivery_status'])
                suppressed += 1

                # Calculate next eligible time
                next_eligible = now + dt.timedelta(hours=1)

                ProtectiveActionLog.objects.create(
                    user=alert.user,
                    event_type=ProtectiveActionLog.EVENT_ALERT_SUPPRESSED,
                    object_type='ProtectiveAlert',
                    object_id=alert.id,
                    rationale=(
                        f"Suppressed by throttle "
                        f"(hourly: {hourly}/{DNE_MAX_ALERTS_PER_HOUR}, "
                        f"daily: {daily}/{DNE_MAX_ALERTS_PER_DAY})"
                    ),
                    metadata={
                        'hourly_count': hourly,
                        'daily_count': daily,
                        'next_eligible': next_eligible.isoformat(),
                    },
                )
                continue

            # Deliver via DNE
            _deliver_alert_via_dne(alert)

            alert.delivery_status = ProtectiveAlert.DELIVERY_DELIVERED
            alert.delivered_at = now
            alert.save(update_fields=['delivery_status', 'delivered_at'])
            delivered += 1

            # Update throttle counts
            hourly += 1
            daily += 1
            user_counts[user_id] = (hourly, daily)

            ProtectiveActionLog.objects.create(
                user=alert.user,
                event_type=ProtectiveActionLog.EVENT_ALERT_DELIVERED,
                object_type='ProtectiveAlert',
                object_id=alert.id,
                rationale=f"Alert delivered: {alert.alert_type}",
                metadata={
                    'alert_type': alert.alert_type,
                    'delivered_at': now.isoformat(),
                },
            )

        except Exception as e:
            errors += 1
            logger.debug("Phase 5: Alert delivery error for alert %s: %s", alert.id, e)

    return {'delivered': delivered, 'suppressed': suppressed, 'errors': errors}


# ---------------------------------------------------------------------------
# 6) Sweep (ISE daily)
# ---------------------------------------------------------------------------

def run_protective_sweep():
    """
    Daily ISE job: recompute protective recommendations + schedule alerts
    for all active users with relevant data.

    Returns:
        dict — {users_processed: int, recommendations: int, alerts: int, errors: int}
    """
    from apps.users.models import User

    users = User.objects.filter(
        is_active=True,
        preferences__ai_enabled=True,
        preferences__personal_assistant_enabled=True,
    ).select_related('preferences')

    processed = 0
    total_recs = 0
    total_alerts = 0
    errors = 0

    for user in users:
        try:
            if not _has_active_data(user):
                continue

            now_local = timezone.now()

            # Expire superseded recommendations
            expire_superseded_recommendations(user)

            # Generate new recommendations
            recs = compute_protective_recommendations(user, now_local)
            total_recs += len(recs)

            # Schedule deadline alerts
            alerts = schedule_deadline_alerts(user, now_local)
            total_alerts += len(alerts)

            processed += 1

        except Exception as e:
            errors += 1
            logger.debug(
                "Phase 5: Protective sweep error for user %s: %s",
                user.pk, e,
            )

    return {
        'users_processed': processed,
        'recommendations': total_recs,
        'alerts': total_alerts,
        'errors': errors,
    }


# ---------------------------------------------------------------------------
# 7) User Actions (dismiss, accept)
# ---------------------------------------------------------------------------

def dismiss_recommendation(recommendation, reason='not_relevant'):
    """
    Dismiss a recommendation with a reason.

    Valid reasons: not_relevant, bad_timing, already_handled.
    """
    recommendation.status = ProtectiveRecommendation.STATUS_DISMISSED
    recommendation.dismissal_reason = reason
    recommendation.save(update_fields=['status', 'dismissal_reason', 'updated_at'])

    ProtectiveActionLog.objects.create(
        user=recommendation.user,
        event_type=ProtectiveActionLog.EVENT_DISMISSED,
        object_type='ProtectiveRecommendation',
        object_id=recommendation.id,
        rationale=f"User dismissed: {reason}",
        metadata={'reason': reason},
    )


def accept_recommendation(recommendation):
    """
    Accept a recommendation. Does NOT auto-schedule — records acceptance
    and generates a follow-up message.

    Returns:
        str — Follow-up message for the user.
    """
    recommendation.status = ProtectiveRecommendation.STATUS_ACCEPTED
    recommendation.save(update_fields=['status', 'updated_at'])

    ProtectiveActionLog.objects.create(
        user=recommendation.user,
        event_type=ProtectiveActionLog.EVENT_ACCEPTED,
        object_type='ProtectiveRecommendation',
        object_id=recommendation.id,
        rationale="User accepted recommendation",
    )

    if recommendation.recommendation_type == ProtectiveRecommendation.TYPE_TIME_BLOCK:
        return "Want me to propose 3 times that could work?"

    return "Got it — I've noted your choice."


# ---------------------------------------------------------------------------
# 8) CoS Context Helpers
# ---------------------------------------------------------------------------

def get_protective_briefing(user):
    """
    Build the protective briefing section for CoS context injection.

    Returns dict with:
        - load_status: Human label (Normal/Elevated/High/Critical)
        - recommendations: Top 1-3 active recommendations (human language)
        - upcoming_alerts: Alerts due in next 24h (brief)
    """
    briefing = {
        'load_status': 'Normal',
        'recommendations': [],
        'upcoming_alerts': [],
    }

    # Load status from latest pressure snapshot
    pressure = _get_latest_pressure(user)
    if pressure:
        briefing['load_status'] = get_load_status_label(pressure.pressure_index)

    # Top 3 active recommendations
    active_recs = ProtectiveRecommendation.active_for_user(user, limit=3)
    for rec in active_recs:
        briefing['recommendations'].append({
            'title': rec.title,
            'message': rec.message,
            'type': rec.recommendation_type,
            'priority': rec.priority,
        })

    # Alerts due in next 24h
    now = timezone.now()
    tomorrow = now + dt.timedelta(hours=24)
    upcoming = ProtectiveAlert.objects.filter(
        user=user,
        delivery_status=ProtectiveAlert.DELIVERY_PENDING,
        scheduled_for__lte=tomorrow,
        scheduled_for__gt=now,
    ).order_by('scheduled_for')[:5]

    for alert in upcoming:
        briefing['upcoming_alerts'].append({
            'message': alert.message,
            'type': alert.alert_type,
            'scheduled_for': alert.scheduled_for.isoformat(),
        })

    return briefing


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _get_latest_pressure(user):
    """Get the latest PressureSnapshot for a user."""
    try:
        from apps.core.blueprint.pressure_models import PressureSnapshot
        return PressureSnapshot.latest_for_user(user)
    except Exception:
        return None


def _find_highest_risk_item(user, now_local):
    """
    Find the highest-risk item for time block suggestion.

    Priority: commitment due soonest > goal eroding > protected habit at breach risk.
    """
    # Check commitments due soonest
    try:
        from apps.core.blueprint.models import Commitment
        pending = Commitment.pending_for_user(user).order_by('time_boundary')
        for c in pending:
            if c.time_boundary and c.time_boundary > now_local:
                return {
                    'label': _truncate(c.normalized_text, 80),
                    'object_type': 'Commitment',
                    'object_id': c.id,
                    'reason': 'soonest_deadline',
                }
    except Exception:
        pass

    # Check eroding goals
    try:
        from apps.purpose.models import LifeGoal
        goals = LifeGoal.objects.filter(
            user=user, status='active',
            target_date__isnull=False,
        ).order_by('target_date')
        for g in goals:
            if g.target_date and g.target_date > now_local.date():
                return {
                    'label': _truncate(g.title, 80),
                    'object_type': 'LifeGoal',
                    'object_id': g.id,
                    'reason': 'goal_eroding',
                }
    except Exception:
        pass

    # Check protected habits (Tier 1 non-negotiables)
    try:
        from apps.core.blueprint.models import NonNegotiable
        nns = NonNegotiable.objects.filter(user=user, is_active=True).first()
        if nns:
            return {
                'label': nns.display_name,
                'object_type': 'NonNegotiable',
                'object_id': nns.id,
                'reason': 'protected_habit',
            }
    except Exception:
        pass

    return None


def _has_free_gap(user, now_local, hours_ahead=48):
    """
    Check if there's a free gap >= 30 minutes in the next N hours.

    Uses ArchitecturePlan blocks to detect gaps in scheduled time.
    """
    try:
        from apps.core.blueprint.models import ArchitecturePlan

        for offset in range(min(hours_ahead // 24 + 1, 3)):  # Check up to 3 days
            target_date = (now_local + dt.timedelta(days=offset)).date()
            plan = ArchitecturePlan.get_active_for_date(user, target_date)

            if not plan:
                return True  # No plan = wide open day

            blocks = list(plan.blocks.all().order_by('start_time'))
            if not blocks:
                return True

            # Check gaps between blocks
            day_start = dt.time(DAY_START_HOUR, 0)
            day_end = dt.time(DAY_END_HOUR, 0)

            prev_end = day_start
            for block in blocks:
                if not block.start_time or not block.end_time:
                    continue
                if block.start_time > prev_end:
                    gap_start = dt.datetime.combine(target_date, prev_end)
                    gap_end = dt.datetime.combine(target_date, block.start_time)
                    gap_minutes = (gap_end - gap_start).total_seconds() / 60
                    if gap_minutes >= MIN_FREE_GAP_MINUTES:
                        return True
                if block.end_time > prev_end:
                    prev_end = block.end_time

            # Check gap after last block
            if prev_end < day_end:
                gap_start = dt.datetime.combine(target_date, prev_end)
                gap_end = dt.datetime.combine(target_date, day_end)
                gap_minutes = (gap_end - gap_start).total_seconds() / 60
                if gap_minutes >= MIN_FREE_GAP_MINUTES:
                    return True

    except Exception:
        pass

    return False


def _get_urgent_commitments(user, now_local, hours=24):
    """Get commitments due within N hours."""
    result = []
    try:
        from apps.core.blueprint.models import Commitment
        deadline = now_local + dt.timedelta(hours=hours)
        pending = Commitment.pending_for_user(user)
        for c in pending:
            if c.time_boundary and now_local < c.time_boundary <= deadline:
                result.append({
                    'id': c.id,
                    'text': c.normalized_text,
                    'time_boundary': c.time_boundary,
                })
    except Exception:
        pass
    return result


def _count_overloaded_days(user, now_local, days=3):
    """Count days with density > 0.85 in the next N days."""
    count = 0
    try:
        from apps.core.blueprint.models import ArchitecturePlan

        for offset in range(days):
            target_date = (now_local + dt.timedelta(days=offset)).date()
            plan = ArchitecturePlan.get_active_for_date(user, target_date)

            if not plan:
                continue

            day_minutes = 0
            for block in plan.blocks.all():
                if block.start_time and block.end_time:
                    start_dt = dt.datetime.combine(target_date, block.start_time)
                    end_dt = dt.datetime.combine(target_date, block.end_time)
                    delta = (end_dt - start_dt).total_seconds() / 60
                    if delta > 0:
                        day_minutes += delta

            density = day_minutes / AVAILABLE_MINUTES_PER_DAY
            if density > DENSITY_OVERLOADED:
                count += 1

    except Exception:
        pass

    return count


def _check_deadline_collisions(user, now_local):
    """
    Check for deadline collisions: >3 hard deadlines/day or <2h gap.

    Returns:
        dict with has_collisions, collision_count, top_deadlines
    """
    result = {'has_collisions': False, 'collision_count': 0, 'top_deadlines': []}

    try:
        from apps.core.blueprint.models import Commitment, DeadlineSnapshot

        # Use latest snapshot if fresh
        snapshot = DeadlineSnapshot.latest_for_user(user)
        if snapshot and not snapshot.is_stale():
            collision_flags = snapshot.collision_flags or []
            if collision_flags:
                result['has_collisions'] = True
                result['collision_count'] = len(collision_flags)

                # Get top deadlines from due_24h/due_72h
                all_deadlines = []
                for item in (snapshot.due_24h or []):
                    all_deadlines.append({
                        'label': _truncate(item.get('text', item.get('title', 'Deadline')), 60),
                        'due': item.get('time_boundary', item.get('due', '')),
                    })
                for item in (snapshot.due_72h or []):
                    all_deadlines.append({
                        'label': _truncate(item.get('text', item.get('title', 'Deadline')), 60),
                        'due': item.get('time_boundary', item.get('due', '')),
                    })
                result['top_deadlines'] = all_deadlines[:3]
            return result

        # Fallback: compute directly
        horizon_end = now_local + dt.timedelta(days=2)
        deadlines = []
        pending = Commitment.pending_for_user(user)
        for c in pending:
            if c.time_boundary and now_local < c.time_boundary <= horizon_end:
                deadlines.append({
                    'label': _truncate(c.normalized_text, 60),
                    'due': c.time_boundary,
                    'id': c.id,
                })

        if len(deadlines) < 2:
            return result

        # Sort by due time
        deadlines.sort(key=lambda d: d['due'])

        # Check for pair collisions (<2h gap)
        collision_count = 0
        for i in range(len(deadlines) - 1):
            gap = (deadlines[i + 1]['due'] - deadlines[i]['due']).total_seconds() / 3600
            if gap < COLLISION_GAP_HOURS:
                collision_count += 1

        # Check for daily overloads (>3 per day)
        from collections import Counter
        day_counts = Counter()
        for d in deadlines:
            day_counts[d['due'].date()] += 1
        for count in day_counts.values():
            if count > COLLISION_HARD_DEADLINE_DAY_MAX:
                collision_count += 1

        if collision_count > 0:
            result['has_collisions'] = True
            result['collision_count'] = collision_count
            result['top_deadlines'] = deadlines[:3]

    except Exception:
        pass

    return result


def _create_recommendation(user, rec_type, title, message, call_to_action,
                           priority, related_type='', related_id=None,
                           risk_start=None, risk_end=None, metadata=None):
    """
    Create a recommendation with supersede checking.

    Returns ProtectiveRecommendation or None if recently superseded.
    """
    # Check if a recent active rec of same type for same object exists
    cutoff = timezone.now() - dt.timedelta(hours=SUPERSEDE_WINDOW_HOURS)
    existing = ProtectiveRecommendation.objects.filter(
        user=user,
        recommendation_type=rec_type,
        related_object_type=related_type,
        related_object_id=related_id,
        status=ProtectiveRecommendation.STATUS_ACTIVE,
        created_at__gte=cutoff,
    ).first()

    if existing:
        return None  # Already have a recent active recommendation

    rec = ProtectiveRecommendation.objects.create(
        user=user,
        recommendation_type=rec_type,
        title=title,
        message=message,
        call_to_action=call_to_action,
        status=ProtectiveRecommendation.STATUS_ACTIVE,
        priority=priority,
        related_object_type=related_type,
        related_object_id=related_id,
        risk_window_start=risk_start,
        risk_window_end=risk_end,
        metadata=metadata or {},
    )

    ProtectiveActionLog.objects.create(
        user=user,
        event_type=ProtectiveActionLog.EVENT_CREATED_RECOMMENDATION,
        object_type='ProtectiveRecommendation',
        object_id=rec.id,
        rationale=f"Created {rec_type}: {title}",
        metadata=metadata or {},
    )

    return rec


def _build_deadline_alert_message(alert_type, commitment_text, deadline):
    """Build human-language alert message and CTA for deadline alerts."""
    short_text = _truncate(commitment_text, 80)

    if alert_type == ProtectiveAlert.TYPE_DEADLINE_24H:
        message = (
            f"Reminder: \"{short_text}\" is due tomorrow. "
            f"Do you have a plan, or do you need to adjust?"
        )
        cta = {
            'A': {'text': "I'm on it", 'action_key': 'confirm'},
            'B': {'text': 'I need to adjust the deadline', 'action_key': 'renegotiate'},
            'C': {'text': "It's done — close it", 'action_key': 'close'},
        }
    elif alert_type == ProtectiveAlert.TYPE_DEADLINE_4H:
        message = (
            f"\"{short_text}\" is due in about 4 hours. What's your status?"
        )
        cta = {
            'A': {'text': "Working on it now", 'action_key': 'confirm'},
            'B': {'text': 'I need more time', 'action_key': 'renegotiate'},
            'C': {'text': "Done — close it", 'action_key': 'close'},
        }
    else:  # 1H
        message = (
            f"Last call: \"{short_text}\" is due in about an hour."
        )
        cta = {
            'A': {'text': "On it", 'action_key': 'confirm'},
            'B': {'text': 'Need more time', 'action_key': 'renegotiate'},
            'C': {'text': "Done", 'action_key': 'close'},
        }

    return message, cta


def _count_recent_deliveries(user, now):
    """Count recent alert deliveries for throttle checking."""
    one_hour_ago = now - dt.timedelta(hours=1)
    day_start = now.replace(hour=0, minute=0, second=0, microsecond=0)

    hourly = ProtectiveAlert.objects.filter(
        user=user,
        delivery_status=ProtectiveAlert.DELIVERY_DELIVERED,
        delivered_at__gte=one_hour_ago,
    ).count()

    daily = ProtectiveAlert.objects.filter(
        user=user,
        delivery_status=ProtectiveAlert.DELIVERY_DELIVERED,
        delivered_at__gte=day_start,
    ).count()

    return (hourly, daily)


def _deliver_alert_via_dne(alert):
    """
    Deliver an alert through the DNE (Delivery Notification Engine).

    Wraps the alert in a DNE-compatible envelope and delivers.
    Falls back to in-app delivery if DNE is unavailable.
    """
    try:
        from apps.core.ai_delivery.delivery_engine import deliver_notification
        deliver_notification(
            user=alert.user,
            notification_type='protective_alert',
            title=f"Alert: {alert.get_alert_type_display()}",
            message=alert.message,
            metadata={
                'alert_id': alert.id,
                'alert_type': alert.alert_type,
                'call_to_action': alert.call_to_action,
            },
        )
    except Exception as e:
        logger.debug("Phase 5: DNE delivery fallback for alert %s: %s", alert.id, e)
        # In-app delivery is the default — the alert record itself
        # serves as the in-app notification when read by CoS context.


def _has_active_data(user):
    """Check if user has active data worth processing."""
    try:
        from apps.core.blueprint.models import Commitment
        if Commitment.pending_for_user(user).exists():
            return True
    except Exception:
        pass

    try:
        from apps.purpose.models import LifeGoal
        if LifeGoal.objects.filter(user=user, status='active').exists():
            return True
    except Exception:
        pass

    try:
        from apps.core.blueprint.models import ArchitecturePlan
        today = timezone.localdate()
        if ArchitecturePlan.get_active_for_date(user, today):
            return True
    except Exception:
        pass

    return False


def _truncate(text, max_len=80):
    """Truncate text to max_len with ellipsis."""
    if not text:
        return ''
    if len(text) <= max_len:
        return text
    return text[:max_len - 3] + '...'
