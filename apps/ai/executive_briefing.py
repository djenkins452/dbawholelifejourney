# ==============================================================================
# File: apps/ai/executive_briefing.py
# Project: Whole Life Journey - Django 5.x Personal Wellness/Journaling App
# Description: Executive Operator — Morning briefing, session gap detection,
#              rolling conversation memory, journal pattern analysis, and
#              life event surfacing for the Chief of Staff.
# Owner: Danny Jenkins (admin@wholelifejourney.com)
# Created: 2026-02-21
# ==============================================================================
"""
Executive Briefing Service

Transforms the Chief of Staff from reactive assistant into proactive executive
operator. Builds structured context injections for:

1. Morning Executive Arrival Experience — first-of-day greeting with sleep,
   health gates, life events, and day overview.
2. Session Gap Detection — human-language awareness of time since last interaction.
3. Rolling Conversation Memory — summarizes older messages beyond the 15-message
   window to prevent context drop-off.
4. Journal Review Intelligence — mood trends and repeated concern detection.
5. Life Event Surfacing — approaching birthdays, anniversaries, and events.

Public API:
    - build_executive_briefing(user, conversation) -> str
    - maybe_generate_rolling_summary(user, conversation) -> None
    - get_conversation_memory(conversation) -> str
"""

import logging
import re
from collections import Counter
from datetime import timedelta
from typing import Optional

from django.utils import timezone

logger = logging.getLogger(__name__)

# Health-related keywords to detect in journal entries
HEALTH_KEYWORDS = re.compile(
    r'\b(hurt|hurts|pain|painful|sore|soreness|tight|tightness|stiff|stiffness|'
    r'injury|injured|headache|migraine|tired|exhausted|fatigue|sick|nauseous|'
    r'ache|aching|swollen|swelling|pulled|strained|sprained|dizzy|insomnia)\b',
    re.IGNORECASE
)

# Stop words for theme extraction
STOP_WORDS = frozenset({
    'the', 'a', 'an', 'is', 'was', 'were', 'been', 'be', 'have', 'has', 'had',
    'do', 'does', 'did', 'will', 'would', 'could', 'should', 'may', 'might',
    'shall', 'can', 'need', 'dare', 'ought', 'used', 'to', 'of', 'in', 'for',
    'on', 'with', 'at', 'by', 'from', 'as', 'into', 'through', 'during',
    'before', 'after', 'above', 'below', 'between', 'out', 'off', 'over',
    'under', 'again', 'further', 'then', 'once', 'here', 'there', 'when',
    'where', 'why', 'how', 'all', 'each', 'every', 'both', 'few', 'more',
    'most', 'other', 'some', 'such', 'no', 'nor', 'not', 'only', 'own',
    'same', 'so', 'than', 'too', 'very', 'just', 'because', 'but', 'and',
    'or', 'if', 'while', 'about', 'up', 'it', 'its', 'i', 'me', 'my',
    'myself', 'we', 'our', 'you', 'your', 'he', 'him', 'his', 'she', 'her',
    'they', 'them', 'their', 'what', 'which', 'who', 'whom', 'this', 'that',
    'these', 'those', 'am', 'are', 'that', 'like', 'really', 'today',
    'feel', 'feeling', 'felt', 'got', 'get', 'going', 'went', 'thing',
    'things', 'much', 'also', 'still', 'back', 'even', 'well', 'way',
    'day', 'time', 'know', 'think', 'make', 'good', 'new', 'want', 'one',
})

# Mood numeric mapping for trend calculation
MOOD_SCORES = {
    'great': 5, 'good': 4, 'okay': 3, 'neutral': 3,
    'low': 2, 'difficult': 1, 'bad': 1, 'awful': 1,
}


