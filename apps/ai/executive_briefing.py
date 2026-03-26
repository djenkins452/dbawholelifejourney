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
    - build_lightweight_alignment(user, conversation) -> str
    - record_interaction_depth(conversation, user, ...) -> None
    - auto_complete_wakeup(user, today) -> bool
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


def handle_day_start(user):
    """
    Authoritative day-start initializer — ONE function, ALL entry points.

    Called on every meaningful user interaction. Idempotent: only performs
    initialization once per user-local date, cached for the rest of the day.

    Responsibilities:
    1. Ensure routine tasks exist for today (fill recurrence gaps)
    2. Auto-complete Wake Up routine for today
    3. Set cache flag so subsequent calls are instant no-ops

    This function must be called BEFORE CoS rendering so that execution
    truth reflects the initialized state.

    Args:
        user: Django User instance.

    Returns:
        dict with:
            initialized: bool — True if this call performed initialization
            wake_completed: bool — True if Wake Up was auto-completed
    """
    from django.core.cache import cache
    from apps.core.utils import get_user_today

    today = get_user_today(user)
    cache_key = f"wlj:day_start:{user.id}:{today}"

    # Fast path: already initialized today (cache hit)
    if cache.get(cache_key):
        return {'initialized': False, 'wake_completed': False}

    # Perform day-start initialization
    wake_completed = False

    # Step 1: Ensure routine tasks exist for today
    try:
        _ensure_routine_tasks_for_today(user, today)
    except Exception as e:
        logger.debug("Day start: routine task ensure failed: %s", e)

    # Step 2: Auto-complete Wake Up
    wake_completed = auto_complete_wakeup(user, today)

    # Mark initialized — TTL until end of day (max 24h)
    cache.set(cache_key, True, timeout=86400)

    logger.info(
        "DAY_START_INITIALIZED user=%s date=%s wake=%s",
        user.id, today, wake_completed,
    )

    return {'initialized': True, 'wake_completed': wake_completed}


def auto_complete_wakeup(user, today):
    """
    Auto-complete the 'Wake Up' routine task for today.

    Internal helper called by handle_day_start(). Safe to call multiple
    times per day (idempotent — only completes pending tasks).

    Args:
        user: Django User instance.
        today: date — user's local today.

    Returns:
        bool — True if a wake_up task was found and completed.
    """
    try:
        from apps.life.models import Task
        wake_task = Task.objects.filter(
            user=user, is_routine=True, completion_status='pending',
            due_date=today, title__icontains='wake up',
        ).first()
        if wake_task:
            wake_task.mark_complete()
            logger.debug(
                "Auto-completed 'Wake Up' task for user=%s", user.email
            )
            return True
    except Exception as e:
        logger.debug("Wake Up auto-complete failed: %s", e)
    return False


def record_interaction_depth(conversation, user, briefing_delivered=False,
                             is_checkin=False):
    """
    Record interaction depth in conversation metadata. Deterministic only.

    Called post-response to track whether a meaningful (deep) interaction
    occurred — used by build_executive_briefing() and the session-start
    endpoint to decide whether to deliver a full briefing or a lightweight
    alignment.

    Deep interaction criteria (any one is sufficient):
    1. Executive briefing was delivered in this response
    2. User triggered a check-in query (status/priorities/etc.)
    3. User sent 3+ messages in last 30 minutes

    When deep: captures an alignment snapshot from execution truth so
    future lightweight alignments can compute the delta.

    Args:
        conversation: AssistantConversation instance.
        user: Django User instance.
        briefing_delivered: bool — True if executive briefing fired.
        is_checkin: bool — True if user asked a check-in/status question.
    """
    metadata = conversation.metadata or {}
    now = timezone.now()

    # Count recent user messages (last 30 min)
    recent_msgs = conversation.messages.filter(
        role='user',
        created_at__gte=now - timedelta(minutes=30),
    ).count()

    is_deep = briefing_delivered or is_checkin or recent_msgs >= 3

    if is_deep:
        metadata['last_deep_interaction_at'] = now.isoformat()
        metadata['interaction_depth'] = 'deep'

        # Capture alignment snapshot from execution truth
        try:
            from apps.core.execution.execution_truth_engine import (
                get_execution_truth,
            )
            truth = get_execution_truth(user)
            routines = truth.get('routines', {})
            tasks = truth.get('tasks', {})
            metadata['alignment_snapshot'] = {
                'captured_at': now.isoformat(),
                'completed_items': [
                    name for name, info
                    in routines.get('items', {}).items()
                    if info.get('fully_complete')
                ],
                'tasks_completed': tasks.get('completed', 0),
                'pending_count': (
                    tasks.get('total', 0) - tasks.get('completed', 0)
                ),
            }
        except Exception as e:
            logger.debug("Alignment snapshot capture failed: %s", e)
    else:
        metadata['interaction_depth'] = 'shallow'

    conversation.metadata = metadata
    conversation.save(update_fields=['metadata'])


