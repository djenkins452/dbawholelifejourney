# ==============================================================================
# File: views.py
# Project: Whole Life Journey - Django 5.x Personal Wellness/Journaling App
# Description: Views for life module - projects, tasks, events, inventory, etc.
# Owner: Danny Jenkins (admin@wholelifejourney.com)
# Created: 2024-01-01
# Last Updated: 2025-12-31
# ==============================================================================
"""
Life Module Views

The daily operating layer of a person's life.
Calm, integrated, and quietly powerful.
"""

import json
import logging
import secrets
from datetime import timedelta

logger = logging.getLogger(__name__)

from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin
from django.db.models import Case, Count, Q, Sum, Value, When
from django.http import FileResponse, HttpResponse, HttpResponseRedirect, JsonResponse
from django.shortcuts import get_object_or_404, redirect
from django.urls import reverse_lazy, reverse
from django.utils import timezone
from django.utils.decorators import method_decorator
from django.views.decorators.clickjacking import xframe_options_sameorigin
from django.views.generic import (
    CreateView,
    DeleteView,
    DetailView,
    ListView,
    TemplateView,
    UpdateView,
    View,
)

from apps.core.utils import get_user_today
from apps.help.mixins import HelpContextMixin

from apps.core.events.domain_events import safe_emit_event, EventTypes

from .models import (
    Project,
    Task,
    LifeEvent,
    InventoryItem,
    InventoryPhoto,
    MaintenanceLog,
    Pet,
    PetRecord,
    Recipe,
    RecipeBulkImportSession,
    RecipeBulkImportPhoto,
    Document,
    Routine,
    RoutineSchedule,
    SignificantEvent,
)
from .forms import RoutineForm, RoutineScheduleFormSet, SignificantEventForm


class LifeAccessMixin(LoginRequiredMixin):
    """Base mixin for Life module views."""
    pass


# Canonical location: apps.life.services.task_queries.refresh_stale_priorities
# Re-exported here for backward compatibility with existing call sites.
from apps.life.services.task_queries import refresh_stale_priorities as _refresh_stale_task_priorities  # noqa: F401


# =============================================================================
# Home / Dashboard
# =============================================================================

class LifeHomeView(HelpContextMixin, LifeAccessMixin, TemplateView):
    """
    Life module dashboard.
    A calm overview of what matters today.
    """
    template_name = "life/home.html"
    help_context_id = "LIFE_HOME"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        user = self.request.user
        from apps.core.utils import get_user_today
        today = get_user_today(user)

        # Refresh stale priorities so tasks move Now/Soon/Someday correctly
        _refresh_stale_task_priorities(user)

        # Active projects
        context['active_projects'] = Project.objects.filter(
            user=user,
            status='active'
        ).order_by('priority', '-updated_at')[:5]

        # Tasks by priority
        context['now_tasks'] = Task.objects.filter(
            user=user,
            completion_status='pending',
            priority='now'
        )[:5]

        context['soon_tasks'] = Task.objects.filter(
            user=user,
            completion_status='pending',
            priority='soon'
        )[:5]

        # Upcoming events (next 7 days)
        week_ahead = today + timezone.timedelta(days=7)
        context['upcoming_events'] = LifeEvent.objects.filter(
            user=user,
            start_date__gte=today,
            start_date__lte=week_ahead
        ).order_by('start_date', 'start_time')[:5]

        # Today's events
        context['todays_events'] = LifeEvent.objects.filter(
            user=user,
            start_date=today
        ).order_by('start_time')

        # Quick stats
        context['stats'] = {
            'active_projects': Project.objects.filter(user=user, status='active').count(),
            'pending_tasks': Task.objects.filter(user=user, completion_status='pending').count(),
            'completed_tasks': Task.objects.filter(user=user, completion_status='completed').count(),
            'inventory_items': InventoryItem.objects.filter(user=user).count(),
            'pets': Pet.objects.filter(user=user, is_active=True).count(),
            'maintenance_logs': MaintenanceLog.objects.filter(user=user).count(),
            'recipes': Recipe.objects.filter(user=user).count(),
        }

        # Overdue tasks
        context['overdue_tasks'] = Task.objects.filter(
            user=user,
            completion_status='pending',
            due_date__lt=today
        ).count()

        # User's today for template date comparisons
        context['user_today'] = today

        # AI insight — engine-first: read latest PIE insight (no OpenAI)
        # Dismiss stale task_due_today insights if referenced tasks changed
        try:
            from apps.core.ai_insights.models import Insight
            from apps.life.services.task_queries import TaskQueries

            stale_insights = Insight.objects.filter(
                user=user,
                insight_type='task_due_today',
                status='new',
            )
            for insight in stale_insights:
                evidence = insight.evidence or {}
                original_ids = sorted(
                    t['task_id'] for t in evidence.get('tasks', [])
                )
                if not original_ids:
                    continue
                current_ids = sorted(
                    TaskQueries.pending(user).filter(
                        id__in=original_ids, due_date=today,
                    ).values_list('id', flat=True)
                )
                # Dismiss if any referenced task was completed/moved
                if current_ids != original_ids:
                    insight.status = 'dismissed'
                    insight.save(update_fields=['status', 'updated_at'])
        except Exception:
            pass  # Validation is best-effort

        from apps.core.ai_insights.services import get_module_insight
        context['ai_insight'] = get_module_insight(user, 'life')
        context['ai_enabled'] = getattr(user.preferences, 'ai_enabled', False)

        return context


# =============================================================================
# Projects
# =============================================================================

class ProjectListView(LifeAccessMixin, ListView):
    """List all projects."""
    model = Project
    template_name = "life/project_list.html"
    context_object_name = "projects"

    def get_queryset(self):
        queryset = Project.objects.filter(user=self.request.user)

        # Filter by status
        status = self.request.GET.get('status')
        if status:
            queryset = queryset.filter(status=status)
        else:
            # Default: show active and paused
            queryset = queryset.filter(status__in=['active', 'paused'])

        # Filter by priority
        priority = self.request.GET.get('priority')
        if priority:
            queryset = queryset.filter(priority=priority)

        return queryset.annotate(
            task_total=Count('tasks'),
            task_done=Count('tasks', filter=Q(tasks__completion_status='completed'))
        ).order_by('priority', '-updated_at')

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['current_status'] = self.request.GET.get('status', '')
        context['current_priority'] = self.request.GET.get('priority', '')
        return context


class ProjectDetailView(LifeAccessMixin, DetailView):
    """View a single project with its tasks."""
    model = Project
    template_name = "life/project_detail.html"
    context_object_name = "project"

    def get_queryset(self):
        return Project.objects.filter(user=self.request.user)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        from apps.core.utils import get_user_today
        # Custom ordering for priority: now=1, soon=2, someday=3
        priority_order = Case(
            When(priority='now', then=Value(1)),
            When(priority='soon', then=Value(2)),
            When(priority='someday', then=Value(3)),
            default=Value(4),
        )
        from django.db.models import F
        context['tasks'] = self.object.tasks.annotate(
            priority_order=priority_order
        ).order_by(
            'completion_status', 'priority_order',
            F('due_date').asc(nulls_last=True),
            F('scheduled_time').asc(nulls_last=True),
            '-created_at',
        )
        context['events'] = self.object.events.order_by('start_date')[:5]
        context['user_today'] = get_user_today(self.request.user)
        return context


class ProjectCreateView(LifeAccessMixin, CreateView):
    """Create a new project."""
    model = Project
    template_name = "life/project_form.html"
    fields = [
        'title', 'description', 'purpose', 'status', 'priority',
        'start_date', 'target_date', 'category', 'cover_image'
    ]

    def get_initial(self):
        """Set default start_date to user's local date."""
        initial = super().get_initial()
        initial['start_date'] = get_user_today(self.request.user)
        return initial

    def form_valid(self, form):
        form.instance.user = self.request.user
        messages.success(self.request, f"Project '{form.instance.title}' created.")
        return super().form_valid(form)


class ProjectUpdateView(LifeAccessMixin, UpdateView):
    """Edit a project."""
    model = Project
    template_name = "life/project_form.html"
    fields = [
        'title', 'description', 'purpose', 'status', 'priority',
        'start_date', 'target_date', 'completed_date', 'category',
        'cover_image', 'reflection'
    ]

    def get_queryset(self):
        return Project.objects.filter(user=self.request.user)

    def form_valid(self, form):
        messages.success(self.request, f"Project '{form.instance.title}' updated.")
        return super().form_valid(form)


class ProjectDeleteView(LifeAccessMixin, DeleteView):
    """Delete a project."""
    model = Project
    template_name = "life/project_confirm_delete.html"
    success_url = reverse_lazy('life:project_list')

    def get_queryset(self):
        return Project.objects.filter(user=self.request.user)

    def form_valid(self, form):
        messages.success(self.request, f"Project '{self.object.title}' deleted.")
        return super().form_valid(form)


# =============================================================================
# Tasks
# =============================================================================

class TaskListView(HelpContextMixin, LifeAccessMixin, ListView):
    """List all tasks with search and filtering capabilities."""
    model = Task
    template_name = "life/task_list.html"
    context_object_name = "tasks"
    help_context_id = "LIFE_TASKS"

    def get_queryset(self):
        from django.db.models import Q

        # Refresh stale priorities before filtering
        _refresh_stale_task_priorities(self.request.user)

        queryset = Task.objects.filter(user=self.request.user)

        # Search functionality - searches title, notes, and project name
        search_query = self.request.GET.get('q', '').strip()
        if search_query:
            queryset = queryset.filter(
                Q(title__icontains=search_query) |
                Q(notes__icontains=search_query) |
                Q(project__title__icontains=search_query)
            )

        # Filter by completion
        show = self.request.GET.get('show', 'active')
        if show == 'active':
            queryset = queryset.filter(completion_status='pending')
        elif show == 'completed':
            queryset = queryset.filter(completion_status='completed')
        elif show == 'skipped':
            queryset = queryset.filter(completion_status='skipped')

        # Filter by priority
        priority = self.request.GET.get('priority')
        if priority:
            queryset = queryset.filter(priority=priority)

        # Filter by project
        project_id = self.request.GET.get('project')
        if project_id:
            queryset = queryset.filter(project_id=project_id)

        from django.db.models import F
        return queryset.select_related('project').order_by(
            'completion_status',
            F('due_date').asc(nulls_last=True),
            F('scheduled_time').asc(nulls_last=True),
            '-created_at',
        )

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        from apps.core.utils import get_user_today
        from datetime import timedelta

        user = self.request.user
        user_today = get_user_today(user)
        tomorrow = user_today + timedelta(days=1)

        context['current_show'] = self.request.GET.get('show', 'active')
        context['current_priority'] = self.request.GET.get('priority', '')
        context['search_query'] = self.request.GET.get('q', '')
        context['user_today'] = user_today
        context['projects'] = Project.objects.filter(
            user=user, status='active'
        )

        # Total task counts for display
        all_tasks = Task.objects.filter(user=user)
        context['total_active_count'] = all_tasks.filter(completion_status='pending').count()
        context['total_completed_count'] = all_tasks.filter(completion_status='completed').count()
        context['total_skipped_count'] = all_tasks.filter(completion_status='skipped').count()
        context['total_all_count'] = all_tasks.count()

        # Time-horizon grouping for active tasks (pending only)
        # Uses centralized classify_time_status() — single source of truth.
        show = self.request.GET.get('show', 'active')
        if show == 'active':
            from apps.core.utils import classify_time_status, get_user_now
            user_now = get_user_now(user)

            tasks = list(context.get('tasks', self.get_queryset()))
            overdue = []
            today_tasks = []
            tomorrow_tasks = []
            future_tasks = []
            no_date_tasks = []

            for t in tasks:
                if t.completion_status != 'pending':
                    continue
                if t.due_date is None:
                    no_date_tasks.append(t)
                elif t.due_date < user_today:
                    overdue.append(t)
                elif t.due_date == user_today:
                    result = classify_time_status(
                        t.due_date, t.scheduled_time, user_now,
                        grace_minutes=getattr(t, 'grace_minutes', 0),
                    )
                    if result['status'] == 'overdue':
                        overdue.append(t)
                    else:
                        today_tasks.append(t)
                elif t.due_date == tomorrow:
                    tomorrow_tasks.append(t)
                else:
                    future_tasks.append(t)

            context['time_horizon_groups'] = [
                ('Overdue', 'overdue', overdue),
                ('Today', 'today', today_tasks),
                ('Tomorrow', 'tomorrow', tomorrow_tasks),
                ('Future', 'future', future_tasks),
                ('No Due Date', 'no-date', no_date_tasks),
            ]
            context['use_time_horizon'] = True

            # Next-up task ID from SAE for visual highlight
            try:
                from apps.core.ai_state.state_engine import get_module_state
                task_state = get_module_state(user, 'tasks') or {}
                next_up = task_state.get('next_up_task')
                context['next_up_task_id'] = next_up.get('id') if next_up else None
            except Exception:
                context['next_up_task_id'] = None
        else:
            context['use_time_horizon'] = False
            context['next_up_task_id'] = None

        return context


class TaskCreateView(LifeAccessMixin, CreateView):
    """Create a new task."""
    model = Task
    template_name = "life/task_form.html"
    fields = ['title', 'notes', 'project', 'effort', 'commitment_level', 'due_date', 'module', 'scheduled_time', 'scheduled_end_time', 'is_recurring', 'recurrence_pattern', 'start_date', 'end_date']

    def get_form(self, form_class=None):
        form = super().get_form(form_class)
        form.fields['project'].queryset = Project.objects.filter(
            user=self.request.user, status='active'
        )
        form.fields['scheduled_time'].required = False
        form.fields['scheduled_end_time'].required = False
        form.fields['module'].required = False
        # commitment_level has model default 'important', so form omission is OK
        if 'commitment_level' in form.fields:
            form.fields['commitment_level'].required = False
        return form

    def get_initial(self):
        """Pre-select project if passed via query parameter."""
        initial = super().get_initial()
        project_id = self.request.GET.get('project')
        if project_id:
            try:
                # Validate that the project belongs to the current user
                project = Project.objects.get(pk=project_id, user=self.request.user)
                initial['project'] = project
            except (Project.DoesNotExist, ValueError):
                pass
        return initial

    def form_valid(self, form):
        form.instance.user = self.request.user
        # Validate recurrence pattern if set
        if form.instance.is_recurring and form.instance.recurrence_pattern:
            from apps.life.services.recurrence import RecurrencePattern
            pattern = RecurrencePattern(form.instance.recurrence_pattern)
            if not pattern.pattern_type:
                form.add_error('recurrence_pattern', 'Invalid recurrence pattern.')
                return self.form_invalid(form)
        messages.success(self.request, f"Task '{form.instance.title}' created.")
        response = super().form_valid(form)
        safe_emit_event(EventTypes.TASK_CREATED, self.request.user, {
            "task_id": self.object.id, "source": "web_view",
        })
        return response

    def get_success_url(self):
        # If we came from a project page, return to that project
        project_id = self.request.GET.get('project')
        if project_id:
            try:
                project = Project.objects.get(pk=project_id, user=self.request.user)
                return reverse('life:project_detail', kwargs={'pk': project.pk})
            except (Project.DoesNotExist, ValueError):
                pass
        # Check for safe 'next' URL (with open redirect protection)
        from apps.core.utils import is_safe_redirect_url
        next_url = self.request.GET.get('next')
        if next_url and is_safe_redirect_url(next_url, self.request):
            return next_url
        return reverse_lazy('life:task_list')