def build_executive_briefing(user, conversation) -> str:
    """
    Build the morning executive briefing for system prompt injection.

    Only fires on first-of-day interactions or after session gaps > 4 hours.
    Returns empty string for mid-conversation messages (fast path).

    Args:
        user: Django User instance.
        conversation: AssistantConversation instance.

    Returns:
        str — formatted system prompt injection, or "" if not applicable.
    """
    try:
        from apps.core.utils import get_user_now, get_user_today

        user_now = get_user_now(user)
        today = get_user_today(user)

        # --- Gate: first-of-day or gap re-entry? ---
        metadata = conversation.metadata or {}
        last_briefing_date = metadata.get('last_briefing_date')
        is_first_of_day = last_briefing_date != str(today)

        gap_hours = _compute_session_gap(conversation)
        is_gap_reentry = (
            gap_hours is not None
            and gap_hours >= 4
            and not is_first_of_day
        )

        if not is_first_of_day and not is_gap_reentry:
            return ""  # Mid-conversation — no briefing needed

        # Mark briefing as delivered
        metadata['last_briefing_date'] = str(today)
        conversation.metadata = metadata
        conversation.save(update_fields=['metadata'])

        # Ensure routine tasks exist for today (fills recurrence gaps)
        # and auto-complete "Wake Up" on first-of-day interaction.
        if is_first_of_day:
            try:
                _ensure_routine_tasks_for_today(user, today)
            except Exception as e:
                logger.debug("Routine task ensure failed: %s", e)

            try:
                from apps.life.models import Task
                wake_task = Task.objects.filter(
                    user=user, is_routine=True, is_completed=False,
                    due_date=today, title__icontains='wake up',
                ).first()
                if wake_task:
                    wake_task.mark_complete()
                    logger.debug(
                        "Auto-completed 'Wake Up' task for user=%s", user.email
                    )
            except Exception as e:
                logger.debug("Wake Up auto-complete failed: %s", e)

        sections = []
        sections.append("--- EXECUTIVE BRIEFING ---")

        # Section A: Time-aware greeting + sleep + gap awareness
        sections.append(
            _build_greeting_section(user, user_now, gap_hours)
        )

        # Section B: Approaching life events (next 7 days)
        sections.append(_build_life_events_section(user, today))

        # Section C: Health gate (meds, fasting, workout)
        sections.append(_build_health_gate_section(user, today))

        # Section D: Day overview narrative
        sections.append(_build_day_overview_section(user, user_now, today))

        # Section E: Journal pattern follow-up (1 item max)
        sections.append(_build_journal_followup_section(user, today))

        # Section F: Gap context (if returning after absence)
        if gap_hours is not None and gap_hours >= 24:
            sections.append(_build_gap_context_section(user, gap_hours, today))

        # Section G: EAE Intelligence Briefing (Phase 8.7)
        # When EAE is enabled, inject scored/budgeted intelligence into briefing.
        # EAE replaces ad-hoc signal injection with controlled cognitive units.
        try:
            from apps.core.blueprint.models import PersonalOperatingBlueprint
            _bp = PersonalOperatingBlueprint.objects.filter(user=user).first()
            if _bp and _bp.eae_enabled:
                from apps.core.ai_eae.eae_engine import arbitrate
                from apps.core.ai_eae.constants import CHANNEL_BRIEFING
                eae_result = arbitrate(user, channel=CHANNEL_BRIEFING)
                if eae_result.prompt_injection:
                    sections.append(eae_result.prompt_injection)
        except Exception as eae_err:
            logger.debug("EAE briefing injection skipped: %s", eae_err)

        sections.append("")
        sections.append(
            "INSTRUCTION: Weave the above into your greeting naturally. "
            "Do NOT present it as a bullet list or data dump. "
            "Present the day as a narrative — like a real Chief of Staff "
            "briefing their executive over coffee. "
            "If the data above lists completed routines or tasks, "
            "briefly acknowledge them. But NEVER claim something is "
            "completed unless it is EXPLICITLY listed as completed above. "
            "If no completed routines or tasks are listed, do NOT "
            "fabricate accomplishments — just greet warmly and move to "
            "what's ahead. "
            "Prioritize health gates (meds, etc.), then events and "
            "relationships, then the day overview. "
            "End by inviting the user to shape their day: "
            "'What needs to move today?' or similar."
        )
        sections.append("--- END EXECUTIVE BRIEFING ---")

        return "\n".join(s for s in sections if s)

    except Exception as e:
        logger.debug("Executive briefing failed: %s", e)
        return ""


