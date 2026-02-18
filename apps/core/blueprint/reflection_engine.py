"""
Whole Life Journey - Post-Event Reflection Engine

Project: Whole Life Journey
Path: apps/core/blueprint/reflection_engine.py
Purpose: Detect reflectable events, generate questions, queue & deliver reflections

Description:
    After meaningful events (meetings, workouts, social gatherings), the CoS
    follows up with targeted reflection questions. Answers are parsed for
    action items which become Tasks or LifeEvents.

    Respects governance flags:
    - event_reflections_enabled must be True
    - Daily cap of 2 reflections
    - Persona-aware question generation

Public API:
    - detect_reflectable_events(user, date) -> list[dict]
    - generate_reflection_questions(event_dict, persona_key) -> list[str]
    - queue_reflection(user, event_dict) -> EventReflection
    - deliver_pending_reflections(user) -> list[dict]
    - process_reflection_answer(user, reflection_id, answer_text) -> dict

Copyright:
    (c) Whole Life Journey. All rights reserved.
"""

import datetime
import logging
from typing import List, Optional

from django.utils import timezone

logger = logging.getLogger(__name__)

# Maximum reflections per user per day
DAILY_REFLECTION_CAP = 2

# Hours after event to schedule reflection (morning preferred)
REFLECTION_DELAY_HOURS = 12
REFLECTION_MAX_DELAY_HOURS = 24


# =============================================================================
# QUESTION TEMPLATES (by source type)
# =============================================================================

REFLECTION_QUESTIONS = {
    'calendar': [
        "Any action items from {title}?",
        "Anything you need to follow up on?",
    ],
    'workout': [
        "How did {title} go?",
        "Any injuries or adjustments needed for next time?",
    ],
    'social': [
        "How was {title}?",
        "Anyone you want to follow up with?",
    ],
    'health': [
        "Your {title} was unusual yesterday — want to note anything?",
        "Should we adjust today's plan?",
    ],
}


# =============================================================================
# DETECT REFLECTABLE EVENTS
# =============================================================================


def detect_reflectable_events(user, date=None):
    """
    Scan completed LifeEvents and WorkoutSessions for reflection-worthy events.

    Criteria:
    - LifeEvents: meeting/social/work type OR duration > 60min
    - WorkoutSessions: completed (if fitness module enabled)
    - Skips events already in reflection queue
    - Respects event_reflections_enabled governance flag
    - Caps daily reflections at DAILY_REFLECTION_CAP

    Args:
        user: User instance
        date: Date to scan (default: yesterday)

    Returns:
        list of event dicts with keys: source_type, source_id, title, event_date
    """
    from .models import PersonalOperatingBlueprint, EventReflection

    # Check governance flag
    bp = PersonalOperatingBlueprint.get_or_create_for_user(user)
    if not bp.event_reflections_enabled:
        return []

    if date is None:
        date = timezone.localdate() - datetime.timedelta(days=1)

    # Check daily cap — how many reflections already queued for delivery today
    today = timezone.localdate()
    today_count = EventReflection.objects.filter(
        user=user,
        scheduled_for__date=today,
    ).exclude(status=EventReflection.STATUS_EXPIRED).count()

    remaining = DAILY_REFLECTION_CAP - today_count
    if remaining <= 0:
        return []

    # Get existing reflection source_ids to avoid duplicates
    existing_ids = set(
        EventReflection.objects.filter(
            user=user,
            event_date=date,
        ).values_list('source_id', flat=True)
    )

    events = []

    # --- Scan LifeEvents ---
    try:
        from apps.life.models import LifeEvent
        reflectable_types = ['work', 'social', 'health', 'family']

        life_events = LifeEvent.objects.filter(
            user=user,
            start_date=date,
            deleted_at__isnull=True,
        )

        for le in life_events:
            source_id = str(le.pk)
            if source_id in existing_ids:
                continue

            # Check if reflectable: type match OR long duration
            is_reflectable_type = le.event_type in reflectable_types
            is_long = False
            if le.start_time and le.end_time:
                start_dt = datetime.datetime.combine(date, le.start_time)
                end_dt = datetime.datetime.combine(
                    le.end_date or date, le.end_time,
                )
                duration_min = (end_dt - start_dt).total_seconds() / 60
                is_long = duration_min > 60

            if is_reflectable_type or is_long:
                source_type = 'social' if le.event_type == 'social' else 'calendar'
                events.append({
                    'source_type': source_type,
                    'source_id': source_id,
                    'title': le.title,
                    'event_date': date,
                    'event_type': le.event_type,
                })

            if len(events) >= remaining:
                return events

    except (ImportError, Exception) as e:
        logger.debug("Reflection: LifeEvent scan failed: %s", e)

    # --- Scan WorkoutSessions (if fitness enabled) ---
    try:
        if bp.is_module_enabled('health') and bp.is_feature_enabled('health.fitness'):
            from apps.health.models import WorkoutSession
            workouts = WorkoutSession.objects.filter(
                user=user,
                date=date,
                deleted_at__isnull=True,
            )

            for ws in workouts:
                source_id = str(ws.pk)
                if source_id in existing_ids:
                    continue

                title = ws.name or ws.workout_type or 'Workout'
                events.append({
                    'source_type': 'workout',
                    'source_id': source_id,
                    'title': title,
                    'event_date': date,
                })

                if len(events) >= remaining:
                    return events

    except (ImportError, Exception) as e:
        logger.debug("Reflection: WorkoutSession scan failed: %s", e)

    return events


