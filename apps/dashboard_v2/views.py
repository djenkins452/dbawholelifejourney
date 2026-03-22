"""
Dashboard V2 Views — Life Command Center.

Main view delivers critical-path data synchronously.
HTMX section endpoints deliver remaining data asynchronously.
Action endpoints handle inline task/medicine/routine interactions.
"""

import logging

from django.contrib.auth.mixins import LoginRequiredMixin
from django.http import HttpResponse, HttpResponseNotAllowed, JsonResponse
from django.shortcuts import get_object_or_404
from django.template.loader import render_to_string
from django.utils import timezone
from django.views import View
from django.views.generic import TemplateView

from apps.core.utils import get_user_today
from apps.help.mixins import HelpContextMixin

from .cache import DashboardV2CacheService
from .services.dashboard_service import DashboardV2Service

logger = logging.getLogger(__name__)


# ── Main Dashboard View ─────────────────────────────────────────────


class DashboardV2View(HelpContextMixin, LoginRequiredMixin, TemplateView):
    """Main dashboard shell. Delivers critical-path data synchronously."""

    template_name = "dashboard_v2/home.html"
    help_context_id = "DASHBOARD_V2_HOME"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)

        # ?refresh=1 bypasses cache for action center + daily progress
        # (used when returning to dashboard after acting externally)
        force_refresh = self.request.GET.get("refresh") == "1"
        if force_refresh:
            DashboardV2CacheService.invalidate(self.request.user.pk, "execution")

        service = DashboardV2Service(self.request.user)
        context.update(service.get_critical_context())

        # Module flags for conditional rendering
        prefs = self.request.user.preferences
        context["health_enabled"] = getattr(prefs, "health_enabled", True)
        context["journal_enabled"] = getattr(prefs, "journal_enabled", True)
        context["faith_enabled"] = getattr(prefs, "faith_enabled", True)
        context["purpose_enabled"] = getattr(prefs, "purpose_enabled", True)
        context["life_enabled"] = getattr(prefs, "life_enabled", True)

        # 7-day adherence score (replaces momentum dial as primary metric)
        try:
            from apps.core.behavior.behavior_score_engine import compute_adherence_summary
            context["adherence"] = compute_adherence_summary(self.request.user)
        except Exception:
            context["adherence"] = None

        # Weather data
        try:
            location_city = getattr(prefs, 'location_city', '') or ''
            if location_city:
                from apps.dashboard.services.weather import weather_service
                weather_data = weather_service.get_weather_data(location_city)
                if weather_data:
                    wd = weather_data.to_dict()
                    # Add clickable weather URL
                    from urllib.parse import quote_plus
                    wd['weather_url'] = (
                        f"https://weather.com/weather/today/l/{quote_plus(location_city)}"
                    )
                    context["weather"] = wd
        except Exception:
            pass

        return context


# ── HTMX Section Endpoints ──────────────────────────────────────────


class ExecutionSectionView(LoginRequiredMixin, TemplateView):
    """HTMX endpoint for today's execution layer."""

    template_name = "dashboard_v2/sections/execution.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        service = DashboardV2Service(self.request.user)
        context.update(service.get_execution_context())
        return context


class StatePanelView(LoginRequiredMixin, TemplateView):
    """HTMX endpoint for current state telemetry."""

    template_name = "dashboard_v2/sections/state_panel.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        service = DashboardV2Service(self.request.user)
        context.update(service.get_state_panel_context())
        return context


class CelebrationSectionView(LoginRequiredMixin, TemplateView):
    """HTMX endpoint for celebration button (or empty if none ready)."""

    template_name = "dashboard_v2/sections/celebration.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        service = DashboardV2Service(self.request.user)
        context.update(service.get_celebration_context())
        return context


class InsightsSectionView(LoginRequiredMixin, TemplateView):
    """HTMX endpoint for guidance, predictions, insights."""

    template_name = "dashboard_v2/sections/insights.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        service = DashboardV2Service(self.request.user)
        context.update(service.get_insights_context())
        return context


