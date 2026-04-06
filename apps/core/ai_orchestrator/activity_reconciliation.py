"""
Activity Reconciliation Layer — prevents duplicate activity creation.

Intercepts create_* intents and checks for existing activities that match
the same concept. All decisions are PROPOSALS — nothing executes without
user confirmation via the CRUD Confirmation Gate.

Registry-based architecture: each domain registers its own reconciler.
If no reconciler exists for an intent, falls through to CRUD gate.

Pipeline position:
    Time/Context Enrichment → Activity Reconciliation → CRUD Confirmation Gate → Execution
"""

import logging
from dataclasses import dataclass, field
from enum import Enum
from typing import Callable, Dict, List, Optional

logger = logging.getLogger(__name__)


# ── Data Structures ──────────────────────────────────────────────────


class ReconciliationDecision(Enum):
    """Possible outcomes of reconciliation."""
    CREATE = 'create'              # No match found — propose creation
    RESCHEDULE = 'reschedule'      # Match found, different time — propose mutate
    SKIP = 'skip'                  # Match found, same time — propose no-op
    CONFIRM = 'confirm'            # Ambiguous match — ask user to choose
    DISAMBIGUATE = 'disambiguate'  # Multiple matches — user must pick one


@dataclass
class ReconciliationResult:
    """Result of the reconciliation check."""
    decision: ReconciliationDecision
    original_intent: str
    redirected_intent: Optional[str] = None
    redirected_params: Optional[dict] = None
    matched_object: Optional[dict] = None   # {model, id, title, time}
    confidence: float = 0.0
    reason: str = ''
    skip_message: Optional[str] = None      # User-facing message for SKIP
    confirm_message: Optional[str] = None   # User-facing message for CONFIRM
    candidates: Optional[list] = field(default_factory=list)


# ── Confidence Thresholds ────────────────────────────────────────────

CONFIDENCE_HIGH = 0.9      # Auto-propose reschedule/skip
CONFIDENCE_MEDIUM = 0.7    # Present match for confirmation
# Below 0.7 → treat as new (CREATE)


# ── Title Matching ───────────────────────────────────────────────────

STOP_WORDS = frozenset({
    'a', 'an', 'the', 'my', 'do', 'go', 'to', 'for', 'at', 'in',
    'on', 'with', 'and', 'or', 'of', 'i', 'me', 'its', 'it',
    'get', 'have', 'take', 'make', 'schedule', 'create', 'add',
    'set', 'up', 'new', 'some', 'this', 'that',
})


def _extract_keywords(title: str) -> Optional[List[str]]:
    """Extract meaningful keywords, stripping stop words."""
    words = title.lower().split()
    keywords = [w for w in words if w not in STOP_WORDS and len(w) > 2]
    return keywords if keywords else None


def _compute_title_similarity(query: str, title: str) -> float:
    """
    Compute similarity score between a query and a title.

    Tier 1: exact match → 1.0
    Tier 2: prefix match → 0.9
    Tier 3: substring match → 0.8
    Tier 4: keyword overlap → 0.5-0.7
    """
    if not query or not title:
        return 0.0
    if query == title:
        return 1.0
    if title.startswith(query) or query.startswith(title):
        return 0.9
    if query in title or title in query:
        return 0.8

    query_kw = set(_extract_keywords(query) or [])
    title_kw = set(_extract_keywords(title) or [])
    if not query_kw or not title_kw:
        return 0.0

    overlap = query_kw & title_kw
    if not overlap:
        return 0.0

    query_coverage = len(overlap) / len(query_kw)
    title_coverage = len(overlap) / len(title_kw)
    combined = (query_coverage + title_coverage) / 2
    return 0.5 + (combined * 0.2)  # Scale to 0.5-0.7


def _score_best_match(query_title: str, candidates):
    """Score candidates and return (best_object, confidence)."""
    query_lower = query_title.strip().lower()
    best = None
    best_score = 0.0

    for obj in candidates:
        title = getattr(obj, 'title', '') or ''
        score = _compute_title_similarity(query_lower, title.strip().lower())
        if score > best_score:
            best_score = score
            best = obj

    return best, best_score


