# ==============================================================================
# File: apps/ai/quick_reply_handlers.py
# Project: Whole Life Journey - Django 5.x Personal Wellness/Journaling App
# Description: Handle quick reply button actions from the assistant chat
# Owner: Danny Jenkins (admin@wholelifejourney.com)
# Created: 2026-02-05
# ==============================================================================
"""
Quick Reply Handlers

Processes quick reply button clicks from the assistant chat.
Each action type has a dedicated handler that executes the action
and returns an appropriate response message.

Action Types:
    - mark_medicine_taken: Mark a medicine dose as taken
    - skip_medicine: Mark a medicine dose as skipped
    - remind_later: Snooze a reminder for later
    - confirm_workout: Mark today's workout as done
    - start_journal: Open journal entry page
    - acknowledge: Simple acknowledgment (dismiss message)
"""

import logging
from datetime import date, timedelta
from typing import Optional

from django.utils import timezone

logger = logging.getLogger(__name__)


def handle_quick_reply(user, action: str, params: dict) -> dict:
    """
    Route a quick reply action to its handler.

    Args:
        user: The user who clicked the quick reply
        action: The action type (e.g., 'mark_medicine_taken')
        params: Action-specific parameters

    Returns:
        dict: {
            'success': bool,
            'message': str,  # Response to show user
            'data': dict,    # Optional additional data
        }
    """
    handlers = {
        'mark_medicine_taken': handle_mark_medicine_taken,
        'skip_medicine': handle_skip_medicine,
        'mark_medicine_group_taken': handle_mark_medicine_group_taken,
        'skip_medicine_group': handle_skip_medicine_group,
        'remind_later': handle_remind_later,
        'confirm_workout': handle_confirm_workout,
        'start_journal': handle_start_journal,
        'acknowledge': handle_acknowledge,
        'mark_task_complete': handle_mark_task_complete,
        'skip_routine_item': handle_skip_routine_item,
        'complete_routine_item': handle_complete_routine_item,
        # Guidance/insight card actions ("Tell me more", "How to use this" → chat;
        # "Got it" → dismiss). 'chat' is fulfilled client-side (the card's question is
        # sent to chat), so the server call is a benign acknowledgement.
        'chat': handle_chat_ack,
        'dismiss': handle_dismiss_guidance,
    }

    handler = handlers.get(action)
    if not handler:
        logger.warning(f"Unknown quick reply action: {action}")
        return {
            'success': False,
            'message': "I'm not sure how to handle that action.",
        }

    try:
        return handler(user, params)
    except Exception as e:
        logger.exception(f"Error handling quick reply {action}: {e}")
        return {
            'success': False,
            'message': "Something went wrong. Please try again.",
        }


def handle_chat_ack(user, params: dict) -> dict:
    """"Tell me more" / "How to use this" — the card's pre-written question is sent to
    chat by the client (so Beth expands the observation / explains how to use it). The
    server call is a benign acknowledgement; nothing to persist."""
    return {'success': True, 'message': ''}


def handle_dismiss_guidance(user, params: dict) -> dict:
    """"Got it" — dismiss a guidance/insight card and PERSIST the dismissal so the same
    observation does not resurface unless it materially changes. Keyed by the card's
    guidance identity (correlation/check-in type) and a content hash: a later card with
    the same hash is suppressed; a materially different one (new hash) surfaces again."""
    import hashlib
    from django.core.cache import cache
    from .models import AssistantMessage

    message_id = params.get('message_id')
    if message_id:
        try:
            msg = AssistantMessage.objects.get(id=message_id, conversation__user=user)
            meta = msg.metadata or {}
            key_id = meta.get('correlation_type') or meta.get('check_in_type') or 'generic'
            content_hash = meta.get('content_hash') or hashlib.sha1(
                (msg.content or '').encode('utf-8')).hexdigest()[:12]
            cache.set(f"wlj:guidance_dismissed:{user.id}:{key_id}",
                      content_hash, 90 * 24 * 3600)
        except AssistantMessage.DoesNotExist:
            pass
        except Exception as e:
            logger.warning(f"dismiss_guidance persist failed: {e}")
    return {'success': True, 'message': ''}