class TaskUpdateView(LifeAccessMixin, UpdateView):
    """Edit a task."""
    model = Task
    template_name = "life/task_form.html"
    fields = ['title', 'notes', 'project', 'effort', 'commitment_level', 'due_date', 'module', 'scheduled_time', 'scheduled_end_time', 'progress_percentage', 'completion_status', 'is_recurring', 'recurrence_pattern', 'start_date', 'end_date']

    def get_queryset(self):
        return Task.objects.filter(user=self.request.user)

    def get_form(self, form_class=None):
        form = super().get_form(form_class)
        form.fields['project'].queryset = Project.objects.filter(
            user=self.request.user, status='active'
        )
        form.fields['scheduled_time'].required = False
        form.fields['scheduled_end_time'].required = False
        form.fields['module'].required = False
        form.fields['completion_status'].label = 'Status'
        return form

    def form_valid(self, form):
        # Validate recurrence pattern if set
        if form.instance.is_recurring and form.instance.recurrence_pattern:
            from apps.life.services.recurrence import RecurrencePattern
            pattern = RecurrencePattern(form.instance.recurrence_pattern)
            if not pattern.pattern_type:
                form.add_error('recurrence_pattern', 'Invalid recurrence pattern.')
                return self.form_invalid(form)
        return super().form_valid(form)

    def get_success_url(self):
        return reverse_lazy('life:task_list')


class TaskDeleteView(LifeAccessMixin, DeleteView):
    """Delete a task (single instance or entire recurring series)."""
    model = Task
    template_name = "life/task_confirm_delete.html"
    success_url = reverse_lazy('life:task_list')

    def get_queryset(self):
        return Task.objects.filter(user=self.request.user)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        task = self.get_object()
        context['is_series'] = task.is_recurring or task.is_routine
        return context

    def post(self, request, *args, **kwargs):
        task = self.get_object()
        delete_series = request.POST.get('delete_series') == 'true'

        if delete_series and (task.is_recurring or task.is_routine):
            # Delete ALL instances (active, completed, etc.) and stop regeneration
            from apps.life.services.recurrence import RecurrenceService
            RecurrenceService.delete_task_series_complete(task)
        else:
            task.soft_delete()

        return HttpResponseRedirect(self.success_url)


class TaskToggleView(LifeAccessMixin, View):
    """Toggle task completion status."""

    def post(self, request, pk):
        from django.http import JsonResponse

        task = get_object_or_404(Task, pk=pk, user=request.user)
        was_completed = task.is_completed

        try:
            if task.is_completed:
                task.mark_incomplete()
            else:
                task.mark_complete()
        except Exception as e:
            # Log error but don't fail - task state may have changed
            import logging
            logging.getLogger(__name__).error(f"Error toggling task {pk}: {e}")

        # Emit domain event only on completion (not un-completion)
        if not was_completed and task.is_completed:
            safe_emit_event(EventTypes.TASK_COMPLETED, request.user, {
                "task_id": task.id, "source": "web_view",
            })

        # Check if this is an AJAX request
        if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
            return JsonResponse({
                'success': True,
                'is_completed': task.is_completed,
                'completion_status': task.completion_status,
                'task_id': task.pk,
            })

        # Return to referring page or task list (with open redirect protection)
        from apps.core.utils import get_safe_redirect_url
        next_url = get_safe_redirect_url(request)

        # Add query param to show completion popup if task was just completed
        if not was_completed:
            separator = '&' if '?' in (next_url or '') else '?'
            if next_url:
                next_url = f"{next_url}{separator}task_completed=1"
                return redirect(next_url)
            return redirect(f"{reverse('life:task_list')}?task_completed=1")

        if next_url:
            return redirect(next_url)
        return redirect('life:task_list')


class TaskSkipView(LifeAccessMixin, View):
    """Mark a task as skipped."""

    def post(self, request, pk):
        from django.http import JsonResponse

        task = get_object_or_404(Task, pk=pk, user=request.user)

        try:
            task.mark_skipped()
        except Exception as e:
            import logging
            logging.getLogger(__name__).error(f"Error skipping task {pk}: {e}")

        # Emit domain event for skip (matches TASK_COMPLETED pattern)
        safe_emit_event(EventTypes.TASK_SKIPPED, request.user, {
            "task_id": task.id, "source": "web_view",
        })

        if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
            return JsonResponse({
                'success': True,
                'completion_status': task.completion_status,
                'task_id': task.pk,
            })

        from apps.core.utils import get_safe_redirect_url
        next_url = get_safe_redirect_url(request)
        if next_url:
            return redirect(next_url)
        return redirect('life:task_list')


# =============================================================================
# Calendar & Events
# =============================================================================

class CalendarView(LifeAccessMixin, TemplateView):
    """Monthly calendar view with grid display."""
    template_name = "life/calendar.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        from apps.core.utils import get_user_today
        import calendar as cal_module
        from datetime import date

        # Get month/year from query params or use current
        today = get_user_today(self.request.user)
        try:
            year = int(self.request.GET.get('year', today.year))
            month = int(self.request.GET.get('month', today.month))
            if month < 1 or month > 12:
                month = today.month
                year = today.year
        except (ValueError, TypeError):
            year = today.year
            month = today.month

        # Get events for this month
        _, last_day = cal_module.monthrange(year, month)

        start_date = date(year, month, 1)
        end_date = date(year, month, last_day)

        events = LifeEvent.objects.filter(
            user=self.request.user,
            start_date__gte=start_date,
            start_date__lte=end_date
        ).order_by('start_date', 'start_time')

        # Build dict mapping dates to events
        events_by_date = {}
        for event in events:
            date_key = event.start_date
            if date_key not in events_by_date:
                events_by_date[date_key] = []
            events_by_date[date_key].append(event)

        # Build calendar weeks (Sunday first)
        calendar = cal_module.Calendar(firstweekday=6)
        weeks = []
        for week in calendar.monthdayscalendar(year, month):
            week_data = []
            for day in week:
                if day == 0:
                    week_data.append({"day": None, "events": [], "is_today": False})
                else:
                    day_date = date(year, month, day)
                    week_data.append({
                        "day": day,
                        "date": day_date,
                        "events": events_by_date.get(day_date, []),
                        "is_today": day_date == today,
                    })
            weeks.append(week_data)

        # Calculate prev/next month
        if month == 1:
            prev_month = 12
            prev_year = year - 1
        else:
            prev_month = month - 1
            prev_year = year

        if month == 12:
            next_month = 1
            next_year = year + 1
        else:
            next_month = month + 1
            next_year = year

        context['weeks'] = weeks
        context['events'] = events  # Keep for list view fallback
        context['year'] = year
        context['month'] = month
        context['month_name'] = cal_module.month_name[month]
        context['prev_month'] = prev_month
        context['prev_year'] = prev_year
        context['next_month'] = next_month
        context['next_year'] = next_year
        context['today'] = today
        context['month_event_count'] = events.count()

        # Google Calendar status
        credential = get_user_google_credential(self.request.user)
        context['google_calendar_connected'] = credential is not None and credential.is_connected
        if context['google_calendar_connected']:
            context['google_calendar_name'] = credential.selected_calendar_name
            context['google_last_sync'] = credential.last_sync

        return context


class EventCreateView(LifeAccessMixin, CreateView):
    """Create a new event."""
    model = LifeEvent
    template_name = "life/event_form.html"
    fields = [
        'title', 'description', 'event_type', 'start_date', 'start_time',
        'end_date', 'end_time', 'is_all_day', 'location', 'project'
    ]

    def get_initial(self):
        """Set default start_date to user's local date."""
        initial = super().get_initial()
        user_today = get_user_today(self.request.user)
        initial['start_date'] = user_today
        initial['end_date'] = user_today
        return initial

    def get_form(self, form_class=None):
        form = super().get_form(form_class)
        form.fields['project'].queryset = Project.objects.filter(
            user=self.request.user, status='active'
        )
        return form

    def form_valid(self, form):
        form.instance.user = self.request.user
        messages.success(self.request, f"Event '{form.instance.title}' created.")
        return super().form_valid(form)

    def get_success_url(self):
        return reverse_lazy('life:calendar')


class EventUpdateView(LifeAccessMixin, UpdateView):
    """Edit an event."""
    model = LifeEvent
    template_name = "life/event_form.html"
    fields = [
        'title', 'description', 'event_type', 'start_date', 'start_time',
        'end_date', 'end_time', 'is_all_day', 'location', 'project'
    ]

    def get_queryset(self):
        return LifeEvent.objects.filter(user=self.request.user)

    def get_form(self, form_class=None):
        form = super().get_form(form_class)
        form.fields['project'].queryset = Project.objects.filter(
            user=self.request.user, status='active'
        )
        return form

    def get_success_url(self):
        return reverse_lazy('life:calendar')


class EventDeleteView(LifeAccessMixin, DeleteView):
    """Delete an event."""
    model = LifeEvent
    template_name = "life/event_confirm_delete.html"
    success_url = reverse_lazy('life:calendar')

    def get_queryset(self):
        return LifeEvent.objects.filter(user=self.request.user)


# =============================================================================
# Inventory
# =============================================================================

class InventoryListView(LifeAccessMixin, ListView):
    """List all inventory items."""
    model = InventoryItem
    template_name = "life/inventory_list.html"
    context_object_name = "items"

    def get_queryset(self):
        queryset = InventoryItem.objects.filter(user=self.request.user)

        # Filter by category
        category = self.request.GET.get('category')
        if category:
            queryset = queryset.filter(category=category)

        # Filter by location
        location = self.request.GET.get('location')
        if location:
            queryset = queryset.filter(location=location)

        # Search
        search = self.request.GET.get('q')
        if search:
            queryset = queryset.filter(
                Q(name__icontains=search) |
                Q(description__icontains=search) |
                Q(brand__icontains=search)
            )

        return queryset.order_by('category', 'name')

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        user_items = InventoryItem.objects.filter(user=self.request.user)

        # Get unique categories and locations for filters
        context['categories'] = user_items.values_list(
            'category', flat=True
        ).distinct().order_by('category')
        context['locations'] = user_items.values_list(
            'location', flat=True
        ).exclude(location='').distinct().order_by('location')

        # Total value
        context['total_value'] = user_items.aggregate(
            total=Sum('estimated_value')
        )['total'] or 0

        return context


class InventoryDetailView(LifeAccessMixin, DetailView):
    """View inventory item details."""
    model = InventoryItem
    template_name = "life/inventory_detail.html"
    context_object_name = "item"

    def get_queryset(self):
        return InventoryItem.objects.filter(user=self.request.user)


class InventoryCreateView(LifeAccessMixin, CreateView):
    """Add new inventory item."""
    model = InventoryItem
    template_name = "life/inventory_form.html"
    fields = [
        'name', 'description', 'category', 'location',
        'purchase_date', 'purchase_price', 'estimated_value',
        'condition', 'brand', 'model_number', 'serial_number',
        'warranty_expiration', 'warranty_info', 'notes'
    ]
    success_url = reverse_lazy('life:inventory_list')

    def get_initial(self):
        """Pre-populate form from query parameters (for AI Camera scan and barcode scan)."""
        initial = super().get_initial()
        # Support prefill from Camera Scan and Barcode Scan features
        if self.request.GET.get('name'):
            initial['name'] = self.request.GET.get('name')
        if self.request.GET.get('category'):
            initial['category'] = self.request.GET.get('category')
        if self.request.GET.get('brand'):
            initial['brand'] = self.request.GET.get('brand')
        if self.request.GET.get('model_number'):
            initial['model_number'] = self.request.GET.get('model_number')
        if self.request.GET.get('location'):
            initial['location'] = self.request.GET.get('location')
        if self.request.GET.get('description'):
            initial['description'] = self.request.GET.get('description')
        if self.request.GET.get('purchase_price'):
            try:
                initial['purchase_price'] = float(self.request.GET.get('purchase_price'))
            except (ValueError, TypeError):
                pass
        if self.request.GET.get('estimated_value'):
            try:
                initial['estimated_value'] = float(self.request.GET.get('estimated_value'))
            except (ValueError, TypeError):
                pass
        return initial

    def get_context_data(self, **kwargs):
        """Add barcode scan context to template."""
        context = super().get_context_data(**kwargs)
        # Check if user has AI consent for barcode scanning
        has_ai_consent = (
            hasattr(self.request.user, 'preferences') and
            self.request.user.preferences.ai_enabled and
            self.request.user.preferences.ai_data_consent
        )
        context['has_ai_consent'] = has_ai_consent
        context['barcode_from_scan'] = self.request.GET.get('barcode', '')
        context['source'] = self.request.GET.get('source', '')
        return context

    def form_valid(self, form):
        form.instance.user = self.request.user
        # Track if created via AI Camera scan or barcode scan
        source = self.request.GET.get('source')
        if source == 'ai_camera':
            form.instance.created_via = InventoryItem.CREATED_VIA_AI_CAMERA
        elif source == 'barcode_scan':
            form.instance.created_via = InventoryItem.CREATED_VIA_AI_CAMERA  # Reuse same constant

        # Save the item first
        response = super().form_valid(form)

        # Check if there's a scanned image to attach
        scan_image_key = self.request.GET.get('scan_image_key')
        if scan_image_key and scan_image_key in self.request.session:
            try:
                self._attach_scanned_image(self.object, scan_image_key)
            except Exception as e:
                logger.warning(f"Failed to attach scanned image: {e}")
                # Don't fail the whole operation if image attachment fails

        messages.success(self.request, f"'{form.instance.name}' added to inventory.")
        return response

    def _attach_scanned_image(self, item, scan_image_key):
        """Attach scanned image from session as InventoryPhoto."""
        import base64
        from django.core.files.base import ContentFile

        image_data = self.request.session.get(scan_image_key)
        if not image_data:
            return

        # Remove data URI prefix if present (e.g., "data:image/jpeg;base64,")
        if ',' in image_data:
            image_data = image_data.split(',', 1)[1]

        # Decode base64 to bytes
        image_bytes = base64.b64decode(image_data)

        # Create ContentFile for ImageField
        image_file = ContentFile(image_bytes, name=f'scan_{item.pk}.jpg')

        # Create InventoryPhoto
        InventoryPhoto.objects.create(
            item=item,
            image=image_file,
            caption='Captured via AI Camera Scan',
            is_primary=True
        )

        # Clean up session (image no longer needed)
        del self.request.session[scan_image_key]
        self.request.session.modified = True

        logger.info(f"Attached scanned image to inventory item {item.pk}")


class InventoryUpdateView(LifeAccessMixin, UpdateView):
    """Edit inventory item."""
    model = InventoryItem
    template_name = "life/inventory_form.html"
    fields = [
        'name', 'description', 'category', 'location',
        'purchase_date', 'purchase_price', 'estimated_value',
        'condition', 'brand', 'model_number', 'serial_number',
        'warranty_expiration', 'warranty_info', 'notes'
    ]

    def get_queryset(self):
        return InventoryItem.objects.filter(user=self.request.user)

    def get_success_url(self):
        return reverse_lazy('life:inventory_detail', kwargs={'pk': self.object.pk})


