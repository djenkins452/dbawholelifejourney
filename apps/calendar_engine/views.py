"""
Calendar Engine Views — API endpoints + Dashboard.

No DRF — standard Django views returning JsonResponse.
"""

import datetime as dt
import json

from django.contrib.auth.mixins import LoginRequiredMixin
from django.db import transaction
from django.http import JsonResponse
from django.utils import timezone
from django.views import View
from django.views.generic import TemplateView

from apps.calendar_engine.utils.idempotency import compute_idempotency_key

from apps.help.mixins import HelpContextMixin

from .models import CalendarEvent, CalendarOverrideLog, RecurrenceRule
from .services import conflicts, metrics, suggestions
from .services.nlp_parse import parse_quick_add
from .services.projection import upsert_execution_block_for_task


# ──────────────────────────────────────────────────────────
# Helpers
# ──────────────────────────────────────────────────────────

def _event_to_dict(event):
    """Serialize a CalendarEvent to a dict for JSON response."""
    # Convert to local time so ISO date portion matches the user's calendar day
    local_start = timezone.localtime(event.start_dt)
    local_end = timezone.localtime(event.end_dt)
    return {
        'id': event.pk,
        'title': event.title,
        'description': event.description,
        'start_dt': local_start.isoformat(),
        'end_dt': local_end.isoformat(),
        'is_all_day': event.is_all_day,
        'event_kind': event.event_kind,
        'source_type': event.source_type,
        'source_id': event.source_id,
        'is_protected': event.is_protected,
        'status': event.status,
        'domain': event.domain.name if event.domain else None,
        'domain_color': event.domain.color if event.domain else '#6b7280',
        'duration_minutes': event.duration_minutes,
        'has_recurrence': hasattr(event, 'recurrence') and event.recurrence is not None,
    }