def _score_all_matches(query_title: str, candidates):
    """Score all candidates and return list of (object, confidence) with score >= CONFIDENCE_MEDIUM, sorted desc."""
    query_lower = query_title.strip().lower()
    scored = []
    for obj in candidates:
        title = getattr(obj, 'title', '') or ''
        score = _compute_title_similarity(query_lower, title.strip().lower())
        if score >= CONFIDENCE_MEDIUM:
            scored.append((obj, score))
    scored.sort(key=lambda x: x[1], reverse=True)
    return scored


def _build_task_candidate_info(task_obj):
    """Build rich candidate dict for a Task object (includes time for disambiguation prompt)."""
    time_str = None
    if task_obj.scheduled_time:
        time_str = task_obj.scheduled_time.strftime('%I:%M %p').lstrip('0')
    return {
        'id': task_obj.id,
        'title': task_obj.title,
        'time': time_str,
        'due_date': str(task_obj.due_date) if getattr(task_obj, 'due_date', None) else None,
        'model': 'Task',
    }


def _build_event_candidate_info(event_obj, user_tz=None):
    """Build rich candidate dict for a CalendarEvent object."""
    time_str = None
    if event_obj.start_dt:
        try:
            if user_tz:
                local_time = event_obj.start_dt.astimezone(user_tz).time()
            else:
                local_time = event_obj.start_dt.time()
            time_str = local_time.strftime('%I:%M %p').lstrip('0')
        except Exception:
            pass
    return {
        'id': event_obj.id,
        'title': event_obj.title,
        'time': time_str,
        'model': 'CalendarEvent',
    }


# ── Time Utilities ───────────────────────────────────────────────────

def _parse_time(time_str):
    """Parse HH:MM to a time object. Returns None if unparseable."""
    if not time_str:
        return None
    from datetime import datetime as dt
    try:
        return dt.strptime(time_str, '%H:%M').time()
    except (ValueError, TypeError):
        return None


def _times_match(time_a, time_b) -> bool:
    """Check if two times are effectively the same."""
    if time_a is None and time_b is None:
        return True
    if time_a is None or time_b is None:
        return False
    return time_a.hour == time_b.hour and time_a.minute == time_b.minute


def _resolve_target_date(date_str, today):
    """Resolve a date string to a date object."""
    from datetime import timedelta

    if not date_str:
        return today

    lower = date_str.lower().strip()
    if lower == 'today':
        return today
    elif lower == 'tomorrow':
        return today + timedelta(days=1)
    else:
        from datetime import datetime as dt
        try:
            return dt.strptime(date_str, '%Y-%m-%d').date()
        except (ValueError, TypeError):
            return today


def _get_user_today(user):
    """Get today's date in the user's timezone."""
    try:
        from apps.core.utils import get_user_today
        return get_user_today(user)
    except (ImportError, Exception):
        from django.utils import timezone
        return timezone.localdate()


# ── Domain Reconcilers ───────────────────────────────────────────────