def maybe_generate_rolling_summary(user, conversation) -> None:
    """
    Post-response hook: generate a rolling summary if message count > 20
    and no recent summary exists.

    Uses gpt-4o-mini for cost efficiency. Stores in conversation.context_summary.
    Non-blocking — failures are silently caught.

    Args:
        user: Django User instance.
        conversation: AssistantConversation instance.
    """
    try:
        msg_count = conversation.messages.count()
        if msg_count < 20:
            return

        # Check if summary is fresh enough
        metadata = conversation.metadata or {}
        last_summary_count = metadata.get('last_summary_msg_count', 0)
        if msg_count - last_summary_count < 10:
            return  # Summary is recent enough

        # Get messages beyond the 15-message active window
        older_count = max(0, msg_count - 15)
        if older_count == 0:
            return

        older_messages = conversation.messages.order_by('created_at')[:older_count]
        if not older_messages.exists():
            return

        # Build compact transcript for summarization
        transcript_lines = []
        for msg in older_messages[:30]:  # Cap input at 30 messages
            role = "User" if msg.role == 'user' else "Assistant"
            content = msg.content[:200]
            if len(msg.content) > 200:
                content += "..."
            transcript_lines.append(f"{role}: {content}")

        transcript = "\n".join(transcript_lines)

        from .services import ai_service
        if not ai_service.is_available:
            return

        summary = ai_service._call_api(
            system_prompt=(
                "Summarize this conversation history in 2-3 concise sentences. "
                "Focus on: key topics discussed, commitments or decisions made, "
                "concerns raised, health data shared, and any unresolved questions. "
                "Be factual and concise. Do not include greetings or filler."
            ),
            user_prompt=transcript,
            max_tokens=200,
            temperature=0.2,
        )

        if summary:
            conversation.context_summary = summary
            metadata['last_summary_msg_count'] = msg_count
            conversation.metadata = metadata
            conversation.save(
                update_fields=['context_summary', 'metadata', 'updated_at']
            )
            logger.debug(
                "Rolling summary generated for user=%s (%d msgs)",
                user.email, msg_count,
            )

    except Exception as e:
        logger.debug("Rolling summary generation failed: %s", e)


def get_conversation_memory(conversation) -> str:
    """
    Return the conversation's rolling summary formatted for system prompt
    injection.

    Returns empty string if no summary exists.

    Args:
        conversation: AssistantConversation instance.

    Returns:
        str — formatted memory block, or "".
    """
    if not conversation.context_summary:
        return ""
    return (
        "--- CONVERSATION MEMORY ---\n"
        f"Earlier in this conversation: {conversation.context_summary}\n"
        "Use this context to maintain continuity. Reference prior topics "
        "naturally when relevant — the user expects you to remember.\n"
        "--- END CONVERSATION MEMORY ---"
    )


# ===========================================================================
# Private helpers
# ===========================================================================


def _ensure_routine_tasks_for_today(user, today):
    """
    Ensure all recurring routine tasks have an instance for today.

    The recurrence system only creates the next occurrence when the current one
    is completed via mark_complete(). If the user skips a day (doesn't complete
    yesterday's routine task), today's instance is never created, breaking the
    entire routine chain.

    This function finds the most recent instance of each routine task and
    creates today's instance if missing.
    """
    from apps.life.models import Task
    from apps.life.services.recurrence import RecurrencePattern

    # Find all distinct routine task titles for this user
    routine_titles = list(
        Task.objects.filter(user=user, is_routine=True, is_recurring=True)
        .exclude(status='deleted')
        .exclude(deleted_at__isnull=False)
        .values_list('title', flat=True)
        .distinct()
    )

    created_count = 0
    for title in routine_titles:
        # Get the most recent instance as a template
        template_task = (
            Task.objects.filter(
                user=user, title=title, is_routine=True,
            )
            .exclude(status='deleted')
            .exclude(deleted_at__isnull=False)
            .order_by('-due_date')
            .first()
        )
        if not template_task:
            continue

        # Respect recurrence pattern — don't create M-F tasks on weekends
        if template_task.recurrence_pattern:
            try:
                pattern = RecurrencePattern(template_task.recurrence_pattern)
                if pattern.weekdays and today.weekday() not in pattern.weekdays:
                    continue  # Today is not a scheduled day for this routine
            except Exception:
                pass  # If pattern parsing fails, proceed with creation

        # Check if an instance already exists for today
        exists_today = Task.objects.filter(
            user=user,
            title=template_task.title,
            is_routine=True,
            due_date=today,
        ).exclude(status='deleted').exclude(deleted_at__isnull=False).exists()

        if exists_today:
            continue

        # Create today's instance from the most recent template
        Task.objects.create(
            user=user,
            title=template_task.title,
            notes=template_task.notes,
            project=template_task.project,
            priority=template_task.priority,
            effort=template_task.effort,
            due_date=today,
            is_recurring=True,
            recurrence_pattern=template_task.recurrence_pattern,
            start_date=template_task.start_date,
            end_date=template_task.end_date,
            is_routine=True,
            scheduled_time=template_task.scheduled_time,
            scheduled_end_time=template_task.scheduled_end_time,
            estimated_duration_minutes=template_task.estimated_duration_minutes,
            module=template_task.module,
        )
        created_count += 1

    if created_count > 0:
        logger.info(
            "Ensured %d routine tasks for today user=%s",
            created_count, user.email,
        )


