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

        # Goal Cockpit — three domain dials (faith, health, work)
        # Health reads from SAE canonical state; no live adherence computation needed.
        try:
            from .services.cockpit_service import GoalCockpitService
            cockpit = GoalCockpitService(self.request.user)
            context["cockpit"] = cockpit.get_cockpit_data()
        except Exception:
            logger.warning("Goal cockpit computation failed", exc_info=True)
            context["cockpit"] = None

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


# ── Cockpit Panel Endpoint ──────────────────────────────────────────


class CockpitPanelView(LoginRequiredMixin, View):
    """HTMX endpoint for cockpit domain expanded panel."""

    VALID_DOMAINS = ('faith', 'health', 'work')

    def get(self, request, domain):
        if domain not in self.VALID_DOMAINS:
            return HttpResponse("Invalid domain", status=400)

        from .services.cockpit_service import GoalCockpitService

        service = GoalCockpitService(request.user)
        data = service.get_domain_detail(domain)
        template = f"dashboard_v2/partials/cockpit_panels/{domain}_panel.html"
        html = render_to_string(template, {domain: data, "request": request}, request=request)
        return HttpResponse(html)


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
        return _render_action_center(request)


class SuggestionsSectionView(LoginRequiredMixin, View):
    """HTMX endpoint for signal suggestion cards."""

    def get(self, request):
        try:
            from apps.core.signals.signal_presenter import get_presented_signals

            result = get_presented_signals(request.user)
            suggestions = result.get("suggestions", [])
        except Exception:
            logger.error("Suggestions section: presenter failed", exc_info=True)
            suggestions = []

        html = render_to_string(
            "dashboard_v2/sections/suggestions.html",
            {"suggestions": suggestions, "request": request},
            request=request,
        )
        return HttpResponse(html)


class SignalInsightsSectionView(LoginRequiredMixin, View):
    """HTMX endpoint for signal insight panel."""

    def get(self, request):
        try:
            from apps.core.signals.insight_service import get_signal_insights

            insights = get_signal_insights(request.user)
        except Exception:
            logger.error("Signal insights section failed", exc_info=True)
            insights = {"reinforced": [], "suppressed": [], "neutral": [], "patterns": []}

        patterns = insights.get("patterns", [])
        has_insights = bool(
            insights["reinforced"] or insights["suppressed"]
            or insights["neutral"] or patterns
        )
        html = render_to_string(
            "dashboard_v2/sections/signal_insights.html",
            {
                "has_insights": has_insights,
                "reinforced": insights["reinforced"],
                "suppressed": insights["suppressed"],
                "neutral": insights["neutral"],
                "patterns": patterns,
                "request": request,
            },
            request=request,
        )
        return HttpResponse(html)


# Backward compat alias
NextActionSectionView = ActionCenterSectionView


# ── Physical Intelligence Section ──────────────────────────────────