class InventoryDeleteView(LifeAccessMixin, DeleteView):
    """Delete inventory item."""
    model = InventoryItem
    template_name = "life/inventory_confirm_delete.html"
    success_url = reverse_lazy('life:inventory_list')

    def get_queryset(self):
        return InventoryItem.objects.filter(user=self.request.user)


# =============================================================================
# Inventory Photos
# =============================================================================

class InventoryPhotoCreateView(LifeAccessMixin, CreateView):
    """Add a photo to an inventory item."""
    model = InventoryPhoto
    template_name = "life/inventory_photo_form.html"
    fields = ['image', 'caption', 'is_primary']

    def dispatch(self, request, *args, **kwargs):
        self.item = get_object_or_404(InventoryItem, pk=kwargs['item_pk'], user=request.user)
        return super().dispatch(request, *args, **kwargs)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['item'] = self.item
        return context

    def form_valid(self, form):
        form.instance.item = self.item

        # If marked as primary, unset other primary photos
        if form.cleaned_data.get('is_primary'):
            InventoryPhoto.objects.filter(item=self.item, is_primary=True).update(is_primary=False)

        messages.success(self.request, "Photo added.")
        return super().form_valid(form)

    def get_success_url(self):
        return reverse('life:inventory_detail', kwargs={'pk': self.item.pk})


class InventoryPhotoDeleteView(LifeAccessMixin, DeleteView):
    """Delete an inventory photo."""
    model = InventoryPhoto
    template_name = "life/inventory_photo_confirm_delete.html"

    def get_queryset(self):
        return InventoryPhoto.objects.filter(item__user=self.request.user)

    def get_success_url(self):
        return reverse('life:inventory_detail', kwargs={'pk': self.object.item.pk})


class InventoryPhotoSetPrimaryView(LifeAccessMixin, View):
    """Set a photo as the primary photo for an item."""

    def post(self, request, pk):
        photo = get_object_or_404(InventoryPhoto, pk=pk, item__user=request.user)

        # Unset all other primary photos
        InventoryPhoto.objects.filter(item=photo.item, is_primary=True).update(is_primary=False)

        # Set this one as primary
        photo.is_primary = True
        photo.save()

        messages.success(request, "Primary photo updated.")
        return redirect('life:inventory_detail', pk=photo.item.pk)


# =============================================================================
# Pets
# =============================================================================

class PetListView(LifeAccessMixin, ListView):
    """List all pets."""
    model = Pet
    template_name = "life/pet_list.html"
    context_object_name = "pets"

    def get_queryset(self):
        return Pet.objects.filter(user=self.request.user)


class PetDetailView(LifeAccessMixin, DetailView):
    """View pet profile."""
    model = Pet
    template_name = "life/pet_detail.html"
    context_object_name = "pet"

    def get_queryset(self):
        return Pet.objects.filter(user=self.request.user)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['records'] = self.object.records.order_by('-date')[:10]
        return context


class PetCreateView(LifeAccessMixin, CreateView):
    """Add a new pet."""
    model = Pet
    template_name = "life/pet_form.html"
    fields = [
        'name', 'species', 'breed', 'birth_date', 'adoption_date',
        'color', 'weight', 'microchip_id', 'veterinarian', 'vet_phone',
        'photo', 'notes'
    ]

    def get_initial(self):
        """Pre-populate form from query parameters (for AI Camera scan)."""
        initial = super().get_initial()
        # Support prefill from Camera Scan feature
        if self.request.GET.get('name'):
            initial['name'] = self.request.GET.get('name')
        if self.request.GET.get('species'):
            initial['species'] = self.request.GET.get('species')
        if self.request.GET.get('breed'):
            initial['breed'] = self.request.GET.get('breed')
        return initial

    def form_valid(self, form):
        form.instance.user = self.request.user
        # Track if created via AI Camera scan
        source = self.request.GET.get('source')
        if source == 'ai_camera':
            form.instance.created_via = Pet.CREATED_VIA_AI_CAMERA
        try:
            response = super().form_valid(form)
            messages.success(self.request, f"Welcome, {form.instance.name}!")
            return response
        except Exception as e:
            logger.exception(f"Error saving pet: {e}")
            messages.error(self.request, "There was a problem saving your pet. Please try again.")
            return self.form_invalid(form)


class PetUpdateView(LifeAccessMixin, UpdateView):
    """Edit pet profile."""
    model = Pet
    template_name = "life/pet_form.html"
    fields = [
        'name', 'species', 'breed', 'birth_date', 'adoption_date',
        'color', 'weight', 'microchip_id', 'veterinarian', 'vet_phone',
        'photo', 'notes', 'is_active', 'passed_date'
    ]

    def get_queryset(self):
        return Pet.objects.filter(user=self.request.user)


class PetDeleteView(LifeAccessMixin, DeleteView):
    """Delete a pet."""
    model = Pet
    template_name = "life/pet_confirm_delete.html"
    success_url = reverse_lazy('life:pet_list')

    def get_queryset(self):
        return Pet.objects.filter(user=self.request.user)

    def form_valid(self, form):
        pet_name = self.object.name
        response = super().form_valid(form)
        messages.success(self.request, f"{pet_name} has been removed.")
        return response


# =============================================================================
# Pet Records
# =============================================================================

class PetRecordCreateView(LifeAccessMixin, CreateView):
    """Add a record to a pet."""
    model = PetRecord
    template_name = "life/pet_record_form.html"
    fields = ['record_type', 'date', 'title', 'description', 'cost', 'next_due_date']

    def dispatch(self, request, *args, **kwargs):
        self.pet = get_object_or_404(Pet, pk=kwargs['pet_pk'], user=request.user)
        return super().dispatch(request, *args, **kwargs)

    def get_initial(self):
        """Set default date to user's local date."""
        initial = super().get_initial()
        initial['date'] = get_user_today(self.request.user)
        return initial

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['pet'] = self.pet
        return context

    def form_valid(self, form):
        form.instance.pet = self.pet
        messages.success(self.request, f"Record added for {self.pet.name}.")
        return super().form_valid(form)

    def get_success_url(self):
        return reverse('life:pet_detail', kwargs={'pk': self.pet.pk})


class PetRecordUpdateView(LifeAccessMixin, UpdateView):
    """Edit a pet record."""
    model = PetRecord
    template_name = "life/pet_record_form.html"
    fields = ['record_type', 'date', 'title', 'description', 'cost', 'next_due_date']

    def get_queryset(self):
        return PetRecord.objects.filter(pet__user=self.request.user)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['pet'] = self.object.pet
        return context

    def get_success_url(self):
        return reverse('life:pet_detail', kwargs={'pk': self.object.pet.pk})


class PetRecordDeleteView(LifeAccessMixin, DeleteView):
    """Delete a pet record."""
    model = PetRecord
    template_name = "life/pet_record_confirm_delete.html"

    def get_queryset(self):
        return PetRecord.objects.filter(pet__user=self.request.user)

    def get_success_url(self):
        return reverse('life:pet_detail', kwargs={'pk': self.object.pet.pk})


# =============================================================================
# Recipes
# =============================================================================

class RecipeListView(LifeAccessMixin, ListView):
    """List all recipes."""
    model = Recipe
    template_name = "life/recipe_list.html"
    context_object_name = "recipes"

    def get_queryset(self):
        queryset = Recipe.objects.filter(user=self.request.user)

        # Filter by category
        category = self.request.GET.get('category')
        if category:
            queryset = queryset.filter(category=category)

        # Filter favorites
        if self.request.GET.get('favorites'):
            queryset = queryset.filter(is_favorite=True)

        # Search
        search = self.request.GET.get('q')
        if search:
            queryset = queryset.filter(
                Q(title__icontains=search) |
                Q(description__icontains=search) |
                Q(ingredients__icontains=search)
            )

        return queryset.order_by('-is_favorite', 'title')

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['categories'] = Recipe.objects.filter(
            user=self.request.user
        ).exclude(category='').values_list(
            'category', flat=True
        ).distinct().order_by('category')
        return context


class RecipeDetailView(LifeAccessMixin, DetailView):
    """View recipe details."""
    model = Recipe
    template_name = "life/recipe_detail.html"
    context_object_name = "recipe"

    def get_queryset(self):
        return Recipe.objects.filter(user=self.request.user)


class RecipeCreateView(LifeAccessMixin, CreateView):
    """Add a new recipe."""
    model = Recipe
    template_name = "life/recipe_form.html"
    fields = [
        'title', 'description', 'ingredients', 'instructions',
        'prep_time_minutes', 'cook_time_minutes', 'servings',
        'difficulty', 'category', 'source', 'source_url',
        'image', 'notes', 'is_favorite'
    ]

    def get_initial(self):
        """Pre-populate form from query parameters (for AI Camera scan)."""
        initial = super().get_initial()
        # Support prefill from Camera Scan feature
        if self.request.GET.get('name'):
            initial['title'] = self.request.GET.get('name')
        if self.request.GET.get('cuisine'):
            initial['category'] = self.request.GET.get('cuisine')
        if self.request.GET.get('course'):
            # Could map to category or description
            course = self.request.GET.get('course')
            if not initial.get('category'):
                initial['category'] = course.title() if course else ''
        return initial

    def form_valid(self, form):
        form.instance.user = self.request.user
        # Track if created via AI Camera scan
        source = self.request.GET.get('source')
        if source == 'ai_camera':
            form.instance.created_via = Recipe.CREATED_VIA_AI_CAMERA
        messages.success(self.request, f"Recipe '{form.instance.title}' saved.")
        return super().form_valid(form)


class RecipeUpdateView(LifeAccessMixin, UpdateView):
    """Edit a recipe."""
    model = Recipe
    template_name = "life/recipe_form.html"
    fields = [
        'title', 'description', 'ingredients', 'instructions',
        'prep_time_minutes', 'cook_time_minutes', 'servings',
        'difficulty', 'category', 'source', 'source_url',
        'image', 'notes', 'is_favorite'
    ]

    def get_queryset(self):
        return Recipe.objects.filter(user=self.request.user)


class RecipeDeleteView(LifeAccessMixin, DeleteView):
    """Delete a recipe."""
    model = Recipe
    template_name = "life/recipe_confirm_delete.html"
    success_url = reverse_lazy('life:recipe_list')

    def get_queryset(self):
        return Recipe.objects.filter(user=self.request.user)


class RecipeToggleFavoriteView(LifeAccessMixin, View):
    """Toggle recipe favorite status."""

    def post(self, request, pk):
        recipe = get_object_or_404(Recipe, pk=pk, user=request.user)
        recipe.is_favorite = not recipe.is_favorite
        recipe.save(update_fields=['is_favorite', 'updated_at'])
        return redirect('life:recipe_detail', pk=pk)


# =============================================================================
# Recipe Photo Import
# =============================================================================

class RecipeScanView(LifeAccessMixin, TemplateView):
    """
    Recipe photo import page.

    Upload a photo of a recipe → AI extracts details → review/edit → save.
    Single-page experience with JS-toggled upload and review states.
    """

    template_name = "life/recipe_scan.html"
    help_context_id = "RECIPE_SCAN"


class RecipeScanProcessView(LifeAccessMixin, View):
    """
    AJAX endpoint: process uploaded recipe photo through Vision AI.

    POST with multipart form data containing a 'photo' file.
    Returns JSON with extracted recipe fields.
    """

    def post(self, request):
        photo = request.FILES.get("photo")
        if not photo:
            return JsonResponse({"error": "No photo provided."}, status=400)

        # Validate file size (10MB max)
        if photo.size > 10 * 1024 * 1024:
            return JsonResponse({"error": "Photo exceeds 10MB limit."}, status=400)

        # Validate file type
        allowed_types = {"image/jpeg", "image/png", "image/webp", "image/heic"}
        content_type = photo.content_type or "image/jpeg"
        if content_type not in allowed_types:
            return JsonResponse(
                {"error": "Unsupported image type. Use JPEG, PNG, or WebP."},
                status=400,
            )

        # Read into memory and process
        raw_bytes = photo.read()

        from apps.life.services.recipe_photo_import import recipe_photo_import_service

        result = recipe_photo_import_service.extract_from_bytes(raw_bytes, content_type)

        # Service now returns list of recipes or dict with error
        if isinstance(result, dict) and "error" in result:
            return JsonResponse({"error": result["error"]}, status=422)

        # For single scan, take the first recipe
        if isinstance(result, list) and len(result) > 0:
            return JsonResponse({"status": "ok", "recipe": result[0]})

        return JsonResponse({"error": "No recipe found in image"}, status=422)


class RecipeScanConfirmView(LifeAccessMixin, View):
    """
    Create Recipe from scanned and user-reviewed data.

    POST with form fields + original photo from request.FILES.
    Creates Recipe, saves photo as image field, redirects to detail page.
    """

    def post(self, request):
        title = request.POST.get("title", "").strip()
        if not title:
            messages.error(request, "Recipe title is required.")
            return redirect("life:recipe_scan")

        recipe = Recipe(
            user=request.user,
            title=title,
            description=request.POST.get("description", "").strip(),
            ingredients=request.POST.get("ingredients", "").strip(),
            instructions=request.POST.get("instructions", "").strip(),
            category=request.POST.get("category", "").strip(),
            difficulty=request.POST.get("difficulty", "").strip(),
            source=request.POST.get("source", "").strip(),
            notes=request.POST.get("notes", "").strip(),
        )

        # Handle numeric fields
        for field in ("prep_time_minutes", "cook_time_minutes", "servings"):
            val = request.POST.get(field, "").strip()
            if val:
                try:
                    int_val = int(val)
                    if int_val > 0:
                        setattr(recipe, field, int_val)
                except (ValueError, TypeError):
                    pass

        # Save the photo as the recipe image
        photo = request.FILES.get("photo")
        if photo:
            recipe.image = photo

        recipe.save()

        messages.success(
            request, f'Recipe "{recipe.title}" imported from photo!'
        )
        return redirect("life:recipe_detail", pk=recipe.pk)


# =============================================================================
# Recipe Bulk Import
# =============================================================================

class RecipeBulkUploadView(LifeAccessMixin, TemplateView):
    """
    Bulk recipe photo upload page.

    Multi-file picker that saves photos → starts Celery task → redirects to review.
    """

    template_name = "life/recipe_bulk_upload.html"
    help_context_id = "RECIPE_BULK_IMPORT"