def _compute_session_gap(conversation) -> Optional[float]:
    """
    Compute hours since last conversation activity.

    Returns:
        float — hours since last update, or None if conversation is new.
    """
    if not conversation.updated_at:
        return None
    now = timezone.now()
    delta = now - conversation.updated_at
    return delta.total_seconds() / 3600


def _humanize_gap(hours: float) -> str:
    """Translate gap hours into natural human language."""
    if hours < 1:
        return "a short while"
    if hours < 2:
        return "about an hour"
    if hours < 24:
        return f"about {int(hours)} hours"
    days = hours / 24
    if days < 1.5:
        return "about a day"
    if days < 2.5:
        return "a couple of days"
    if days < 7:
        return f"{int(days)} days"
    if days < 10:
        return "about a week"
    if days < 14:
        return f"about {int(days)} days"
    weeks = int(days / 7)
    return f"about {weeks} weeks"


def _build_greeting_section(user, user_now, gap_hours) -> str:
    """Build greeting context with time, sleep, and gap awareness."""
    lines = []

    # Time of day
    hour = user_now.hour
    if hour < 12:
        time_of_day = "morning"
    elif hour < 17:
        time_of_day = "afternoon"
    else:
        time_of_day = "evening"

    time_str = user_now.strftime('%I:%M %p').lstrip('0')
    lines.append(
        f"Time: {time_of_day} ({time_str}). "
        f"Greet them warmly for the {time_of_day}."
    )

    # Sleep data from last night
    try:
        from apps.health.models import SleepEntry
        yesterday = (user_now - timedelta(days=1)).date()
        sleep = SleepEntry.objects.filter(
            user=user, sleep_date=yesterday
        ).exclude(status='deleted').first()
        if sleep:
            duration = ""
            if sleep.asleep_duration_minutes:
                h = sleep.asleep_duration_minutes // 60
                m = sleep.asleep_duration_minutes % 60
                duration = f"{h}h{m}m" if m else f"{h}h"
            elif sleep.total_duration_minutes:
                h = sleep.total_duration_minutes // 60
                m = sleep.total_duration_minutes % 60
                duration = f"{h}h{m}m" if m else f"{h}h"

            quality = sleep.quality_rating or ""
            parts = []
            if duration:
                parts.append(f"slept {duration}")
            if quality:
                parts.append(f"quality: {quality}")
            if parts:
                lines.append(f"Last night's sleep: {', '.join(parts)}.")
    except Exception:
        pass

    # Session gap awareness
    if gap_hours is not None and gap_hours >= 24:
        human_gap = _humanize_gap(gap_hours)
        lines.append(
            f"It's been {human_gap} since they last checked in. "
            "Acknowledge the gap naturally — not as a guilt trip, "
            "but as awareness (e.g., 'It's been a few days...')."
        )

    return "\n".join(lines)


