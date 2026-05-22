"""
CoS Situation Computer — Pure-logic task that computes CoSSituationState.

Runs every 15 minutes via ISE scheduler. No LLM calls.
Reads engine outputs (insights, predictions, guidance, health signals,
tasks, schedule) and distills them into a pre-interpreted awareness state
that CoS can inject directly into prompts.

This eliminates per-request context rebuilding and provides:
- Delta tracking (what changed since last interaction)
- Situation-appropriate mode (morning vs evening vs urgent)
- Pre-computed narrative framing (opening sentence)
- Signal transparency (what was suppressed by EAE)
"""

import logging
from datetime import timedelta
from django.utils import timezone

logger = logging.getLogger(__name__)


def compute_situation_for_user(user):
    """
    Compute and persist the CoSSituationState for a single user.

    Pure logic — no LLM calls. Reads from existing engine outputs
    and database records.

    Returns:
        CoSSituationState instance or None on failure.
    """
    try:
        from apps.core.ai_state.models import CoSSituationState

        now = timezone.now()

        # Get or create the situation state
        situation, _created = CoSSituationState.objects.get_or_create(
            user=user,
            defaults={'situation_mode': CoSSituationState.MODE_MORNING_ORIENTATION},
        )

        # Save previous state for delta computation
        previous_concern = situation.dominant_concern
        previous_escalations = list(situation.escalations or [])
        previous_last_interaction = situation.last_user_interaction

        # Intra-day rhythm refresh — narrow trigger, returning-only.
        # See _maybe_refresh_rhythm_for_returning for the architectural rule.
        _maybe_refresh_rhythm_for_returning(user)

        # ── Gather signals ──
        rhythm = _read_rhythm_state(user)
        is_first_interaction_today = _is_first_interaction_today(user, previous_last_interaction)
        mode = _compute_situation_mode(
            user, now, rhythm=rhythm,
            is_first_interaction_today=is_first_interaction_today,
        )
        concern, priority = _compute_dominant_concern_and_priority(user, now)
        changes = _compute_changes_since_last_interaction(user, situation)
        escalations = _compute_escalations(user, previous_escalations)
        resolutions = _compute_resolutions(user, previous_escalations)
        opening = _build_opening_sentence(
            user, mode, concern, priority, changes, now, rhythm=rhythm,
        )
        suppressed = _get_suppressed_signals(user)
        last_interaction = _get_last_user_interaction(user)
        msgs_since_briefing = _count_messages_since_briefing(user)

        # ── Persist ──
        situation.situation_mode = mode
        situation.dominant_concern = concern
        situation.top_priority = priority
        situation.changes_since_last_interaction = changes
        situation.escalations = escalations
        situation.resolutions = resolutions
        situation.opening_sentence = opening
        situation.suppressed_signals = suppressed
        situation.last_user_interaction = last_interaction
        situation.messages_since_briefing = msgs_since_briefing
        situation.previous_dominant_concern = previous_concern
        situation.save()

        logger.info(
            "COS_SITUATION_COMPUTED user=%s mode=%s concern=%s",
            user.id, mode, concern[:60] if concern else '(none)',
        )
        return situation

    except Exception as e:
        logger.error(
            "COS_SITUATION_COMPUTE_ERROR user=%s error=%s",
            user.id, e, exc_info=True,
        )
        return None


# ─────────────────────────────────────────────────────────────────────
# Rhythm-state helpers (Phase 1 — behavior.rhythm_state consumer)
# ─────────────────────────────────────────────────────────────────────


def _read_rhythm_state(user):
    """Read behavior.rhythm_state from SAE. Returns dict or empty dict.

    Staleness gate: if computed_at is missing or older than
    RHYTHM_STALENESS_HOURS, returns an empty dict so consumers fall through
    to time-based modes (fail closed toward silence). Protects against
    rhythm narrative persisting on stale numbers when the nightly compute
    has failed.
    """
    try:
        from apps.core.ai_state.models import UserState
        from apps.core.ai_state.state_builder import RHYTHM_STALENESS_HOURS
        state = UserState.objects.filter(user=user).first()
        if not state:
            return {}
        behavior = state.get_module('behavior') or {}
        rhythm = behavior.get('rhythm_state') or {}
        if not rhythm:
            return {}
        computed_at_raw = rhythm.get('computed_at')
        if not computed_at_raw:
            return {}
        try:
            from datetime import datetime
            computed_at = datetime.fromisoformat(computed_at_raw)
            # If timezone-naive (shouldn't happen in normal nightly path),
            # treat as UTC to avoid a tz-mixed comparison.
            if computed_at.tzinfo is None:
                from datetime import timezone as _tz
                computed_at = computed_at.replace(tzinfo=_tz.utc)
            age_hours = (timezone.now() - computed_at).total_seconds() / 3600.0
            if age_hours > RHYTHM_STALENESS_HOURS:
                return {}
        except (ValueError, TypeError):
            # Unparseable computed_at — fail closed toward silence.
            return {}
        return rhythm
    except Exception:
        logger.warning("rhythm read failed for user=%s", getattr(user, 'id', '?'), exc_info=True)
        return {}