# =============================================================================
# GENERATE REFLECTION QUESTIONS
# =============================================================================


def generate_reflection_questions(event_dict, persona_key=None):
    """
    Generate persona-appropriate reflection questions for an event.

    Args:
        event_dict: dict with source_type, title, event_type (optional)
        persona_key: Optional persona key for tone adjustment

    Returns:
        list of question strings
    """
    source_type = event_dict.get('source_type', 'calendar')
    title = event_dict.get('title', 'your event')
    templates = REFLECTION_QUESTIONS.get(source_type, REFLECTION_QUESTIONS['calendar'])

    questions = [t.format(title=title) for t in templates]

    # Persona tone adjustment (gentle personas get softer framing)
    if persona_key in ('gentle', 'calm_guide'):
        questions = [q.replace('Any ', 'Were there any ') for q in questions]

    return questions


# =============================================================================
# QUEUE REFLECTION
# =============================================================================


def queue_reflection(user, event_dict):
    """
    Create an EventReflection queued for delivery.

    Schedules for the next morning (8am) after the event, or 12h after
    if the event is early in the day.

    Args:
        user: User instance
        event_dict: dict with source_type, source_id, title, event_date

    Returns:
        EventReflection instance
    """
    from .models import EventReflection, PersonalOperatingBlueprint

    bp = PersonalOperatingBlueprint.get_or_create_for_user(user)
    persona_key = bp.persona_id or ''

    questions = generate_reflection_questions(event_dict, persona_key)

    # Schedule for next morning 8am local time, or 12h from now
    event_date = event_dict['event_date']
    tomorrow_8am = timezone.make_aware(
        datetime.datetime.combine(
            event_date + datetime.timedelta(days=1),
            datetime.time(8, 0),
        ),
    )

    # Use 12h from now if that's later (event happened late)
    twelve_hours = timezone.now() + datetime.timedelta(hours=REFLECTION_DELAY_HOURS)
    scheduled_for = max(tomorrow_8am, twelve_hours)

    reflection = EventReflection.objects.create(
        user=user,
        source_type=event_dict['source_type'],
        source_id=event_dict['source_id'],
        source_title=event_dict['title'],
        event_date=event_date,
        scheduled_for=scheduled_for,
        questions=questions,
    )

    logger.info(
        "Reflection queued for %s: '%s' (scheduled %s)",
        user.email, event_dict['title'], scheduled_for,
    )
    return reflection


# =============================================================================
# DELIVER PENDING REFLECTIONS
# =============================================================================


def deliver_pending_reflections(user):
    """
    Get and mark as delivered any reflections past their scheduled time.

    Called when user opens Command Mode or assistant.

    Args:
        user: User instance

    Returns:
        list of dicts with reflection info for display
    """
    from .models import EventReflection

    now = timezone.now()
    pending = EventReflection.objects.filter(
        user=user,
        status=EventReflection.STATUS_PENDING,
        scheduled_for__lte=now,
    ).order_by('scheduled_for')[:DAILY_REFLECTION_CAP]

    delivered = []
    for ref in pending:
        # Expire if too stale (48h+)
        cutoff = ref.scheduled_for + datetime.timedelta(hours=48)
        if now > cutoff:
            ref.status = EventReflection.STATUS_EXPIRED
            ref.save(update_fields=['status', 'updated_at'])
            continue

        ref.mark_delivered()
        delivered.append({
            'id': ref.pk,
            'source_type': ref.source_type,
            'title': ref.source_title,
            'event_date': str(ref.event_date),
            'question': ref.questions[0] if ref.questions else f"How did {ref.source_title} go?",
            'all_questions': ref.questions,
        })

    return delivered