def _reconcile_task(user, enriched_action) -> ReconciliationResult:
    """Reconcile create_task / create_routine_task against existing tasks."""
    from apps.life.models import Task
    from django.db.models import Q

    params = enriched_action.parameters
    title = params.get('title', '')
    intent = enriched_action.intent_type

    if not title:
        return ReconciliationResult(
            decision=ReconciliationDecision.CREATE,
            original_intent=intent, reason='no_title',
        )

    today = _get_user_today(user)
    target_date = _resolve_target_date(params.get('due_date'), today)

    base_qs = Task.objects.filter(
        user=user, status='active', completion_status='pending',
    )
    if target_date:
        base_qs = base_qs.filter(Q(due_date=target_date) | Q(is_routine=True))
    else:
        base_qs = base_qs.filter(is_routine=True)

    # Tiered matching
    title_stripped = title.strip()
    candidates = list(base_qs.filter(title__iexact=title_stripped))
    if not candidates:
        candidates = list(base_qs.filter(title__istartswith=title_stripped))
    if not candidates:
        candidates = list(base_qs.filter(title__icontains=title_stripped))
    if not candidates:
        keywords = _extract_keywords(title_stripped)
        if keywords:
            q = Q()
            for kw in keywords:
                q |= Q(title__icontains=kw)
            candidates = list(base_qs.filter(q))

    if not candidates:
        _log_decision(intent, title, None, 0.0, 'CREATE', 'no_match')
        return ReconciliationResult(
            decision=ReconciliationDecision.CREATE,
            original_intent=intent, reason='no_match',
        )

    best, confidence = _score_best_match(title, candidates)

    if confidence < CONFIDENCE_MEDIUM:
        _log_decision(intent, title, best.title if best else None, confidence, 'CREATE', 'low_confidence')
        return ReconciliationResult(
            decision=ReconciliationDecision.CREATE,
            original_intent=intent, confidence=confidence,
            reason=f'low_confidence ({confidence:.2f})',
        )

    matched_obj = {
        'model': 'Task', 'id': best.id, 'title': best.title,
        'time': str(best.scheduled_time) if best.scheduled_time else None,
    }

    # Multiple high-confidence candidates → DISAMBIGUATE
    if len(candidates) > 1:
        scored = _score_all_matches(title, candidates)
        high_scorers = [s for s in scored if s[1] >= CONFIDENCE_MEDIUM]
        if len(high_scorers) > 1:
            _log_decision(intent, title, best.title, confidence, 'DISAMBIGUATE',
                          f'multiple_high_confidence ({len(high_scorers)})')
            return ReconciliationResult(
                decision=ReconciliationDecision.DISAMBIGUATE,
                original_intent=intent, confidence=confidence,
                matched_object=matched_obj,
                candidates=[_build_task_candidate_info(obj) for obj, _ in high_scorers[:5]],
                confirm_message=f'I found {len(high_scorers)} tasks matching "{title}". Which one?',
                reason='multiple_high_confidence',
            )

    # Time comparison (single match or only one high-confidence)
    new_time = _parse_time(params.get('scheduled_time'))
    existing_time = best.scheduled_time

    if _times_match(new_time, existing_time):
        time_str = existing_time.strftime('%I:%M %p').lstrip('0') if existing_time else 'today'
        _log_decision(intent, title, best.title, confidence, 'SKIP', 'same_time')
        return ReconciliationResult(
            decision=ReconciliationDecision.SKIP,
            original_intent=intent, confidence=confidence,
            matched_object=matched_obj,
            skip_message=(
                f'You already have "{best.title}" scheduled'
                + (f' at {time_str}' if existing_time else '')
                + '. No changes needed.'
            ),
            reason='same_time_skip',
        )
    else:
        _log_decision(intent, title, best.title, confidence, 'RESCHEDULE', 'different_time')
        return ReconciliationResult(
            decision=ReconciliationDecision.RESCHEDULE,
            original_intent=intent, confidence=confidence,
            matched_object=matched_obj,
            redirected_intent='mutate_task',
            redirected_params=_build_task_mutate_params(best, params),
            reason='different_time_reschedule',
        )