class PhysicalIntelligenceSectionView(LoginRequiredMixin, View):
    """HTMX endpoint for Physical Intelligence coach panel.

    Reads pre-computed PhysicalDecision from SAE state.
    Zero computation — display only.
    """

    def get(self, request):
        pi = None
        try:
            from apps.core.ai_state.state_engine import get_module_state

            health_state = get_module_state(request.user, "health") or {}
            pi = health_state.get("physical_decision")
        except ImportError:
            pass
        except Exception:
            logger.warning("Physical Intelligence section failed", exc_info=True)

        # Build display context from pre-computed decision
        ctx = self._build_display_context(pi)
        ctx["request"] = request

        html = render_to_string(
            "dashboard_v2/sections/physical_intelligence.html",
            ctx,
            request=request,
        )
        return HttpResponse(html)

    def _build_display_context(self, pi):
        """Transform PhysicalDecision dict into display-ready context.

        No computation. Only formatting and label mapping.
        """
        if not pi or pi.get("decision_type") == "fallback":
            return {"pi_available": False}

        body_comp = pi.get("body_composition") or {}

        # ── Verdict display ──
        outcome_status = pi.get("outcome_status")
        VERDICT_LABELS = {
            "working": "Working",
            "partial": "Partially Working",
            "not_working": "Not Working",
            "unknown": "Unknown",
            "too_early": "Building Baseline",
            None: "No Active Goal",
        }
        VERDICT_CSS = {
            "working": "pi-verdict-good",
            "partial": "pi-verdict-mixed",
            "not_working": "pi-verdict-bad",
            "unknown": "pi-verdict-neutral",
            "too_early": "pi-verdict-neutral",
            None: "pi-verdict-neutral",
        }

        # ── Trajectory display ──
        trajectory = pi.get("goal_trajectory")
        TRAJECTORY_LABELS = {
            "ahead": "Ahead of Schedule",
            "on_pace": "On Pace",
            "behind": "Behind",
            "off_track": "Off Track",
            None: "",
        }
        TRAJECTORY_ICONS = {
            "ahead": "\u2191\u2191",    # ↑↑
            "on_pace": "\u2192",        # →
            "behind": "\u2193",         # ↓
            "off_track": "\u2193\u2193", # ↓↓
            None: "",
        }
        TRAJECTORY_CSS = {
            "ahead": "pi-trend-good",
            "on_pace": "pi-trend-good",
            "behind": "pi-trend-bad",
            "off_track": "pi-trend-bad",
            None: "",
        }

        # ── Confidence display ──
        confidence = pi.get("confidence", "low")
        CONFIDENCE_LABELS = {
            "high": "High Confidence",
            "medium": "Moderate Confidence",
            "low": "Low Confidence",
        }

        # ── Body signals ──
        fat_loss = body_comp.get("fat_loss_status", "no_data")
        muscle = body_comp.get("muscle_gain_status", "no_data")
        plateau = body_comp.get("plateau_status", "none")

        SIGNAL_ICONS = {
            "confirmed": "\u2193",       # ↓ (losing fat = good)
            "likely": "\u2198",          # ↘
            "not_confirmed": "\u2192",   # →
            "stalled": "\u2192",         # →
            "reversed": "\u2191",        # ↑ (gaining fat = bad)
            "gaining": "\u2191",         # ↑
            "maintaining": "\u2192",     # →
            "losing": "\u2193",          # ↓
            "unclear": "?",
            "no_data": "\u2014",         # —
        }
        SIGNAL_CSS = {
            "confirmed": "pi-signal-good",
            "likely": "pi-signal-good",
            "not_confirmed": "pi-signal-neutral",
            "stalled": "pi-signal-warn",
            "reversed": "pi-signal-bad",
            "gaining": "pi-signal-good",
            "maintaining": "pi-signal-neutral",
            "losing": "pi-signal-bad",
            "unclear": "pi-signal-neutral",
            "no_data": "pi-signal-neutral",
        }

        FAT_LABELS = {
            "confirmed": "Losing Fat",
            "likely": "Likely Losing",
            "not_confirmed": "Flat",
            "stalled": "Stalled",
            "reversed": "Gaining",
            "no_data": "No Data",
        }
        MUSCLE_LABELS = {
            "gaining": "Gaining",
            "maintaining": "Holding",
            "losing": "Losing",
            "unclear": "Unclear",
            "no_data": "No Data",
        }

        # ── Urgency display ──
        urgency = pi.get("urgency", "this_week")
        URGENCY_LABELS = {
            "immediate": "Now",
            "today": "Today",
            "this_week": "This Week",
        }
        URGENCY_CSS = {
            "immediate": "pi-urgency-now",
            "today": "pi-urgency-today",
            "this_week": "pi-urgency-week",
        }

        # ── Conflicts ──
        conflicts = pi.get("conflicts") or []
        display_conflicts = []
        for c in conflicts[:2]:
            display_conflicts.append(
                {
                    "description": c.get("description", ""),
                    "resolution": c.get("resolution", ""),
                    "positive": c.get("positive", False),
                    "css": "pi-conflict-positive" if c.get("positive") else "pi-conflict-warning",
                }
            )

        # ── Protocol expired special case ──
        is_expired = pi.get("decision_type") == "protocol_expired"

        return {
            "pi_available": True,
            "is_expired": is_expired,
            # Verdict
            "verdict_label": VERDICT_LABELS.get(outcome_status, "Unknown"),
            "verdict_css": VERDICT_CSS.get(outcome_status, "pi-verdict-neutral"),
            # Trajectory
            "trajectory_label": TRAJECTORY_LABELS.get(trajectory, ""),
            "trajectory_icon": TRAJECTORY_ICONS.get(trajectory, ""),
            "trajectory_css": TRAJECTORY_CSS.get(trajectory, ""),
            "trajectory_detail": pi.get("trajectory_detail", ""),
            # Confidence
            "confidence_label": CONFIDENCE_LABELS.get(confidence, "Low Confidence"),
            "confidence_value": confidence,
            # Decision / Action
            "summary": pi.get("summary", ""),
            "recommended_action": pi.get("recommended_action", ""),
            "urgency_label": URGENCY_LABELS.get(urgency, ""),
            "urgency_css": URGENCY_CSS.get(urgency, ""),
            "decision_type": pi.get("decision_type", "on_track"),
            "impact_statement": pi.get("impact_statement", ""),
            # Body signals
            "fat_loss_label": FAT_LABELS.get(fat_loss, "No Data"),
            "fat_loss_icon": SIGNAL_ICONS.get(fat_loss, "\u2014"),
            "fat_loss_css": SIGNAL_CSS.get(fat_loss, "pi-signal-neutral"),
            "muscle_label": MUSCLE_LABELS.get(muscle, "No Data"),
            "muscle_icon": SIGNAL_ICONS.get(muscle, "\u2014"),
            "muscle_css": SIGNAL_CSS.get(muscle, "pi-signal-neutral"),
            "weight_trend": body_comp.get("weight_trend"),
            "waist_trend": body_comp.get("waist_trend"),
            "plateau_active": plateau in ("confirmed", "possible"),
            "plateau_days": body_comp.get("plateau_days", 0),
            # Conflicts
            "conflicts": display_conflicts,
            "has_conflicts": bool(display_conflicts),
        }