def _build_life_events_section(user, today) -> str:
    """Surface approaching life events (next 7 days)."""
    try:
        from apps.life.models import SignificantEvent
        events = []

        for event in SignificantEvent.objects.filter(user=user):
            try:
                days_until = event.days_until_next(today)
                if days_until is not None and days_until <= 7:
                    label = event.title
                    person = event.person_name or ""
                    if days_until == 0:
                        timing = "today"
                    elif days_until == 1:
                        timing = "tomorrow"
                    else:
                        timing = f"in {days_until} days"
                    entry = f"{label} ({timing})"
                    if person:
                        entry += f" — {person}"
                    events.append((days_until, entry))
            except Exception:
                continue

        # Also check upcoming LifeEvents
        try:
            from apps.life.models import LifeEvent
            cutoff = today + timedelta(days=7)
            for event in LifeEvent.objects.filter(
                user=user, start_date__gte=today, start_date__lte=cutoff,
            ).exclude(status='deleted').order_by('start_date')[:5]:
                days_until = (event.start_date - today).days
                if days_until == 0:
                    timing = "today"
                elif days_until == 1:
                    timing = "tomorrow"
                else:
                    timing = f"in {days_until} days"
                events.append((days_until, f"{event.title} ({timing})"))
        except Exception:
            pass

        if not events:
            return ""

        events.sort(key=lambda x: x[0])
        lines = ["Relational/Life Events This Week:"]
        for _, desc in events[:5]:
            lines.append(f"  - {desc}")
        lines.append(
            "Mention relevant events naturally. For relationships, "
            "show you remember and care."
        )
        return "\n".join(lines)

    except Exception:
        return ""