# =============================================================================
# PROCESS REFLECTION ANSWER
# =============================================================================


def process_reflection_answer(user, reflection_id, answer_text):
    """
    Process a user's reflection answer.

    Parses for action items and follow-up events. Creates Tasks/LifeEvents
    as needed. Marks reflection completed.

    Args:
        user: User instance
        reflection_id: EventReflection.pk
        answer_text: User's response text

    Returns:
        dict with keys: completed, action_items, message
    """
    from .models import EventReflection

    try:
        reflection = EventReflection.objects.get(pk=reflection_id, user=user)
    except EventReflection.DoesNotExist:
        return {'completed': False, 'message': 'Reflection not found.'}

    if reflection.status not in (
        EventReflection.STATUS_PENDING,
        EventReflection.STATUS_DELIVERED,
    ):
        return {'completed': False, 'message': 'Reflection already processed.'}

    action_items = []

    # Try to extract action items via SUE if available
    try:
        from apps.core.ai_semantics.semantic_engine import interpret
        result = interpret(user, answer_text)
        entities = result.entities if hasattr(result, 'entities') else {}

        # Look for action-like entities
        if entities.get('action_items'):
            for item in entities['action_items']:
                action_items.append({
                    'type': 'task',
                    'title': item,
                    'source': f'reflection_{reflection_id}',
                })
    except (ImportError, Exception):
        pass

    # Simple keyword detection fallback for action items
    action_keywords = [
        'follow up', 'need to', 'should', 'must', 'have to',
        'schedule', 'call', 'email', 'send', 'book',
    ]
    answer_lower = answer_text.lower()
    has_action_signal = any(kw in answer_lower for kw in action_keywords)

    # Extract people mentions from the answer
    people_extracted = []
    try:
        from apps.core.ai_relationships.relationship_engine import extract_people_from_text
        signals = extract_people_from_text(
            user, answer_text, 'reflection', str(reflection_id),
        )
        people_extracted = [s.person.display_name for s in signals]
    except (ImportError, Exception):
        pass

    # Store the answer
    answers = reflection.answers or {}
    answers['response'] = answer_text
    answers['has_action_signal'] = has_action_signal
    if people_extracted:
        answers['people_mentioned'] = people_extracted

    # Mark completed
    reflection.mark_completed(
        answers=answers,
        action_items=[item.get('title', '') for item in action_items],
    )

    message = "Got it, thanks for reflecting."
    if action_items:
        titles = [item['title'] for item in action_items]
        message += f" I noted action items: {', '.join(titles)}."
    elif has_action_signal:
        message += " It sounds like there might be follow-ups — want me to create any tasks?"

    return {
        'completed': True,
        'action_items': action_items,
        'has_action_signal': has_action_signal,
        'message': message,
    }


# =============================================================================
# SKIP / DISMISS REFLECTION
# =============================================================================


def skip_reflection(user, reflection_id):
    """
    Skip a reflection. User chose not to reflect.

    Args:
        user: User instance
        reflection_id: EventReflection.pk

    Returns:
        bool — True if skipped successfully
    """
    from .models import EventReflection

    try:
        reflection = EventReflection.objects.get(pk=reflection_id, user=user)
    except EventReflection.DoesNotExist:
        return False

    if reflection.status in (
        EventReflection.STATUS_PENDING,
        EventReflection.STATUS_DELIVERED,
    ):
        reflection.mark_skipped()
        return True

    return False


# =============================================================================
# EXPIRE STALE REFLECTIONS
# =============================================================================


def expire_stale_reflections():
    """
    Expire all reflections that are 48h+ past their scheduled time
    and still pending. Called by scheduler.

    Returns:
        int — number of reflections expired
    """
    from .models import EventReflection

    cutoff = timezone.now() - datetime.timedelta(hours=48)
    expired = EventReflection.objects.filter(
        status=EventReflection.STATUS_PENDING,
        scheduled_for__lt=cutoff,
    ).update(status=EventReflection.STATUS_EXPIRED)

    if expired:
        logger.info("Expired %d stale reflections", expired)

    return expired