def build_lightweight_alignment(user, conversation) -> str:
    """
    Build a compressed alignment when a full briefing would be redundant.

    Called when the executive briefing gate fires (first-of-day or gap
    re-entry) but a deep interaction occurred within the last 90 minutes.
    Returns a short system prompt injection that acknowledges the prior
    alignment and highlights only what changed.

    Data sources (all pre-computed, no heavy computation):
    - conversation.metadata['alignment_snapshot'] — state at last alignment
    - get_execution_truth(user) — current state
    - get_today_context(user)['next'] — current next action

    Args:
        user: Django User instance.
        conversation: AssistantConversation instance.

    Returns:
        str — formatted system prompt injection, or "" if snapshot missing.
    """
    try:
        metadata = conversation.metadata or {}
        snapshot = metadata.get('alignment_snapshot')
        deep_at = metadata.get('last_deep_interaction_at')

        if not snapshot or not deep_at:
            return ""  # No snapshot — fall through to full briefing

        from django.utils.dateparse import parse_datetime
        deep_ts = parse_datetime(deep_at)
        if not deep_ts:
            return ""

        # Format the prior alignment time
        from apps.core.utils import get_user_now
        user_now = get_user_now(user)
        alignment_time = deep_ts.strftime('%I:%M %p').lstrip('0')

        # Get current execution truth
        from apps.core.execution.execution_truth_engine import (
            get_execution_truth,
        )
        truth = get_execution_truth(user)

        # Compute delta: what completed since last alignment
        prev_completed = set(snapshot.get('completed_items', []))
        current_routines = truth.get('routines', {}).get('items', {})
        current_completed = {
            name for name, info in current_routines.items()
            if info.get('fully_complete')
        }
        newly_completed = current_completed - prev_completed

        # Current next action
        try:
            from apps.core.today.today_engine import get_today_context
            today_ctx = get_today_context(user)
            next_action = today_ctx.get('next', '')
        except Exception:
            next_action = ''

        # Build lightweight alignment injection
        sections = ["--- LIGHTWEIGHT ALIGNMENT ---"]
        first_name = getattr(user, 'first_name', '') or 'the user'
        sections.append(
            f"You already aligned with {first_name} at {alignment_time}."
        )

        if newly_completed:
            items_str = ', '.join(sorted(newly_completed))
            sections.append(f"Since then: {items_str} completed.")
        else:
            sections.append("No new completions since then.")

        if next_action:
            sections.append(f"Current focus: {next_action}.")

        sections.append(
            "Do NOT repeat the full briefing. Reference only what has "
            "changed. Be brief and forward-looking."
        )
        sections.append("--- END LIGHTWEIGHT ALIGNMENT ---")

        logger.info(
            "LIGHTWEIGHT_ALIGNMENT user=%s prior_at=%s newly_completed=%d",
            user.id, alignment_time, len(newly_completed),
        )
        return "\n".join(sections)

    except Exception as e:
        logger.debug("Lightweight alignment failed: %s", e)
        return ""


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

        # NOTE: Do NOT mark last_briefing_date here. The caller is
        # responsible for marking delivery AFTER the briefing is
        # successfully consumed (i.e., after the LLM response passes
        # quality checks). Marking here prematurely burns the flag —
        # if the LLM call subsequently fails, no briefing can fire
        # for the rest of the day. See mark_briefing_delivered().

        # Check for recent deep interaction — if user already had a
        # meaningful alignment within 90 minutes, deliver a lightweight
        # alignment instead of the full briefing (prevents repetition).
        deep_at = metadata.get('last_deep_interaction_at')
        if deep_at:
            from django.utils.dateparse import parse_datetime
            deep_ts = parse_datetime(deep_at)
            if deep_ts and (timezone.now() - deep_ts).total_seconds() < 90 * 60:
                lightweight = build_lightweight_alignment(user, conversation)
                if lightweight:
                    logger.info(
                        "BRIEFING_SUPPRESSED_LIGHTWEIGHT user=%s "
                        "deep_at=%s",
                        user.id, deep_at,
                    )
                    return lightweight

        # Authoritative day-start (idempotent) — ensures routine tasks
        # exist and auto-completes Wake Up. Safe to call even if
        # handle_day_start already ran from another entry point.
        handle_day_start(user)

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

        # Section C.5: Behavioral pattern awareness (v8)
        # DISABLED: SA calls during briefing contribute to connection pressure.
        # Re-enable after connection pooling is stable.
        # sections.append(_build_pattern_section(user))

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
            "briefing their executive over coffee.\n"
            "CRITICAL TRUTH RULES:\n"
            "- The FACTS section at the top of your context is AUTHORITATIVE. "
            "Obey it completely.\n"
            "- If FACTS say prayer_completed_today: NO, do NOT say prayer is done.\n"
            "- If FACTS say bible_reading_completed_today: NO, do NOT say "
            "reading is done.\n"
            "- ONLY claim completion if FACTS show YES for that domain.\n"
            "- Items marked [NOT COMPLETED] are NOT done. Period.\n"
            "- A task being PAST its scheduled time means MISSED, not done.\n"
            "- NEVER infer completion from schedule, habits, patterns, or streaks.\n"
            "- If nothing is completed, say so honestly. Do NOT fabricate.\n"
            "- Do NOT say 'great start' or 'productive' when most items are not done.\n"
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