def handle_mark_medicine_taken(user, params: dict) -> dict:
    """Mark a medicine dose as taken."""
    from apps.health.models import Intake, IntakeLog

    medicine_id = params.get('medicine_id')
    schedule_id = params.get('schedule_id')
    dose_time = params.get('dose_time')

    if not medicine_id:
        return {
            'success': False,
            'message': "I couldn't find which medicine to mark.",
        }

    try:
        medicine = Intake.objects.get(id=medicine_id, user=user)

        # Create medicine log entry
        log_date = date.today()
        log_time = dose_time or timezone.now().strftime('%H:%M')

        # Check if already logged
        existing = IntakeLog.objects.filter(
            intake=medicine,
            date=log_date,
            time=log_time,
        ).first()

        if existing and existing.status == 'taken':
            return {
                'success': True,
                'message': f"You've already logged taking {medicine.name}. All set!",
            }

        # Create or update log
        if existing:
            existing.status = 'taken'
            existing.save()
        else:
            IntakeLog.objects.create(
                intake=medicine,
                date=log_date,
                time=log_time,
                status='taken',
                notes='Logged via assistant quick reply',
            )

        return {
            'success': True,
            'message': f"Great! I've logged your {medicine.name}. Keep it up!",
            'data': {'medicine_name': medicine.name},
        }

    except Intake.DoesNotExist:
        return {
            'success': False,
            'message': "I couldn't find that medicine in your list.",
        }


def handle_skip_medicine(user, params: dict) -> dict:
    """Mark a medicine dose as skipped."""
    from apps.health.models import Intake, IntakeLog

    medicine_id = params.get('medicine_id')
    schedule_id = params.get('schedule_id')
    dose_time = params.get('dose_time')
    reason = params.get('reason', '')

    if not medicine_id:
        return {
            'success': False,
            'message': "I couldn't find which medicine to skip.",
        }

    try:
        medicine = Intake.objects.get(id=medicine_id, user=user)

        log_date = date.today()
        log_time = dose_time or timezone.now().strftime('%H:%M')

        # Create skip log
        # NOTE: field names below (date/time/status) appear to be stale —
        # current schema uses scheduled_date/scheduled_time/log_status.
        # Out-of-scope to fix in this stabilization PR; tracked separately.
        # The `source` kwarg is added defensively so provenance is
        # captured if/when the field names are corrected.
        IntakeLog.objects.update_or_create(
            intake=medicine,
            date=log_date,
            time=log_time,
            defaults={
                'status': 'skipped',
                'notes': reason or 'Skipped via assistant',
                'source': IntakeLog.SOURCE_QUICK_REPLY,
            }
        )

        return {
            'success': True,
            'message': f"Okay, I've noted that you skipped {medicine.name}. Want me to remind you later?",
        }

    except Intake.DoesNotExist:
        return {
            'success': False,
            'message': "I couldn't find that medicine in your list.",
        }