def _is_first_interaction_today(user, previous_last_interaction):
    """Detect whether the current compute represents the user's first
    interaction context of the local day.

    Uses the previous-cycle's last_user_interaction (captured before the
    current recompute). True when there is no prior interaction or the
    prior interaction was on a different calendar day in user TZ.
    """
    try:
        from apps.core.utils import get_user_today
        user_today = get_user_today(user)
    except Exception:
        return False

    if previous_last_interaction is None:
        return True
    try:
        # Convert to user's local date for comparison.
        from apps.core.utils import get_user_now
        user_now = get_user_now(user)
        # previous_last_interaction is timezone-aware UTC; convert to user TZ date.
        local_prev = previous_last_interaction.astimezone(user_now.tzinfo).date()
        return local_prev < user_today
    except Exception:
        return False


def _maybe_refresh_rhythm_for_returning(user):
    """Narrow intra-day rhythm refresh — returning detection only.

    Architectural rule: rhythm_state is computed fully at the nightly
    Operating Profile job. The only intra-day transition permitted is
    `* -> returning`. We rebuild behavior.rhythm_state here only when
    the existing state suggests the user was absent >=2 days and the
    user has now interacted today (UserDailyActivity row exists today).

    All other state changes wait for the nightly recompute.
    """
    try:
        from apps.core.utils import get_user_today
        from apps.core.ai_state.models import UserState
        from apps.core.models import UserDailyActivity

        rhythm = _read_rhythm_state(user)
        if not rhythm:
            return
        days_since = rhythm.get('days_since_last_interaction')
        if days_since is None or days_since < 2:
            return
        # If already in returning, leave alone — nightly recompute will clear.
        if rhythm.get('status') == 'returning':
            return

        user_today = get_user_today(user)
        had_today = UserDailyActivity.objects.filter(
            user=user, date=user_today,
        ).exists()
        if not had_today:
            return

        # Conditions met: recompute behavior state so rhythm_state flips to returning.
        from apps.core.ai_state.state_builder import build_behavior_state
        new_behavior = build_behavior_state(user)
        state_row = UserState.objects.filter(user=user).first()
        if state_row is None:
            return
        state_row.set_module('behavior', new_behavior)
        state_row.save(update_fields=['state_data', 'last_updated'])
    except Exception:
        logger.warning("intra-day rhythm refresh failed", exc_info=True)


# ─────────────────────────────────────────────────────────────────────
# Signal gathering functions (all pure logic, no LLM calls)
# ─────────────────────────────────────────────────────────────────────


def _compute_situation_mode(user, now, rhythm=None, is_first_interaction_today=False):
    """
    Determine the appropriate interaction mode based on time, state, and signals.

    Rhythm-aware modes (off_rhythm, returning) only surface on the first
    interaction of the user's local day. Subsequent same-day interactions
    fall through to the standard time-based modes.
    """
    from apps.core.ai_state.models import CoSSituationState

    # Get user's local time
    try:
        from apps.core.utils import get_user_now
        user_now = get_user_now(user)
    except Exception:
        user_now = now

    hour = user_now.hour
    weekday = user_now.weekday()  # 0=Monday, 6=Sunday
    is_weekend = weekday >= 5

    # Check for urgent intervention first (highest priority)
    if _has_urgent_signals(user, now):
        return CoSSituationState.MODE_URGENT_INTERVENTION

    # Check for recovery mode
    if _is_in_recovery(user):
        return CoSSituationState.MODE_RECOVERY

    # Rhythm-aware modes — first-message-of-day surfacing only.
    if is_first_interaction_today and rhythm:
        rhythm_status = rhythm.get('status')
        if rhythm_status == 'returning':
            return CoSSituationState.MODE_RETURNING
        if rhythm_status == 'off_rhythm':
            return CoSSituationState.MODE_OFF_RHYTHM

    # Check for celebration mode
    if _has_celebration_signals(user, now):
        return CoSSituationState.MODE_CELEBRATION

    # Time-based modes
    if is_weekend and hour < 12:
        return CoSSituationState.MODE_WEEKEND_REFLECTION

    if hour < 10:
        return CoSSituationState.MODE_MORNING_ORIENTATION
    elif hour < 13:
        return CoSSituationState.MODE_MIDDAY_CHECKPOINT
    elif hour < 17:
        return CoSSituationState.MODE_AFTERNOON_FOCUS
    else:
        return CoSSituationState.MODE_EVENING_REVIEW