class RecipeBulkUploadProcessView(LifeAccessMixin, View):
    """
    POST endpoint: receive multiple recipe photos, create session, kick off Celery.

    Saves photos to RecipeBulkImportPhoto records, then dispatches
    the background processing task.
    """

    def post(self, request):
        photos = request.FILES.getlist("photos")
        if not photos:
            messages.error(request, "No photos selected.")
            return redirect("life:recipe_bulk_upload")

        if len(photos) > 50:
            messages.error(request, "Maximum 50 photos per batch.")
            return redirect("life:recipe_bulk_upload")

        allowed_types = {"image/jpeg", "image/png", "image/webp", "image/heic"}

        # Create session
        session = RecipeBulkImportSession.objects.create(
            user=request.user,
            total_photos=0,
        )

        saved_count = 0
        for photo in photos:
            # Validate size (10MB max)
            if photo.size > 10 * 1024 * 1024:
                continue

            # Validate type
            content_type = photo.content_type or "image/jpeg"
            if content_type not in allowed_types:
                continue

            photo_obj = RecipeBulkImportPhoto.objects.create(
                user=request.user,
                session=session,
                image=photo,
                original_filename=photo.name or "",
                photo_status='pending',
            )
            # Capture Cloudinary URL now (web process has Cloudinary configured;
            # Celery worker may not, causing storage mismatch).
            try:
                url = photo_obj.image.url
                if url and url.startswith('http'):
                    photo_obj.image_url = url
                    photo_obj.save(update_fields=['image_url'])
            except Exception:
                pass  # URL not critical if storage.open() works in worker
            saved_count += 1

        if saved_count == 0:
            session.delete()
            messages.error(
                request,
                "No valid photos found. Use JPEG, PNG, or WebP under 10MB."
            )
            return redirect("life:recipe_bulk_upload")

        session.total_photos = saved_count
        session.import_status = 'processing'
        session.save(update_fields=['total_photos', 'import_status', 'updated_at'])

        # Processing is driven by the review page JS (AJAX calls to
        # RecipeBulkProcessOneView) rather than Celery. This keeps
        # processing in the web process where all env vars are available.

        return redirect("life:recipe_bulk_review", session_id=session.pk)


class RecipeBulkReviewView(LifeAccessMixin, DetailView):
    """
    Review page for a bulk import session.

    Shows processing progress and extracted recipes for review/confirmation.
    """

    template_name = "life/recipe_bulk_review.html"
    context_object_name = "session"
    pk_url_kwarg = "session_id"

    def get_queryset(self):
        return RecipeBulkImportSession.objects.filter(user=self.request.user)

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        session = self.object
        ctx['photos'] = session.photos.all().select_related('recipe')
        ctx['extracted_photos'] = session.photos.filter(photo_status='extracted')
        ctx['confirmed_photos'] = session.photos.filter(photo_status='confirmed')
        ctx['failed_photos'] = session.photos.filter(photo_status='failed')
        ctx['pending_photos'] = session.photos.filter(
            photo_status__in=['pending', 'processing']
        )
        return ctx


class RecipeBulkProcessOneView(LifeAccessMixin, View):
    """
    AJAX endpoint: process a single photo through Vision AI.

    Called by the review page JS to process photos one-by-one in the
    web process. This avoids Celery worker env var issues since the
    web process has all required env vars (OpenAI, Cloudinary).
    """

    def post(self, request, session_id, photo_id):
        from apps.life.services.recipe_photo_import import recipe_photo_import_service

        try:
            session = RecipeBulkImportSession.objects.get(
                pk=session_id, user=request.user
            )
        except RecipeBulkImportSession.DoesNotExist:
            return JsonResponse({"error": "Session not found"}, status=404)

        try:
            photo = session.photos.get(pk=photo_id)
        except RecipeBulkImportPhoto.DoesNotExist:
            return JsonResponse({"error": "Photo not found"}, status=404)

        if photo.photo_status not in ('pending', 'processing', 'failed'):
            # Already processed
            return JsonResponse({
                "status": photo.photo_status,
                "title": photo.extracted_data.get('title', '') if photo.extracted_data else '',
                "photo_id": photo.pk,
            })

        photo.photo_status = 'processing'
        photo.save(update_fields=['photo_status', 'updated_at'])

        try:
            # Read image bytes
            raw_bytes = None
            try:
                photo.image.open('rb')
                raw_bytes = photo.image.read()
                photo.image.close()
            except (FileNotFoundError, OSError):
                pass

            if raw_bytes is None and photo.image_url:
                import urllib.request
                raw_bytes = urllib.request.urlopen(photo.image_url).read()

            if raw_bytes is None:
                raise FileNotFoundError(f"Could not read image for photo {photo.pk}")

            # Determine content type
            name = (photo.original_filename or photo.image.name).lower()
            if name.endswith('.png'):
                content_type = 'image/png'
            elif name.endswith('.webp'):
                content_type = 'image/webp'
            elif name.endswith('.heic'):
                content_type = 'image/heic'
            else:
                content_type = 'image/jpeg'

            result = recipe_photo_import_service.extract_from_bytes(raw_bytes, content_type)

            # Result is either a list of recipes or a dict with 'error'
            if isinstance(result, dict) and "error" in result:
                photo.photo_status = 'failed'
                photo.error_message = result["error"]
                photo.save(update_fields=['photo_status', 'error_message', 'updated_at'])
            elif isinstance(result, list) and len(result) > 0:
                # First recipe goes on this photo record
                first = result[0]
                photo.photo_status = 'extracted'
                photo.extracted_data = first
                photo.confidence = first.get('confidence', 0.5)
                photo.save(update_fields=[
                    'photo_status', 'extracted_data', 'confidence', 'updated_at',
                ])

                # Additional recipes from the same image → create new photo entries
                extra_photos = []
                for extra_recipe in result[1:]:
                    extra = RecipeBulkImportPhoto.objects.create(
                        user=request.user,
                        session=session,
                        image=photo.image,  # Same image
                        image_url=photo.image_url,
                        original_filename=photo.original_filename,
                        photo_status='extracted',
                        extracted_data=extra_recipe,
                        confidence=extra_recipe.get('confidence', 0.5),
                    )
                    extra_photos.append({
                        "photo_id": extra.pk,
                        "title": extra_recipe.get('title', ''),
                        "confidence": extra_recipe.get('confidence', 0.5),
                    })

                if extra_photos:
                    session.total_photos = session.photos.count()
                    session.save(update_fields=['total_photos', 'updated_at'])
            else:
                photo.photo_status = 'failed'
                photo.error_message = 'No recipes found in image'
                photo.save(update_fields=['photo_status', 'error_message', 'updated_at'])

            # Update session counts
            session.processed_count = session.photos.filter(
                photo_status__in=['extracted', 'confirmed']
            ).count()
            session.failed_count = session.photos.filter(photo_status='failed').count()
            session.save(update_fields=['processed_count', 'failed_count', 'updated_at'])

            # Build response
            response_data = {
                "status": photo.photo_status,
                "photo_id": photo.pk,
                "title": photo.extracted_data.get('title', '') if photo.extracted_data else '',
                "error": photo.error_message or '',
                "confidence": photo.confidence,
                "total_photos": session.total_photos,
            }
            # Include extra recipes so JS can add cards for them
            if isinstance(result, list) and len(result) > 1:
                response_data["extra_recipes"] = extra_photos

            return JsonResponse(response_data)

        except Exception as e:
            photo.photo_status = 'failed'
            photo.error_message = str(e)
            photo.save(update_fields=['photo_status', 'error_message', 'updated_at'])
            session.failed_count = session.photos.filter(photo_status='failed').count()
            session.save(update_fields=['failed_count', 'updated_at'])
            return JsonResponse({
                "status": "failed",
                "photo_id": photo.pk,
                "error": str(e),
            }, status=500)


class RecipeBulkStatusView(LifeAccessMixin, View):
    """
    AJAX endpoint: returns current processing progress for a session.

    Polled by the review page JS to update progress bar.
    """

    def get(self, request, session_id):
        try:
            session = RecipeBulkImportSession.objects.get(
                pk=session_id, user=request.user
            )
        except RecipeBulkImportSession.DoesNotExist:
            return JsonResponse({"error": "Session not found"}, status=404)

        photos = list(session.photos.values(
            'pk', 'photo_status', 'original_filename', 'confidence', 'error_message',
        ))

        # Include extracted_data title for display
        for p in photos:
            photo_obj = session.photos.get(pk=p['pk'])
            p['title'] = photo_obj.extracted_data.get('title', '') if photo_obj.extracted_data else ''
            if photo_obj.image:
                p['image_url'] = photo_obj.image.url
            else:
                p['image_url'] = ''

        # Remap photo_status → status for JS compatibility
        for p in photos:
            p['status'] = p.pop('photo_status')

        return JsonResponse({
            "status": session.import_status,
            "total": session.total_photos,
            "processed": session.processed_count,
            "failed": session.failed_count,
            "confirmed": session.confirmed_count,
            "progress_percent": session.progress_percent,
            "photos": photos,
        })


class RecipeBulkConfirmView(LifeAccessMixin, View):
    """
    POST endpoint: confirm one or more extracted recipes.

    Creates Recipe objects from the extracted data and original photos.
    Accepts JSON body with photo_ids list, or a single photo_id.
    """

    def post(self, request, session_id):
        try:
            session = RecipeBulkImportSession.objects.get(
                pk=session_id, user=request.user
            )
        except RecipeBulkImportSession.DoesNotExist:
            return JsonResponse({"error": "Session not found"}, status=404)

        try:
            data = json.loads(request.body)
        except (json.JSONDecodeError, ValueError):
            return JsonResponse({"error": "Invalid JSON"}, status=400)

        photo_ids = data.get('photo_ids', [])
        if not photo_ids:
            return JsonResponse({"error": "No photos specified"}, status=400)

        photos = session.photos.filter(
            pk__in=photo_ids, photo_status='extracted'
        )

        created = []
        for photo in photos:
            ext = photo.extracted_data
            if not ext or not ext.get('title'):
                continue

            recipe = Recipe(
                user=request.user,
                title=ext.get('title', ''),
                description=ext.get('description', ''),
                ingredients=ext.get('ingredients', ''),
                instructions=ext.get('instructions', ''),
                category=ext.get('category', ''),
                difficulty=ext.get('difficulty', ''),
                source=ext.get('source', ''),
                notes=ext.get('notes', ''),
            )

            # Numeric fields
            for field in ('prep_time_minutes', 'cook_time_minutes', 'servings'):
                val = ext.get(field)
                if val is not None:
                    try:
                        int_val = int(val)
                        if int_val > 0:
                            setattr(recipe, field, int_val)
                    except (ValueError, TypeError):
                        pass

            # Copy the uploaded image as the recipe image
            if photo.image:
                recipe.image = photo.image

            recipe.save()

            photo.photo_status = 'confirmed'
            photo.recipe = recipe
            photo.save(update_fields=['photo_status', 'recipe', 'updated_at'])

            created.append({
                'photo_id': photo.pk,
                'recipe_id': recipe.pk,
                'title': recipe.title,
            })

        # Update session confirmed count
        session.confirmed_count = session.photos.filter(photo_status='confirmed').count()
        session.save(update_fields=['confirmed_count', 'updated_at'])

        return JsonResponse({
            "status": "ok",
            "created": created,
            "confirmed_total": session.confirmed_count,
        })


class RecipeBulkConfirmAllView(LifeAccessMixin, View):
    """
    POST endpoint: confirm ALL extracted recipes in a session at once.
    """

    def post(self, request, session_id):
        try:
            session = RecipeBulkImportSession.objects.get(
                pk=session_id, user=request.user
            )
        except RecipeBulkImportSession.DoesNotExist:
            return JsonResponse({"error": "Session not found"}, status=404)

        photos = session.photos.filter(photo_status='extracted')
        created_count = 0

        for photo in photos:
            ext = photo.extracted_data
            if not ext or not ext.get('title'):
                continue

            recipe = Recipe(
                user=request.user,
                title=ext.get('title', ''),
                description=ext.get('description', ''),
                ingredients=ext.get('ingredients', ''),
                instructions=ext.get('instructions', ''),
                category=ext.get('category', ''),
                difficulty=ext.get('difficulty', ''),
                source=ext.get('source', ''),
                notes=ext.get('notes', ''),
            )

            for field in ('prep_time_minutes', 'cook_time_minutes', 'servings'):
                val = ext.get(field)
                if val is not None:
                    try:
                        int_val = int(val)
                        if int_val > 0:
                            setattr(recipe, field, int_val)
                    except (ValueError, TypeError):
                        pass

            if photo.image:
                recipe.image = photo.image

            recipe.save()

            photo.photo_status = 'confirmed'
            photo.recipe = recipe
            photo.save(update_fields=['photo_status', 'recipe', 'updated_at'])
            created_count += 1

        session.confirmed_count = session.photos.filter(photo_status='confirmed').count()
        session.save(update_fields=['confirmed_count', 'updated_at'])

        return JsonResponse({
            "status": "ok",
            "created_count": created_count,
            "confirmed_total": session.confirmed_count,
        })


# =============================================================================
# Maintenance Logs
# =============================================================================

class MaintenanceLogListView(LifeAccessMixin, ListView):
    """List all maintenance logs."""
    model = MaintenanceLog
    template_name = "life/maintenance_list.html"
    context_object_name = "logs"

    def get_queryset(self):
        queryset = MaintenanceLog.objects.filter(user=self.request.user)

        # Filter by type
        log_type = self.request.GET.get('type')
        if log_type:
            queryset = queryset.filter(log_type=log_type)

        # Filter by area
        area = self.request.GET.get('area')
        if area:
            queryset = queryset.filter(area=area)

        # Search
        search = self.request.GET.get('q')
        if search:
            queryset = queryset.filter(
                Q(title__icontains=search) |
                Q(description__icontains=search) |
                Q(area__icontains=search)
            )

        return queryset.order_by('-date')

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        from apps.core.utils import get_user_today
        user_logs = MaintenanceLog.objects.filter(user=self.request.user)

        # Get unique areas for filter
        context['areas'] = user_logs.values_list(
            'area', flat=True
        ).distinct().order_by('area')

        # Total spent
        context['total_spent'] = user_logs.aggregate(
            total=Sum('cost')
        )['total'] or 0

        # Upcoming follow-ups
        today = get_user_today(self.request.user)
        context['upcoming_followups'] = user_logs.filter(
            follow_up_date__gte=today
        ).order_by('follow_up_date')[:5]

        return context


class MaintenanceLogDetailView(LifeAccessMixin, DetailView):
    """View maintenance log details."""
    model = MaintenanceLog
    template_name = "life/maintenance_detail.html"
    context_object_name = "log"

    def get_queryset(self):
        return MaintenanceLog.objects.filter(user=self.request.user)