def _build_health_gate_section(user, today) -> str:
    """Build health status gate — meds, fasting, workout."""
    lines = []

    # Medication check
    try:
        from django.utils import timezone
        from apps.health.models import Medicine, MedicineLog
        from apps.core.utils import get_user_now
        user_now = get_user_now(user)
        active_meds = Medicine.objects.filter(
            user=user, medicine_status=Medicine.STATUS_ACTIVE,
        ).exclude(status='deleted')

        if active_meds.exists():
            current_time = user_now.time()  # user's local time, NOT UTC
            day_of_week = today.weekday()  # 0=Mon, 6=Sun
            total_scheduled = 0
            taken_count = 0
            overdue_count = 0
            upcoming_count = 0
            overdue_names = []
            upcoming_names = []
            for med in active_meds:
                schedules = med.schedules.all()
                for sched in schedules:
                    # Skip schedules that don't apply today
                    # (e.g., Mounjaro is Thursday-only)
                    if not sched.applies_to_day(day_of_week):
                        continue
                    total_scheduled += 1
                    taken = MedicineLog.objects.filter(
                        medicine=med,
                        schedule=sched,
                        scheduled_date=today,
                        log_status__in=['taken', 'late'],
                    ).exists()
                    if taken:
                        taken_count += 1
                    elif sched.scheduled_time and sched.scheduled_time > current_time:
                        upcoming_count += 1
                        time_str = sched.scheduled_time.strftime('%I:%M %p').lstrip('0')
                        upcoming_names.append(f"{med.name} ({time_str})")
                    else:
                        overdue_count += 1
                        overdue_names.append(med.name)

            if total_scheduled > 0:
                if overdue_count > 0:
                    med_list = ', '.join(overdue_names)
                    lines.append(
                        f"HEALTH GATE — Medication: {overdue_count} of "
                        f"{total_scheduled} doses OVERDUE today: {med_list}. "
                        "Ask if they've taken their medicine before "
                        "moving to tasks."
                    )
                    if upcoming_count > 0:
                        upcoming_list = ', '.join(upcoming_names)
                        lines.append(
                            f"({upcoming_count} more doses scheduled later today: "
                            f"{upcoming_list} — not yet due.)"
                        )
                elif upcoming_count > 0:
                    upcoming_list = ', '.join(upcoming_names)
                    lines.append(
                        f"Medication: {taken_count} of {total_scheduled} doses taken. "
                        f"{upcoming_count} scheduled later today: {upcoming_list} (not yet due)."
                    )
                else:
                    lines.append(
                        f"Medication: All {total_scheduled} doses taken today."
                    )
    except Exception:
        logger.error("Executive briefing: medication gate failed", exc_info=True)

    # Active fast
    try:
        from apps.health.models import FastingWindow
        active_fast = FastingWindow.objects.filter(
            user=user, ended_at__isnull=True
        ).exclude(status='deleted').first()
        if active_fast:
            elapsed = active_fast.duration_hours
            target = active_fast.target_hours
            if elapsed is not None and target:
                remaining = target - elapsed
                if remaining > 0:
                    lines.append(
                        f"Active Fast: {elapsed:.1f}h elapsed of "
                        f"{target}h target ({remaining:.1f}h remaining)."
                    )
                else:
                    lines.append(
                        f"Active Fast: Goal reached ({elapsed:.1f}h of "
                        f"{target}h). They can break it when ready."
                    )
    except Exception:
        pass

    # Workout check
    try:
        from apps.health.models import WorkoutSession
        has_workout_today = WorkoutSession.objects.filter(
            user=user, date=today
        ).exclude(status='deleted').exists()
        if has_workout_today:
            # Positive confirmation so AI knows workout was completed
            workout = WorkoutSession.objects.filter(
                user=user, date=today
            ).exclude(status='deleted').first()
            workout_name = workout.name or workout.workout_type or "Workout"
            lines.append(
                f"Workout: {workout_name} logged today. Acknowledge this."
            )
        else:
            # Check if there's a scheduled workout
            try:
                from apps.health.models import WorkoutSchedule
                day_of_week = today.weekday()  # 0=Monday
                has_scheduled = WorkoutSchedule.objects.filter(
                    plan__user=user,
                    plan__is_active=True,
                    day_of_week=day_of_week,
                ).exists()
                if has_scheduled:
                    lines.append(
                        "Workout: Scheduled for today but not yet logged."
                    )
            except Exception:
                pass
    except Exception:
        pass

    # Reading plan / Quiet Time check
    try:
        from apps.faith.models import UserReadingPlan, UserReadingProgress
        active_plans = UserReadingPlan.objects.filter(
            user=user, plan_status='active'
        ).exclude(status='deleted')
        if active_plans.exists():
            # Check if any reading was completed today
            completed_today = UserReadingProgress.objects.filter(
                user_plan__in=active_plans,
                is_completed=True,
                completed_at__date=today,
            ).exists()
            if completed_today:
                lines.append(
                    "Reading Plan / Quiet Time: Completed today. "
                    "Acknowledge this."
                )
            else:
                lines.append(
                    "Reading Plan / Quiet Time: Active plan exists but "
                    "today's reading not yet marked complete."
                )
    except Exception:
        pass

    # Routine task check (daily routines modeled as tasks)
    try:
        from apps.life.models import Task
        completed_routines = list(Task.objects.filter(
            user=user, is_routine=True, is_completed=True,
            due_date=today,
        ).values_list('title', flat=True)[:5])
        pending_routines = list(Task.objects.filter(
            user=user, is_routine=True, is_completed=False,
            due_date=today,
        ).values_list('title', flat=True)[:5])

        total_routines = len(completed_routines) + len(pending_routines)
        if completed_routines and total_routines > 0:
            completion_ratio = len(completed_routines) / total_routines
            if completion_ratio >= 0.7:
                # Most/all routines done — celebrate broadly
                lines.append(
                    f"Routines Completed: {', '.join(completed_routines)}. "
                    "Celebrate this warmly! Summarize with energy "
                    "(e.g., 'You've already knocked out your morning routine!')."
                )
            else:
                # Only some routines done — acknowledge but don't overstate
                lines.append(
                    f"Routines Completed So Far: {', '.join(completed_routines)}. "
                    "Acknowledge briefly but do NOT say they've 'knocked out' "
                    "or 'completed' their morning routine — they're still in progress."
                )
        if pending_routines:
            lines.append(
                f"Routines Still Ahead: {', '.join(pending_routines)}. "
                "Mention these naturally as what's coming up, not as things they missed."
            )
        if not completed_routines and not pending_routines:
            lines.append(
                "Routines: No routine tasks found for today. "
                "Do NOT claim the user has completed any routines — "
                "only mention routines if they are explicitly listed above."
            )
    except Exception:
        pass

    if not lines:
        return ""

    return "\n".join(lines)