def handle_mark_medicine_group_taken(user, params: dict) -> dict:
    """Mark ALL medicines in a time-of-day group as taken."""
    from apps.health.models import Intake, IntakeLog, IntakeSchedule
    from apps.core.utils import get_user_today

    time_of_day = params.get('time_of_day')
    medicine_ids = params.get('medicine_ids', [])
    dose_time = params.get('due_time') or params.get('dose_time')

    if not medicine_ids:
        return {
            'success': False,
            'message': "I couldn't find which medicines to mark.",
        }

    today = get_user_today(user)
    marked_count = 0
    med_names = []

    for med_id in medicine_ids:
        try:
            medicine = Intake.objects.get(id=med_id, user=user)
            # Find the schedule for this medicine and time_of_day
            schedule = IntakeSchedule.objects.filter(
                intake=medicine,
                is_active=True,
                time_of_day=time_of_day,
            ).first()

            log_time = schedule.scheduled_time.strftime('%H:%M') if schedule else (dose_time or '09:00')

            # Create or update log
            # NOTE: stale field names — see comment on first IntakeLog.update_or_create above.
            IntakeLog.objects.update_or_create(
                intake=medicine,
                date=today,
                time=log_time,
                defaults={
                    'status': 'taken',
                    'notes': 'Logged via assistant group quick reply',
                    'source': IntakeLog.SOURCE_QUICK_REPLY,
                }
            )
            marked_count += 1
            med_names.append(medicine.name)
        except Intake.DoesNotExist:
            continue

    if marked_count == 0:
        return {
            'success': False,
            'message': "Couldn't find those medicines in your list.",
        }

    group_display = (time_of_day or 'morning').replace('_', ' ')
    return {
        'success': True,
        'message': f"Marked all {marked_count} {group_display} meds as taken.",
        'data': {'marked_count': marked_count, 'medicine_names': med_names},
    }


def handle_skip_medicine_group(user, params: dict) -> dict:
    """Skip ALL medicines in a time-of-day group."""
    from apps.health.models import Intake, IntakeLog, IntakeSchedule
    from apps.core.utils import get_user_today

    time_of_day = params.get('time_of_day')
    medicine_ids = params.get('medicine_ids', [])
    dose_time = params.get('due_time') or params.get('dose_time')

    if not medicine_ids:
        return {
            'success': False,
            'message': "I couldn't find which medicines to skip.",
        }

    today = get_user_today(user)
    skipped_count = 0

    for med_id in medicine_ids:
        try:
            medicine = Intake.objects.get(id=med_id, user=user)
            schedule = IntakeSchedule.objects.filter(
                intake=medicine,
                is_active=True,
                time_of_day=time_of_day,
            ).first()

            log_time = schedule.scheduled_time.strftime('%H:%M') if schedule else (dose_time or '09:00')

            # NOTE: stale field names — see comment on first IntakeLog.update_or_create above.
            IntakeLog.objects.update_or_create(
                intake=medicine,
                date=today,
                time=log_time,
                defaults={
                    'status': 'skipped',
                    'notes': 'Skipped via assistant group quick reply',
                    'source': IntakeLog.SOURCE_QUICK_REPLY,
                }
            )
            skipped_count += 1
        except Intake.DoesNotExist:
            continue

    group_display = (time_of_day or 'morning').replace('_', ' ')
    return {
        'success': True,
        'message': f"Noted. Skipped all {skipped_count} {group_display} meds.",
    }


def handle_remind_later(user, params: dict) -> dict:
    """Snooze a reminder for later. Uses the actual due time when available."""
    reminder_type = params.get('reminder_type', 'general')
    item_id = params.get('item_id')
    due_time = params.get('due_time')

    # Calculate snooze: use actual due time if available, otherwise 30 min
    if due_time:
        try:
            from apps.core.utils import get_user_now
            from datetime import datetime
            user_now = get_user_now(user)
            due_hour, due_min = map(int, due_time.split(':'))
            due_dt = user_now.replace(hour=due_hour, minute=due_min, second=0, microsecond=0)

            # If due time hasn't passed yet, remind at due time
            if due_dt > user_now:
                diff_minutes = int((due_dt - user_now).total_seconds() / 60)
                time_display = due_dt.strftime('%I:%M %p').lstrip('0')
                return {
                    'success': True,
                    'message': f"Got it! I'll remind you at {time_display}.",
                    'data': {'snooze_until': due_dt.isoformat()},
                }
        except Exception:
            pass

    # Fallback: 30 minute snooze
    snooze_time = timezone.now() + timedelta(minutes=30)
    return {
        'success': True,
        'message': "Got it! I'll check back in about 30 minutes.",
        'data': {'snooze_until': snooze_time.isoformat()},
    }