class MaintenanceLogCreateView(LifeAccessMixin, CreateView):
    """Create a new maintenance log."""
    model = MaintenanceLog
    template_name = "life/maintenance_form.html"
    fields = [
        'title', 'description', 'log_type', 'area', 'date',
        'cost', 'provider', 'provider_contact', 'inventory_item',
        'notes', 'follow_up_date'
    ]

    def get_initial(self):
        """Pre-populate form with defaults and query parameters.

        Supports prefill from:
        - AI Camera scan (source=ai_camera)
        - Routine completion bridge (source=routine)
        """
        initial = super().get_initial()
        # Set default date to user's local date
        initial['date'] = get_user_today(self.request.user)
        # Support prefill from Camera Scan and Routine Bridge
        if self.request.GET.get('title'):
            initial['title'] = self.request.GET.get('title')
        if self.request.GET.get('area'):
            initial['area'] = self.request.GET.get('area')
        if self.request.GET.get('log_type'):
            initial['log_type'] = self.request.GET.get('log_type')
        if self.request.GET.get('follow_up_date'):
            initial['follow_up_date'] = self.request.GET.get('follow_up_date')
        return initial

    def get_form(self, form_class=None):
        form = super().get_form(form_class)
        form.fields['inventory_item'].queryset = InventoryItem.objects.filter(
            user=self.request.user
        )
        return form

    def form_valid(self, form):
        form.instance.user = self.request.user
        source = self.request.GET.get('source')
        if source == 'ai_camera':
            form.instance.created_via = MaintenanceLog.CREATED_VIA_AI_CAMERA
        elif source == 'routine':
            form.instance.created_via = MaintenanceLog.CREATED_VIA_ROUTINE
            # Set soft reference to the originating schedule
            _sched_id = self.request.GET.get('schedule_id')
            if _sched_id and _sched_id.isdigit():
                form.instance.matched_schedule_id = int(_sched_id)

        response = super().form_valid(form)

        # Auto-sync: when created from routine bridge, sync timing + flags
        if source == 'routine':
            _sched_id = self.request.GET.get('schedule_id')
            if _sched_id and _sched_id.isdigit():
                try:
                    from apps.life.services.routine_sync_service import sync_routine_from_maintenance
                    schedule = RoutineSchedule.objects.get(
                        pk=int(_sched_id),
                        routine__user=self.request.user,
                    )
                    sync_routine_from_maintenance(
                        schedule, self.object, self.request.user,
                    )
                except RoutineSchedule.DoesNotExist:
                    pass
                except Exception:
                    logger.warning("Routine sync failed", exc_info=True)

        # Part B: Check for matching routines and store in session
        if source != 'routine':
            try:
                from apps.life.services.maintenance_routine_matcher import find_matching_routines
                matches = find_matching_routines(self.object, self.request.user)
                if matches:
                    self.request.session['maintenance_matches'] = {
                        'log_id': self.object.pk,
                        'matches': matches,
                    }
            except Exception:
                pass

        messages.success(self.request, f"Maintenance log '{form.instance.title}' added.")
        return response

    def get_success_url(self):
        matches = self.request.session.get('maintenance_matches')
        if matches and matches.get('log_id') == self.object.pk:
            return reverse(
                'life:maintenance_match_review',
                kwargs={'pk': self.object.pk},
            )
        return reverse('life:maintenance_list')


class MaintenanceLogUpdateView(LifeAccessMixin, UpdateView):
    """Edit a maintenance log."""
    model = MaintenanceLog
    template_name = "life/maintenance_form.html"
    fields = [
        'title', 'description', 'log_type', 'area', 'date',
        'cost', 'provider', 'provider_contact', 'inventory_item',
        'notes', 'follow_up_date'
    ]

    def get_queryset(self):
        return MaintenanceLog.objects.filter(user=self.request.user)

    def get_form(self, form_class=None):
        form = super().get_form(form_class)
        form.fields['inventory_item'].queryset = InventoryItem.objects.filter(
            user=self.request.user
        )
        return form

    def get_success_url(self):
        return reverse('life:maintenance_detail', kwargs={'pk': self.object.pk})


class MaintenanceLogDeleteView(LifeAccessMixin, DeleteView):
    """Delete a maintenance log."""
    model = MaintenanceLog
    template_name = "life/maintenance_confirm_delete.html"
    success_url = reverse_lazy('life:maintenance_list')

    def get_queryset(self):
        return MaintenanceLog.objects.filter(user=self.request.user)


class MaintenanceMatchReviewView(LifeAccessMixin, DetailView):
    """Show matching routine suggestions after creating a maintenance log."""
    model = MaintenanceLog
    template_name = "life/maintenance_match_review.html"
    context_object_name = "log"

    def get_queryset(self):
        return MaintenanceLog.objects.filter(user=self.request.user)

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        session_data = self.request.session.pop('maintenance_matches', None)
        if session_data and session_data.get('log_id') == self.object.pk:
            ctx['matches'] = session_data['matches']
        else:
            ctx['matches'] = []
        return ctx


class MaintenanceSyncRoutineView(LifeAccessMixin, View):
    """Link a maintenance log to a routine schedule (user-confirmed).

    Sets the soft reference matched_schedule_id on the maintenance log.
    Does NOT create RoutineLog or modify past logs.
    """

    def post(self, request, pk, schedule_id):
        log = get_object_or_404(
            MaintenanceLog, pk=pk, user=request.user,
        )
        schedule = get_object_or_404(
            RoutineSchedule.objects.select_related('routine'),
            pk=schedule_id,
            routine__user=request.user,
        )
        log.matched_schedule_id = schedule.pk
        log.save(update_fields=['matched_schedule_id'])

        messages.success(
            request,
            f"Linked '{log.title}' to routine '{schedule.name}'.",
        )
        return redirect('life:maintenance_detail', pk=log.pk)


# =============================================================================
# Documents
# =============================================================================

class DocumentListView(LifeAccessMixin, ListView):
    """List all documents."""
    model = Document
    template_name = "life/document_list.html"
    context_object_name = "documents"

    def get_queryset(self):
        queryset = Document.objects.filter(user=self.request.user)

        # Filter by archived
        show_archived = self.request.GET.get('archived')
        if not show_archived:
            queryset = queryset.filter(is_archived=False)

        # Filter by category
        category = self.request.GET.get('category')
        if category:
            queryset = queryset.filter(category=category)

        # Search
        search = self.request.GET.get('q')
        if search:
            queryset = queryset.filter(
                Q(title__icontains=search) |
                Q(description__icontains=search) |
                Q(notes__icontains=search)
            )

        return queryset.order_by('-created_at')

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        from apps.core.utils import get_user_today

        # Category choices for filter
        context['categories'] = Document.CATEGORY_CHOICES

        # Expiring soon
        today = get_user_today(self.request.user)
        thirty_days = today + timedelta(days=30)
        context['expiring_soon'] = Document.objects.filter(
            user=self.request.user,
            is_archived=False,
            expiration_date__isnull=False,
            expiration_date__lte=thirty_days,
            expiration_date__gte=today
        ).count()

        return context


class DocumentDetailView(LifeAccessMixin, DetailView):
    """View document details."""
    model = Document
    template_name = "life/document_detail.html"
    context_object_name = "document"

    def get_queryset(self):
        return Document.objects.filter(user=self.request.user)


class DocumentCreateView(LifeAccessMixin, CreateView):
    """Upload a new document."""
    model = Document
    template_name = "life/document_form.html"
    fields = [
        'title', 'description', 'category', 'file',
        'document_date', 'expiration_date',
        'related_inventory_item', 'related_pet', 'notes'
    ]

    def get_initial(self):
        """Pre-populate form with defaults and query parameters (for AI Camera scan)."""
        initial = super().get_initial()
        # Set default document_date to user's local date
        initial['document_date'] = get_user_today(self.request.user)
        # Support prefill from Camera Scan feature
        if self.request.GET.get('name'):
            initial['title'] = self.request.GET.get('name')
        if self.request.GET.get('title'):
            initial['title'] = self.request.GET.get('title')
        if self.request.GET.get('category'):
            initial['category'] = self.request.GET.get('category')
        return initial

    def get_form(self, form_class=None):
        form = super().get_form(form_class)
        form.fields['related_inventory_item'].queryset = InventoryItem.objects.filter(
            user=self.request.user
        )
        form.fields['related_pet'].queryset = Pet.objects.filter(
            user=self.request.user
        )
        return form

    def form_valid(self, form):
        form.instance.user = self.request.user
        # Track if created via AI Camera scan
        source = self.request.GET.get('source')
        if source == 'ai_camera':
            form.instance.created_via = Document.CREATED_VIA_AI_CAMERA
        messages.success(self.request, f"Document '{form.instance.title}' uploaded.")
        return super().form_valid(form)

    def get_success_url(self):
        return reverse('life:document_list')


class DocumentUpdateView(LifeAccessMixin, UpdateView):
    """Edit document metadata and optionally replace file."""
    model = Document
    template_name = "life/document_form.html"
    fields = [
        'title', 'description', 'category', 'file',
        'document_date', 'expiration_date',
        'related_inventory_item', 'related_pet', 'notes', 'is_archived'
    ]

    def get_queryset(self):
        return Document.objects.filter(user=self.request.user)

    def get_form(self, form_class=None):
        form = super().get_form(form_class)
        # File is optional when editing (only required for new documents)
        form.fields['file'].required = False
        form.fields['related_inventory_item'].queryset = InventoryItem.objects.filter(
            user=self.request.user
        )
        form.fields['related_pet'].queryset = Pet.objects.filter(
            user=self.request.user
        )
        return form

    def form_valid(self, form):
        # If a new file was uploaded, delete the old one from storage
        if 'file' in form.changed_data and self.object.file:
            old_file = Document.objects.get(pk=self.object.pk).file
            if old_file:
                try:
                    old_file.delete(save=False)
                except Exception:
                    pass  # Don't fail if old file can't be deleted
        return super().form_valid(form)

    def get_success_url(self):
        return reverse('life:document_detail', kwargs={'pk': self.object.pk})


class DocumentDeleteView(LifeAccessMixin, DeleteView):
    """Delete a document."""
    model = Document
    template_name = "life/document_confirm_delete.html"
    success_url = reverse_lazy('life:document_list')

    def get_queryset(self):
        return Document.objects.filter(user=self.request.user)

    def form_valid(self, form):
        # Delete the file from storage
        if self.object.file:
            self.object.file.delete(save=False)
        messages.success(self.request, f"Document '{self.object.title}' deleted.")
        return super().form_valid(form)


class DocumentDownloadView(LifeAccessMixin, View):
    """Download a document file."""

    def get(self, request, pk):
        document = get_object_or_404(Document, pk=pk, user=request.user)

        if document.file:
            response = FileResponse(
                document.file.open('rb'),
                as_attachment=True,
                filename=document.file.name.split('/')[-1]
            )
            return response

        messages.error(request, "File not found.")
        return redirect('life:document_detail', pk=pk)


@method_decorator(xframe_options_sameorigin, name='dispatch')
class DocumentViewInlineView(LifeAccessMixin, View):
    """View a document file inline (for PDF viewing in iframe)."""

    def get(self, request, pk):
        document = get_object_or_404(Document, pk=pk, user=request.user)

        if not document.file:
            return HttpResponse("File not found.", status=404)

        # Determine content type
        content_type = 'application/octet-stream'
        if document.file_type == 'pdf':
            content_type = 'application/pdf'
        elif document.file_type == 'image/jpeg':
            content_type = 'image/jpeg'
        elif document.file_type == 'image/png':
            content_type = 'image/png'

        try:
            # Try to open and stream the file
            file_handle = document.file.open('rb')
            response = FileResponse(
                file_handle,
                as_attachment=False,  # Inline viewing
                content_type=content_type,
            )
            return response
        except Exception as e:
            # If we can't open the file (e.g., Cloudinary issue),
            # try to redirect to the direct URL
            logger.warning(f"Failed to open document file {pk}: {e}")
            try:
                # For Cloudinary files, try redirecting to the URL directly
                file_url = document.file.url
                if file_url:
                    from django.http import HttpResponseRedirect
                    return HttpResponseRedirect(file_url)
            except Exception:
                pass
            return HttpResponse(
                "Unable to load file. Please try downloading instead.",
                status=500
            )


# =============================================================================
# Significant Events (Birthdays, Anniversaries, etc.)
# =============================================================================

class SignificantEventListView(HelpContextMixin, LifeAccessMixin, ListView):
    """List all significant events."""
    model = SignificantEvent
    template_name = "life/significant_event_list.html"
    context_object_name = "events"
    help_context_id = "LIFE_SIGNIFICANT_EVENTS"

    def get_queryset(self):
        return SignificantEvent.objects.filter(
            user=self.request.user
        ).order_by('event_date')

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        today = get_user_today(self.request.user)

        # Annotate events with next occurrence info
        events_with_dates = []
        for event in context['events']:
            event.next_occurrence = event.get_next_occurrence(today)
            event.days_until = event.days_until_next(today)
            events_with_dates.append(event)

        # Sort by days until next occurrence
        events_with_dates.sort(key=lambda e: e.days_until)
        context['events'] = events_with_dates

        # Upcoming events (within 30 days)
        context['upcoming_events'] = [e for e in events_with_dates if e.days_until <= 30]
        context['upcoming_count'] = len(context['upcoming_events'])

        # Count by type
        context['type_counts'] = {}
        for event in context['events']:
            event_type = event.get_event_type_display()
            context['type_counts'][event_type] = context['type_counts'].get(event_type, 0) + 1

        context['user_today'] = today

        return context


class SignificantEventDetailView(HelpContextMixin, LifeAccessMixin, DetailView):
    """View details of a significant event."""
    model = SignificantEvent
    template_name = "life/significant_event_detail.html"
    context_object_name = "event"
    help_context_id = "LIFE_SIGNIFICANT_EVENT_DETAIL"

    def get_queryset(self):
        return SignificantEvent.objects.filter(user=self.request.user)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        today = get_user_today(self.request.user)

        # Add computed properties
        context['next_occurrence'] = self.object.get_next_occurrence(today)
        context['days_until'] = self.object.days_until_next(today)
        context['years_display'] = self.object.get_years_display()
        context['user_today'] = today

        return context


class SignificantEventCreateView(HelpContextMixin, LifeAccessMixin, CreateView):
    """Create a new significant event."""
    model = SignificantEvent
    form_class = SignificantEventForm
    template_name = "life/significant_event_form.html"
    help_context_id = "LIFE_SIGNIFICANT_EVENT_CREATE"

    def form_valid(self, form):
        form.instance.user = self.request.user
        messages.success(self.request, f"'{form.instance.title}' added to your significant events.")
        return super().form_valid(form)

    def get_success_url(self):
        return reverse('life:significant_event_list')


class SignificantEventUpdateView(HelpContextMixin, LifeAccessMixin, UpdateView):
    """Edit a significant event."""
    model = SignificantEvent
    form_class = SignificantEventForm
    template_name = "life/significant_event_form.html"
    help_context_id = "LIFE_SIGNIFICANT_EVENT_EDIT"

    def get_queryset(self):
        return SignificantEvent.objects.filter(user=self.request.user)

    def form_valid(self, form):
        messages.success(self.request, f"'{form.instance.title}' updated.")
        return super().form_valid(form)

    def get_success_url(self):
        return reverse('life:significant_event_detail', kwargs={'pk': self.object.pk})


class SignificantEventDeleteView(LifeAccessMixin, DeleteView):
    """Delete a significant event."""
    model = SignificantEvent
    template_name = "life/significant_event_confirm_delete.html"
    success_url = reverse_lazy('life:significant_event_list')

    def get_queryset(self):
        return SignificantEvent.objects.filter(user=self.request.user)

    def form_valid(self, form):
        messages.success(self.request, f"'{self.object.title}' has been deleted.")
        return super().form_valid(form)


# =============================================================================
# Google Calendar Integration
# =============================================================================

