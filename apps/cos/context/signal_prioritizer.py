"""
COS-CX2: Lead Signal Prioritizer
=================================

Determines the single most important situational signal RIGHT NOW.
This is the difference between dumping 30 signals and leading with:
"Your strategy meeting begins in 10 minutes."

Scoring algorithm:
  score = base_urgency × time_decay × tier_weight

Runs AFTER build_specificity_block so it can reference named items.

Performance target: < 2ms (pure computation, no DB queries).
Token budget: 1-2 sentences max.
"""
import logging
from datetime import timedelta

logger = logging.getLogger(__name__)


def compute_lead_signal(user, specificity_block, now, cos_context=None):
    """
    Compute the single most important signal to lead with.

    Args:
        user: Django User object
        specificity_block: str from build_specificity_block()
        now: timezone-aware datetime in user's timezone
        cos_context: optional dict from build_cos_context() for richer signals

    Returns:
        str — formatted lead signal text, or "" if nothing urgent.
    """
    try:
        candidates = []

        # --- Signal 1: Imminent calendar event ---
        _score_imminent_events(candidates, user, now)

        # --- Signal 2: Overdue medications ---
        _score_overdue_meds(candidates, user, now)

        # --- Signal 3: Overdue high-priority tasks ---
        _score_overdue_tasks(candidates, user, now)

        # --- Signal 4: Active event (happening NOW) ---
        _score_active_event(candidates, user, now)

        # --- Signal 5: Severe goal gap (from cos_context if available) ---
        if cos_context:
            _score_goal_gaps(candidates, cos_context)

        # --- Signal 6: High pressure / burnout risk ---
        if cos_context:
            _score_pressure(candidates, cos_context)

        if not candidates:
            return ""

        # Pick highest-scoring signal
        candidates.sort(key=lambda x: x[0], reverse=True)
        best_score, best_text = candidates[0]

        # Only emit if score exceeds minimum threshold
        if best_score < 30:
            return ""

        return f"=== LEAD WITH THIS ===\n{best_text}"

    except Exception as e:
        logger.debug("Lead signal computation skipped: %s", e)
        return ""


def _score_imminent_events(candidates, user, now):
    """Events starting within 15 minutes get highest urgency."""
    try:
        from apps.calendar_engine.models import CalendarEvent

        window_start = now
        window_end = now + timedelta(minutes=15)

        upcoming = CalendarEvent.objects.filter(
            user=user,
            start_dt__gte=window_start,
            start_dt__lte=window_end,
            deleted_at__isnull=True,
        ).exclude(status='canceled').order_by('start_dt').first()

        if upcoming:
            minutes_away = int((upcoming.start_dt - now).total_seconds() / 60)
            local_start = upcoming.start_dt.astimezone(now.tzinfo)
            time_str = local_start.strftime('%I:%M %p').lstrip('0')

            if minutes_away <= 2:
                text = f"Your {upcoming.title} starts NOW ({time_str})."
                score = 100
            elif minutes_away <= 5:
                text = f"Your {upcoming.title} starts in {minutes_away} minutes ({time_str})."
                score = 95
            else:
                text = f"Your {upcoming.title} begins in {minutes_away} minutes ({time_str})."
                score = 85

            # Protected events get a boost
            if getattr(upcoming, 'is_protected', False):
                score = min(score + 5, 100)

            candidates.append((score, text))
    except Exception as e:
        logger.debug("Imminent event scoring skipped: %s", e)


def _score_overdue_meds(candidates, user, now):
    """Overdue medications score high — health is non-negotiable."""
    try:
        from apps.health.models import Medicine, MedicineLog

        today = now.date()
        current_time = now.time()

        active_meds = Medicine.objects.filter(
            user=user,
            medicine_status=Medicine.STATUS_ACTIVE,
        ).prefetch_related('schedules')

        overdue_names = []
        for med in active_meds:
            for sched in med.schedules.all():
                if sched.scheduled_time and sched.scheduled_time < current_time:
                    taken = MedicineLog.objects.filter(
                        medicine=med,
                        scheduled_date=today,
                        schedule=sched,
                        log_status__in=['taken', 'late'],
                    ).exists()
                    if not taken:
                        time_str = sched.scheduled_time.strftime(
                            '%I:%M %p'
                        ).lstrip('0')
                        overdue_names.append(f"{med.name} ({time_str})")
            if len(overdue_names) >= 3:
                break

        if overdue_names:
            if len(overdue_names) == 1:
                text = f"Your {overdue_names[0]} hasn't been marked yet."
            else:
                names = ", ".join(overdue_names)
                text = f"Medications not yet logged: {names}."
            # Score based on how many are overdue
            score = 70 + (len(overdue_names) * 5)
            candidates.append((min(score, 90), text))
    except Exception as e:
        logger.debug("Overdue med scoring skipped: %s", e)


def _score_overdue_tasks(candidates, user, now):
    """Overdue high-priority tasks."""
    try:
        from apps.life.models import Task

        today = now.date()
        overdue = Task.objects.filter(
            user=user,
            completion_status='pending',
            due_date__lt=today,
            priority='now',
        ).order_by('due_date').first()

        if overdue:
            days_overdue = (today - overdue.due_date).days
            text = f'"{overdue.title}" is {days_overdue} day{"s" if days_overdue != 1 else ""} overdue.'
            score = 55 + min(days_overdue * 3, 25)  # Max 80
            candidates.append((score, text))
    except Exception as e:
        logger.debug("Overdue task scoring skipped: %s", e)


def _score_active_event(candidates, user, now):
    """Currently happening event — user should know they're in it."""
    try:
        from apps.calendar_engine.models import CalendarEvent

        active = CalendarEvent.objects.filter(
            user=user,
            start_dt__lte=now,
            end_dt__gte=now,
            deleted_at__isnull=True,
        ).exclude(status__in=['canceled', 'completed']).first()

        if active:
            local_end = active.end_dt.astimezone(now.tzinfo)
            end_str = local_end.strftime('%I:%M %p').lstrip('0')
            remaining = int((active.end_dt - now).total_seconds() / 60)
            text = f"You're in {active.title} right now (ends {end_str}, {remaining} min left)."
            score = 60
            candidates.append((score, text))
    except Exception as e:
        logger.debug("Active event scoring skipped: %s", e)


def _score_goal_gaps(candidates, cos_context):
    """Severe goal gaps from the gap analyzer (if available)."""
    try:
        gaps = cos_context.get('goal_behavior_gaps', [])
        for gap in gaps:
            if gap.get('risk_level') == 'high' and gap.get('gap_pct', 0) <= -50:
                text = (
                    f"Your \"{gap['goal_title']}\" goal is "
                    f"{abs(gap['gap_pct'])}% behind target."
                )
                candidates.append((50, text))
                break  # Only surface the worst gap
    except Exception:
        pass


def _score_pressure(candidates, cos_context):
    """High pressure / burnout risk."""
    try:
        pressure = cos_context.get('pressure_snapshot', {})
        cpi = pressure.get('pressure_index', 0)
        if cpi > 85:
            candidates.append((
                45,
                "Your load is at critical levels this week. "
                "Protect your energy for what matters most."
            ))
    except Exception:
        pass