def handle_confirm_workout(user, params: dict) -> dict:
    """Mark today's workout as done."""
    from apps.health.models import WorkoutSession
    from apps.core.utils import get_user_today

    today = get_user_today(user)

    # Check if already logged today
    existing = WorkoutSession.objects.filter(
        user=user,
        date=today,
    ).first()

    if existing:
        return {
            'success': True,
            'message': "You've already logged a workout today! Nice work keeping active.",
        }

    # Create a quick workout entry
    workout_type = params.get('workout_type', 'General')
    duration = params.get('duration', 30)

    WorkoutSession.objects.create(
        user=user,
        date=today,
        workout_type=workout_type,
        duration_minutes=duration,
        notes='Logged via assistant quick reply',
    )

    return {
        'success': True,
        'message': "Awesome! I've logged your workout. Way to stay active!",
        'data': {'workout_type': workout_type, 'duration': duration},
    }


def handle_start_journal(user, params: dict) -> dict:
    """Prompt user to start journaling."""
    return {
        'success': True,
        'message': "Great idea! Head to your journal to capture your thoughts.",
        'data': {
            'action': 'navigate',
            'url': '/journal/new/',
        },
    }


def handle_acknowledge(user, params: dict) -> dict:
    """Simple acknowledgment - dismiss the message."""
    message = params.get('message', "Got it!")
    return {
        'success': True,
        'message': message,
    }


def handle_mark_task_complete(user, params: dict) -> dict:
    """Mark a task as complete."""
    from apps.life.models import Task

    task_id = params.get('task_id')

    if not task_id:
        return {
            'success': False,
            'message': "I couldn't find which task to complete.",
        }

    try:
        task = Task.objects.get(id=task_id, user=user)

        if task.is_complete:
            return {
                'success': True,
                'message': f"'{task.title}' is already marked complete!",
            }

        task.complete()

        return {
            'success': True,
            'message': f"Done! '{task.title}' is now complete.",
            'data': {'task_title': task.title},
        }

    except Task.DoesNotExist:
        return {
            'success': False,
            'message': "I couldn't find that task.",
        }


# =============================================================================
# QUICK REPLY GENERATORS
# =============================================================================

def generate_medicine_check_in_replies(medicine_id: int, medicine_name: str, dose_time: str) -> list:
    """Generate quick reply buttons for a medicine check-in."""
    return [
        {
            'id': 'yes_taken',
            'label': 'Yes, I took it',
            'action': 'mark_medicine_taken',
            'params': {
                'medicine_id': medicine_id,
                'dose_time': dose_time,
            },
            'style': 'primary',
        },
        {
            'id': 'no_skip',
            'label': 'Skip this dose',
            'action': 'skip_medicine',
            'params': {
                'medicine_id': medicine_id,
                'dose_time': dose_time,
            },
            'style': 'secondary',
        },
        {
            'id': 'remind_later',
            'label': 'Remind me later',
            'action': 'remind_later',
            'params': {
                'reminder_type': 'medicine',
                'item_id': medicine_id,
                'snooze_minutes': 30,
            },
            'style': 'secondary',
        },
    ]