def _reconcile_event(user, enriched_action) -> ReconciliationResult:
    """Reconcile create_event against existing calendar events."""
    import datetime as _dt
    from django.db.models import Q

    params = enriched_action.parameters
    title = params.get('title', '')
    intent = enriched_action.intent_type

    if not title:
        return ReconciliationResult(
            decision=ReconciliationDecision.CREATE,
            original_intent=intent, reason='no_title',
        )

    try:
        from apps.calendar_engine.models import CalendarEvent
    except ImportError:
        return ReconciliationResult(
            decision=ReconciliationDecision.CREATE,
            original_intent=intent, reason='calendar_module_missing',
        )

    today = _get_user_today(user)
    target_date = _resolve_target_date(params.get('start_date'), today)

    # Get user timezone
    try:
        from apps.core.utils import get_current_local_datetime
        user_now = get_current_local_datetime(user)
        user_tz = user_now.tzinfo
    except Exception:
        import pytz
        user_tz = pytz.timezone('America/Chicago')

    qs = CalendarEvent.objects.filter(
        user=user, deleted_at__isnull=True,
    )
    if hasattr(CalendarEvent, 'STATUS_CANCELED'):
        qs = qs.exclude(status=CalendarEvent.STATUS_CANCELED)

    if target_date and user_tz:
        day_start = _dt.datetime.combine(target_date, _dt.time.min)
        day_end = _dt.datetime.combine(target_date, _dt.time.max)
        try:
            if hasattr(user_tz, 'localize'):
                day_start = user_tz.localize(day_start)
                day_end = user_tz.localize(day_end)
            else:
                day_start = day_start.replace(tzinfo=user_tz)
                day_end = day_end.replace(tzinfo=user_tz)
        except Exception:
            pass
        qs = qs.filter(start_dt__gte=day_start, start_dt__lte=day_end)

    title_stripped = title.strip()
    candidates = list(qs.filter(title__iexact=title_stripped))
    if not candidates:
        candidates = list(qs.filter(title__icontains=title_stripped))
    if not candidates:
        keywords = _extract_keywords(title_stripped)
        if keywords:
            q = Q()
            for kw in keywords:
                q |= Q(title__icontains=kw)
            candidates = list(qs.filter(q))

    if not candidates:
        _log_decision(intent, title, None, 0.0, 'CREATE', 'no_match')
        return ReconciliationResult(
            decision=ReconciliationDecision.CREATE,
            original_intent=intent, reason='no_match',
        )

    best, confidence = _score_best_match(title, candidates)

    if confidence < CONFIDENCE_MEDIUM:
        _log_decision(intent, title, best.title if best else None, confidence, 'CREATE', 'low_confidence')
        return ReconciliationResult(
            decision=ReconciliationDecision.CREATE,
            original_intent=intent, confidence=confidence,
            reason=f'low_confidence ({confidence:.2f})',
        )

    # Multiple high-confidence candidates → DISAMBIGUATE
    if len(candidates) > 1:
        scored = _score_all_matches(title, candidates)
        high_scorers = [s for s in scored if s[1] >= CONFIDENCE_MEDIUM]
        if len(high_scorers) > 1:
            _log_decision(intent, title, best.title, confidence, 'DISAMBIGUATE',
                          f'multiple_high_confidence ({len(high_scorers)})')
            return ReconciliationResult(
                decision=ReconciliationDecision.DISAMBIGUATE,
                original_intent=intent, confidence=confidence,
                matched_object={
                    'model': 'CalendarEvent', 'id': best.id, 'title': best.title,
                    'time': None,
                },
                candidates=[_build_event_candidate_info(obj, user_tz) for obj, _ in high_scorers[:5]],
                confirm_message=f'I found {len(high_scorers)} events matching "{title}". Which one?',
                reason='multiple_high_confidence',
            )

    existing_time = None
    if best.start_dt and user_tz:
        try:
            existing_time = best.start_dt.astimezone(user_tz).time()
        except Exception:
            existing_time = best.start_dt.time() if best.start_dt else None

    matched_obj = {
        'model': 'CalendarEvent', 'id': best.id, 'title': best.title,
        'time': str(existing_time) if existing_time else None,
    }

    new_time = _parse_time(params.get('start_time'))

    if _times_match(new_time, existing_time):
        time_str = existing_time.strftime('%I:%M %p').lstrip('0') if existing_time else ''
        _log_decision(intent, title, best.title, confidence, 'SKIP', 'same_time')
        return ReconciliationResult(
            decision=ReconciliationDecision.SKIP,
            original_intent=intent, confidence=confidence,
            matched_object=matched_obj,
            skip_message=(
                f'You already have "{best.title}" on your calendar'
                + (f' at {time_str}' if time_str else '')
                + '. No changes needed.'
            ),
            reason='same_time_skip',
        )
    else:
        _log_decision(intent, title, best.title, confidence, 'RESCHEDULE', 'different_time')
        return ReconciliationResult(
            decision=ReconciliationDecision.RESCHEDULE,
            original_intent=intent, confidence=confidence,
            matched_object=matched_obj,
            redirected_intent='mutate_calendar_event',
            redirected_params=_build_event_mutate_params(best, params, user),
            reason='different_time_reschedule',
        )