# ── Morning Reconciliation ──────────────────────────────────────────


class ReconciliationSectionView(LoginRequiredMixin, View):
    """HTMX endpoint for morning reconciliation (yesterday's missing items)."""

    def get(self, request):
        try:
            from apps.life.services.morning_reconciliation import (
                get_reconciliation_context,
            )

            ctx = get_reconciliation_context(request.user)
        except Exception:
            logger.error("Reconciliation section failed", exc_info=True)
            ctx = {"show": False, "items": [], "yesterday_date": ""}

        html = render_to_string(
            "dashboard_v2/sections/reconciliation.html",
            {"reconciliation": ctx, "request": request},
            request=request,
        )
        return HttpResponse(html)


class ReconciliationRespondView(LoginRequiredMixin, View):
    """POST endpoint for reconciliation item responses.

    Accepts: schedule_id, response (on_schedule, later, skip), date (yesterday).
    Routes through existing execution services — never creates new logic paths.
    """

    def post(self, request):
        from datetime import date as _date_cls

        from apps.life.models import RoutineSchedule
        from apps.life.services.morning_reconciliation import (
            get_yesterdays_missing_items,
            mark_reconciliation_shown,
        )

        schedule_id = request.POST.get("schedule_id")
        response_type = request.POST.get("response")
        date_str = request.POST.get("date")

        if not schedule_id or response_type not in ("on_schedule", "later", "skip"):
            return JsonResponse(
                {"success": False, "error": "Invalid parameters"}, status=400
            )

        try:
            target_date = _date_cls.fromisoformat(date_str) if date_str else None
        except (ValueError, TypeError):
            return JsonResponse(
                {"success": False, "error": "Invalid date"}, status=400
            )

        if not target_date:
            from apps.core.utils import get_user_today
            from datetime import timedelta

            target_date = get_user_today(request.user) - timedelta(days=1)

        schedule = get_object_or_404(
            RoutineSchedule.objects.select_related("routine"),
            pk=schedule_id,
            routine__user=request.user,
        )

        if response_type == "on_schedule":
            from apps.life.services.routine_helpers import toggle_routine_completion

            result = toggle_routine_completion(
                request.user, schedule, target_date,
                completion_mode="scheduled",
            )
        elif response_type == "later":
            from apps.life.services.routine_helpers import toggle_routine_completion

            result = toggle_routine_completion(
                request.user, schedule, target_date,
                completion_mode="late",
            )
        elif response_type == "skip":
            from apps.life.services.routine_helpers import skip_routine

            skip_routine(request.user, schedule, target_date)
            result = {"status": "skipped"}

        # Check if all items are now resolved — if so, mark reconciliation done
        remaining = get_yesterdays_missing_items(request.user)
        if not remaining:
            mark_reconciliation_shown(request.user)

        return JsonResponse({
            "success": True,
            "schedule_id": int(schedule_id),
            "response": response_type,
            "status": result.get("status", ""),
            "remaining": len(remaining),
        })