def generate_grouped_medicine_replies(time_of_day: str, medicine_ids: list, due_time: str = None) -> list:
    """
    Generate quick reply buttons for a GROUPED medicine check-in.

    Instead of per-pill buttons, gives group-level actions:
    - "I took them" → marks ALL medicines in this group as taken
    - "Skip" → marks all as skipped
    - "Remind me later" → reminds at the actual due time (not hardcoded 30 min)
    """
    # Calculate snooze: time until actual due time, or 30 min fallback
    snooze_minutes = 30
    if due_time:
        try:
            from datetime import datetime
            from apps.core.time.system_clock import get_current_time
            now = get_current_time()
            due_dt = datetime.strptime(due_time, '%H:%M')
            # Use a simple minutes-until-due calculation
            due_hour, due_min = int(due_time.split(':')[0]), int(due_time.split(':')[1])
            # We'll pass the actual due_time and let the handler compute
        except Exception:
            pass

    return [
        {
            'id': 'group_taken',
            'label': 'I took them',
            'action': 'mark_medicine_group_taken',
            'params': {
                'time_of_day': time_of_day,
                'medicine_ids': medicine_ids,
                'due_time': due_time,
            },
            'style': 'primary',
        },
        {
            'id': 'group_skip',
            'label': 'Skip',
            'action': 'skip_medicine_group',
            'params': {
                'time_of_day': time_of_day,
                'medicine_ids': medicine_ids,
                'due_time': due_time,
            },
            'style': 'secondary',
        },
        {
            'id': 'remind_later',
            'label': 'Remind me later',
            'action': 'remind_later',
            'params': {
                'reminder_type': 'medicine_group',
                'time_of_day': time_of_day,
                'item_id': medicine_ids[0] if medicine_ids else None,
                'due_time': due_time,
            },
            'style': 'secondary',
        },
    ]


def generate_workout_check_in_replies() -> list:
    """Generate quick reply buttons for a workout check-in."""
    return [
        {
            'id': 'yes_done',
            'label': 'Yes, I worked out',
            'action': 'confirm_workout',
            'params': {},
            'style': 'primary',
        },
        {
            'id': 'remind_later',
            'label': 'Remind me later',
            'action': 'remind_later',
            'params': {
                'reminder_type': 'workout',
                'snooze_minutes': 60,
            },
            'style': 'secondary',
        },
        {
            'id': 'skip_today',
            'label': 'Not today',
            'action': 'acknowledge',
            'params': {
                'message': "No problem! Rest days are important too. I'll check in tomorrow.",
            },
            'style': 'secondary',
        },
    ]


def generate_journal_check_in_replies() -> list:
    """Generate quick reply buttons for a journal check-in."""
    return [
        {
            'id': 'start_journal',
            'label': 'Start journaling',
            'action': 'start_journal',
            'params': {},
            'style': 'primary',
        },
        {
            'id': 'remind_later',
            'label': 'Remind me later',
            'action': 'remind_later',
            'params': {
                'reminder_type': 'journal',
                'snooze_minutes': 120,
            },
            'style': 'secondary',
        },
        {
            'id': 'skip_today',
            'label': 'Skip today',
            'action': 'acknowledge',
            'params': {
                'message': "That's okay! Journaling when you're ready makes it more meaningful.",
            },
            'style': 'secondary',
        },
    ]


def generate_mood_check_in_replies() -> list:
    """Generate quick reply buttons for a mood check-in."""
    return [
        {
            'id': 'doing_well',
            'label': 'Doing well',
            'action': 'acknowledge',
            'params': {
                'message': "Glad to hear it! Keep that momentum going.",
            },
            'style': 'primary',
        },
        {
            'id': 'could_be_better',
            'label': 'Could be better',
            'action': 'acknowledge',
            'params': {
                'message': "Thanks for sharing. Would you like to journal about what's on your mind? Sometimes writing helps process things.",
            },
            'style': 'secondary',
        },
        {
            'id': 'need_support',
            'label': 'Need some support',
            'action': 'acknowledge',
            'params': {
                'message': "I'm here for you. Take a moment to breathe. Would you like to talk through what's going on, or would journaling help?",
            },
            'style': 'secondary',
        },
    ]