def _reconcile_health_log(user, enriched_action) -> ReconciliationResult:
    """Reconcile health log intents (weight, BP, HR, etc.) against same-day entries."""
    intent = enriched_action.intent_type
    params = enriched_action.parameters
    today = _get_user_today(user)

    # Map intent → model + value field
    MODEL_MAP = {
        'log_weight': ('apps.health.models', 'Weight', 'weight'),
        'log_blood_pressure': ('apps.health.models', 'BloodPressure', None),
        'log_heart_rate': ('apps.health.models', 'HeartRate', 'bpm'),
        'log_glucose': ('apps.health.models', 'Glucose', 'level'),
        'log_blood_oxygen': ('apps.health.models', 'BloodOxygen', 'spo2'),
        'log_body_measurement': ('apps.health.models', 'BodyMeasurement', None),
    }

    mapping = MODEL_MAP.get(intent)
    if not mapping:
        return ReconciliationResult(
            decision=ReconciliationDecision.CREATE,
            original_intent=intent, reason='unknown_health_type',
        )

    module_path, model_name, value_field = mapping

    try:
        import importlib
        mod = importlib.import_module(module_path)
        Model = getattr(mod, model_name)
    except (ImportError, AttributeError):
        return ReconciliationResult(
            decision=ReconciliationDecision.CREATE,
            original_intent=intent, reason='model_import_failed',
        )

    # Check for same-day entries
    try:
        existing = Model.objects.filter(user=user, recorded_at__date=today).order_by('-recorded_at').first()
    except Exception:
        try:
            existing = Model.objects.filter(user=user, date=today).order_by('-id').first()
        except Exception:
            return ReconciliationResult(
                decision=ReconciliationDecision.CREATE,
                original_intent=intent, reason='query_failed',
            )

    if not existing:
        _log_decision(intent, str(params), None, 0.0, 'CREATE', 'no_existing_today')
        return ReconciliationResult(
            decision=ReconciliationDecision.CREATE,
            original_intent=intent, reason='no_existing_today',
        )

    # Same-day entry exists — check value
    matched_obj = {'model': model_name, 'id': existing.id, 'title': model_name, 'time': str(today)}

    if value_field and hasattr(existing, value_field):
        existing_val = getattr(existing, value_field)
        new_val = params.get(value_field) or params.get('value')
        if new_val is not None and str(existing_val) == str(new_val):
            _log_decision(intent, str(new_val), str(existing_val), 1.0, 'SKIP', 'same_value')
            return ReconciliationResult(
                decision=ReconciliationDecision.SKIP,
                original_intent=intent, confidence=1.0,
                matched_object=matched_obj,
                skip_message=f"Already logged {existing_val} for {model_name.lower()} today.",
                reason='same_value_skip',
            )

    # Different value or can't compare — CONFIRM
    _log_decision(intent, str(params.get(value_field, '')), str(getattr(existing, value_field, '')),
                  0.9, 'CONFIRM', 'different_value')
    return ReconciliationResult(
        decision=ReconciliationDecision.CONFIRM,
        original_intent=intent, confidence=0.9,
        matched_object=matched_obj,
        confirm_message=f"You already logged {model_name.lower()} today. Log another entry?",
        reason='existing_today_different_value',
    )


def _reconcile_medicine(user, enriched_action) -> ReconciliationResult:
    """Reconcile take_medication against same-day medication logs."""
    intent = enriched_action.intent_type
    params = enriched_action.parameters
    med_name = params.get('medication_name', params.get('name', ''))
    today = _get_user_today(user)

    if not med_name:
        return ReconciliationResult(
            decision=ReconciliationDecision.CREATE,
            original_intent=intent, reason='no_med_name',
        )

    try:
        from apps.medical.models import MedicationLog
        existing = MedicationLog.objects.filter(
            user=user,
            taken_at__date=today,
            medication__name__iexact=med_name.strip(),
        ).exists()
    except (ImportError, Exception):
        return ReconciliationResult(
            decision=ReconciliationDecision.CREATE,
            original_intent=intent, reason='query_failed',
        )

    if existing:
        _log_decision(intent, med_name, med_name, 1.0, 'SKIP', 'already_taken')
        return ReconciliationResult(
            decision=ReconciliationDecision.SKIP,
            original_intent=intent, confidence=1.0,
            matched_object={'model': 'MedicationLog', 'id': None, 'title': med_name, 'time': str(today)},
            skip_message=f'"{med_name}" is already marked as taken today.',
            reason='already_taken_today',
        )

    return ReconciliationResult(
        decision=ReconciliationDecision.CREATE,
        original_intent=intent, reason='not_taken_yet',
    )