def build_checkin_briefing(user) -> str:
    """
    Build a lightweight check-in briefing for mid-conversation status requests.

    Unlike build_executive_briefing(), this has NO first-of-day or gap gate —
    it fires every time the user asks "check in", "what's left", "status", etc.
    Reuses the same section builders as the morning briefing but skips the
    greeting and journal follow-up (which are morning-only concerns).

    Returns a structured context block for system prompt injection, or empty
    string if all sections are empty.
    """
    try:
        from apps.core.utils import get_user_now, get_user_today

        user_now = get_user_now(user)
        today = get_user_today(user)

        sections = []
        sections.append("--- MID-CONVERSATION CHECK-IN BRIEFING ---")

        # Health gate (meds, fasting, workout, reading)
        sections.append(_build_health_gate_section(user, today))

        # Day overview (calendar, tasks, overdue)
        sections.append(_build_day_overview_section(user, user_now, today))

        # Life events (approaching birthdays, etc.)
        sections.append(_build_life_events_section(user, today))

        sections.append("")
        sections.append(
            "INSTRUCTION: The user is asking for a status check-in. "
            "Use the data above to give a SPECIFIC, DATA-DRIVEN response. "
            "Report what's done, what's pending, what's overdue. "
            "Do NOT ask generic questions like 'What can I help you with?' — "
            "the user asked YOU for their status. ANSWER with concrete data.\n"
            "CRITICAL TRUTH RULES:\n"
            "- The FACTS section at the top of your context is AUTHORITATIVE. "
            "Obey it completely.\n"
            "- If FACTS say prayer_completed_today: NO, do NOT say prayer is done.\n"
            "- If FACTS say bible_reading_completed_today: NO, do NOT say "
            "reading is done.\n"
            "- ONLY claim completion if FACTS show YES for that domain.\n"
            "- Items marked [NOT COMPLETED] are NOT done. Period.\n"
            "- A task being PAST its scheduled time means MISSED, not done.\n"
            "- NEVER infer completion from schedule, habits, patterns, or streaks.\n"
            "- If nothing is completed, say so honestly. Do NOT fabricate.\n"
            "- Do NOT say 'great start' or 'productive' when most items are not done.\n"
            "Present as a brief, natural narrative — not a bullet list. "
            "End by asking what they want to tackle next."
        )
        sections.append("--- END CHECK-IN BRIEFING ---")

        result = "\n".join(s for s in sections if s)

        # If only the wrapper lines exist (no actual data), return empty
        if result.count('\n') <= 3:
            logger.info(
                "CHECKIN_BRIEFING_EMPTY user=%s — no data sections produced",
                user.id,
            )
            return ""

        logger.info(
            "CHECKIN_BRIEFING_BUILT user=%s len=%d",
            user.id, len(result),
        )
        return result

    except Exception as e:
        logger.warning("Mid-conversation check-in briefing failed: %s", e, exc_info=True)
        return ""


