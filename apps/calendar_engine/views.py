"""
Calendar Engine Views — API endpoints + Dashboard.

No DRF — standard Django views returning JsonResponse.
"""

import datetime as dt
import json

from django.contrib.auth.mixins import LoginRequiredMixin
from django.http import JsonResponse
from django.utils import timezone
from django.views import View
from django.views.generic import TemplateView

from .models import CalendarEvent, CalendarOverrideLog, RecurrenceRule
from .services import conflicts, metrics, suggestions
from .services.nlp_parse import parse_quick_add
from .services.projection import upsert_execution_block_for_task


# ──────────────────────────────────────────────────────────
# Helpers
# ──────────────────────────────────────────────────────────

def _event_to_dict(event):
    """Serialize a CalendarEvent to a dict for JSON response."""
    return {
        'id': event.pk,
        'title': event.title,
        'description': event.description,
        'start_dt': event.start_dt.isoformat(),
        'end_dt': event.end_dt.isoformat(),
        'is_all_day': event.is_all_day,
        'event_kind': event.event_kind,
        'source_type': event.source_type,
        'source_id': event.source_id,
        'is_protected': event.is_protected,
        'status': event.status,
        'domain': event.domain.name if event.domain else None,
        'domain_color': event.domain.color if event.domain else '#6b7280',
        'duration_minutes': event.duration_minutes,
    }


def _occurrence_to_dict(event, occ_start, occ_end):
    """Serialize a recurring occurrence to a dict."""
    return {
        'id': event.pk,
        'title': event.title,
        'description': event.description,
        'start_dt': occ_start.isoformat(),
        'end_dt': occ_end.isoformat(),
        'is_all_day': event.is_all_day,
        'event_kind': event.event_kind,
        'source_type': event.source_type,
        'source_id': event.source_id,
        'is_protected': event.is_protected,
        'status': event.status,
        'domain': event.domain.name if event.domain else None,
        'domain_color': event.domain.color if event.domain else '#6b7280',
        'duration_minutes': int((occ_end - occ_start).total_seconds() / 60),
        'is_occurrence': True,
    }


def _get_events_in_range(user, range_start, range_end):
    """Get all events (including recurring occurrences) in a date range."""
    # Direct events
    direct = CalendarEvent.objects.filter(
        user=user,
        status=CalendarEvent.STATUS_SCHEDULED,
        start_dt__lt=range_end,
        end_dt__gt=range_start,
    ).select_related('domain')

    result = [_event_to_dict(e) for e in direct]

    # Recurring event occurrences
    recurring = CalendarEvent.objects.filter(
        user=user,
        status=CalendarEvent.STATUS_SCHEDULED,
        recurrence__isnull=False,
    ).select_related('domain', 'recurrence').exclude(
        pk__in=direct.values_list('pk', flat=True),
    )

    for event in recurring:
        occurrences = event.recurrence.get_occurrences(range_start, range_end)
        for occ_start, occ_end in occurrences:
            result.append(_occurrence_to_dict(event, occ_start, occ_end))

    # Sort by start time
    result.sort(key=lambda e: e['start_dt'])
    return result


def _parse_body(request):
    """Parse JSON from request body."""
    try:
        return json.loads(request.body)
    except (json.JSONDecodeError, ValueError):
        return None


# ──────────────────────────────────────────────────────────
# Dashboard View
# ──────────────────────────────────────────────────────────

class CalendarDashboardView(LoginRequiredMixin, TemplateView):
    template_name = 'calendar_engine/dashboard.html'

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        user = self.request.user
        ctx['today_balance'] = metrics.get_today_balance(user)
        ctx['week_balance'] = metrics.get_week_balance(user)
        ctx['suggestions'] = suggestions.generate_suggestions(user)
        ctx['app_name'] = 'calendar_engine'
        return ctx


# ──────────────────────────────────────────────────────────
# Timeline APIs
# ──────────────────────────────────────────────────────────

class TodayTimelineView(LoginRequiredMixin, View):
    """GET /calendar/api/today/ — events for today."""

    def get(self, request):
        tz = timezone.get_current_timezone()
        today = timezone.localdate()
        start = timezone.make_aware(dt.datetime.combine(today, dt.time.min), tz)
        end = timezone.make_aware(dt.datetime.combine(today, dt.time.max), tz)

        events = _get_events_in_range(request.user, start, end)
        return JsonResponse({'events': events, 'date': today.isoformat()})