def _reconcile_workout(user, enriched_action) -> ReconciliationResult:
    """Reconcile log_workout against same-day workout entries."""
    intent = enriched_action.intent_type
    params = enriched_action.parameters
    workout_type = params.get('workout_type', params.get('type', ''))
    today = _get_user_today(user)

    try:
        from apps.health.models import Workout
        qs = Workout.objects.filter(user=user, date=today)
        if workout_type:
            qs = qs.filter(workout_type__iexact=workout_type.strip())
        existing = qs.first()
    except (ImportError, Exception):
        return ReconciliationResult(
            decision=ReconciliationDecision.CREATE,
            original_intent=intent, reason='query_failed',
        )

    if existing:
        label = workout_type or 'workout'
        _log_decision(intent, label, label, 0.9, 'CONFIRM', 'existing_today')
        return ReconciliationResult(
            decision=ReconciliationDecision.CONFIRM,
            original_intent=intent, confidence=0.9,
            matched_object={'model': 'Workout', 'id': existing.id, 'title': label, 'time': str(today)},
            confirm_message=f"You already logged a {label} today. Log another one?",
            reason='existing_workout_today',
        )

    return ReconciliationResult(
        decision=ReconciliationDecision.CREATE,
        original_intent=intent, reason='no_existing_today',
    )


def _reconcile_goal(user, enriched_action) -> ReconciliationResult:
    """Reconcile create_goal against existing goals with same title."""
    intent = enriched_action.intent_type
    params = enriched_action.parameters
    title = params.get('title', params.get('name', ''))

    if not title:
        return ReconciliationResult(
            decision=ReconciliationDecision.CREATE,
            original_intent=intent, reason='no_title',
        )

    try:
        from apps.purpose.models import Goal
        existing = Goal.objects.filter(
            user=user, status='active', title__iexact=title.strip(),
        ).first()
    except (ImportError, Exception):
        return ReconciliationResult(
            decision=ReconciliationDecision.CREATE,
            original_intent=intent, reason='query_failed',
        )

    if existing:
        _log_decision(intent, title, existing.title, 1.0, 'SKIP', 'goal_exists')
        return ReconciliationResult(
            decision=ReconciliationDecision.SKIP,
            original_intent=intent, confidence=1.0,
            matched_object={'model': 'Goal', 'id': existing.id, 'title': existing.title, 'time': None},
            skip_message=f'You already have an active goal "{existing.title}".',
            reason='goal_already_exists',
        )

    return ReconciliationResult(
        decision=ReconciliationDecision.CREATE,
        original_intent=intent, reason='no_existing_goal',
    )


def _reconcile_intention(user, enriched_action) -> ReconciliationResult:
    """Reconcile set_intention against today's existing intention."""
    intent = enriched_action.intent_type
    today = _get_user_today(user)

    try:
        from apps.purpose.models import Intention
        existing = Intention.objects.filter(user=user, date=today).first()
    except (ImportError, Exception):
        return ReconciliationResult(
            decision=ReconciliationDecision.CREATE,
            original_intent=intent, reason='query_failed',
        )

    if existing:
        _log_decision(intent, 'new intention', existing.text[:30] if hasattr(existing, 'text') else '',
                      0.9, 'CONFIRM', 'intention_exists_today')
        return ReconciliationResult(
            decision=ReconciliationDecision.CONFIRM,
            original_intent=intent, confidence=0.9,
            matched_object={'model': 'Intention', 'id': existing.id, 'title': 'Daily Intention', 'time': str(today)},
            confirm_message="You already set an intention for today. Replace it?",
            reason='intention_exists_today',
        )

    return ReconciliationResult(
        decision=ReconciliationDecision.CREATE,
        original_intent=intent, reason='no_intention_today',
    )