def generate_task_check_in_replies(task_id: int, task_title: str) -> list:
    """Generate quick reply buttons for a task check-in."""
    return [
        {
            'id': 'mark_complete',
            'label': 'Mark complete',
            'action': 'mark_task_complete',
            'params': {
                'task_id': task_id,
            },
            'style': 'primary',
        },
        {
            'id': 'working_on_it',
            'label': 'Working on it',
            'action': 'acknowledge',
            'params': {
                'message': "Great! Keep at it. Let me know when you're done.",
            },
            'style': 'secondary',
        },
        {
            'id': 'need_help',
            'label': 'Need help',
            'action': 'acknowledge',
            'params': {
                'message': "What's blocking you? Maybe I can help you break it down into smaller steps.",
            },
            'style': 'secondary',
        },
    ]


# =============================================================================
# Phase 4: Cross-Domain Quick Reply Handlers
# =============================================================================


def generate_faith_reading_replies(plan_id: int) -> list:
    """Quick replies for faith reading plan check-in."""
    return [
        {
            'id': 'open_plan',
            'label': "Open today's reading",
            'action': 'navigate',
            'params': {'url': f'/faith/reading-plans/{plan_id}/'},
            'style': 'primary',
        },
        {
            'id': 'remind_later',
            'label': 'Remind me later',
            'action': 'acknowledge',
            'params': {'message': "I'll check back later."},
            'style': 'secondary',
        },
    ]


def generate_finance_budget_replies(category_name: str) -> list:
    """Quick replies for budget threshold alert."""
    return [
        {
            'id': 'view_budget',
            'label': 'View budget',
            'action': 'navigate',
            'params': {'url': '/finance/budgets/'},
            'style': 'primary',
        },
        {
            'id': 'got_it',
            'label': 'Got it',
            'action': 'acknowledge',
            'params': {'message': "Noted. I'll keep tracking."},
            'style': 'secondary',
        },
    ]


def generate_goal_check_in_replies(goal_id: int, goal_type: str = 'life') -> list:
    """Quick replies for goal deadline/stalling check-in."""
    url = '/purpose/goals/' if goal_type == 'life' else '/purpose/habits/'
    return [
        {
            'id': 'view_goal',
            'label': 'View goal',
            'action': 'navigate',
            'params': {'url': url},
            'style': 'primary',
        },
        {
            'id': 'update_progress',
            'label': 'Update progress',
            'action': 'acknowledge',
            'params': {'message': "What progress have you made? I can help log it."},
            'style': 'primary',
        },
        {
            'id': 'remind_later',
            'label': 'Remind me later',
            'action': 'acknowledge',
            'params': {'message': "I'll check back later."},
            'style': 'secondary',
        },
    ]


def generate_relationship_drift_replies(person_name: str) -> list:
    """Quick replies for relationship drift alert."""
    return [
        {
            'id': 'reach_out',
            'label': 'Remind me to reach out',
            'action': 'acknowledge',
            'params': {'message': f"I'll add a reminder to reach out to {person_name}."},
            'style': 'primary',
        },
        {
            'id': 'already_connected',
            'label': 'Already connected',
            'action': 'acknowledge',
            'params': {'message': "Got it, I'll update the record."},
            'style': 'secondary',
        },
    ]


def generate_journal_concern_replies() -> list:
    """Quick replies for recurring journal concern check-in."""
    return [
        {
            'id': 'lets_talk',
            'label': "Let's talk about it",
            'action': 'acknowledge',
            'params': {'message': "I'm here. What's on your mind?"},
            'style': 'primary',
        },
        {
            'id': 'im_fine',
            'label': "I'm handling it",
            'action': 'acknowledge',
            'params': {'message': "Good to hear. I'll keep an eye on it."},
            'style': 'secondary',
        },
    ]


# =============================================================================
# Routine Recovery Quick Reply Handlers + Generators
# =============================================================================