class RangeView(LoginRequiredMixin, View):
    """GET /calendar/api/range/?start=YYYY-MM-DD&end=YYYY-MM-DD"""

    def get(self, request):
        start_str = request.GET.get('start')
        end_str = request.GET.get('end')
        if not start_str or not end_str:
            return JsonResponse({'error': 'start and end params required'}, status=400)

        try:
            tz = timezone.get_current_timezone()
            start_date = dt.date.fromisoformat(start_str)
            end_date = dt.date.fromisoformat(end_str)
            start = timezone.make_aware(dt.datetime.combine(start_date, dt.time.min), tz)
            end = timezone.make_aware(dt.datetime.combine(end_date, dt.time.max), tz)
        except ValueError:
            return JsonResponse({'error': 'Invalid date format. Use YYYY-MM-DD.'}, status=400)

        events = _get_events_in_range(request.user, start, end)
        return JsonResponse({'events': events})


# ──────────────────────────────────────────────────────────
# Event CRUD
# ──────────────────────────────────────────────────────────

class EventCreateView(LoginRequiredMixin, View):
    """POST /calendar/api/events/ — create a manual event."""

    def post(self, request):
        data = _parse_body(request)
        if not data:
            return JsonResponse({'error': 'Invalid JSON'}, status=400)

        title = data.get('title', '').strip()
        if not title:
            return JsonResponse({'error': 'title is required'}, status=400)

        try:
            start_dt = dt.datetime.fromisoformat(data['start_dt'])
            end_dt = dt.datetime.fromisoformat(data['end_dt'])
        except (KeyError, ValueError):
            return JsonResponse({'error': 'start_dt and end_dt required in ISO format'}, status=400)

        if not timezone.is_aware(start_dt):
            start_dt = timezone.make_aware(start_dt, timezone.get_current_timezone())
        if not timezone.is_aware(end_dt):
            end_dt = timezone.make_aware(end_dt, timezone.get_current_timezone())

        # Resolve domain
        domain = None
        domain_slug = data.get('domain_slug')
        if domain_slug:
            from apps.purpose.models import LifeDomain
            domain = LifeDomain.objects.filter(slug=domain_slug, is_active=True).first()

        event = CalendarEvent.objects.create(
            user=request.user,
            title=title,
            description=data.get('description', ''),
            start_dt=start_dt,
            end_dt=end_dt,
            is_all_day=data.get('is_all_day', False),
            domain=domain,
            event_kind=data.get('event_kind', CalendarEvent.KIND_MANUAL),
            is_protected=data.get('is_protected', False),
        )

        # Create recurrence rule if provided
        recurrence = data.get('recurrence')
        if recurrence:
            RecurrenceRule.objects.create(
                event=event,
                frequency=recurrence.get('frequency', 'weekly'),
                byweekday=recurrence.get('byweekday', []),
                interval=recurrence.get('interval', 1),
                until_dt=dt.datetime.fromisoformat(recurrence['until_dt']) if recurrence.get('until_dt') else None,
                count=recurrence.get('count'),
            )

        return JsonResponse({'event': _event_to_dict(event)}, status=201)


class EventDetailView(LoginRequiredMixin, View):
    """
    GET /calendar/api/events/<id>/ — get event details
    PATCH /calendar/api/events/<id>/ — update event
    DELETE /calendar/api/events/<id>/ — delete event
    """

    def _get_event(self, request, pk):
        try:
            return CalendarEvent.objects.select_related('domain').get(
                pk=pk, user=request.user
            )
        except CalendarEvent.DoesNotExist:
            return None

    def get(self, request, pk):
        event = self._get_event(request, pk)
        if not event:
            return JsonResponse({'error': 'Not found'}, status=404)
        return JsonResponse({'event': _event_to_dict(event)})

    def patch(self, request, pk):
        event = self._get_event(request, pk)
        if not event:
            return JsonResponse({'error': 'Not found'}, status=404)

        data = _parse_body(request)
        if not data:
            return JsonResponse({'error': 'Invalid JSON'}, status=400)

        # Update allowed fields
        for field in ['title', 'description', 'is_all_day', 'is_protected', 'status']:
            if field in data:
                setattr(event, field, data[field])

        if 'start_dt' in data:
            event.start_dt = dt.datetime.fromisoformat(data['start_dt'])
            if not timezone.is_aware(event.start_dt):
                event.start_dt = timezone.make_aware(event.start_dt, timezone.get_current_timezone())
        if 'end_dt' in data:
            event.end_dt = dt.datetime.fromisoformat(data['end_dt'])
            if not timezone.is_aware(event.end_dt):
                event.end_dt = timezone.make_aware(event.end_dt, timezone.get_current_timezone())

        event.save()
        return JsonResponse({'event': _event_to_dict(event)})

    def delete(self, request, pk):
        event = self._get_event(request, pk)
        if not event:
            return JsonResponse({'error': 'Not found'}, status=404)
        event.delete()
        return JsonResponse({'status': 'deleted'})