def _build_day_overview_section(user, user_now, today) -> str:
    """Build day overview with commitments, conflicts, and overload risk."""
    lines = []

    try:
        from apps.calendar_engine.models import CalendarEvent

        events = CalendarEvent.objects.filter(
            user=user, start_dt__date=today
        ).exclude(status='canceled').exclude(
            deleted_at__isnull=False
        ).order_by('start_dt')[:10]

        event_list = list(events)
        if not event_list:
            lines.append(
                "Today's Schedule: No calendar events. "
                "Open day — ask what they want to focus on."
            )
        else:
            # Count and summarize
            total = len(event_list)
            completed = sum(1 for e in event_list if e.status == 'completed')
            remaining = total - completed

            # Calculate total scheduled minutes for capacity
            total_minutes = 0
            for e in event_list:
                if hasattr(e, 'duration_minutes') and e.duration_minutes:
                    total_minutes += e.duration_minutes

            # Detect conflicts (overlapping time ranges)
            conflicts = []
            for i, e1 in enumerate(event_list):
                for e2 in event_list[i + 1:]:
                    if e1.end_dt and e2.start_dt and e1.end_dt > e2.start_dt:
                        conflicts.append(
                            f"'{e1.title}' overlaps with '{e2.title}'"
                        )

            lines.append(
                f"Today's Schedule: {total} events ({remaining} remaining)."
            )

            if total_minutes > 0:
                hours = total_minutes / 60
                capacity_pct = min(100, int((total_minutes / (16 * 60)) * 100))
                lines.append(
                    f"Scheduled: {hours:.1f}h ({capacity_pct}% of waking hours)."
                )
                if capacity_pct > 85:
                    lines.append(
                        "OVERLOAD RISK: Schedule is packed. "
                        "Suggest what could move or be dropped."
                    )

            if conflicts:
                lines.append(f"Conflicts: {'; '.join(conflicts[:3])}.")

    except Exception:
        pass

    # ── Tasks due today and overdue (non-routine — routines handled by health gate) ──
    try:
        from apps.life.models import Task

        # Overdue tasks (any type)
        overdue_tasks = list(
            Task.objects.filter(
                user=user, is_completed=False, due_date__lt=today
            )
            .exclude(status='deleted')
            .exclude(deleted_at__isnull=False)
            .values_list('title', flat=True)[:8]
        )

        # Non-routine tasks due today (routines already in health gate)
        due_today_tasks = list(
            Task.objects.filter(
                user=user, is_completed=False, due_date=today,
                is_routine=False,
            )
            .exclude(status='deleted')
            .exclude(deleted_at__isnull=False)
            .values_list('title', flat=True)[:8]
        )

        # Tasks with no due date (appear in "Now" bucket on task page)
        no_date_tasks = list(
            Task.objects.filter(
                user=user, is_completed=False, due_date__isnull=True,
            )
            .exclude(status='deleted')
            .exclude(deleted_at__isnull=False)
            .values_list('title', flat=True)[:5]
        )

        # Completed today (non-routine)
        completed_today = list(
            Task.objects.filter(
                user=user, is_completed=True, is_routine=False,
                completed_at__date=today,
            )
            .exclude(status='deleted')
            .exclude(deleted_at__isnull=False)
            .values_list('title', flat=True)[:5]
        )

        if completed_today:
            lines.append(
                f"Tasks Completed Today: {', '.join(completed_today)}. "
                "Acknowledge these accomplishments."
            )
        if overdue_tasks:
            lines.append(
                f"Overdue Tasks: {', '.join(overdue_tasks)}. "
                "Mention gently — ask if they want to tackle, reschedule, "
                "or remove any of these."
            )
        if due_today_tasks:
            lines.append(
                f"Tasks Due Today: {', '.join(due_today_tasks)}. "
                "Mention these as part of what's on their plate."
            )
        if no_date_tasks:
            lines.append(
                f"Open Tasks (no due date): {', '.join(no_date_tasks)}. "
                "These are on their list but not time-bound."
            )
        if not overdue_tasks and not due_today_tasks and not completed_today:
            lines.append("Tasks: No tasks due today or overdue.")
    except Exception as e:
        logger.warning("Failed to load tasks for day overview: %s", e)

    if lines:
        lines.append(
            "Present their day as a narrative, not a list. "
            "Highlight what matters NOW and what's coming up soon."
        )

    return "\n".join(lines) if lines else ""