def get_user_google_credential(user):
    """Get the user's Google Calendar credential from database, or None."""
    from apps.life.models import GoogleCalendarCredential
    try:
        return user.google_calendar_credential
    except GoogleCalendarCredential.DoesNotExist:
        return None


class GoogleCalendarSettingsView(LifeAccessMixin, TemplateView):
    """Settings page for Google Calendar integration."""
    template_name = "life/google_calendar_settings.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)

        # Check if Google is configured in settings
        from django.conf import settings as django_settings
        context['is_configured'] = bool(
            getattr(django_settings, 'GOOGLE_CALENDAR_CLIENT_ID', None)
        )

        # Get credentials from database
        credential = get_user_google_credential(self.request.user)
        context['is_connected'] = credential is not None and credential.is_connected

        if context['is_connected'] and context['is_configured']:
            # Check for decryption errors (key rotation, etc.)
            if credential.has_decryption_error():
                messages.error(
                    self.request,
                    "Your Google Calendar connection needs to be re-authorized. "
                    "Please disconnect and reconnect your account."
                )
                context['has_decryption_error'] = True
                context['calendars'] = []
            else:
                # Check if token needs refresh
                if credential.is_token_expired and credential.refresh_token:
                    try:
                        self._refresh_token(credential)
                    except Exception as e:
                        messages.warning(self.request, f"Could not refresh token: {str(e)}")

                # Get user's calendars
                try:
                    from apps.life.services.google_calendar import GoogleCalendarService
                    service = GoogleCalendarService()
                    context['calendars'] = service.list_calendars(credential.get_credentials_dict())
                except Exception as e:
                    context['calendars'] = []
                    messages.warning(self.request, f"Could not load calendars: {str(e)}")

            # Get sync settings from database
            context['selected_calendar'] = credential.selected_calendar_id
            context['selected_calendar_name'] = credential.selected_calendar_name
            context['sync_direction'] = credential.sync_direction
            context['days_past'] = credential.days_past
            context['days_future'] = credential.days_future
            context['sync_types'] = credential.get_sync_event_types()
            context['auto_sync'] = credential.auto_sync_enabled
            context['last_sync'] = credential.last_sync
            context['last_sync_status'] = credential.last_sync_status

        # Available event types for the form
        context['available_event_types'] = [
            ('personal', 'Personal'),
            ('family', 'Family'),
            ('work', 'Work'),
            ('health', 'Health'),
            ('social', 'Social'),
            ('travel', 'Travel'),
            ('household', 'Household'),
            ('faith', 'Faith'),
            ('other', 'Other'),
        ]

        return context

    def _refresh_token(self, credential):
        """Refresh an expired access token."""
        from apps.life.services.google_calendar import GoogleCalendarService
        service = GoogleCalendarService()
        new_credentials = service.refresh_credentials(credential.get_credentials_dict())
        if new_credentials:
            credential.update_from_credentials(new_credentials)


class GoogleCalendarSaveSettingsView(LifeAccessMixin, View):
    """Save Google Calendar sync settings to database."""

    def post(self, request):
        credential = get_user_google_credential(request.user)

        if not credential:
            messages.error(request, "Please connect Google Calendar first.")
            return redirect('life:google_calendar_settings')

        # Check for decryption errors (key rotation, etc.)
        if credential.has_decryption_error():
            messages.error(
                request,
                "Your Google Calendar connection needs to be re-authorized. "
                "Please disconnect and reconnect your account."
            )
            return redirect('life:google_calendar_settings')

        # Update settings in database
        credential.selected_calendar_id = request.POST.get('calendar_id', 'primary')
        credential.sync_direction = request.POST.get('sync_direction', 'import')
        credential.days_past = int(request.POST.get('days_past', 0))
        credential.days_future = int(request.POST.get('days_future', 30))
        credential.auto_sync_enabled = request.POST.get('auto_sync') == 'on'

        # Sync types (checkboxes)
        sync_types = request.POST.getlist('sync_types')
        if sync_types:
            credential.set_sync_event_types(sync_types)

        # Get calendar name for display
        try:
            from apps.life.services.google_calendar import GoogleCalendarService
            service = GoogleCalendarService()
            calendars = service.list_calendars(credential.get_credentials_dict())
            for cal in calendars:
                if cal.get('id') == credential.selected_calendar_id:
                    credential.selected_calendar_name = cal.get('summary', '')
                    break
        except Exception:
            pass

        credential.save()
        messages.success(request, "Google Calendar settings saved.")

        return redirect('life:google_calendar_settings')


class GoogleCalendarConnectView(LifeAccessMixin, View):
    """Initiate Google Calendar OAuth2 flow."""

    def get(self, request):
        try:
            from apps.life.services.google_calendar import GoogleCalendarService

            service = GoogleCalendarService()
            state = secrets.token_urlsafe(32)
            request.session['google_oauth_state'] = state

            authorization_url, _ = service.get_authorization_url(state=state)
            return redirect(authorization_url)

        except ImportError as e:
            messages.error(request, str(e))
            return redirect('life:google_calendar_settings')
        except ValueError as e:
            messages.error(request, str(e))
            return redirect('life:google_calendar_settings')


class GoogleCalendarCallbackView(LifeAccessMixin, View):
    """Handle Google Calendar OAuth2 callback and store credentials in database."""

    def get(self, request):
        from apps.life.models import GoogleCalendarCredential

        state = request.GET.get('state')
        stored_state = request.session.get('google_oauth_state')

        if state != stored_state:
            messages.error(request, "Invalid OAuth state. Please try again.")
            return redirect('life:google_calendar_settings')

        error = request.GET.get('error')
        if error:
            messages.error(request, f"Google Calendar authorization failed: {error}")
            return redirect('life:google_calendar_settings')

        code = request.GET.get('code')
        if not code:
            messages.error(request, "No authorization code received.")
            return redirect('life:google_calendar_settings')

        try:
            from apps.life.services.google_calendar import GoogleCalendarService

            service = GoogleCalendarService()
            credentials_dict = service.exchange_code_for_credentials(code)

            # Store credentials in database (create or update)
            credential, created = GoogleCalendarCredential.objects.update_or_create(
                user=request.user,
                defaults={
                    'access_token': credentials_dict.get('token', ''),
                    'refresh_token': credentials_dict.get('refresh_token', ''),
                    'token_uri': credentials_dict.get('token_uri', 'https://oauth2.googleapis.com/token'),
                    'client_id': credentials_dict.get('client_id', ''),
                    'client_secret': credentials_dict.get('client_secret', ''),
                }
            )

            # Set expiry if available
            if credentials_dict.get('expiry'):
                credential.token_expiry = credentials_dict['expiry']

            if credentials_dict.get('scopes'):
                credential.set_scopes_list(credentials_dict['scopes'])

            credential.save()

            # Clear OAuth state from session
            if 'google_oauth_state' in request.session:
                del request.session['google_oauth_state']

            messages.success(request, "Google Calendar connected successfully! Configure your sync settings below.")
            return redirect('life:google_calendar_settings')

        except Exception as e:
            messages.error(request, f"Failed to connect Google Calendar: {str(e)}")
            return redirect('life:google_calendar_settings')


class GoogleCalendarDisconnectView(LifeAccessMixin, View):
    """Disconnect Google Calendar by removing credentials from database."""

    def post(self, request):
        from apps.life.models import GoogleCalendarCredential

        # Delete credentials from database
        GoogleCalendarCredential.objects.filter(user=request.user).delete()

        messages.success(request, "Google Calendar disconnected.")
        return redirect('life:google_calendar_settings')


class GoogleCalendarSyncView(LifeAccessMixin, View):
    """Sync events with Google Calendar using database-stored credentials."""

    def post(self, request):
        credential = get_user_google_credential(request.user)

        if not credential or not credential.is_connected:
            messages.error(request, "Please connect Google Calendar first.")
            return redirect('life:google_calendar_settings')

        # Check for decryption errors (key rotation, etc.)
        if credential.has_decryption_error():
            messages.error(
                request,
                "Your Google Calendar connection needs to be re-authorized. "
                "Please disconnect and reconnect your account."
            )
            return redirect('life:google_calendar_settings')

        # Refresh token if needed
        if credential.is_token_expired and credential.refresh_token:
            try:
                from apps.life.services.google_calendar import GoogleCalendarService
                service = GoogleCalendarService()
                new_creds = service.refresh_credentials(credential.get_credentials_dict())
                if new_creds:
                    credential.update_from_credentials(new_creds)
            except Exception as e:
                messages.error(request, f"Could not refresh token: {str(e)}")
                return redirect('life:google_calendar_settings')

        # Get sync settings from database
        credentials_dict = credential.get_credentials_dict()
        sync_action = request.POST.get('sync_action', credential.sync_direction)
        calendar_id = credential.selected_calendar_id
        days_past = credential.days_past
        days_future = credential.days_future

        stats = {'imported': 0, 'exported': 0, 'updated': 0}

        try:
            from apps.life.services.google_calendar import CalendarSyncService

            sync_service = CalendarSyncService(request.user)

            # Import from Google
            if sync_action in ('import', 'both'):
                created, updated = sync_service.sync_from_google(
                    credentials_dict,
                    calendar_id=calendar_id,
                    days_past=days_past,
                    days_ahead=days_future
                )
                stats['imported'] = created
                stats['updated'] += updated

            # Export to Google
            if sync_action in ('export', 'both'):
                exported = sync_service.sync_to_google_bulk(
                    credentials_dict,
                    calendar_id=calendar_id,
                    days_past=days_past,
                    days_ahead=days_future,
                    event_types=credential.get_sync_event_types()
                )
                stats['exported'] = exported

            # Record sync in database
            msg_parts = []
            if stats['imported']:
                msg_parts.append(f"{stats['imported']} imported")
            if stats['exported']:
                msg_parts.append(f"{stats['exported']} exported")
            if stats['updated']:
                msg_parts.append(f"{stats['updated']} updated")

            credential.record_sync(
                success=True,
                message=', '.join(msg_parts) if msg_parts else 'No changes'
            )

            if msg_parts:
                messages.success(request, f"Sync complete: {', '.join(msg_parts)}.")
            else:
                messages.info(request, "Sync complete. No changes needed.")

        except Exception as e:
            credential.record_sync(success=False, message=str(e))
            messages.error(request, f"Sync failed: {str(e)}")

        return redirect('life:google_calendar_settings')


class GoogleCalendarPushEventView(LifeAccessMixin, View):
    """Push a single event to Google Calendar."""

    def post(self, request, pk):
        credential = get_user_google_credential(request.user)

        if not credential or not credential.is_connected:
            messages.error(request, "Please connect Google Calendar first.")
            return redirect('life:event_update', pk=pk)

        # Check for decryption errors (key rotation, etc.)
        if credential.has_decryption_error():
            messages.error(
                request,
                "Your Google Calendar connection needs to be re-authorized. "
                "Please disconnect and reconnect your account."
            )
            return redirect('life:google_calendar_settings')

        calendar_id = credential.selected_calendar_id

        try:
            event = LifeEvent.objects.get(pk=pk, user=request.user)

            from apps.life.services.google_calendar import CalendarSyncService

            sync_service = CalendarSyncService(request.user)
            result = sync_service.sync_to_google(event, credential.get_credentials_dict(), calendar_id)

            if result:
                messages.success(request, "Event synced to Google Calendar.")
            else:
                messages.error(request, "Failed to sync event.")

        except LifeEvent.DoesNotExist:
            messages.error(request, "Event not found.")
        except Exception as e:
            messages.error(request, f"Sync failed: {str(e)}")

        return redirect('life:calendar')


# =============================================================================
# Gmail Integration Views
# =============================================================================

def get_user_gmail_credential(user):
    """Get user's Gmail credential or None."""
    from apps.life.models import GmailCredential
    try:
        return GmailCredential.objects.get(user=user)
    except GmailCredential.DoesNotExist:
        return None


class GmailSettingsView(LifeAccessMixin, TemplateView):
    """Gmail integration settings page."""

    template_name = "life/gmail_settings.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)

        # Check if Gmail is configured in settings
        from django.conf import settings
        context['is_configured'] = all([
            getattr(settings, 'GMAIL_CLIENT_ID', ''),
            getattr(settings, 'GMAIL_CLIENT_SECRET', ''),
            getattr(settings, 'GMAIL_REDIRECT_URI', ''),
        ])

        # Get user's credential
        credential = get_user_gmail_credential(self.request.user)
        context['credential'] = credential
        context['is_connected'] = credential and credential.access_token

        if credential:
            context['last_scan'] = credential.last_scan
            context['scan_enabled'] = credential.scan_enabled
            context['max_emails'] = credential.max_emails_per_scan
            context['days_back'] = credential.days_to_look_back
            context['last_tasks_created'] = credential.last_scan_tasks_created
            context['last_scan_status'] = credential.last_scan_status
            context['last_scan_message'] = credential.last_scan_message

        return context


class GmailConnectView(LifeAccessMixin, View):
    """Initiate Gmail OAuth2 flow."""

    def get(self, request):
        try:
            from apps.life.services.gmail import GmailService

            service = GmailService()
            state = secrets.token_urlsafe(32)
            request.session['gmail_oauth_state'] = state

            authorization_url, _ = service.get_authorization_url(state=state)
            return redirect(authorization_url)

        except ImportError as e:
            messages.error(request, str(e))
            return redirect('life:gmail_settings')
        except ValueError as e:
            messages.error(request, str(e))
            return redirect('life:gmail_settings')


class GmailCallbackView(LifeAccessMixin, View):
    """Handle Gmail OAuth2 callback and store credentials in database."""

    def get(self, request):
        from apps.life.models import GmailCredential

        state = request.GET.get('state')
        stored_state = request.session.get('gmail_oauth_state')

        if state != stored_state:
            messages.error(request, "Invalid OAuth state. Please try again.")
            return redirect('life:gmail_settings')

        error = request.GET.get('error')
        if error:
            messages.error(request, f"Gmail authorization failed: {error}")
            return redirect('life:gmail_settings')

        code = request.GET.get('code')
        if not code:
            messages.error(request, "No authorization code received.")
            return redirect('life:gmail_settings')

        try:
            from apps.life.services.gmail import GmailService

            service = GmailService()
            credentials_dict = service.exchange_code_for_credentials(code)

            # Store credentials in database (create or update)
            credential, created = GmailCredential.objects.update_or_create(
                user=request.user,
                defaults={
                    'client_id': credentials_dict.get('client_id', ''),
                }
            )

            # Use encrypted setters for sensitive data
            credential.set_access_token(credentials_dict.get('token', ''))
            credential.set_refresh_token(credentials_dict.get('refresh_token', ''))
            credential.set_client_secret(credentials_dict.get('client_secret', ''))
            credential.token_uri = credentials_dict.get('token_uri', 'https://oauth2.googleapis.com/token')

            # Set expiry if available
            if credentials_dict.get('expiry'):
                from datetime import datetime
                expiry = credentials_dict['expiry']
                if isinstance(expiry, str):
                    credential.token_expiry = datetime.fromisoformat(expiry.replace('Z', '+00:00'))
                else:
                    credential.token_expiry = expiry

            if credentials_dict.get('scopes'):
                credential.set_scopes_list(credentials_dict['scopes'])

            credential.save()

            # Clear OAuth state from session
            if 'gmail_oauth_state' in request.session:
                del request.session['gmail_oauth_state']

            messages.success(
                request,
                "Gmail connected successfully! Configure your scan settings below."
            )
            return redirect('life:gmail_settings')

        except Exception as e:
            logger.error(f"Gmail callback error: {e}", exc_info=True)
            messages.error(request, f"Failed to connect Gmail: {str(e)}")
            return redirect('life:gmail_settings')