# ── Action Endpoints ─────────────────────────────────────────────────


def _render_action_center(request):
    """Shared helper: invalidate cache, rebuild execution context,
    render the unified action center template.

    All toggle actions (task, routine, medicine) use this to return
    the full action center as a single HTMX swap target.
    """
    DashboardV2CacheService.invalidate(request.user.pk, "execution")
    service = DashboardV2Service(request.user)
    # Ensure daily progress is available for binary domain items
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


class TaskToggleAction(LoginRequiredMixin, View):
    """HTMX POST endpoint to toggle task completion from dashboard."""

    def post(self, request, pk):
        from apps.life.models import Task

        task = get_object_or_404(Task, pk=pk, user=request.user)

        if task.completion_status == "completed":
            task.mark_incomplete()
        else:
            task.mark_complete()

        # Invalidate cache and return the unified action center
        return _render_action_center(request)


class MedicineLogAction(LoginRequiredMixin, View):
    """HTMX POST endpoint to log medicine dose from dashboard.

    Matches canonical MedicineTakeView behavior:
    - Sets scheduled_time on log
    - Uses mark_taken() for late/on-time classification
    - Decrements supply if tracked
    - Fires medication taken event
    """

    def post(self, request, schedule_id):
        from apps.core.events.domain_events import EventTypes, safe_emit_event
        from apps.core.utils import get_user_today
        from apps.health.models import MedicineLog, MedicineSchedule

        schedule = get_object_or_404(
            MedicineSchedule.objects.select_related("medicine"),
            pk=schedule_id,
            medicine__user=request.user,
        )
        today = get_user_today(request.user)
        medicine = schedule.medicine

        # Validate schedule applies to today
        if not schedule.applies_to_day(today.weekday()):
            return _render_action_center(request)

        # Check if already logged
        existing = MedicineLog.objects.filter(
            user=request.user,
            medicine=medicine,
            schedule=schedule,
            scheduled_date=today,
            log_status__in=["taken", "late"],
        ).first()

        if existing:
            # Undo: delete log and restore supply
            existing.delete()
            if medicine.current_supply is not None:
                medicine.current_supply += 1
                medicine.save(update_fields=["current_supply", "updated_at"])
        else:
            # Create log with canonical fields
            log, _created = MedicineLog.objects.get_or_create(
                user=request.user,
                medicine=medicine,
                schedule=schedule,
                scheduled_date=today,
                defaults={
                    "scheduled_time": schedule.scheduled_time,
                    "is_prn_dose": False,
                },
            )
            # mark_taken handles late/on-time classification via grace period
            log.mark_taken()

            # Decrement supply if tracked
            if medicine.current_supply is not None and medicine.current_supply > 0:
                medicine.current_supply -= 1
                medicine.save(update_fields=["current_supply", "updated_at"])

            # Fire event for signal pipeline
            safe_emit_event(EventTypes.HEALTH_MEDICATION_TAKEN, request.user, {
                "log_id": log.id, "medicine_name": medicine.name,
                "source": "dashboard_action_center",
            })

        # Return unified action center
        return _render_action_center(request)


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

        # Invalidate cache and return the unified action center
        return _render_action_center(request)


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

        # Invalidate cache and return the unified action center
        return _render_action_center(request)


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

        # Invalidate cache and return the unified action center
        return _render_action_center(request)