def _has_urgent_signals(user, now):
    """Check for signals that warrant urgent intervention mode."""
    try:
        # Missed medication (2+ hours overdue)
        from apps.health.models import MedicationLog, MedicationSchedule
        today = now.date()
        schedules = MedicationSchedule.objects.filter(
            user=user, is_active=True,
        ).select_related('medication')

        for sched in schedules:
            dose_logged = MedicationLog.objects.filter(
                user=user,
                medication=sched.medication,
                taken_at__date=today,
                status='taken',
            ).exists()
            if not dose_logged and sched.time_of_day:
                # Check if dose is 2+ hours overdue
                try:
                    from apps.core.utils import get_user_now
                    user_now = get_user_now(user)
                    from datetime import datetime, time as dt_time
                    dose_hour = int(sched.time_of_day.split(':')[0]) if ':' in str(sched.time_of_day) else 8
                    if user_now.hour >= dose_hour + 2:
                        return True
                except Exception:
                    pass
    except (ImportError, Exception):
        pass

    try:
        # Critical health insight in last 24h
        from apps.core.ai_insights.models import Insight
        critical_count = Insight.objects.filter(
            user=user,
            severity='critical',
            status='new',
            created_at__gte=now - timedelta(hours=24),
        ).count()
        if critical_count > 0:
            return True
    except (ImportError, Exception):
        pass

    try:
        # High drift probability
        from apps.core.blueprint.models import DriftScore
        latest_drift = DriftScore.objects.filter(
            user=user,
        ).order_by('-created_at').first()
        if latest_drift and hasattr(latest_drift, 'probability_24h'):
            if latest_drift.probability_24h and latest_drift.probability_24h > 0.75:
                return True
    except (ImportError, Exception):
        pass

    return False


def _is_in_recovery(user):
    """Check if user is in recovery mode (from blueprint)."""
    try:
        from apps.core.blueprint.models import Blueprint
        bp = Blueprint.objects.filter(user=user).first()
        if bp and hasattr(bp, 'in_recovery') and bp.in_recovery:
            return True
    except (ImportError, Exception):
        pass
    return False


def _has_celebration_signals(user, now):
    """Check for celebration-worthy events (streaks, completions)."""
    try:
        from apps.core.ai_insights.models import Insight
        celebrations = Insight.objects.filter(
            user=user,
            severity='positive',
            status='new',
            created_at__gte=now - timedelta(hours=6),
        ).count()
        return celebrations >= 2
    except (ImportError, Exception):
        return False