def handle_skip_routine_item(user, params: dict) -> dict:
    """Skip a routine item for today."""
    from apps.life.models import RoutineSchedule
    from apps.life.services.routine_helpers import skip_routine

    schedule_id = params.get('schedule_id')
    if not schedule_id:
        return {
            'success': False,
            'message': "I couldn't find which routine item to skip.",
        }

    try:
        schedule = RoutineSchedule.objects.get(id=schedule_id, routine__user=user)
        from apps.core.utils import get_user_today
        today = get_user_today(user)
        skip_routine(user, schedule, today)
        return {
            'success': True,
            'message': f"Okay, skipped {schedule.task_name} for today.",
            'data': {'schedule_id': schedule_id, 'item_name': schedule.task_name},
        }
    except RoutineSchedule.DoesNotExist:
        return {
            'success': False,
            'message': "I couldn't find that routine item.",
        }
    except Exception as e:
        logger.exception(f"Error skipping routine item {schedule_id}: {e}")
        return {
            'success': False,
            'message': "Something went wrong. Please try again.",
        }


def handle_complete_routine_item(user, params: dict) -> dict:
    """Mark a routine item as completed (will be completed_late if past window)."""
    from apps.life.models import RoutineSchedule
    from apps.life.services.routine_helpers import toggle_routine_completion

    schedule_id = params.get('schedule_id')
    if not schedule_id:
        return {
            'success': False,
            'message': "I couldn't find which routine item to complete.",
        }

    try:
        schedule = RoutineSchedule.objects.get(id=schedule_id, routine__user=user)
        from apps.core.utils import get_user_today
        today = get_user_today(user)
        result = toggle_routine_completion(user, schedule, today)
        return {
            'success': True,
            'message': f"Done! {schedule.task_name} marked complete.",
            'data': {'schedule_id': schedule_id, 'item_name': schedule.task_name},
        }
    except RoutineSchedule.DoesNotExist:
        return {
            'success': False,
            'message': "I couldn't find that routine item.",
        }
    except Exception as e:
        logger.exception(f"Error completing routine item {schedule_id}: {e}")
        return {
            'success': False,
            'message': "Something went wrong. Please try again.",
        }


def generate_routine_recovery_replies(schedule_id: int, item_name: str) -> list:
    """
    Generate quick reply buttons for routine recovery check-in.

    Options:
    - Reschedule: prompts user for time (CoS handles via intent)
    - Skip today: skips the routine item
    - Done already: marks complete (completed_late)
    """
    return [
        {
            'id': 'reschedule',
            'label': 'Reschedule',
            'action': 'acknowledge',
            'params': {
                'message': f"What time would you like to do {item_name}?",
            },
            'style': 'primary',
        },
        {
            'id': 'done_already',
            'label': 'Done already',
            'action': 'complete_routine_item',
            'params': {
                'schedule_id': schedule_id,
            },
            'style': 'primary',
        },
        {
            'id': 'skip_today',
            'label': 'Skip today',
            'action': 'skip_routine_item',
            'params': {
                'schedule_id': schedule_id,
            },
            'style': 'secondary',
        },
    ]


def generate_nudge_follow_up_replies(schedule_id: int, item_name: str) -> list:
    """
    Generate quick reply buttons for due-now and follow-up nudges.

    Options:
    - Mark done: marks complete
    - Not yet: acknowledges, no action
    - Reschedule: prompts for new time
    - Skip: skips the routine item
    """
    return [
        {
            'id': 'done_already',
            'label': 'Mark done',
            'action': 'complete_routine_item',
            'params': {
                'schedule_id': schedule_id,
            },
            'style': 'primary',
        },
        {
            'id': 'not_yet',
            'label': 'Not yet',
            'action': 'acknowledge',
            'params': {
                'message': f"Got it — keep {item_name} on your radar.",
            },
            'style': 'secondary',
        },
        {
            'id': 'reschedule',
            'label': 'Reschedule',
            'action': 'acknowledge',
            'params': {
                'message': f"What time would you like to do {item_name}?",
            },
            'style': 'secondary',
        },
        {
            'id': 'skip_today',
            'label': 'Skip',
            'action': 'skip_routine_item',
            'params': {
                'schedule_id': schedule_id,
            },
            'style': 'secondary',
        },
    ]