class GmailDisconnectView(LifeAccessMixin, View):
    """Disconnect Gmail by removing credentials from database."""

    def post(self, request):
        from apps.life.models import GmailCredential, ProcessedEmail

        # Delete credentials and processed email records
        GmailCredential.objects.filter(user=request.user).delete()
        ProcessedEmail.objects.filter(user=request.user).delete()

        messages.success(request, "Gmail disconnected.")
        return redirect('life:gmail_settings')


class GmailSaveSettingsView(LifeAccessMixin, View):
    """Save Gmail scan settings."""

    def post(self, request):
        credential = get_user_gmail_credential(request.user)
        if not credential:
            messages.error(request, "Please connect Gmail first.")
            return redirect('life:gmail_settings')

        # Update settings
        credential.scan_enabled = request.POST.get('scan_enabled') == 'on'

        try:
            credential.max_emails_per_scan = int(request.POST.get('max_emails', 20))
            credential.max_emails_per_scan = max(1, min(50, credential.max_emails_per_scan))
        except (ValueError, TypeError):
            credential.max_emails_per_scan = 20

        try:
            credential.days_to_look_back = int(request.POST.get('days_back', 3))
            credential.days_to_look_back = max(1, min(14, credential.days_to_look_back))
        except (ValueError, TypeError):
            credential.days_to_look_back = 3

        credential.save()

        messages.success(request, "Gmail settings saved.")
        return redirect('life:gmail_settings')


class GmailManualScanView(LifeAccessMixin, View):
    """Trigger manual Gmail scan for current user."""

    def post(self, request):
        credential = get_user_gmail_credential(request.user)
        if not credential or not credential.access_token:
            messages.error(request, "Please connect Gmail first.")
            return redirect('life:gmail_settings')

        from apps.life.services.gmail_sync import GmailSyncService

        try:
            sync_service = GmailSyncService()
            result = sync_service.scan_user_inbox(request.user)

            if result.get('error'):
                if result['error'] == 'decryption_error':
                    messages.warning(
                        request,
                        "Your Gmail connection needs to be re-authorized. "
                        "Please disconnect and reconnect."
                    )
                else:
                    messages.error(request, f"Scan failed: {result['error']}")
            elif result['tasks_created'] > 0:
                messages.success(
                    request,
                    f"Scan complete! Created {result['tasks_created']} new tasks "
                    f"from {result['emails_scanned']} emails."
                )
            else:
                messages.info(
                    request,
                    f"Scan complete. Checked {result['emails_scanned']} emails, "
                    "no new action items found."
                )

        except Exception as e:
            logger.error(f"Gmail scan error: {e}", exc_info=True)
            messages.error(request, f"Scan failed: {str(e)}")

        return redirect('life:gmail_settings')


class GmailSyncCronView(View):
    """
    External cron trigger for Gmail inbox scanning.

    Called by external services (cron-job.org, GitHub Actions) to trigger
    inbox scanning for all users with Gmail connected.

    Authentication:
        Requires X-Gmail-Sync-API-Key header matching settings.GMAIL_SYNC_API_KEY

    GET /life/api/gmail/cron-sync/

    Returns:
        JSON with users_processed, tasks_created, errors
    """

    def get(self, request):
        from django.conf import settings
        from django.http import JsonResponse

        # Authenticate
        api_key = request.headers.get('X-Gmail-Sync-API-Key', '')

        expected_key = getattr(settings, 'GMAIL_SYNC_API_KEY', '')
        if not expected_key:
            return JsonResponse(
                {'error': 'GMAIL_SYNC_API_KEY not configured'},
                status=500
            )

        # Constant-time comparison to prevent timing attacks
        import hmac
        if not hmac.compare_digest(api_key, expected_key):
            logger.warning(f"Gmail cron: Invalid API key from {request.META.get('REMOTE_ADDR')}")
            return JsonResponse(
                {'error': 'Invalid API key'},
                status=401
            )

        # Run sync for all enabled users
        try:
            from apps.life.services.gmail_sync import GmailSyncService

            sync_service = GmailSyncService()
            result = sync_service.scan_all_users()

            return JsonResponse({
                'status': 'success',
                'users_processed': result['users_processed'],
                'tasks_created': result['tasks_created'],
                'errors': result.get('errors'),
            })

        except Exception as e:
            logger.exception(f"Gmail cron sync error: {e}")
            return JsonResponse(
                {'error': str(e)},
                status=500
            )


# =============================================================================
# Bulk Delete Views
# =============================================================================

class BulkDeleteTasksView(LoginRequiredMixin, View):
    """Bulk delete tasks."""

    def post(self, request):
        try:
            data = json.loads(request.body)
            ids = data.get('ids', [])
        except (json.JSONDecodeError, ValueError):
            return JsonResponse({'success': False, 'error': 'Invalid JSON'}, status=400)

        if not ids:
            return JsonResponse({'success': False, 'error': 'No items selected'}, status=400)

        entries = Task.objects.filter(user=request.user, pk__in=ids)
        count = entries.count()

        if count == 0:
            return JsonResponse({'success': False, 'error': 'No entries found'}, status=404)

        delete_series = data.get('delete_series', False)

        for entry in entries:
            if delete_series and (entry.is_recurring or entry.is_routine):
                from apps.life.services.recurrence import RecurrenceService
                RecurrenceService.delete_task_series_complete(entry)
            else:
                entry.soft_delete()

        return JsonResponse({
            'success': True,
            'message': f'{count} task{"" if count == 1 else "s"} deleted',
            'count': count
        })


class BulkDeleteInventoryView(LoginRequiredMixin, View):
    """Bulk delete inventory items."""

    def post(self, request):
        try:
            data = json.loads(request.body)
            ids = data.get('ids', [])
        except (json.JSONDecodeError, ValueError):
            return JsonResponse({'success': False, 'error': 'Invalid JSON'}, status=400)

        if not ids:
            return JsonResponse({'success': False, 'error': 'No items selected'}, status=400)

        entries = InventoryItem.objects.filter(user=request.user, pk__in=ids)
        count = entries.count()

        if count == 0:
            return JsonResponse({'success': False, 'error': 'No entries found'}, status=404)

        for entry in entries:
            entry.soft_delete()

        return JsonResponse({
            'success': True,
            'message': f'{count} item{"" if count == 1 else "s"} deleted',
            'count': count
        })


class BulkDeleteDocumentsView(LoginRequiredMixin, View):
    """Bulk delete documents."""

    def post(self, request):
        try:
            data = json.loads(request.body)
            ids = data.get('ids', [])
        except (json.JSONDecodeError, ValueError):
            return JsonResponse({'success': False, 'error': 'Invalid JSON'}, status=400)

        if not ids:
            return JsonResponse({'success': False, 'error': 'No items selected'}, status=400)

        entries = Document.objects.filter(user=request.user, pk__in=ids)
        count = entries.count()

        if count == 0:
            return JsonResponse({'success': False, 'error': 'No entries found'}, status=404)

        for entry in entries:
            entry.soft_delete()

        return JsonResponse({
            'success': True,
            'message': f'{count} document{"" if count == 1 else "s"} deleted',
            'count': count
        })


class BulkDeleteRecipesView(LoginRequiredMixin, View):
    """Bulk delete recipes."""

    def post(self, request):
        try:
            data = json.loads(request.body)
            ids = data.get('ids', [])
        except (json.JSONDecodeError, ValueError):
            return JsonResponse({'success': False, 'error': 'Invalid JSON'}, status=400)

        if not ids:
            return JsonResponse({'success': False, 'error': 'No items selected'}, status=400)

        entries = Recipe.objects.filter(user=request.user, pk__in=ids)
        count = entries.count()

        if count == 0:
            return JsonResponse({'success': False, 'error': 'No entries found'}, status=404)

        for entry in entries:
            entry.soft_delete()

        return JsonResponse({
            'success': True,
            'message': f'{count} recipe{"" if count == 1 else "s"} deleted',
            'count': count
        })


class BulkDeleteMaintenanceView(LoginRequiredMixin, View):
    """Bulk delete maintenance logs."""

    def post(self, request):
        try:
            data = json.loads(request.body)
            ids = data.get('ids', [])
        except (json.JSONDecodeError, ValueError):
            return JsonResponse({'success': False, 'error': 'Invalid JSON'}, status=400)

        if not ids:
            return JsonResponse({'success': False, 'error': 'No items selected'}, status=400)

        entries = MaintenanceLog.objects.filter(user=request.user, pk__in=ids)
        count = entries.count()

        if count == 0:
            return JsonResponse({'success': False, 'error': 'No entries found'}, status=404)

        for entry in entries:
            entry.soft_delete()

        return JsonResponse({
            'success': True,
            'message': f'{count} log{"" if count == 1 else "s"} deleted',
            'count': count
        })


class BulkDeleteSignificantEventsView(LoginRequiredMixin, View):
    """Bulk delete significant events."""

    def post(self, request):
        try:
            data = json.loads(request.body)
            ids = data.get('ids', [])
        except (json.JSONDecodeError, ValueError):
            return JsonResponse({'success': False, 'error': 'Invalid JSON'}, status=400)

        if not ids:
            return JsonResponse({'success': False, 'error': 'No items selected'}, status=400)

        entries = SignificantEvent.objects.filter(user=request.user, pk__in=ids)
        count = entries.count()

        if count == 0:
            return JsonResponse({'success': False, 'error': 'No entries found'}, status=404)

        for entry in entries:
            entry.soft_delete()

        return JsonResponse({
            'success': True,
            'message': f'{count} event{"" if count == 1 else "s"} deleted',
            'count': count
        })


# =============================================================================
# Routines — First-class domain views
# =============================================================================


def _invalidate_routine_caches(user):
    """Invalidate caches after routine CRUD.

    Only performs cheap cache.delete() operations. SAE module rebuilds
    are handled by post_save signal handlers via deferred Celery tasks —
    calling update_user_state() here was redundant and added 200-400ms
    of blocking work to the HTTP response.
    """
    try:
        from apps.ai.readiness_cache import invalidate_cos_context_on_action
        invalidate_cos_context_on_action(user)
    except Exception:
        pass  # CoS invalidation is best-effort
    try:
        from apps.dashboard_v2.cache import DashboardV2CacheService
        DashboardV2CacheService.invalidate(user.pk, "execution")
    except Exception:
        pass  # Dashboard cache invalidation is best-effort


class RoutineListView(HelpContextMixin, LifeAccessMixin, TemplateView):
    """
    Today's routines grouped by time window.

    Reads canonical state via build_routine_state() — the ONLY public
    interface for routine state. UI never calls helpers directly.
    """
    template_name = "life/routine_list.html"
    help_context_id = "ROUTINE_LIST"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        from apps.core.ai_state.state_builder import build_routine_state
        from apps.core.time_windows import WINDOW_DISPLAY_NAMES, WINDOW_ORDER
        from apps.life.models import Routine

        state = build_routine_state(self.request.user)
        contract = state.get('_contract', {})
        summary = contract.get('summary', {})
        today = contract.get('today', {})
        items_by_window = today.get('items_by_window', {})

        # Build ordered list of windows for template iteration
        _routine_completion = today.get('routine_completion', {})
        windows = []
        for window_key in WINDOW_ORDER:
            items = items_by_window.get(window_key, [])
            completed_count = sum(1 for i in items if i.get('status') == 'completed')
            # Collect unique routines in this window with their completion state
            _window_routines = {}
            for item in items:
                rid = item.get('routine_id')
                if rid and rid not in _window_routines:
                    rc = _routine_completion.get(rid, {})
                    _window_routines[rid] = {
                        'id': rid,
                        'name': item.get('routine_name', ''),
                        'all_complete': rc.get('all_complete', False),
                        'completed_count': rc.get('completed_count', 0),
                        'total_count': rc.get('total_count', 0),
                    }
            windows.append({
                'key': window_key,
                'name': WINDOW_DISPLAY_NAMES.get(window_key, window_key.title()),
                'items': items,
                'completed_count': completed_count,
                'is_current': window_key == today.get('current_window'),
                'routines': list(_window_routines.values()),
            })

        context['windows'] = windows
        context['today_count'] = summary.get('today_count', 0)
        context['today_completed'] = summary.get('today_completed', 0)
        context['today_missed'] = summary.get('today_missed', 0)
        context['current_window'] = today.get('current_window')
        context['total_routines'] = summary.get('total_routines', 0)
        context['routine_completion'] = today.get('routine_completion', {})
        # All routines for manage panel (lightweight query)
        context['all_routines'] = Routine.objects.filter(
            user=self.request.user, is_active=True,
        ).order_by('sort_order', 'name')

        # Check for legacy routine tasks for migration prompt
        legacy_count = Task.objects.filter(
            user=self.request.user, is_routine=True,
            completion_status='pending',
        ).count()
        context['legacy_routine_count'] = legacy_count

        # Routine health signals (for badges/indicators)
        try:
            from apps.life.services.routine_health_service import evaluate_all_routine_health
            health_signals = evaluate_all_routine_health(self.request.user)
            # Index by schedule_id for template lookup
            context['routine_health'] = {
                rs['schedule_id']: rs['top_signal']
                for rs in health_signals
            }
        except Exception:
            context['routine_health'] = {}

        return context


class RoutineCreateView(HelpContextMixin, LifeAccessMixin, CreateView):
    """Create a new routine with schedule items."""
    model = Routine
    form_class = RoutineForm
    template_name = "life/routine_form.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        if self.request.POST:
            context['formset'] = RoutineScheduleFormSet(
                self.request.POST, instance=self.object
            )
        else:
            context['formset'] = RoutineScheduleFormSet(instance=self.object)
        context['is_edit'] = False
        return context

    def form_valid(self, form):
        form.instance.user = self.request.user
        # is_active checkbox is not rendered during create (only during edit),
        # so Django form binding sets it to False. Force True for new routines.
        form.instance.is_active = True
        self.object = form.save()

        formset = RoutineScheduleFormSet(self.request.POST, instance=self.object)
        if formset.is_valid():
            formset.save()
            _invalidate_routine_caches(self.request.user)
            messages.success(self.request, f"Routine '{self.object.name}' created.")
            return redirect('life:routine_list')
        else:
            return self.form_invalid(form)

    def get_success_url(self):
        return reverse('life:routine_list')