def _compute_dominant_concern_and_priority(user, now):
    """
    Identify the single most important concern and recommended action.

    Priority hierarchy:
    1. Medication not taken (scheduled dose overdue)
    2. Deadline within 48 hours
    3. Critical health signal
    4. High drift probability
    5. Overdue tasks
    6. General guidance
    """
    concern = ''
    priority = ''

    # 1. Medication gap
    try:
        from apps.health.models import MedicationLog, MedicationSchedule
        today = now.date()
        schedules = MedicationSchedule.objects.filter(
            user=user, is_active=True,
        ).select_related('medication')

        overdue_meds = []
        for sched in schedules:
            dose_logged = MedicationLog.objects.filter(
                user=user,
                medication=sched.medication,
                taken_at__date=today,
                status='taken',
            ).exists()
            if not dose_logged:
                overdue_meds.append(sched.medication.name)

        if overdue_meds:
            med_names = ', '.join(overdue_meds[:3])
            concern = f"Medication gap: {med_names} not logged today"
            priority = f"Log {overdue_meds[0]} medication"
            return concern, priority
    except (ImportError, Exception):
        pass

    # 2. Deadline within 48 hours
    try:
        from apps.life.services.task_queries import TaskQueries
        deadline_cutoff = now + timedelta(hours=48)
        urgent_tasks = TaskQueries.due_within(
            user, deadline_cutoff
        ).order_by('due_date')[:3]

        if urgent_tasks.exists():
            task = urgent_tasks.first()
            count = urgent_tasks.count()
            concern = f"Deadline approaching: '{task.title}' due {task.due_date.strftime('%b %d')}"
            if count > 1:
                concern += f" (+{count - 1} more within 48h)"
            priority = f"Focus on '{task.title}'"
            return concern, priority
    except (ImportError, Exception):
        pass

    # 3. Critical health signal
    try:
        from apps.core.ai_insights.models import Insight
        critical = Insight.objects.filter(
            user=user,
            severity__in=['critical', 'warning'],
            status='new',
        ).order_by(
            models.Case(
                models.When(severity='critical', then=0),
                models.When(severity='warning', then=1),
                default=2,
                output_field=models.IntegerField(),
            )
        ).first()

        if critical:
            concern = f"Health signal: {critical.title}"
            priority = critical.message[:100] if critical.message else "Review health data"
            return concern, priority
    except (ImportError, Exception):
        pass

    # 4. Overdue tasks
    try:
        from apps.life.services.task_queries import TaskQueries
        overdue = TaskQueries.overdue(user).count()

        if overdue > 0:
            concern = f"{overdue} overdue task{'s' if overdue > 1 else ''}"
            priority = "Review and reschedule overdue tasks"
            return concern, priority
    except (ImportError, Exception):
        pass

    # 5. Active guidance
    try:
        from apps.core.ai_guidance.models import GuidanceItem
        top_guidance = GuidanceItem.objects.filter(
            user=user,
            is_active=True,
        ).order_by('priority').first()

        if top_guidance:
            concern = top_guidance.title
            priority = top_guidance.message[:100] if top_guidance.message else ''
            return concern, priority
    except (ImportError, Exception):
        pass

    return concern, priority


def _compute_changes_since_last_interaction(user, situation):
    """Compute what has changed since the user last interacted."""
    changes = []
    last = situation.last_user_interaction
    if not last:
        return changes

    try:
        now = timezone.now()

        # New insights since last interaction
        from apps.core.ai_insights.models import Insight
        new_insights = Insight.objects.filter(
            user=user,
            created_at__gt=last,
        ).count()
        if new_insights:
            changes.append({
                'what': f"{new_insights} new insight{'s' if new_insights > 1 else ''}",
                'when': 'since last interaction',
                'significance': 'info',
            })

        # New guidance since last interaction
        from apps.core.ai_guidance.models import GuidanceItem
        new_guidance = GuidanceItem.objects.filter(
            user=user,
            is_active=True,
            created_at__gt=last,
        ).count()
        if new_guidance:
            changes.append({
                'what': f"{new_guidance} new guidance item{'s' if new_guidance > 1 else ''}",
                'when': 'since last interaction',
                'significance': 'info',
            })

        # Tasks completed since last interaction
        from apps.life.services.task_queries import TaskQueries
        completed_tasks = TaskQueries.completed_since(user, last).count()
        if completed_tasks:
            changes.append({
                'what': f"{completed_tasks} task{'s' if completed_tasks > 1 else ''} completed",
                'when': 'since last interaction',
                'significance': 'positive',
            })

    except (ImportError, Exception) as e:
        logger.debug("Delta computation error: %s", e)

    return changes[:10]  # Cap at 10 changes


def _compute_escalations(user, previous_escalations):
    """Identify things getting worse."""
    escalations = []

    try:
        # Drift probability increasing
        from apps.core.blueprint.models import DriftScore
        scores = list(
            DriftScore.objects.filter(user=user)
            .order_by('-created_at')
            .values_list('daily_score', flat=True)[:3]
        )
        if len(scores) >= 2 and scores[0] and scores[1]:
            if scores[0] > scores[1]:
                escalations.append({
                    'signal': 'drift_increasing',
                    'description': f"Drift score increasing: {scores[1]} → {scores[0]}",
                })
    except (ImportError, Exception):
        pass

    try:
        # Growing overdue task count
        from apps.life.services.task_queries import TaskQueries
        overdue = TaskQueries.overdue(user).count()
        if overdue >= 3:
            escalations.append({
                'signal': 'task_overdue_growing',
                'description': f"{overdue} tasks overdue",
            })
    except (ImportError, Exception):
        pass

    return escalations[:5]