def _reconcile_prayer(user, enriched_action) -> ReconciliationResult:
    """Reconcile log_prayer against existing prayers with same title."""
    intent = enriched_action.intent_type
    params = enriched_action.parameters
    title = params.get('title', params.get('request', ''))

    if not title:
        return ReconciliationResult(
            decision=ReconciliationDecision.CREATE,
            original_intent=intent, reason='no_title',
        )

    try:
        from apps.faith.models import PrayerRequest
        existing = PrayerRequest.objects.filter(
            user=user, title__iexact=title.strip(), status='active',
        ).first()
    except (ImportError, Exception):
        return ReconciliationResult(
            decision=ReconciliationDecision.CREATE,
            original_intent=intent, reason='query_failed',
        )

    if existing:
        _log_decision(intent, title, existing.title, 1.0, 'SKIP', 'prayer_exists')
        return ReconciliationResult(
            decision=ReconciliationDecision.SKIP,
            original_intent=intent, confidence=1.0,
            matched_object={'model': 'PrayerRequest', 'id': existing.id, 'title': existing.title, 'time': None},
            skip_message=f'You already have an active prayer request "{existing.title}".',
            reason='prayer_already_exists',
        )

    return ReconciliationResult(
        decision=ReconciliationDecision.CREATE,
        original_intent=intent, reason='no_existing_prayer',
    )


def _reconcile_habit(user, enriched_action) -> ReconciliationResult:
    """Reconcile log_habit against same-day habit entries."""
    intent = enriched_action.intent_type
    params = enriched_action.parameters
    habit_name = params.get('habit_name', params.get('name', ''))
    today = _get_user_today(user)

    if not habit_name:
        return ReconciliationResult(
            decision=ReconciliationDecision.CREATE,
            original_intent=intent, reason='no_habit_name',
        )

    try:
        from apps.purpose.models import HabitEntry
        existing = HabitEntry.objects.filter(
            user=user, date=today, habit__name__iexact=habit_name.strip(),
        ).exists()
    except (ImportError, Exception):
        return ReconciliationResult(
            decision=ReconciliationDecision.CREATE,
            original_intent=intent, reason='query_failed',
        )

    if existing:
        _log_decision(intent, habit_name, habit_name, 1.0, 'SKIP', 'already_logged')
        return ReconciliationResult(
            decision=ReconciliationDecision.SKIP,
            original_intent=intent, confidence=1.0,
            matched_object={'model': 'HabitEntry', 'id': None, 'title': habit_name, 'time': str(today)},
            skip_message=f'"{habit_name}" is already logged for today.',
            reason='habit_already_logged',
        )

    return ReconciliationResult(
        decision=ReconciliationDecision.CREATE,
        original_intent=intent, reason='no_existing_today',
    )


def _reconcile_journal(user, enriched_action) -> ReconciliationResult:
    """Reconcile create_journal_entry — journals allow multiple per day, so just CREATE."""
    return ReconciliationResult(
        decision=ReconciliationDecision.CREATE,
        original_intent=enriched_action.intent_type,
        reason='journals_allow_multiple',
    )


def _reconcile_reminder(user, enriched_action) -> ReconciliationResult:
    """Reconcile add_reminder against existing reminders with same title/time."""
    intent = enriched_action.intent_type
    params = enriched_action.parameters
    title = params.get('title', params.get('message', ''))

    if not title:
        return ReconciliationResult(
            decision=ReconciliationDecision.CREATE,
            original_intent=intent, reason='no_title',
        )

    # Reminders are typically unique; just pass through to CRUD gate
    return ReconciliationResult(
        decision=ReconciliationDecision.CREATE,
        original_intent=intent, reason='reminders_passthrough',
    )


# ── Intent Transformation ────────────────────────────────────────────

def _build_task_mutate_params(existing_task, create_params: dict) -> dict:
    """Transform create_task params into mutate_task params."""
    mutate_params = {
        'action': 'update',
        'task_query': existing_task.title,  # Exact match via resolver tier 1
    }
    if create_params.get('scheduled_time'):
        mutate_params['new_scheduled_time'] = create_params['scheduled_time']
    if create_params.get('end_time'):
        mutate_params['new_end_time'] = create_params['end_time']
    if create_params.get('due_date'):
        mutate_params['new_due_date'] = create_params['due_date']
    # Preserve internal orchestrator keys
    for k, v in create_params.items():
        if k.startswith('_'):
            mutate_params[k] = v
    return mutate_params