def _occurrence_to_dict(event, occ_start, occ_end):
    """Serialize a recurring occurrence to a dict."""
    local_start = timezone.localtime(occ_start)
    local_end = timezone.localtime(occ_end)
    return {
        'id': event.pk,
        'title': event.title,
        'description': event.description,
        'start_dt': local_start.isoformat(),
        'end_dt': local_end.isoformat(),
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
    import logging
    logger = logging.getLogger(__name__)

    # Direct events
    direct = CalendarEvent.objects.filter(
        user=user,
        status=CalendarEvent.STATUS_SCHEDULED,
        start_dt__lt=range_end,
        end_dt__gt=range_start,
    ).select_related('domain')

    result = [_event_to_dict(e) for e in direct]

    # Build a set of (title_lower, date_str) from direct events for
    # deduplication against recurring occurrences.  When a manually-created
    # or source-projected event already exists on a given day, a recurring
    # occurrence for the same title on the same day is redundant.
    direct_title_dates = set()
    for evt_dict in result:
        title_lower = evt_dict['title'].strip().lower()
        date_str = evt_dict['start_dt'][:10]  # YYYY-MM-DD from ISO
        direct_title_dates.add((title_lower, date_str))

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
            occ_dict = _occurrence_to_dict(event, occ_start, occ_end)
            # Skip if a direct event already covers this title+date
            occ_title = occ_dict['title'].strip().lower()
            occ_date = occ_dict['start_dt'][:10]
            if (occ_title, occ_date) in direct_title_dates:
                logger.debug(
                    "Skipping recurring occurrence '%s' on %s — "
                    "direct event already exists",
                    occ_dict['title'], occ_date,
                )
                continue
            result.append(occ_dict)

    # Availability blocks (calendar-native planning constraints). Projected into
    # the same event stream, flagged event_kind='availability' so the client
    # renders them as a constraints lane — never a task/commitment. They are NOT
    # CalendarEvents, so the ~49 CalendarEvent consumers never see them.
    from apps.calendar_engine.models import AvailabilityBlock
    _AVAIL_COLOR = {'unavailable': '#94a3b8', 'available': '#34d399'}
    for block in AvailabilityBlock.active(user):
        for occ_start, occ_end in block.get_occurrences(range_start, range_end):
            local_start = timezone.localtime(occ_start)
            local_end = timezone.localtime(occ_end)
            result.append({
                'id': block.pk,
                'title': block.label,
                'description': '',
                'start_dt': local_start.isoformat(),
                'end_dt': local_end.isoformat(),
                'is_all_day': False,
                'event_kind': 'availability',
                'source_type': 'availability',
                'source_id': str(block.pk),
                'is_protected': False,
                'status': 'scheduled',
                'domain': block.get_kind_display(),
                'domain_color': _AVAIL_COLOR.get(block.kind, '#94a3b8'),
                'duration_minutes': int((local_end - local_start).total_seconds() / 60),
                'is_available': block.kind == AvailabilityBlock.KIND_AVAILABLE,
                'is_occurrence': block.is_recurring,
            })

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

# Rhythm sources — recurring life-habit items (the heartbeat of the day), shown
# in "Today's Rhythms" grouped by daypart, NOT on the hard commitment timeline.
_RHYTHM_SOURCES = {
    CalendarEvent.SOURCE_HABIT,
    CalendarEvent.SOURCE_MEDICINE_SCHEDULE,
    CalendarEvent.SOURCE_FAITH_ROUTINE,
    CalendarEvent.SOURCE_WORKOUT_SCHEDULE,
}


def _fmt_time(local_dt):
    """12-hour label, e.g. '7:30 AM'."""
    return local_dt.strftime('%-I:%M %p')


def _fmt_hm(minutes):
    """'10h 30m' / '45m' / '2h'."""
    minutes = max(int(minutes), 0)
    h, m = divmod(minutes, 60)
    if h and m:
        return f"{h}h {m}m"
    if h:
        return f"{h}h"
    return f"{m}m"


def _merge_intervals(intervals):
    """Union of [(start, end)] aware-datetime intervals (merged, sorted)."""
    if not intervals:
        return []
    ordered = sorted(intervals, key=lambda p: p[0])
    merged = [list(ordered[0])]
    for s, e in ordered[1:]:
        if s <= merged[-1][1]:
            merged[-1][1] = max(merged[-1][1], e)
        else:
            merged.append([s, e])
    return [(s, e) for s, e in merged]


def _free_windows(busy, window_start, window_end):
    """Complement of merged busy intervals within [window_start, window_end]."""
    free = []
    cursor = window_start
    for s, e in _merge_intervals(busy):
        if e <= cursor:
            continue
        if s > cursor:
            free.append((cursor, min(s, window_end)))
        cursor = max(cursor, e)
        if cursor >= window_end:
            break
    if cursor < window_end:
        free.append((cursor, window_end))
    return [(s, e) for s, e in free if (e - s).total_seconds() >= 15 * 60]


def _waking_window(user, day):
    """(wake_dt, sleep_dt) for the day — from the operating blueprint if set,
    else 6:00 AM–10:00 PM. Crash-safe."""
    tz = timezone.get_current_timezone()
    wake, sleep = dt.time(6, 0), dt.time(22, 0)
    try:
        from apps.core.blueprint.models import PersonalOperatingBlueprint
        bp = PersonalOperatingBlueprint.objects.filter(user=user).first()
        if bp:
            wake = getattr(bp, 'recommended_wake_time', None) or wake
            sleep = getattr(bp, 'recommended_sleep_time', None) or sleep
    except Exception:
        pass
    return (
        timezone.make_aware(dt.datetime.combine(day, wake), tz),
        timezone.make_aware(dt.datetime.combine(day, sleep), tz),
    )


# ── The life-story composition (A Calendar View of Life) ──────────────────
# Domain palette (kept in sync with the calendar template's colors).
_LIFE_COLORS = {
    'faith': '#6a64cf', 'health': '#3f9d78', 'meal': '#c58524', 'work': '#79839a',
    'move': '#df6a4c', 'journal': '#8a6fce', 'water': '#3f9fc4', 'sleep': '#7b8496',
    'rel': '#cf5a86',
}

_WORK_MEETING_CUES = ('1:1', 'standup', 'stand-up', 'meeting', 'sync', 'review',
                      'client', 'interview', 'deadline', 'project', 'work', 'email')
_PERSONAL_CUES = ('dinner with', 'lunch with', 'breakfast with', 'coffee with',
                  'date night', 'date with', 'family night', 'family time',
                  'visit', 'call mom', 'call dad')


def _detect_person(title):
    """Extract a person's first name from a title ("… with Sarah", "Call Haley").

    Keyword is matched case-insensitively; the name must still be capitalized.
    """
    import re
    for pat in (r'\b[Ww]ith ([A-Z][a-zA-Z]+)', r'\b[Cc]all ([A-Z][a-zA-Z]+)',
                r'\b[Vv]isit ([A-Z][a-zA-Z]+)'):
        m = re.search(pat, title or '')
        if m:
            name = m.group(1)
            if name.lower() not in ('the', 'team', 'my', 'your', 'a', 'mom', 'dad'):
                return name
    return None


def _classify_moment(ev):
    """Return (domain_key, person_name|None) for a projected event.

    People-first: personal relationship moments (dinner with Heather, call Haley)
    classify as 'rel' so they read as human, not as tasks. A person in a work
    meeting keeps 'work' but still surfaces an avatar.
    """
    title = ev.get('title') or ''
    low = title.lower()
    dom = (ev.get('domain') or '').lower()
    src = ev.get('source_type') or ''
    person = _detect_person(title)

    def has(*ks):
        return any(k in low for k in ks)

    # Projected rhythm sources are unambiguous.
    if src == CalendarEvent.SOURCE_MEDICINE_SCHEDULE:
        return 'health', person
    if src == CalendarEvent.SOURCE_FAITH_ROUTINE:
        return 'faith', person
    if src == CalendarEvent.SOURCE_WORKOUT_SCHEDULE:
        return 'move', person

    is_work_meeting = has(*_WORK_MEETING_CUES)
    # 1. Personal relationships — warm, human.
    if dom in ('relationships', 'relationship', 'family') or has(*_PERSONAL_CUES) \
            or (person and not is_work_meeting):
        return 'rel', person
    # 2. Faith / movement / meals / etc.
    if has('prayer', 'bible', 'devotion', 'scripture', 'quiet time', 'reading plan'):
        return 'faith', person
    if has('workout', 'run', 'gym', 'exercise', 'lift', 'cardio', 'yoga', 'stretch', 'walk'):
        return 'move', person
    if has('breakfast', 'lunch', 'dinner', 'brunch', 'meal', 'snack', 'coffee'):
        return 'meal', person
    if has('water', 'hydrat'):
        return 'water', person
    if has('journal', 'reflect', 'gratitude'):
        return 'journal', person
    if has('medication', 'medicine', 'supplement', 'vitamin', 'pill', 'dose'):
        return 'health', person
    if has('sleep', 'bed', 'wind down', 'night reset', 'wake'):
        return 'sleep', person
    # 3. Work (may carry a person → avatar).
    if is_work_meeting or has('call'):
        return 'work', person
    if dom == 'faith':
        return 'faith', person
    if dom == 'health':
        return 'health', person
    return 'work', person


def _work_window(events):
    """(work_start, work_end) from today's unavailable 'work' availability block,
    or (None, None) if there isn't one."""
    starts, ends = [], []
    for e in events:
        if e.get('event_kind') == 'availability' and not e.get('is_available'):
            label = (e.get('title') or '').lower()
            if 'work' in label or 'office' in label:
                starts.append(dt.datetime.fromisoformat(e['start_dt']))
                ends.append(dt.datetime.fromisoformat(e['end_dt']))
    if starts:
        return min(starts), max(ends)
    return None, None


def _opening_line(current_name, next_moment):
    phase = {
        'Morning': 'Your morning is underway.',
        'Work': "You're in the workday.",
        'Day': "You're partway through the day.",
        'Evening': 'Into the evening now.',
        'Night': 'The day is winding down.',
    }.get(current_name, "Here's your day.")
    if next_moment and next_moment.get('time_label'):
        return f"{phase} Next — {next_moment['title']} at {next_moment['time_label']}."
    return phase


def _compose_life_day(user):
    """Compose today as a life story in chapters (Morning · Work · Evening · Night).

    Pure, bounded, request-path-safe (reads _get_events_in_range + arithmetic — no
    LLM, no rebuild). Everything meaningful that happens in time becomes a moment on
    the day's thread; due-with-no-time and availability stay off it.
    """
    tz = timezone.get_current_timezone()
    today = timezone.localdate()
    day_start = timezone.make_aware(dt.datetime.combine(today, dt.time.min), tz)
    day_end = timezone.make_aware(dt.datetime.combine(today, dt.time.max), tz)
    now = timezone.localtime()

    events = _get_events_in_range(user, day_start, day_end)
    work_start, work_end = _work_window(events)
    has_work = work_start is not None

    due = []
    moments = []  # timed life moments (not availability, not deadline markers)
    for e in events:
        if e.get('event_kind') == CalendarEvent.KIND_DEADLINE_MARKER:
            due.append(e)
            continue
        if e.get('event_kind') == 'availability':
            continue  # availability is context (Work chapter), never a moment
        start = dt.datetime.fromisoformat(e['start_dt'])
        end = dt.datetime.fromisoformat(e['end_dt'])
        domain_key, person = _classify_moment(e)
        if end <= now:
            state = 'lived'
        elif start <= now < end:
            state = 'now'
        else:
            state = 'upcoming'
        moments.append({
            '_start': start, '_end': end,
            'title': e['title'],
            'time_label': _fmt_time(start) if not e.get('is_all_day') else '',
            'domain': domain_key,
            'color': _LIFE_COLORS.get(domain_key, '#79839a'),
            'is_person': bool(person),
            'person_initial': person[0].upper() if person else '',
            'is_rel': domain_key == 'rel',
            'state': state,
            'source_type': e['source_type'],
            'source_id': e['source_id'],
            'event_id': e['id'],
        })
    moments.sort(key=lambda m: m['_start'])

    # Assign each moment to a chapter.
    def chapter_of(start):
        h = timezone.localtime(start).hour
        if has_work:
            if start < work_start:
                return 'Morning'
            if start < work_end:
                return 'Work'
            return 'Evening' if h < 21 else 'Night'
        if h < 12:
            return 'Morning'
        if h < 17:
            return 'Day'
        if h < 21:
            return 'Evening'
        return 'Night'

    order = ['Morning', 'Work', 'Day', 'Evening', 'Night']
    subs = {
        'Morning': 'before the day begins', 'Work': 'the workday',
        'Day': 'midday', 'Evening': 'back home', 'Night': 'winding down',
    }
    buckets = {name: [] for name in order}
    for m in moments:
        buckets[chapter_of(m['_start'])].append(m)

    current_chapter = chapter_of(now)
    next_moment = next((m for m in moments if m['state'] == 'upcoming'), None)
    if next_moment:
        next_moment['is_next'] = True

    chapters = []
    for name in order:
        items = buckets[name]
        is_work_ch = (name == 'Work' and has_work)
        if not items and not is_work_ch:
            continue
        here = is_work_ch and work_start <= now < work_end
        sub = subs[name]
        if is_work_ch:
            sub = f"{_fmt_time(work_start)} – {_fmt_time(work_end)}"
        # Insert the NOW marker into the current chapter (between lived & upcoming).
        rendered = []
        now_inserted = False
        for m in items:
            if (name == current_chapter and not now_inserted
                    and m['state'] != 'lived'):
                rendered.append({'is_now_marker': True, 'time_label': _fmt_time(now)})
                now_inserted = True
            rendered.append(m)
        if name == current_chapter and not now_inserted:
            rendered.append({'is_now_marker': True, 'time_label': _fmt_time(now)})
        chapters.append({
            'name': name, 'sub': sub, 'is_work': is_work_ch, 'here': here,
            'ambient': (f"Heads-down until {_fmt_time(work_end)}." if here else ''),
            'moments': rendered,
        })

    return {
        'date_serif': now.strftime('%A, %B %-d'),
        'clock': _fmt_time(now),
        'opening': _opening_line(current_chapter, next_moment),
        'chapters': chapters,
        'due': [{
            'title': (d['title'] or '').replace('Due: ', ''),
            'source_type': d['source_type'], 'source_id': d['source_id'],
            'event_id': d['id'],
        } for d in due],
        'has_anything': bool(chapters or due),
    }


class CalendarDashboardView(HelpContextMixin, LoginRequiredMixin, TemplateView):
    template_name = 'calendar_engine/dashboard.html'
    help_context_id = 'CALENDAR_MAIN'

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        user = self.request.user
        ctx['life'] = _compose_life_day(user)
        ctx['recommendations'] = suggestions.generate_suggestions(user)[:2]
        ctx['app_name'] = 'calendar_engine'
        return ctx


class MonthView(LoginRequiredMixin, TemplateView):
    """Full month calendar grid view."""
    template_name = 'calendar_engine/month.html'

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx['app_name'] = 'calendar_engine'

        # Determine which month to show
        year = self.request.GET.get('year')
        month = self.request.GET.get('month')
        today = timezone.localdate()

        if year and month:
            try:
                year = int(year)
                month = int(month)
            except (ValueError, TypeError):
                year, month = today.year, today.month
        else:
            year, month = today.year, today.month

        ctx['year'] = year
        ctx['month'] = month
        ctx['month_name'] = dt.date(year, month, 1).strftime('%B %Y')
        return ctx


class ManageEventsView(HelpContextMixin, LoginRequiredMixin, TemplateView):
    """Full CRUD management page for calendar events."""
    template_name = 'calendar_engine/manage.html'
    help_context_id = 'CALENDAR_MANAGE'

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx['app_name'] = 'calendar_engine'
        ctx['domains'] = list(
            CalendarEvent.objects.filter(user=self.request.user)
            .exclude(domain__isnull=True)
            .values_list('domain__name', flat=True)
            .distinct()
        )
        return ctx


class AllEventsView(LoginRequiredMixin, View):
    """GET /calendar/api/events/all/?status=scheduled&kind=&q="""

    def get(self, request):
        qs = CalendarEvent.objects.filter(
            user=request.user,
        ).select_related('domain').order_by('-start_dt')

        # Filters
        status = request.GET.get('status')
        if status:
            qs = qs.filter(status=status)

        kind = request.GET.get('kind')
        if kind:
            qs = qs.filter(event_kind=kind)

        source = request.GET.get('source')
        if source:
            qs = qs.filter(source_type=source)

        q = request.GET.get('q', '').strip()
        if q:
            qs = qs.filter(title__icontains=q)

        events = []
        for e in qs[:200]:
            d = _event_to_dict(e)
            d['has_recurrence'] = hasattr(e, 'recurrence') and RecurrenceRule.objects.filter(event=e).exists()
            events.append(d)

        return JsonResponse({'events': events})


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
            idempotency_key=compute_idempotency_key(
                request.user.id, title, start_dt, end_dt=end_dt,
            ),
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

        # Build update fields dict — parse datetimes where needed
        update_fields = {}
        for field in ['title', 'description', 'is_all_day', 'is_protected', 'status']:
            if field in data:
                update_fields[field] = data[field]

        if 'start_dt' in data:
            parsed = dt.datetime.fromisoformat(data['start_dt'])
            if not timezone.is_aware(parsed):
                parsed = timezone.make_aware(parsed, timezone.get_current_timezone())
            update_fields['start_dt'] = parsed

        if 'end_dt' in data:
            parsed = dt.datetime.fromisoformat(data['end_dt'])
            if not timezone.is_aware(parsed):
                parsed = timezone.make_aware(parsed, timezone.get_current_timezone())
            update_fields['end_dt'] = parsed

        if not update_fields:
            return JsonResponse(
                {'error': 'No changes detected in request'},
                status=409,
            )

        # Delegate to CalendarMutationService — single mutation path
        from apps.calendar_engine.services.calendar_mutation_service import (
            CalendarMutationService,
        )
        service = CalendarMutationService(request.user)
        result = service.update(pk, **update_fields)

        if not result.success:
            return JsonResponse({'error': result.error}, status=409)

        # Re-fetch for serialization with select_related
        verified = CalendarEvent.objects.select_related('domain').get(
            pk=pk, user=request.user,
        )
        return JsonResponse({'event': _event_to_dict(verified)})

    def delete(self, request, pk):
        event = self._get_event(request, pk)
        if not event:
            return JsonResponse({'error': 'Not found'}, status=404)

        # Delegate to CalendarMutationService — soft delete
        from apps.calendar_engine.services.calendar_mutation_service import (
            CalendarMutationService,
        )
        service = CalendarMutationService(request.user)
        result = service.delete(pk)

        if not result.success:
            return JsonResponse({'error': result.error}, status=409)

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

        # Capture original start for drift tracking
        original_start_dt = event.start_dt

        # Perform the move
        event.start_dt = new_start
        event.end_dt = new_end
        event.save()

        # Log schedule change to unified ExecutionLog
        if original_start_dt != new_start:
            from apps.core.drift.engine import DriftEngine
            DriftEngine.record_schedule_change(
                request.user, event, original_start_dt, new_start,
            )

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
            # Create or update execution block linked to goal
            domain = None
            try:
                from apps.purpose.models import LifeGoal
                goal = LifeGoal.objects.get(pk=int(source_id), user=request.user)
                domain = goal.domain
            except Exception:
                pass

            # Check for existing execution block for this goal
            existing = CalendarEvent.objects.filter(
                user=request.user,
                source_type=CalendarEvent.SOURCE_GOAL,
                source_id=str(source_id),
                event_kind=CalendarEvent.KIND_EXECUTION_BLOCK,
                status=CalendarEvent.STATUS_SCHEDULED,
                deleted_at__isnull=True,
            ).first()

            if existing:
                existing.start_dt = start_dt
                existing.end_dt = end_dt
                existing.domain = domain
                existing.save(update_fields=['start_dt', 'end_dt', 'domain', 'updated_at'])
                return JsonResponse({'event': _event_to_dict(existing)})

            event = CalendarEvent.objects.create(
                user=request.user,
                title=title,
                start_dt=start_dt,
                end_dt=end_dt,
                domain=domain,
                event_kind=CalendarEvent.KIND_EXECUTION_BLOCK,
                source_type=CalendarEvent.SOURCE_GOAL,
                source_id=str(source_id),
                idempotency_key=compute_idempotency_key(
                    request.user.id, title, start_dt, end_dt=end_dt,
                    source_type='goal', source_id=str(source_id),
                ),
            )
            return JsonResponse({'event': _event_to_dict(event)}, status=201)

        return JsonResponse({'error': 'Unsupported source_type'}, status=400)


class DeclineSuggestionView(LoginRequiredMixin, View):
    """
    POST /calendar/api/suggestions/decline/
    Body: {source_type, source_id}

    Records that the user declined a suggestion so it won't reappear today.
    """

    def post(self, request):
        from apps.calendar_engine.models import DeclinedSuggestion

        data = _parse_body(request)
        if not data:
            return JsonResponse({'error': 'Invalid JSON'}, status=400)

        source_type = data.get('source_type', '')
        source_id = data.get('source_id', '')

        if not source_type or not source_id:
            return JsonResponse({'error': 'source_type and source_id required'}, status=400)

        today = timezone.localdate()
        DeclinedSuggestion.objects.get_or_create(
            user=request.user,
            source_type=source_type,
            source_id=source_id,
            declined_date=today,
        )

        return JsonResponse({'status': 'declined'})


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
            idempotency_key=compute_idempotency_key(
                request.user.id, parsed['title'], start_dt, end_dt=end_dt,
            ),
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


# ──────────────────────────────────────────────────────────
# Month Data API
# ──────────────────────────────────────────────────────────

# ──────────────────────────────────────────────────────────
# Availability Blocks (calendar-native planning constraints)
# ──────────────────────────────────────────────────────────

def _parse_iso_dt(value):
    """Parse an ISO datetime, making it aware in the current tz. None on failure."""
    if not value:
        return None
    try:
        parsed = dt.datetime.fromisoformat(value)
    except (TypeError, ValueError):
        return None
    if not timezone.is_aware(parsed):
        parsed = timezone.make_aware(parsed, timezone.get_current_timezone())
    return parsed


def _availability_to_dict(block):
    return {
        'id': block.pk,
        'label': block.label,
        'kind': block.kind,
        'start_dt': timezone.localtime(block.start_dt).isoformat(),
        'end_dt': timezone.localtime(block.end_dt).isoformat(),
        'frequency': block.frequency,
        'byweekday': block.byweekday,
        'interval': block.interval,
        'until_dt': timezone.localtime(block.until_dt).isoformat() if block.until_dt else None,
        'count': block.count,
        'is_recurring': block.is_recurring,
    }


class AvailabilityManageView(HelpContextMixin, LoginRequiredMixin, TemplateView):
    """Management page for Availability Blocks."""
    template_name = 'calendar_engine/availability.html'
    help_context_id = 'CALENDAR_AVAILABILITY'

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx['app_name'] = 'calendar_engine'
        return ctx


# Edit scopes for recurring availability blocks (Outlook-style).
_AV_EDITABLE = ('label', 'kind', 'frequency', 'byweekday', 'interval', 'count')


class AvailabilityListCreateView(LoginRequiredMixin, View):
    """GET  /calendar/api/availability/       — list active blocks
       POST /calendar/api/availability/       — create a block"""

    def get(self, request):
        from apps.calendar_engine.models import AvailabilityBlock
        blocks = [_availability_to_dict(b) for b in AvailabilityBlock.active(request.user)]
        return JsonResponse({'blocks': blocks})

    def post(self, request):
        from apps.calendar_engine.models import AvailabilityBlock

        data = _parse_body(request)
        if not data:
            return JsonResponse({'error': 'Invalid JSON'}, status=400)

        start_dt = _parse_iso_dt(data.get('start_dt'))
        end_dt = _parse_iso_dt(data.get('end_dt'))
        if not start_dt or not end_dt:
            return JsonResponse({'error': 'start_dt and end_dt required (ISO)'}, status=400)
        if end_dt <= start_dt:
            return JsonResponse({'error': 'end_dt must be after start_dt'}, status=400)

        kind = data.get('kind', AvailabilityBlock.KIND_UNAVAILABLE)
        if kind not in (AvailabilityBlock.KIND_AVAILABLE, AvailabilityBlock.KIND_UNAVAILABLE):
            return JsonResponse({'error': 'Invalid kind'}, status=400)

        block = AvailabilityBlock.objects.create(
            user=request.user,
            label=(data.get('label') or 'Availability').strip()[:200],
            kind=kind,
            start_dt=start_dt,
            end_dt=end_dt,
            frequency=data.get('frequency', ''),
            byweekday=data.get('byweekday', []),
            interval=data.get('interval', 1),
            until_dt=_parse_iso_dt(data.get('until_dt')),
            count=data.get('count'),
            timezone=request.user.preferences.timezone_iana,
        )
        return JsonResponse({'block': _availability_to_dict(block)}, status=201)


class AvailabilityDetailView(LoginRequiredMixin, View):
    """PATCH  /calendar/api/availability/<id>/  — update (scope: series|future|occurrence)
       DELETE /calendar/api/availability/<id>/  — delete (scope: series|future|occurrence)"""

    def _get_block(self, request, pk):
        from apps.calendar_engine.models import AvailabilityBlock
        try:
            return AvailabilityBlock.objects.get(pk=pk, user=request.user, deleted_at__isnull=True)
        except AvailabilityBlock.DoesNotExist:
            return None

    def patch(self, request, pk):
        block = self._get_block(request, pk)
        if not block:
            return JsonResponse({'error': 'Not found'}, status=404)

        data = _parse_body(request)
        if not data:
            return JsonResponse({'error': 'Invalid JSON'}, status=400)

        scope = data.get('scope', 'series')

        fields = {k: data[k] for k in _AV_EDITABLE if k in data}
        if 'start_dt' in data:
            fields['start_dt'] = _parse_iso_dt(data['start_dt'])
        if 'end_dt' in data:
            fields['end_dt'] = _parse_iso_dt(data['end_dt'])
        if 'until_dt' in data:
            fields['until_dt'] = _parse_iso_dt(data['until_dt'])

        if scope == 'occurrence':
            occ = _parse_iso_dt(data.get('occurrence_start'))
            if not occ:
                return JsonResponse({'error': 'occurrence_start required for occurrence scope'}, status=400)
            block.move_occurrence(occ, fields.get('start_dt') or block.start_dt, fields.get('end_dt'))
            return JsonResponse({'block': _availability_to_dict(block)})

        if scope == 'future':
            boundary = _parse_iso_dt(data.get('occurrence_start'))
            if not boundary:
                return JsonResponse({'error': 'occurrence_start required for future scope'}, status=400)
            new_block = block.split_future(boundary, **fields)
            return JsonResponse({'block': _availability_to_dict(new_block)})

        # series — edit the base block in place
        for k, v in fields.items():
            setattr(block, k, v)
        block.save()
        return JsonResponse({'block': _availability_to_dict(block)})

    def delete(self, request, pk):
        import datetime as _dt
        block = self._get_block(request, pk)
        if not block:
            return JsonResponse({'error': 'Not found'}, status=404)

        data = _parse_body(request) or {}
        scope = data.get('scope', 'series')
        occ = _parse_iso_dt(data.get('occurrence_start'))

        if scope == 'occurrence' and occ:
            block.cancel_occurrence(occ)
        elif scope == 'future' and occ:
            block.until_dt = occ - _dt.timedelta(seconds=1)
            block.save(update_fields=['until_dt', 'updated_at'])
        else:
            block.soft_delete()
        return JsonResponse({'status': 'deleted'})


class AvailabilityOccurrencesView(LoginRequiredMixin, View):
    """GET /calendar/api/availability/<id>/occurrences/?days=42

    Upcoming occurrences of a recurring block, so the management UI can act on a
    single occurrence (delete/move this one) with the exact occurrence start — the
    Outlook "edit this occurrence" flow without the user typing a timestamp.
    """

    def get(self, request, pk):
        from apps.calendar_engine.models import AvailabilityBlock
        try:
            block = AvailabilityBlock.objects.get(
                pk=pk, user=request.user, deleted_at__isnull=True)
        except AvailabilityBlock.DoesNotExist:
            return JsonResponse({'error': 'Not found'}, status=404)

        try:
            days = min(max(int(request.GET.get('days', 42)), 1), 180)
        except (ValueError, TypeError):
            days = 42

        tz = timezone.get_current_timezone()
        start = timezone.make_aware(
            dt.datetime.combine(timezone.localdate(), dt.time.min), tz)
        end = start + dt.timedelta(days=days)
        occ = [
            {
                'start_dt': timezone.localtime(s).isoformat(),
                'end_dt': timezone.localtime(e).isoformat(),
            }
            for s, e in block.get_occurrences(start, end)
        ]
        return JsonResponse({'occurrences': occ, 'is_recurring': block.is_recurring})


class MonthDataView(LoginRequiredMixin, View):
    """
    GET /calendar/api/month/?year=2026&month=2

    Returns all events for the given month (including days visible
    in the grid from adjacent months).
    """

    def get(self, request):
        import calendar

        today = timezone.localdate()
        try:
            year = int(request.GET.get('year', today.year))
            month = int(request.GET.get('month', today.month))
        except (ValueError, TypeError):
            year, month = today.year, today.month

        # First day of the month and last day
        first_day = dt.date(year, month, 1)
        last_day = dt.date(year, month, calendar.monthrange(year, month)[1])

        # Extend to cover the full grid (Sunday-start weeks)
        # Go back to the Sunday at or before the first day
        grid_start = first_day - dt.timedelta(days=first_day.weekday() + 1)
        if first_day.weekday() == 6:  # Sunday
            grid_start = first_day
        # Go forward to the Saturday at or after the last day
        grid_end = last_day + dt.timedelta(days=(6 - last_day.weekday()) % 7)
        if last_day.weekday() == 6:  # Sunday — need full week after
            grid_end = last_day + dt.timedelta(days=6)

        tz = timezone.get_current_timezone()
        range_start = timezone.make_aware(
            dt.datetime.combine(grid_start, dt.time.min), tz
        )
        range_end = timezone.make_aware(
            dt.datetime.combine(grid_end, dt.time.max), tz
        )

        events = _get_events_in_range(request.user, range_start, range_end)

        return JsonResponse({
            'events': events,
            'year': year,
            'month': month,
            'grid_start': grid_start.isoformat(),
            'grid_end': grid_end.isoformat(),
        })