def _compute_resolutions(user, previous_escalations):
    """Identify things that have resolved since last check."""
    resolutions = []

    prev_signals = {e.get('signal') for e in previous_escalations if isinstance(e, dict)}

    # Check if previous escalations are now resolved
    if 'drift_increasing' in prev_signals:
        try:
            from apps.core.blueprint.models import DriftScore
            scores = list(
                DriftScore.objects.filter(user=user)
                .order_by('-created_at')
                .values_list('daily_score', flat=True)[:2]
            )
            if len(scores) >= 2 and scores[0] and scores[1] and scores[0] <= scores[1]:
                resolutions.append({
                    'signal': 'drift_stabilized',
                    'description': "Drift score has stabilized or improved",
                })
        except (ImportError, Exception):
            pass

    return resolutions[:5]


def _build_opening_sentence(user, mode, concern, priority, changes, now, rhythm=None):
    """
    Build a pre-computed opening sentence for CoS.

    This is the hardest part of the CoS problem — turning signals into
    a natural-language opening. Done here in the scheduled task so the
    LLM doesn't have to do it ad-hoc.
    """
    from apps.core.ai_state.models import CoSSituationState

    try:
        from apps.core.utils import get_user_now
        user_now = get_user_now(user)
    except Exception:
        user_now = now

    hour = user_now.hour

    # Time-appropriate greeting
    if hour < 12:
        greeting = "Good morning"
    elif hour < 17:
        greeting = "Good afternoon"
    else:
        greeting = "Good evening"

    # Get user's first name
    first_name = getattr(user, 'first_name', '') or ''
    if first_name:
        greeting = f"{greeting}, {first_name}"

    # Build based on mode
    if mode == CoSSituationState.MODE_URGENT_INTERVENTION:
        if concern:
            return f"{greeting}. Priority alert: {concern}."
        return f"{greeting}. I have something important to flag."

    if mode == CoSSituationState.MODE_RETURNING:
        return _build_returning_sentence(rhythm)

    if mode == CoSSituationState.MODE_OFF_RHYTHM:
        return _build_off_rhythm_sentence(rhythm)

    if mode == CoSSituationState.MODE_CELEBRATION:
        return f"{greeting}. Great progress today — let me highlight what's going well."

    if mode == CoSSituationState.MODE_RECOVERY:
        return f"{greeting}. Recovery mode is active — let's keep things manageable today."

    # Standard modes — weave in concern if present
    parts = [greeting + "."]

    if changes:
        change_count = len(changes)
        parts.append(f"{'A few things have' if change_count > 1 else 'One thing has'} changed since we last spoke.")

    if concern:
        parts.append(f"Top of mind: {concern}.")

    if priority and not concern:
        parts.append(f"Suggested focus: {priority}.")

    return ' '.join(parts)


# ─────────────────────────────────────────────────────────────────────
# Rhythm phrasing templates — deterministic, locked.
#
# Templates are static strings with formatted values from contributors.
# Do NOT make these LLM-generated. Do NOT add emotional inference.
# Do NOT add causal claims. Beth observes; she does not feel.
# ─────────────────────────────────────────────────────────────────────


_OFF_RHYTHM_TEMPLATES = {
    'foundational_adherence_delta': (
        "Your foundationals are at {recent}% this week — your usual is closer to {baseline}%."
    ),
    'engagement_delta': (
        "Last week's been quieter than usual — {recent} active days versus your typical {baseline}."
    ),
    'workout_consistency_delta': (
        "You've logged {recent} workouts this week — your usual pace is closer to {baseline}."
    ),
}


def _render_contributor_line(contributor):
    """Render one off_rhythm contributor into a sentence fragment.

    Returns None if the contributor signal is unknown — fails closed
    rather than inventing language.
    """
    template = _OFF_RHYTHM_TEMPLATES.get(contributor.get('signal_name'))
    if not template:
        return None
    recent = contributor.get('recent_value')
    baseline = contributor.get('baseline_value')
    if recent is None or baseline is None:
        return None
    try:
        return template.format(recent=recent, baseline=baseline)
    except (KeyError, ValueError):
        return None