class ActionCenterSectionView(LoginRequiredMixin, View):
    """HTMX endpoint for the Action Center (refreshed after inline actions)."""

    def get(self, request):
        service = DashboardV2Service(request.user)
        # Ensure daily progress is available for action center binary items
        from .services.daily_progress_service import DailyProgressService
        progress_service = DailyProgressService(request.user)
        service._daily_progress = progress_service.get_today()

        exec_ctx = service.get_execution_context()
        html = render_to_string(
            "dashboard_v2/partials/action_center.html",
            {**exec_ctx, "request": request},
            request=request,
        )
        return HttpResponse(html)


# Backward compat alias
NextActionSectionView = ActionCenterSectionView


# ── Action Endpoints ─────────────────────────────────────────────────


class TaskToggleAction(LoginRequiredMixin, View):
    """HTMX POST endpoint to toggle task completion from dashboard."""

    def post(self, request, pk):
        from apps.life.models import Task

        task = get_object_or_404(Task, pk=pk, user=request.user)

        if task.completion_status == "completed":
            task.mark_incomplete()
        else:
            task.mark_complete()

        # Invalidate cache and return full schedule card
        DashboardV2CacheService.invalidate(request.user.pk, "execution")
        service = DashboardV2Service(request.user)
        exec_ctx = service.get_execution_context()

        html = render_to_string(
            "dashboard_v2/partials/schedule_card.html",
            {**exec_ctx, "request": request},
            request=request,
        )
        response = HttpResponse(html)
        response["HX-Trigger"] = "refresh-next-action"
        return response


class MedicineLogAction(LoginRequiredMixin, View):
    """HTMX POST endpoint to log medicine dose from dashboard."""

    def post(self, request, schedule_id):
        from apps.core.utils import get_user_today
        from apps.health.models import MedicineLog, MedicineSchedule

        schedule = get_object_or_404(
            MedicineSchedule,
            pk=schedule_id,
            medicine__user=request.user,
        )
        today = get_user_today(request.user)

        # Check if already logged
        existing = MedicineLog.objects.filter(
            user=request.user,
            medicine=schedule.medicine,
            schedule=schedule,
            scheduled_date=today,
            log_status__in=["taken", "late"],
        ).first()

        if existing:
            # Un-log: delete the log entry
            existing.delete()
            taken = False
        else:
            # Log as taken
            MedicineLog.objects.create(
                user=request.user,
                medicine=schedule.medicine,
                schedule=schedule,
                scheduled_date=today,
                log_status="taken",
                taken_at=timezone.now(),
            )
            taken = True

        html = render_to_string(
            "dashboard_v2/partials/medicine_row.html",
            {
                "item": {
                    "medicine": schedule.medicine,
                    "schedule": schedule,
                    "taken": taken,
                },
                "request": request,
            },
            request=request,
        )
        return HttpResponse(html)


class RoutineCompleteAction(LoginRequiredMixin, View):
    """HTMX POST endpoint to complete a routine task."""

    def post(self, request, pk):
        from apps.life.models import Task

        task = get_object_or_404(
            Task, pk=pk, user=request.user, is_routine=True
        )

        if task.completion_status == "completed":
            task.mark_incomplete()
        else:
            task.mark_complete()

        # Invalidate cache and return full routine card
        DashboardV2CacheService.invalidate(request.user.pk, "execution")
        service = DashboardV2Service(request.user)
        exec_ctx = service.get_execution_context()

        html = render_to_string(
            "dashboard_v2/partials/routine_card.html",
            {**exec_ctx, "request": request},
            request=request,
        )
        response = HttpResponse(html)
        response["HX-Trigger"] = "refresh-next-action"
        return response


class RoutineScheduleToggleAction(LoginRequiredMixin, View):
    """HTMX POST endpoint to toggle a RoutineSchedule item completion.

    This handles the canonical Routine model items (not legacy Task-based routines).
    """

    def post(self, request, schedule_id):
        from apps.core.utils import get_user_today
        from apps.life.models import RoutineSchedule
        from apps.life.services.routine_helpers import toggle_routine_completion

        schedule = get_object_or_404(
            RoutineSchedule.objects.select_related('routine'),
            pk=schedule_id,
            routine__user=request.user,
        )

        today = get_user_today(request.user)
        toggle_routine_completion(request.user, schedule, today)

        # Invalidate cache and return full routine card
        DashboardV2CacheService.invalidate(request.user.pk, "execution")
        service = DashboardV2Service(request.user)
        exec_ctx = service.get_execution_context()

        html = render_to_string(
            "dashboard_v2/partials/routine_card.html",
            {**exec_ctx, "request": request},
            request=request,
        )
        response = HttpResponse(html)
        response["HX-Trigger"] = "refresh-next-action"
        return response