# ──────────────────────────────────────────────────────────
# Drag/Drop Move with Writeback
# ──────────────────────────────────────────────────────────

class EventMoveView(LoginRequiredMixin, View):
    """
    POST /calendar/api/events/<id>/move/
    Body: {new_start_dt, new_end_dt, override: bool}

    Moves an event and writes back to source if applicable.
    """

    def post(self, request, pk):
        try:
            event = CalendarEvent.objects.select_related('domain').get(
                pk=pk, user=request.user
            )
        except CalendarEvent.DoesNotExist:
            return JsonResponse({'error': 'Not found'}, status=404)

        data = _parse_body(request)
        if not data:
            return JsonResponse({'error': 'Invalid JSON'}, status=400)

        try:
            new_start = dt.datetime.fromisoformat(data['new_start_dt'])
            new_end = dt.datetime.fromisoformat(data['new_end_dt'])
        except (KeyError, ValueError):
            return JsonResponse({'error': 'new_start_dt and new_end_dt required'}, status=400)

        if not timezone.is_aware(new_start):
            new_start = timezone.make_aware(new_start, timezone.get_current_timezone())
        if not timezone.is_aware(new_end):
            new_end = timezone.make_aware(new_end, timezone.get_current_timezone())

        override = data.get('override', False)

        # Check for protected conflicts
        if not override:
            conflict_result = conflicts.check_conflicts(
                request.user, new_start, new_end, exclude_event_id=event.pk
            )
            if conflict_result['conflict']:
                return JsonResponse(conflict_result, status=409)

        # If overriding, log it
        if override:
            conflicting = CalendarEvent.objects.filter(
                user=request.user,
                is_protected=True,
                status=CalendarEvent.STATUS_SCHEDULED,
                start_dt__lt=new_end,
                end_dt__gt=new_start,
            ).exclude(pk=event.pk)
            for c in conflicting:
                conflicts.log_override(
                    request.user, event, c,
                    reason=data.get('override_reason', 'User confirmed override')
                )

        # Perform the move
        event.start_dt = new_start
        event.end_dt = new_end
        event.save()

        # Writeback to source
        writeback_result = self._writeback(event, new_start, new_end)

        result = {'event': _event_to_dict(event)}
        if writeback_result:
            result['writeback'] = writeback_result

        return JsonResponse(result)

    def _writeback(self, event, new_start, new_end):
        """Write calendar changes back to the source object."""
        if event.source_type == CalendarEvent.SOURCE_TASK:
            return self._writeback_task(event, new_start, new_end)
        elif event.source_type == CalendarEvent.SOURCE_HABIT:
            return {'info': 'Habit schedule not modified. Single occurrence moved only.'}
        return None

    def _writeback_task(self, event, new_start, new_end):
        """Update task due_date when deadline marker is dragged."""
        from apps.life.models import Task

        try:
            task = Task.objects.get(pk=int(event.source_id), user=event.user)
        except (Task.DoesNotExist, ValueError):
            return {'error': 'Source task not found'}

        if event.event_kind == CalendarEvent.KIND_DEADLINE_MARKER:
            new_date = new_start.date()
            task.due_date = new_date
            task.save()
            return {'updated': 'task.due_date', 'new_value': new_date.isoformat()}
        elif event.event_kind == CalendarEvent.KIND_EXECUTION_BLOCK:
            return {'info': 'Execution block moved. Task dates unchanged.'}

        return None


# ──────────────────────────────────────────────────────────
# Smart Gap Suggestions
# ──────────────────────────────────────────────────────────

class GapSuggestionsView(LoginRequiredMixin, View):
    """POST /calendar/api/suggestions/gaps/"""

    def post(self, request):
        data = _parse_body(request) or {}
        date_str = data.get('date')
        date = None
        if date_str:
            try:
                date = dt.date.fromisoformat(date_str)
            except ValueError:
                pass

        result = suggestions.generate_suggestions(request.user, date)
        return JsonResponse({'suggestions': result})

    def get(self, request):
        result = suggestions.generate_suggestions(request.user)
        return JsonResponse({'suggestions': result})


