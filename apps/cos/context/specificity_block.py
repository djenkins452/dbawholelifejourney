"""
COS-CX1: Always-On Specificity Block
=====================================

Ensures CoS ALWAYS knows specific named items in ALL interactions — not just
check-in mode. This is the difference between "you have 3 tasks" and
"Your quarterly report is overdue, your strategy meeting starts at 2,
and your Valsartan 8AM isn't marked yet."

Injected into every CoS context, every message, unconditionally.

Performance target: < 10ms (4 bounded queries, all indexed).
Token budget: ~200 tokens max.
"""
import logging
from datetime import timedelta

logger = logging.getLogger(__name__)

# Hard limits per Safety Directive 5
MAX_TASKS = 3
MAX_EVENTS = 5
MAX_MEDS = 5
MAX_GOALS = 3


def build_specificity_block(user, now):
    """
    Build the always-on specificity block with named items.

    Args:
        user: Django User object
        now: timezone-aware datetime in user's timezone

    Returns:
        str — formatted block, or "" if nothing to show.
    """
    try:
        parts = []
        today = now.date()

        # --- Tasks: top urgent by name ---
        task_lines = _build_task_lines(user, today)
        if task_lines:
            parts.append("TASKS:")
            parts.extend(task_lines)

        # --- Calendar events today ---
        event_lines = _build_event_lines(user, now, today)
        if event_lines:
            parts.append("EVENTS:")
            parts.extend(event_lines)

        # --- Outstanding medications ---
        med_lines = _build_med_lines(user, today)
        if med_lines:
            parts.append("MEDICATIONS:")
            parts.extend(med_lines)

        # --- Primary active goals ---
        goal_lines = _build_goal_lines(user, today)
        if goal_lines:
            parts.append("GOALS:")
            parts.extend(goal_lines)

        if not parts:
            return ""

        header = "=== TOP PRIORITY ITEMS ==="
        return header + "\n" + "\n".join(parts)

    except Exception as e:
        logger.debug("Specificity block skipped: %s", e)
        return ""


def _build_task_lines(user, today):
    """Top tasks by urgency: overdue first, then due today."""
    try:
        from apps.life.models import Task

        lines = []

        # Overdue tasks (due before today, not completed)
        overdue = list(
            Task.objects.filter(
                user=user,
                is_completed=False,
                due_date__lt=today,
            ).order_by('due_date')
            .values_list('title', 'due_date', 'priority')[:MAX_TASKS]
        )
        for title, due_date, priority in overdue:
            tier_tag = _priority_tag(priority)
            lines.append(f"  \u2022 {title} \u2014 OVERDUE{tier_tag}")

        # Due today (fill remaining slots)
        remaining = MAX_TASKS - len(lines)
        if remaining > 0:
            due_today = list(
                Task.objects.filter(
                    user=user,
                    is_completed=False,
                    due_date=today,
                ).order_by('priority')
                .values_list('title', 'priority')[:remaining]
            )
            for title, priority in due_today:
                tier_tag = _priority_tag(priority)
                lines.append(f"  \u2022 {title} \u2014 Due Today{tier_tag}")

        return lines
    except Exception as e:
        logger.debug("Task specificity skipped: %s", e)
        return []


def _build_event_lines(user, now, today):
    """Today's calendar events with times and status."""
    try:
        from apps.calendar_engine.models import CalendarEvent

        events = list(
            CalendarEvent.objects.filter(
                user=user,
                start_dt__date=today,
                deleted_at__isnull=True,
            ).exclude(
                status='canceled'
            ).order_by('start_dt')[:MAX_EVENTS]
        )

        lines = []
        for ev in events:
            local_start = ev.start_dt.astimezone(now.tzinfo)
            time_str = local_start.strftime('%I:%M %p').lstrip('0')

            # Time-relative status
            if ev.status == 'completed':
                tag = " [done]"
            elif ev.end_dt and now > ev.end_dt:
                tag = " [done]"
            elif ev.start_dt <= now <= (ev.end_dt or ev.start_dt + timedelta(hours=1)):
                tag = " [NOW]"
            elif ev.start_dt <= now + timedelta(minutes=15):
                tag = " [SOON]"
            else:
                tag = ""

            protected = " (protected)" if getattr(ev, 'is_protected', False) else ""
            lines.append(f"  \u2022 {ev.title} \u2014 {time_str}{protected}{tag}")

        return lines
    except Exception as e:
        logger.debug("Event specificity skipped: %s", e)
        return []


def _build_med_lines(user, today):
    """Outstanding medications by name with scheduled time."""
    try:
        from apps.health.models import Medicine, MedicineLog

        active_meds = Medicine.objects.filter(
            user=user,
            medicine_status=Medicine.STATUS_ACTIVE,
        ).prefetch_related('schedules')

        lines = []
        for med in active_meds:
            schedules = med.schedules.all()
            for sched in schedules:
                taken = MedicineLog.objects.filter(
                    medicine=med,
                    scheduled_date=today,
                    schedule=sched,
                    log_status__in=['taken', 'late'],
                ).exists()

                if not taken:
                    time_str = (
                        sched.scheduled_time.strftime('%I:%M %p').lstrip('0')
                        if sched.scheduled_time else ''
                    )
                    label = f"{med.name} ({time_str})" if time_str else med.name
                    lines.append(f"  \u2022 {label} \u2014 NOT TAKEN")

                if len(lines) >= MAX_MEDS:
                    break
            if len(lines) >= MAX_MEDS:
                break

        return lines
    except Exception as e:
        logger.debug("Med specificity skipped: %s", e)
        return []


def _build_goal_lines(user, today):
    """Primary active goals with deadline proximity."""
    try:
        from apps.purpose.models import LifeGoal

        goals = list(
            LifeGoal.objects.filter(
                user=user,
                status='active',
            ).order_by('target_date')[:MAX_GOALS]
        )

        lines = []
        for goal in goals:
            deadline = ""
            if goal.target_date:
                days_left = (goal.target_date - today).days
                if days_left < 0:
                    deadline = " \u2014 OVERDUE"
                elif days_left <= 7:
                    deadline = f" \u2014 {days_left}d left"
                elif days_left <= 30:
                    deadline = f" \u2014 {days_left}d left"

            progress = ""
            try:
                pct = goal.milestone_progress_percent
                if pct is not None and pct > 0:
                    progress = f" ({pct}% complete)"
            except Exception:
                pass

            lines.append(f"  \u2022 {goal.title}{progress}{deadline}")

        return lines
    except Exception as e:
        logger.debug("Goal specificity skipped: %s", e)
        return []


def _priority_tag(priority):
    """Convert priority field to display tag."""
    if priority == 'now':
        return " (Tier 1)"
    elif priority == 'soon':
        return " (Tier 2)"
    return ""