def _build_journal_followup_section(user, today) -> str:
    """Extract patterns from recent journal entries for follow-up."""
    try:
        from apps.journal.models import JournalEntry

        entries = list(
            JournalEntry.objects.filter(user=user)
            .exclude(status='deleted')
            .order_by('-entry_date')[:5]
        )

        if not entries:
            return ""

        followups = []

        # Mood trend analysis
        moods = [(e.entry_date, MOOD_SCORES.get(e.mood, 3)) for e in entries if e.mood]
        if len(moods) >= 3:
            recent_avg = sum(s for _, s in moods[:3]) / 3
            if recent_avg <= 2.0:
                followups.append(
                    "Mood has been low across recent journal entries. "
                    "Check in gently — not as therapy, but as awareness."
                )
            elif len(moods) >= 4:
                older_avg = sum(s for _, s in moods[2:]) / len(moods[2:])
                if recent_avg < older_avg - 0.8:
                    followups.append(
                        "Mood appears to be declining over recent entries. "
                        "Surface this observation if appropriate."
                    )

        # Health keyword detection across entries
        health_mentions = Counter()
        for entry in entries:
            body = entry.body or ""
            matches = HEALTH_KEYWORDS.findall(body.lower())
            for match in matches:
                health_mentions[match] += 1

        repeated_health = [
            (word, count) for word, count in health_mentions.items()
            if count >= 2
        ]
        if repeated_health:
            top = max(repeated_health, key=lambda x: x[1])
            followups.append(
                f"They mentioned '{top[0]}' {top[1]} times across recent "
                f"journal entries. Follow up naturally: 'Still dealing with "
                f"that {top[0]}?'"
            )

        if not followups:
            return ""

        # Only surface 1 follow-up to keep briefing concise
        return (
            "Journal Pattern:\n"
            f"  {followups[0]}"
        )

    except Exception:
        return ""


def _build_gap_context_section(user, gap_hours, today) -> str:
    """Summarize what happened (or didn't) during a session gap."""
    try:
        from datetime import timedelta as td
        gap_days = int(gap_hours / 24)
        if gap_days < 1:
            return ""

        since_date = today - td(days=gap_days)
        lines = [f"Since Last Session ({_humanize_gap(gap_hours)} ago):"]

        # Journal entries during gap
        try:
            from apps.journal.models import JournalEntry
            journal_count = JournalEntry.objects.filter(
                user=user,
                entry_date__gte=since_date,
                entry_date__lt=today,
            ).exclude(status='deleted').count()
            if journal_count > 0:
                lines.append(f"  - Wrote {journal_count} journal entries")
            elif gap_days >= 2:
                lines.append(f"  - No journal entries for {gap_days} days")
        except Exception:
            pass

        # Medication gaps during absence
        try:
            from apps.health.models import MedicineLog
            missed_days = MedicineLog.objects.filter(
                medicine__user=user,
                scheduled_date__gte=since_date,
                scheduled_date__lt=today,
                log_status='missed',
            ).values('scheduled_date').distinct().count()
            if missed_days > 0:
                lines.append(
                    f"  - Missed medication on {missed_days} "
                    f"day{'s' if missed_days > 1 else ''}"
                )
        except Exception:
            pass

        # Overdue tasks
        try:
            from apps.life.models import Task
            overdue = Task.objects.filter(
                user=user,
                due_date__lt=today,
                is_completed=False,
            ).exclude(status='deleted').count()
            if overdue > 0:
                lines.append(f"  - {overdue} tasks now overdue")
        except Exception:
            pass

        if len(lines) <= 1:
            return ""  # Nothing notable during the gap

        lines.append(
            "Mention what's relevant — don't guilt-trip. "
            "Frame as 'here's what shifted' not 'you missed things'."
        )
        return "\n".join(lines)

    except Exception:
        return ""