def mark_briefing_delivered(conversation):
    """
    Mark the executive briefing as delivered for today.

    Call this ONLY after the briefing has been successfully consumed —
    i.e., the LLM produced a quality response that passed all checks
    and was delivered to the user. Never call this just because
    briefing text was built or injected into the system prompt.

    This prevents the metadata-poisoning bug where a failed LLM call
    burns the last_briefing_date flag and blocks briefings for the
    rest of the day.
    """
    from apps.core.utils import get_user_today
    try:
        today = get_user_today(conversation.user)
        metadata = conversation.metadata or {}
        metadata['last_briefing_date'] = str(today)
        conversation.metadata = metadata
        conversation.save(update_fields=['metadata'])
        logger.info(
            "BRIEFING_MARKED_DELIVERED user=%s date=%s",
            conversation.user.id, today,
        )
    except Exception as e:
        logger.warning("Failed to mark briefing delivered: %s", e)


def maybe_generate_rolling_summary(user, conversation) -> None:
    """
    Post-response hook: generate a rolling summary if message count > 20
    and no recent summary exists.

    Uses the configured OPENAI_MODEL. Stores in conversation.context_summary.
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
        ).exists()

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
    # IMPORTANT: Routine tasks are ORGANIZATIONAL items only. Actual activity
    # completion is tracked by dedicated models (WorkoutSession for workouts,
    # UserReadingProgress for reading, MedicineLog for meds). A routine task
    # being marked complete does NOT prove the activity actually happened.
    # The dedicated checks above (workout, reading plan, medication) are
    # AUTHORITATIVE — routine task status is supplementary.
    try:
        from apps.life.models import Task
        completed_routines = list(Task.objects.filter(
            user=user, is_routine=True, completion_status='completed',
            due_date=today,
        ).values_list('title', flat=True)[:5])
        pending_routines = list(Task.objects.filter(
            user=user, is_routine=True, completion_status='pending',
            due_date=today,
        ).values_list('title', flat=True)[:5])

        # Filter out routine tasks that duplicate dedicated checks above
        # to prevent conflicting signals. The workout/reading/medication
        # checks above are authoritative — don't report these again here.
        dedupe_keywords = {'workout', 'prayer', 'pray', 'bible', 'scripture',
                           'reading', 'quiet time', 'devotion', 'medication',
                           'medicine', 'meds'}
        def _is_dedicated_activity(title):
            return any(kw in title.lower() for kw in dedupe_keywords)

        completed_routines = [t for t in completed_routines if not _is_dedicated_activity(t)]
        pending_routines = [t for t in pending_routines if not _is_dedicated_activity(t)]

        total_routines = len(completed_routines) + len(pending_routines)
        if completed_routines and total_routines > 0:
            lines.append(
                f"[VERIFIED COMPLETED] Routine Tasks: {', '.join(completed_routines)}."
            )
        if pending_routines:
            lines.append(
                f"[NOT COMPLETED] Routine Tasks Still Pending: {', '.join(pending_routines)}. "
                "These have NOT been completed — do NOT claim they are done."
            )
        if not completed_routines and not pending_routines:
            lines.append(
                "Routines: No routine tasks found for today. "
                "Do NOT claim the user has completed any routines — "
                "only mention routines if they are EXPLICITLY listed as "
                "[VERIFIED COMPLETED] above."
            )

        # Explicit negative assertions for common false-positive items
        # This prevents the LLM from inferring completion of activities
        # that have dedicated truth sources elsewhere.
        _neg_assertions = []
        if not has_workout_today:
            _neg_assertions.append(
                "Workout has NOT been logged today — do NOT say it is done."
            )
        _neg_assertions_text = ' '.join(_neg_assertions)
        if _neg_assertions_text:
            lines.append(f"NEGATIVE ASSERTIONS: {_neg_assertions_text}")
    except Exception:
        pass

    if not lines:
        return ""

    return "\n".join(lines)


def _build_pattern_section(user) -> str:
    """
    v8: Build behavioral pattern context for morning briefing.

    Injects momentum, drift, one-off sensitivity, and emotional context
    so the LLM can weave pattern observations into the briefing narrative.
    """
    try:
        from apps.ai.situational_awareness import build_situational_awareness
        sa = build_situational_awareness(user)

        if not sa or not sa.get('lines'):
            return ""

        parts = []

        momentum = sa.get('momentum_signals', [])
        drift = sa.get('drift_signals', [])
        one_off = sa.get('one_off_sensitive_domains', [])
        emotional = sa.get('emotional_context', 'none')

        if momentum:
            parts.append(
                f"PATTERN CONTEXT: User has been consistent with "
                f"{', '.join(momentum)}. Reinforce — do not recommend "
                f"these as new improvements."
            )

        if drift:
            parts.append(
                f"DRIFT CONTEXT: {', '.join(drift)} has dropped off "
                f"(active goal exists). Frame as recommit-or-deprioritize, "
                f"not guilt."
            )

        if one_off:
            parts.append(
                f"ONE-OFF CONTEXT: {', '.join(one_off)} is recently "
                f"consistent but may not be done yet today. "
                f"Gentle nudge only — not failure."
            )

        if emotional != 'none':
            parts.append(
                f"EMOTIONAL CONTEXT: {emotional} signals detected in "
                f"recent conversations. Reduce pressure in this briefing. "
                f"Prioritize care and stability."
            )

        if not parts:
            return ""

        return "\n".join(parts)

    except Exception as e:
        logger.debug("Executive briefing: pattern section unavailable: %s", e)
        return ""


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

    # ── Tasks — EXACT same query as the Organize page ──────────────────
    # The Organize page uses Task.objects (SoftDeleteManager → status='active')
    # filtered by completion_status='pending' and the stored `priority` field.
    # We use the IDENTICAL queryset here. The count MUST match what the UI
    # shows. Beth may include up to 3 example titles for context, but the
    # count is always the true total from .count().
    try:
        from apps.life.models import Task
        from apps.life.views import _refresh_stale_task_priorities

        # Refresh stale priorities so overnight changes are reflected
        _refresh_stale_task_priorities(user)

        # Same base queryset as Organize page — SoftDeleteManager already
        # filters status='active'. No extra .exclude() calls.
        pending_base = Task.objects.filter(
            user=user, completion_status='pending',
        )

        # Counts — must match what the Organize page shows
        now_count = pending_base.filter(priority='now').count()
        soon_count = pending_base.filter(priority='soon').count()

        # TEMPORARY: include task IDs for entity grounding — remove when
        # Phase 2 signal-driven insights replace raw task injection.
        now_examples = [
            f"(id:{tid}) {title}"
            for tid, title in pending_base.filter(priority='now')
            .values_list('id', 'title')[:3]
        ]
        soon_examples = [
            f"(id:{tid}) {title}"
            for tid, title in pending_base.filter(priority='soon')
            .values_list('id', 'title')[:3]
        ]

        # Completed today
        completed_count = Task.objects.filter(
            user=user, completion_status='completed',
            completed_at__date=today,
        ).count()
        completed_examples = list(
            Task.objects.filter(
                user=user, completion_status='completed',
                completed_at__date=today,
            ).values_list('title', flat=True)[:3]
        )

        if completed_count:
            example_str = ', '.join(completed_examples)
            if completed_count > len(completed_examples):
                example_str += f' (+{completed_count - len(completed_examples)} more)'
            lines.append(
                f"Tasks Completed Today ({completed_count}): {example_str}. "
                "Acknowledge these accomplishments."
            )
        if now_count:
            example_str = ', '.join(now_examples)
            if now_count > len(now_examples):
                example_str += f' (+{now_count - len(now_examples)} more)'
            lines.append(
                f"Tasks — Now ({now_count}): {example_str}. "
                "These are due today or overdue — the user's immediate priorities."
            )
        if soon_count:
            example_str = ', '.join(soon_examples)
            if soon_count > len(soon_examples):
                example_str += f' (+{soon_count - len(soon_examples)} more)'
            lines.append(
                f"Tasks — Soon ({soon_count}): {example_str}. "
                "Due within the next 7 days."
            )
        if not now_count and not soon_count and not completed_count:
            lines.append("Tasks: No tasks due today, overdue, or due soon.")
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

        # Overdue tasks — use priority-based count matching Organize page
        try:
            from apps.life.models import Task
            from apps.life.views import _refresh_stale_task_priorities
            _refresh_stale_task_priorities(user)
            overdue = Task.objects.filter(
                user=user,
                priority='now',
                due_date__lt=today,
                completion_status='pending',
            ).count()
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