class MedicineGroupLogAction(LoginRequiredMixin, View):
    """HTMX POST endpoint to log/unlog all medicines in a time_of_day group.

    Matches canonical MedicineBulkTakeView behavior:
    - Filters by days_of_week (only schedules applicable today)
    - Sets scheduled_time on each log
    - Uses mark_taken() for late/on-time classification
    - Decrements supply per medicine
    - Fires medication taken event
    """

    def post(self, request, time_of_day):
        from apps.core.events.domain_events import EventTypes, safe_emit_event
        from apps.health.models import Medicine, MedicineLog, MedicineSchedule

        today = get_user_today(request.user)

        # Get all active, non-PRN schedules for this time_of_day
        schedules = list(
            MedicineSchedule.objects.filter(
                medicine__user=request.user,
                medicine__medicine_status=Medicine.STATUS_ACTIVE,
                medicine__is_prn=False,
                is_active=True,
                time_of_day=time_of_day,
            ).select_related("medicine")
        )

        # Filter to schedules that apply today (day-of-week check)
        applicable = [s for s in schedules if s.applies_to_day(today.weekday())]

        if not applicable:
            return _render_action_center(request)

        applicable_pks = {s.pk for s in applicable}

        # Check if ALL applicable are already logged
        today_logs = set(
            MedicineLog.objects.filter(
                user=request.user,
                scheduled_date=today,
                log_status__in=["taken", "late"],
                schedule_id__in=applicable_pks,
            ).values_list("schedule_id", flat=True)
        )
        all_taken = len(today_logs) >= len(applicable)

        if all_taken:
            # Undo: delete logs and restore supply
            logs_to_delete = MedicineLog.objects.filter(
                user=request.user,
                scheduled_date=today,
                log_status__in=["taken", "late"],
                schedule_id__in=applicable_pks,
            ).select_related("medicine")

            # Restore supply per medicine before deleting
            for log in logs_to_delete:
                med = log.medicine
                if med.current_supply is not None:
                    med.current_supply += 1
                    med.save(update_fields=["current_supply", "updated_at"])

            logs_to_delete.delete()
        else:
            # Log missing ones — matching canonical MedicineBulkTakeView
            taken_count = 0
            for schedule in applicable:
                if schedule.pk in today_logs:
                    continue  # Already handled

                # Check for any existing log (taken/late/skipped/missed)
                existing_log = MedicineLog.objects.filter(
                    medicine=schedule.medicine,
                    schedule=schedule,
                    scheduled_date=today,
                ).first()

                if existing_log and existing_log.log_status in [
                    MedicineLog.STATUS_TAKEN,
                    MedicineLog.STATUS_LATE,
                    MedicineLog.STATUS_SKIPPED,
                ]:
                    continue  # Already handled (skipped counts as handled)

                # Create or update log with canonical fields
                log, _created = MedicineLog.objects.get_or_create(
                    user=request.user,
                    medicine=schedule.medicine,
                    schedule=schedule,
                    scheduled_date=today,
                    defaults={
                        "scheduled_time": schedule.scheduled_time,
                        "is_prn_dose": False,
                    },
                )
                # mark_taken handles late/on-time classification
                log.mark_taken()
                taken_count += 1

                # Decrement supply if tracked
                med = schedule.medicine
                if med.current_supply is not None and med.current_supply > 0:
                    med.current_supply -= 1
                    med.save(update_fields=["current_supply", "updated_at"])

            if taken_count > 0:
                safe_emit_event(EventTypes.HEALTH_MEDICATION_TAKEN, request.user, {
                    "count": taken_count, "time_of_day": time_of_day,
                    "source": "dashboard_action_center_bulk",
                })

        # Invalidate cache and return the unified action center
        return _render_action_center(request)


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


# ── Compliance Drill-Down ───────────────────────────────────────────


class ComplianceDetailView(LoginRequiredMixin, TemplateView):
    """
    Drill-down view for a compliance card.

    Shows itemized audit rows grouped by date, with status explanations.
    Triggered via HTMX when clicking a compliance card on V2.
    """

    template_name = "dashboard_v2/compliance/detail.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        bucket = self.kwargs.get("bucket", "")
        status_filter = self.request.GET.get("status")

        from apps.dashboard_v2.compliance.constants import (
            SCORING_BUCKET_CHOICES,
            FINAL_STATUS_CHOICES,
        )
        from apps.dashboard_v2.compliance.service import ComplianceService

        svc = ComplianceService(self.request.user)

        # Ensure events are fresh (cached — won't recompute every request)
        svc.ensure_evaluated()

        # Get rollup summary for header
        rollup = svc.get_rollup(bucket)

        # Get detail rows
        detail_groups = svc.get_detail(bucket, status_filter=status_filter)

        # Bucket label
        bucket_labels = dict(SCORING_BUCKET_CHOICES)
        bucket_label = bucket_labels.get(bucket, bucket)

        context.update({
            "bucket": bucket,
            "bucket_label": bucket_label,
            "rollup": rollup,
            "detail_groups": detail_groups,
            "status_filter": status_filter or "all",
            "status_options": [
                ("all", "All"),
                ("missed", "Missed"),
                ("completed_late", "Late"),
                ("skipped", "Skipped"),
                ("overdue", "Overdue"),
                ("completed", "Completed"),
            ],
        })
        return context