def _build_event_mutate_params(existing_event, create_params: dict, user) -> dict:
    """Transform create_event params into mutate_calendar_event params."""
    import hashlib
    from django.utils import timezone as dj_tz

    idem_key = hashlib.sha256(
        f"reconcile-{user.id}-{existing_event.id}-{dj_tz.now().isoformat()}".encode()
    ).hexdigest()[:32]

    try:
        from apps.core.utils import get_current_local_datetime
        user_now = get_current_local_datetime(user)
        tz_str = str(user_now.tzinfo)
    except Exception:
        tz_str = 'America/Chicago'

    mutate_params = {
        'action': 'update',
        'event_id': existing_event.id,
        'idempotency_key': f'reconcile-{idem_key}',
        'timezone': tz_str,
    }
    if create_params.get('start_time'):
        mutate_params['start_time'] = create_params['start_time']
    if create_params.get('end_time'):
        mutate_params['end_time'] = create_params['end_time']
    if create_params.get('start_date'):
        mutate_params['start_date'] = create_params['start_date']
    for k, v in create_params.items():
        if k.startswith('_'):
            mutate_params[k] = v
    return mutate_params


# ── Structured Logging ───────────────────────────────────────────────

def _log_decision(intent, input_val, matched, confidence, decision, reason):
    """Log a reconciliation decision in structured format."""
    msg = (
        f"[RECONCILE] intent={intent} input={input_val!r} "
        f"matched={matched!r} confidence={confidence:.2f} "
        f"decision={decision} reason={reason}"
    )
    if decision in ('CREATE',) and confidence < CONFIDENCE_MEDIUM:
        logger.debug(msg)
    else:
        logger.info(msg)


# ── Registry ─────────────────────────────────────────────────────────

ACTIVITY_RECONCILERS: Dict[str, Callable] = {
    # Life / Tasks
    'create_task': _reconcile_task,
    'create_routine_task': _reconcile_task,
    # Calendar
    'create_event': _reconcile_event,
    # Purpose
    'create_goal': _reconcile_goal,
    'set_intention': _reconcile_intention,
    # Faith
    'log_prayer': _reconcile_prayer,
    # Fitness
    'log_workout': _reconcile_workout,
    # Health logs (same-day dedup)
    'log_weight': _reconcile_health_log,
    'log_blood_pressure': _reconcile_health_log,
    'log_heart_rate': _reconcile_health_log,
    'log_glucose': _reconcile_health_log,
    'log_blood_oxygen': _reconcile_health_log,
    'log_body_measurement': _reconcile_health_log,
    # Intake (Medications)
    'take_medication': _reconcile_medicine,
    # Habits
    'log_habit': _reconcile_habit,
    # Journal
    'create_journal_entry': _reconcile_journal,
    # Reminders
    'add_reminder': _reconcile_reminder,
}


# ── Main Entry Point ─────────────────────────────────────────────────

def reconcile_activity(user, enriched_action) -> ReconciliationResult:
    """
    Check if a create/log intent duplicates an existing activity.

    Called between route_action() and the CRUD confirmation gate in the
    orchestrator pipeline. Only runs for intents registered in
    ACTIVITY_RECONCILERS. Unregistered intents get CREATE (passthrough).

    Args:
        user: Django User instance
        enriched_action: EnrichedAction from route_action()

    Returns:
        ReconciliationResult with decision and optionally redirected
        intent_type + params.
    """
    intent_type = enriched_action.intent_type
    reconciler = ACTIVITY_RECONCILERS.get(intent_type)

    if not reconciler:
        return ReconciliationResult(
            decision=ReconciliationDecision.CREATE,
            original_intent=intent_type,
            reason='no_reconciler_registered',
        )

    try:
        return reconciler(user, enriched_action)
    except Exception as e:
        logger.error(
            "[RECONCILE] Error for %s (user=%s): %s",
            intent_type, user.id, e, exc_info=True,
        )
        return ReconciliationResult(
            decision=ReconciliationDecision.CREATE,
            original_intent=intent_type,
            reason=f'reconciliation_error: {e}',
        )