def _build_off_rhythm_sentence(rhythm):
    """Compose the off_rhythm opening from rhythm_state.contributors.

    Uses up to two contributors (top by severity), joining with ' Also,'.
    Falls back to a safe generic sentence only if no contributor can
    be rendered — never invents data.
    """
    contributors = (rhythm or {}).get('contributors') or []
    rendered = []
    for c in contributors[:2]:
        line = _render_contributor_line(c)
        if line:
            rendered.append(line)
    if not rendered:
        return "Last week's looked different from your usual rhythm."
    if len(rendered) == 1:
        return rendered[0]
    # Combine top + secondary. Lowercase the leading word of the secondary
    # clause so it reads naturally after " Also,".
    secondary = rendered[1]
    if secondary and secondary[0].isupper():
        secondary = secondary[0].lower() + secondary[1:]
    return f"{rendered[0]} Also, {secondary}"


def _build_returning_sentence(rhythm):
    """Compose the returning opening from rhythm_state.

    Uses days_since_last_interaction. Pluralizes 'day'/'days'.
    """
    days = (rhythm or {}).get('days_since_last_interaction')
    if not isinstance(days, int) or days < 2:
        # Defensive fallback — should not happen because the mode is
        # only set when days >= 2, but never invent a specific count.
        return "Welcome back — what do you want to focus on first?"
    unit = "day" if days == 1 else "days"
    return f"It's been {days} {unit}. Welcome back — what do you want to focus on first?"


def _get_suppressed_signals(user):
    """Get signals that were suppressed by EAE noise budget."""
    try:
        from apps.core.ai_eae.eae_engine import get_last_arbitration_result
        result = get_last_arbitration_result(user)
        if result and hasattr(result, 'suppressed_items'):
            return [
                {'signal': s.get('type', 'unknown'), 'reason': 'noise_budget'}
                for s in (result.suppressed_items or [])[:5]
            ]
    except (ImportError, Exception):
        pass
    return []


def _get_last_user_interaction(user):
    """Get timestamp of user's last message."""
    try:
        from apps.ai.models import AssistantMessage
        last = (
            AssistantMessage.objects
            .filter(conversation__user=user, role='user')
            .order_by('-created_at')
            .values_list('created_at', flat=True)
            .first()
        )
        return last
    except (ImportError, Exception):
        return None


def _count_messages_since_briefing(user):
    """Count messages exchanged since last daily briefing."""
    try:
        from apps.ai.models import AssistantConversation
        conv = AssistantConversation.objects.filter(user=user).first()
        if not conv:
            return 0

        metadata = conv.metadata or {}
        last_briefing = metadata.get('last_briefing_date')
        if not last_briefing:
            return 0

        from apps.ai.models import AssistantMessage
        from datetime import date
        briefing_date = date.fromisoformat(last_briefing)
        from django.utils import timezone as dj_tz
        briefing_start = dj_tz.make_aware(
            dj_tz.datetime(briefing_date.year, briefing_date.month, briefing_date.day)
        )
        return AssistantMessage.objects.filter(
            conversation=conv,
            created_at__gte=briefing_start,
        ).count()
    except (ImportError, Exception):
        return 0


# ─────────────────────────────────────────────────────────────────────
# Batch runner (called by ISE scheduler)
# ─────────────────────────────────────────────────────────────────────


def run_situation_compute():
    """
    Compute CoSSituationState for all active AI users.

    Called by ISE scheduler every 15 minutes. Pure logic — no LLM calls.

    Returns:
        dict — {computed: int, errors: int}
    """
    try:
        from apps.core.ai_scheduler.scheduler_runner import _get_active_ai_users
    except ImportError:
        logger.error("ISE: Cannot import _get_active_ai_users for situation compute")
        return {"computed": 0, "errors": 0}

    users = _get_active_ai_users()
    computed = 0
    errors = 0

    for user in users:
        try:
            result = compute_situation_for_user(user)
            if result:
                computed += 1
        except Exception as e:
            logger.warning(
                "COS_SITUATION_COMPUTE_FAIL user=%s error=%s",
                user.id, e,
            )
            errors += 1

    logger.info(
        "COS_SITUATION_BATCH_COMPLETE computed=%d errors=%d total=%d",
        computed, errors, len(users),
    )
    return {"computed": computed, "errors": errors}