class AcceptSuggestionView(LoginRequiredMixin, View):
    """
    POST /calendar/api/suggestions/accept/
    Body: {source_type, source_id, start_dt, end_dt, title}

    One-click accept creates an EXECUTION_BLOCK.
    """

    def post(self, request):
        data = _parse_body(request)
        if not data:
            return JsonResponse({'error': 'Invalid JSON'}, status=400)

        source_type = data.get('source_type')
        source_id = data.get('source_id')
        title = data.get('title', 'Execution Block')

        try:
            start_dt = dt.datetime.fromisoformat(data['start_dt'])
            end_dt = dt.datetime.fromisoformat(data['end_dt'])
        except (KeyError, ValueError):
            return JsonResponse({'error': 'start_dt and end_dt required'}, status=400)

        if not timezone.is_aware(start_dt):
            start_dt = timezone.make_aware(start_dt, timezone.get_current_timezone())
        if not timezone.is_aware(end_dt):
            end_dt = timezone.make_aware(end_dt, timezone.get_current_timezone())

        if source_type == 'task':
            from apps.life.models import Task
            try:
                task = Task.objects.get(pk=int(source_id), user=request.user)
                event = upsert_execution_block_for_task(task, start_dt, end_dt)
                return JsonResponse({'event': _event_to_dict(event)}, status=201)
            except (Task.DoesNotExist, ValueError):
                return JsonResponse({'error': 'Task not found'}, status=404)
        elif source_type == 'goal':
            # Create execution block linked to goal
            from apps.purpose.models import LifeDomain
            domain = None
            try:
                from apps.purpose.models import LifeGoal
                goal = LifeGoal.objects.get(pk=int(source_id), user=request.user)
                domain = goal.domain
            except Exception:
                pass

            event = CalendarEvent.objects.create(
                user=request.user,
                title=title,
                start_dt=start_dt,
                end_dt=end_dt,
                domain=domain,
                event_kind=CalendarEvent.KIND_EXECUTION_BLOCK,
                source_type=CalendarEvent.SOURCE_GOAL,
                source_id=str(source_id),
            )
            return JsonResponse({'event': _event_to_dict(event)}, status=201)

        return JsonResponse({'error': 'Unsupported source_type'}, status=400)


# ──────────────────────────────────────────────────────────
# Domain Balance Metrics
# ──────────────────────────────────────────────────────────

class DomainBalanceView(LoginRequiredMixin, View):
    """GET /calendar/api/metrics/balance/?period=today|week"""

    def get(self, request):
        period = request.GET.get('period', 'today')
        if period == 'week':
            balance = metrics.get_week_balance(request.user)
        else:
            balance = metrics.get_today_balance(request.user)
        return JsonResponse({'balance': balance, 'period': period})


# ──────────────────────────────────────────────────────────
# NLP Quick Add
# ──────────────────────────────────────────────────────────

class NLPCreateView(LoginRequiredMixin, View):
    """
    POST /calendar/api/nlp_create/
    Body: {text: "Bible Study Wednesdays 6pm-8pm"}
    """

    def post(self, request):
        data = _parse_body(request)
        if not data or not data.get('text'):
            return JsonResponse({'error': 'text field required'}, status=400)

        parsed = parse_quick_add(data['text'])

        # Determine start date
        tz = timezone.get_current_timezone()
        if parsed['date']:
            event_date = parsed['date']
        elif parsed['weekdays']:
            # Find next occurrence of first weekday
            today = timezone.localdate()
            target_weekday = parsed['weekdays'][0]
            days_ahead = (target_weekday - today.isoweekday()) % 7
            if days_ahead == 0:
                days_ahead = 7  # Next week
            event_date = today + dt.timedelta(days=days_ahead)
        else:
            event_date = timezone.localdate()

        start_time = parsed['start_time'] or dt.time(9, 0)
        end_time = parsed['end_time'] or dt.time(10, 0)

        start_dt = timezone.make_aware(
            dt.datetime.combine(event_date, start_time), tz
        )
        end_dt = timezone.make_aware(
            dt.datetime.combine(event_date, end_time), tz
        )

        # Handle end time crossing midnight
        if end_dt <= start_dt:
            end_dt += dt.timedelta(days=1)

        # Resolve domain
        domain = None
        if parsed['domain_slug']:
            from apps.purpose.models import LifeDomain
            domain = LifeDomain.objects.filter(
                slug=parsed['domain_slug'], is_active=True
            ).first()

        event = CalendarEvent.objects.create(
            user=request.user,
            title=parsed['title'],
            start_dt=start_dt,
            end_dt=end_dt,
            domain=domain,
            event_kind=CalendarEvent.KIND_MANUAL,
        )

        # Create recurrence if detected
        if parsed['is_recurring']:
            RecurrenceRule.objects.create(
                event=event,
                frequency=RecurrenceRule.FREQ_WEEKLY,
                byweekday=parsed['weekdays'] or [],
                interval=1,
            )

        return JsonResponse({
            'event': _event_to_dict(event),
            'parsed': {
                'title': parsed['title'],
                'start_time': str(parsed['start_time']),
                'end_time': str(parsed['end_time']),
                'weekdays': parsed['weekdays'],
                'is_recurring': parsed['is_recurring'],
                'domain_slug': parsed['domain_slug'],
            },
        }, status=201)