class RoutineCompleteToggleAction(LoginRequiredMixin, View):
    """HTMX POST endpoint to toggle routine-level completion (all items).

    Routine-level checkbox: derives current state from item logs,
    then either completes all pending items or reverts all completions.
    """

    def post(self, request, routine_id):
        from apps.core.utils import get_user_today
        from apps.life.models import Routine
        from apps.life.services.routine_helpers import toggle_routine_complete

        routine = get_object_or_404(Routine, pk=routine_id, user=request.user)
        today = get_user_today(request.user)
        toggle_routine_complete(request.user, routine, today)

        # Invalidate cache and return full routine card
        DashboardV2CacheService.invalidate(request.user.pk, "execution")
        service = DashboardV2Service(request.user)
        exec_ctx = service.get_execution_context()

        html = render_to_string(
            "dashboard_v2/partials/routine_card.html",
            {**exec_ctx, "request": request},
            request=request,
        )
        response = HttpResponse(html)
        response["HX-Trigger"] = "refresh-next-action"
        return response


class MedicineGroupLogAction(LoginRequiredMixin, View):
    """HTMX POST endpoint to log/unlog all medicines in a time_of_day group."""

    def post(self, request, time_of_day):
        from apps.health.models import Medicine, MedicineLog, MedicineSchedule

        today = get_user_today(request.user)

        # Get all active schedules for this time_of_day
        schedules = MedicineSchedule.objects.filter(
            medicine__user=request.user,
            medicine__medicine_status=Medicine.STATUS_ACTIVE,
            time_of_day=time_of_day,
        ).select_related("medicine")

        if not schedules.exists():
            return HttpResponse(status=404)

        # Check if ALL are already logged
        today_logs = set(
            MedicineLog.objects.filter(
                user=request.user,
                scheduled_date=today,
                log_status__in=["taken", "late"],
                schedule__in=schedules,
            ).values_list("schedule_id", flat=True)
        )
        all_taken = len(today_logs) == schedules.count()

        if all_taken:
            # Un-log all
            MedicineLog.objects.filter(
                user=request.user,
                scheduled_date=today,
                log_status__in=["taken", "late"],
                schedule__in=schedules,
            ).delete()
        else:
            # Log missing ones
            now = timezone.now()
            for schedule in schedules:
                if schedule.pk not in today_logs:
                    MedicineLog.objects.create(
                        user=request.user,
                        medicine=schedule.medicine,
                        schedule=schedule,
                        scheduled_date=today,
                        log_status="taken",
                        taken_at=now,
                    )

        # Invalidate cache and re-render medicine card
        DashboardV2CacheService.invalidate(request.user.pk, "execution")
        service = DashboardV2Service(request.user)
        exec_ctx = service.get_execution_context()

        html = render_to_string(
            "dashboard_v2/partials/medicine_card.html",
            {**exec_ctx, "request": request},
            request=request,
        )
        response = HttpResponse(html)
        response["HX-Trigger"] = "refresh-next-action"
        return response


# ── Celebration Endpoints ────────────────────────────────────────────


class CelebrationRevealView(LoginRequiredMixin, View):
    """Reveal a prepared celebration."""

    def post(self, request, pk):
        from .models import PreparedCelebration

        celebration = get_object_or_404(
            PreparedCelebration, pk=pk, user=request.user, celebration_status="ready"
        )
        celebration.reveal()

        html = render_to_string(
            "dashboard_v2/partials/celebration_modal.html",
            {"celebration": celebration},
            request=request,
        )
        return HttpResponse(html)


class CelebrationDismissView(LoginRequiredMixin, View):
    """Dismiss a celebration."""

    def post(self, request, pk):
        from .models import PreparedCelebration

        celebration = get_object_or_404(
            PreparedCelebration, pk=pk, user=request.user
        )
        celebration.dismiss()
        return HttpResponse("")