class RoutineUpdateView(HelpContextMixin, LifeAccessMixin, UpdateView):
    """Edit an existing routine and its schedule items."""
    model = Routine
    form_class = RoutineForm
    template_name = "life/routine_form.html"

    def get_queryset(self):
        return Routine.objects.filter(user=self.request.user)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        if self.request.POST:
            context['formset'] = RoutineScheduleFormSet(
                self.request.POST, instance=self.object
            )
        else:
            context['formset'] = RoutineScheduleFormSet(instance=self.object)
        context['is_edit'] = True
        return context

    def form_valid(self, form):
        self.object = form.save()

        formset = RoutineScheduleFormSet(self.request.POST, instance=self.object)
        if formset.is_valid():
            formset.save()
            _invalidate_routine_caches(self.request.user)
            messages.success(self.request, f"Routine '{self.object.name}' updated.")
            return redirect('life:routine_list')
        else:
            return self.form_invalid(form)

    def get_success_url(self):
        return reverse('life:routine_list')


class RoutineDeleteView(LifeAccessMixin, View):
    """Soft-delete a routine (POST only)."""

    def post(self, request, pk):
        routine = get_object_or_404(
            Routine.objects.filter(user=request.user), pk=pk
        )
        routine.soft_delete()
        _invalidate_routine_caches(request.user)
        messages.success(request, f"Routine '{routine.name}' deleted.")
        return redirect('life:routine_list')


class RoutineToggleView(LifeAccessMixin, View):
    """Toggle routine schedule completion for a given date.

    Delegates to routine_helpers.toggle_routine_completion() —
    the single source of truth for status transitions.
    """

    def post(self, request, *args, **kwargs):
        schedule_id = request.POST.get('schedule_id')
        date_str = request.POST.get('date')

        if not schedule_id:
            return JsonResponse({'success': False, 'error': 'Missing schedule_id'}, status=400)

        from apps.core.utils import get_user_today
        user_today = get_user_today(request.user)
        if date_str:
            from datetime import date as _date_cls
            try:
                target_date = _date_cls.fromisoformat(date_str)
            except ValueError:
                return JsonResponse({'success': False, 'error': 'Invalid date'}, status=400)
            if target_date > user_today:
                return JsonResponse(
                    {'success': False, 'error': 'Cannot complete a future date'},
                    status=400,
                )
        else:
            target_date = user_today

        schedule = get_object_or_404(
            RoutineSchedule.objects.select_related('routine'),
            pk=schedule_id,
            routine__user=request.user,
        )

        # completion_mode: 'scheduled' (on time), 'late' (now), or absent (auto)
        completion_mode = request.POST.get('completion_mode') or None

        from .services.routine_helpers import toggle_routine_completion
        result = toggle_routine_completion(
            request.user, schedule, target_date,
            completion_mode=completion_mode,
        )

        # Rebuild SAE execution state so CoS sees updated routine completion
        _invalidate_routine_caches(request.user)

        response_data = {
            'success': True,
            'schedule_id': int(schedule_id),
            'status': result['status'],
            'is_completed': result['is_completed'],
            'completed_as_scheduled': result.get('completed_as_scheduled', False),
            'timing': result.get('timing', ''),
            'is_user_corrected': result.get('is_user_corrected', False),
        }

        # Include maintenance bridge config when item is completed and bridge
        # is enabled — the frontend shows "Log maintenance?" prompt.
        # Suppress if maintenance was already logged for this item today.
        # Check both the RoutineLog flag AND if a MaintenanceLog exists
        # with this schedule_id for today (covers toggle uncomplete/re-complete).
        if result['is_completed'] and schedule.creates_maintenance_log:
            from apps.life.models import RoutineLog
            _already_logged = RoutineLog.objects.filter(
                schedule=schedule,
                scheduled_date=target_date,
                maintenance_logged=True,
            ).exists()
            if not _already_logged:
                _already_logged = MaintenanceLog.objects.filter(
                    user=request.user,
                    matched_schedule_id=schedule.pk,
                    date=target_date,
                ).exists()
            if not _already_logged:
                from datetime import timedelta
                follow_up_date = ''
                if schedule.follow_up_days:
                    follow_up_date = (
                        target_date + timedelta(days=schedule.follow_up_days)
                    ).isoformat()
                response_data['maintenance_config'] = {
                    'title': schedule.default_maintenance_title or schedule.name,
                    'log_type': schedule.maintenance_type or 'maintenance',
                    'area': schedule.maintenance_area or '',
                    'follow_up_date': follow_up_date,
                    'schedule_id': int(schedule_id),
                }

        return JsonResponse(response_data)


class RoutineToMaintenanceView(LifeAccessMixin, View):
    """Redirect from routine completion to prefilled maintenance form.

    Builds query params from the schedule's bridge config and redirects
    to the existing MaintenanceLogCreateView. Used by the "convert to
    maintenance" wrench icon on completed routine items.
    """

    def get(self, request, schedule_id):
        schedule = get_object_or_404(
            RoutineSchedule.objects.select_related('routine'),
            pk=schedule_id,
            routine__user=request.user,
        )
        if not schedule.creates_maintenance_log:
            messages.warning(
                request,
                "This routine item is not configured for maintenance logging.",
            )
            return redirect('life:routine_list')

        from datetime import timedelta
        from apps.core.utils import get_user_today
        from urllib.parse import urlencode

        params = {
            'title': schedule.default_maintenance_title or schedule.name,
            'log_type': schedule.maintenance_type or 'maintenance',
            'area': schedule.maintenance_area or '',
            'source': 'routine',
            'schedule_id': str(schedule.pk),
        }
        if schedule.follow_up_days:
            user_today = get_user_today(request.user)
            params['follow_up_date'] = (
                user_today + timedelta(days=schedule.follow_up_days)
            ).isoformat()

        url = reverse('life:maintenance_create') + '?' + urlencode(params)
        return redirect(url)


class RoutineAdherenceView(HelpContextMixin, LifeAccessMixin, TemplateView):
    """7-day adherence drilldown — shows raw missed items + grouped summary."""
    template_name = "life/routine_adherence.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        from apps.core.behavior.behavior_score_engine import (
            compute_adherence_summary, get_missed_items_detail, get_missed_items_raw,
        )
        context['adherence'] = compute_adherence_summary(self.request.user)
        context['missed_raw'] = get_missed_items_raw(self.request.user)
        context['missed_groups'] = get_missed_items_detail(self.request.user)

        # Group raw items by date for template rendering
        from itertools import groupby
        from operator import itemgetter
        grouped = []
        for date_key, items in groupby(context['missed_raw'], key=itemgetter('date')):
            grouped.append({
                'date': date_key,
                'items': list(items),
            })
        context['missed_by_date'] = grouped
        return context


class RoutineHistoryView(HelpContextMixin, LifeAccessMixin, TemplateView):
    """Date-navigable routine history with retroactive CRUD.

    Reconstructs the routine items that applied on a chosen past day and lets
    the user mark complete / undo / skip via the existing toggle + skip
    endpoints (which accept a `date` param). Retroactive completions are flagged
    is_user_corrected so historical truth is preserved — the UI distinguishes
    real-time completions from later corrections.
    """
    template_name = "life/routine_history.html"
    help_context_id = "ROUTINE_HISTORY"

    def get_context_data(self, **kwargs):
        from datetime import date as _date_cls, timedelta
        from apps.core.utils import get_user_today
        from apps.life.services.routine_helpers import get_routine_items_for_date

        context = super().get_context_data(**kwargs)
        user_today = get_user_today(self.request.user)

        date_str = self.request.GET.get('date')
        if date_str:
            try:
                target_date = _date_cls.fromisoformat(date_str)
            except ValueError:
                target_date = user_today - timedelta(days=1)
        else:
            target_date = user_today - timedelta(days=1)

        # Never let the history screen target a future day.
        if target_date > user_today:
            target_date = user_today

        history = get_routine_items_for_date(self.request.user, target_date)

        context['history'] = history
        context['target_date'] = target_date
        context['user_today'] = user_today
        context['is_today'] = target_date == user_today
        context['prev_date'] = target_date - timedelta(days=1)
        # next_date is only navigable up to today.
        context['next_date'] = (
            target_date + timedelta(days=1) if target_date < user_today else None
        )
        context['max_date'] = user_today.isoformat()
        return context


class RoutineSkipView(LifeAccessMixin, View):
    """Mark a routine schedule as skipped for a given date.

    Delegates to routine_helpers.skip_routine() —
    the single source of truth for status transitions.
    """

    def post(self, request, *args, **kwargs):
        schedule_id = request.POST.get('schedule_id')
        date_str = request.POST.get('date')

        if not schedule_id:
            return JsonResponse({'success': False, 'error': 'Missing schedule_id'}, status=400)

        from apps.core.utils import get_user_today
        user_today = get_user_today(request.user)
        if date_str:
            from datetime import date as _date_cls
            try:
                target_date = _date_cls.fromisoformat(date_str)
            except ValueError:
                return JsonResponse({'success': False, 'error': 'Invalid date'}, status=400)
            if target_date > user_today:
                return JsonResponse(
                    {'success': False, 'error': 'Cannot skip a future date'},
                    status=400,
                )
        else:
            target_date = user_today

        schedule = get_object_or_404(
            RoutineSchedule.objects.select_related('routine'),
            pk=schedule_id,
            routine__user=request.user,
        )

        from .services.routine_helpers import skip_routine
        result = skip_routine(request.user, schedule, target_date)

        # Rebuild SAE execution state so CoS sees updated routine status
        _invalidate_routine_caches(request.user)

        return JsonResponse({
            'success': True,
            'schedule_id': int(schedule_id),
            'status': 'skipped',
        })


class RoutineCompleteToggleView(LifeAccessMixin, View):
    """Toggle routine-level completion (check/uncheck all items).

    Routine-level checkbox: derives current state from item logs,
    then either completes all pending items or reverts all completions.
    Delegates to routine_helpers.toggle_routine_complete().
    """

    def post(self, request, routine_id):
        from apps.life.models import Routine
        from apps.life.services.routine_helpers import toggle_routine_complete
        from apps.core.utils import get_user_today

        routine = get_object_or_404(Routine, pk=routine_id, user=request.user)
        target_date = get_user_today(request.user)

        result = toggle_routine_complete(request.user, routine, target_date)
        _invalidate_routine_caches(request.user)

        return JsonResponse({
            'success': True,
            'routine_id': routine_id,
            'all_complete': result['all_complete'],
            'completed_count': result['completed_count'],
            'total_count': result['total_count'],
        })


class RoutineBulkActionView(LifeAccessMixin, View):
    """Section-level bulk actions for routine time windows.

    Mirrors the medicine module's bulk action pattern:
    - done_at_scheduled: mark all pending items as on_time at their scheduled time
    - complete_all: evaluate each item individually using grace window
    - skip_all: skip all pending items
    """

    def post(self, request, *args, **kwargs):
        from apps.core.utils import get_user_now, get_user_today
        from apps.life.models import RoutineLog, RoutineSchedule
        from apps.life.services.routine_helpers import (
            _compute_timing_and_performed_at, _get_scheduled_datetime,
            skip_routine, toggle_routine_completion,
        )

        window_key = request.POST.get('window_key')
        action = request.POST.get('action')

        if not window_key or action not in ('done_at_scheduled', 'complete_all', 'skip_all'):
            return JsonResponse({'success': False, 'error': 'Invalid parameters'}, status=400)

        user = request.user
        user_today = get_user_today(user)
        user_now = get_user_now(user)
        now = timezone.now()
        weekday = user_today.weekday()

        # Find all active routines in this time window
        from apps.life.models import Routine
        routines = Routine.objects.filter(
            user=user, is_active=True, time_of_day=window_key,
        ).prefetch_related('items')

        # Collect applicable schedules
        applicable = []
        for routine in routines:
            for item in routine.items.filter(is_active=True):
                if item.specific_date:
                    if item.specific_date != user_today:
                        continue
                elif not item.applies_to_day(weekday):
                    continue
                # Only binary routines — activity routines auto-complete
                if getattr(item, 'routine_type', 'binary') == 'activity':
                    continue
                applicable.append(item)

        # Filter to pending items (no completed log for today)
        schedule_ids = [item.id for item in applicable]
        existing_logs = set(
            RoutineLog.objects.filter(
                schedule_id__in=schedule_ids,
                scheduled_date=user_today,
                log_status__in=('completed', 'completed_late'),
            ).values_list('schedule_id', flat=True)
        )
        pending = [item for item in applicable if item.id not in existing_logs]

        results = []
        if action == 'done_at_scheduled':
            for item in pending:
                result = toggle_routine_completion(
                    user, item, user_today, completion_mode='scheduled',
                )
                results.append({
                    'schedule_id': item.id, 'status': result['status'],
                    'timing': result.get('timing', ''),
                })
        elif action == 'complete_all':
            for item in pending:
                result = toggle_routine_completion(
                    user, item, user_today, completion_mode=None,
                )
                results.append({
                    'schedule_id': item.id, 'status': result['status'],
                    'timing': result.get('timing', ''),
                })
        elif action == 'skip_all':
            for item in pending:
                skip_routine(user, item, user_today)
                results.append({
                    'schedule_id': item.id, 'status': 'skipped', 'timing': '',
                })

        _invalidate_routine_caches(user)

        return JsonResponse({
            'success': True,
            'action': action,
            'window_key': window_key,
            'results': results,
            'count': len(results),
        })


class RoutineMigrationView(HelpContextMixin, LifeAccessMixin, TemplateView):
    """
    Legacy migration tool: convert Task.is_routine tasks to canonical Routine objects.

    This is a one-way migration utility, not an ongoing dual-entry workflow.
    """
    template_name = "life/routine_migration.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['routine_tasks'] = Task.objects.filter(
            user=self.request.user,
            is_routine=True,
            completion_status='pending',
        ).order_by('scheduled_time', 'title')
        return context

    def post(self, request, *args, **kwargs):
        task_ids = request.POST.getlist('task_ids')
        if not task_ids:
            messages.warning(request, "No tasks selected for migration.")
            return redirect('life:routine_migration')

        tasks = Task.objects.filter(
            pk__in=task_ids,
            user=request.user,
            is_routine=True,
        )

        migrated = 0
        skipped = 0
        for task in tasks:
            # Idempotency check: skip if a routine with this exact name already exists
            if Routine.objects.filter(user=request.user, name=task.title).exists():
                skipped += 1
                continue

            # Determine time_of_day from scheduled_time using canonical windows
            time_of_day = 'morning'
            if task.scheduled_time:
                from apps.core.time_windows import get_window_for_hour
                window = get_window_for_hour(task.scheduled_time.hour)
                if window != 'other':
                    time_of_day = window

            # Create Routine
            routine = Routine.objects.create(
                user=request.user,
                name=task.title,
                description=task.notes or '',
                time_of_day=time_of_day,
                is_active=True,
            )

            # Create a single RoutineSchedule item
            RoutineSchedule.objects.create(
                routine=routine,
                name=task.title,
                scheduled_time=task.scheduled_time or timezone.now().time(),
                grace_period_minutes=30,
                days_of_week='0,1,2,3,4,5,6',  # Default: every day
                is_active=True,
            )

            # Mark legacy task as completed
            task.is_routine = False
            task.completion_status = 'completed'
            task.completed_at = timezone.now()
            task.save(update_fields=['is_routine', 'completion_status', 'completed_at', 'updated_at'])

            migrated += 1

        msg = f"Migrated {migrated} task(s) to routines."
        if skipped:
            msg += f" Skipped {skipped} (routine with same name already exists)."
        messages.success(request, msg)
        return redirect('life:routine_list')
