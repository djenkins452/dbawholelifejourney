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

        # Goal Cockpit — dynamic domain dials driven by user's active goals and SAE signals
        try:
            from .services.cockpit_service import GoalCockpitService
            cockpit = GoalCockpitService(self.request.user)
            context["cockpit_domains"] = cockpit.get_cockpit_data()
        except Exception:
            logger.warning("Goal cockpit computation failed", exc_info=True)
            context["cockpit_domains"] = []

        # Weather data
        try:
            location_city = getattr(prefs, 'location_city', '') or ''
            if location_city:
                from apps.dashboard.services.weather import weather_service
                weather_data = weather_service.get_weather_data(location_city)
                if weather_data:
                    # weather_url is now built inside to_dict() using lat/lon
                    context["weather"] = weather_data.to_dict()
        except Exception:
            pass

        # Water tracking tile
        if getattr(prefs, 'health_enabled', True):
            try:
                from apps.health.models import WaterEntry
                from apps.core.utils import get_user_now
                from datetime import timedelta

                today = get_user_now(self.request.user).date()
                progress = WaterEntry.get_daily_goal_progress(
                    self.request.user, today
                )
                week_ago = today - timedelta(days=7)
                week_entries = WaterEntry.objects.filter(
                    user=self.request.user,
                    logged_date__gte=week_ago,
                    logged_date__lte=today,
                )
                avg_water_oz = None
                if week_entries.exists():
                    daily_totals = {}
                    for entry in week_entries:
                        daily_totals[entry.logged_date] = (
                            daily_totals.get(entry.logged_date, 0)
                            + entry.amount_oz
                        )
                    avg_water_oz = round(
                        sum(daily_totals.values()) / len(daily_totals), 1
                    )

                entry_count = WaterEntry.objects.filter(
                    user=self.request.user
                ).count()

                context["water_data"] = {
                    "total_oz": progress["total_oz"],
                    "raw_total_oz": progress["raw_total_oz"],
                    "goal_oz": progress["goal_oz"],
                    "percentage": progress["percentage"],
                    "goal_met": progress["goal_met"],
                    "avg_water_oz": avg_water_oz,
                    "entry_count": entry_count,
                }
            except Exception:
                logger.warning("Water data error", exc_info=True)

        return context


# ── Cockpit Panel Endpoint ──────────────────────────────────────────


class CockpitPanelView(LoginRequiredMixin, View):
    """HTMX endpoint for cockpit domain expanded panel."""

    # Domain-specific panel templates (rich detail views)
    PANEL_TEMPLATES = {
        'faith': 'dashboard_v2/partials/cockpit_panels/faith_panel.html',
        'health': 'dashboard_v2/partials/cockpit_panels/health_panel.html',
        'work': 'dashboard_v2/partials/cockpit_panels/work_panel.html',
    }

    def get(self, request, domain):
        from .services.cockpit_service import GoalCockpitService

        # Validate against user's actual active domains (not a hardcoded list)
        service = GoalCockpitService(request.user)
        active_slugs = service.get_active_domain_slugs()
        if domain not in active_slugs:
            return HttpResponse("Invalid domain", status=400)

        data = service.get_domain_detail(domain)

        # Use domain-specific template if available, otherwise generic
        template = self.PANEL_TEMPLATES.get(
            domain,
            'dashboard_v2/partials/cockpit_panels/generic_panel.html',
        )
        html = render_to_string(
            template,
            {domain: data, 'domain_data': data, "request": request},
            request=request,
        )
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
            # Vitals snapshot (glucose, BP, HR)
            "vitals": pi.get("vitals_snapshot") or [],
            "has_vitals": bool(pi.get("vitals_snapshot")),
            # Conflicts
            "conflicts": display_conflicts,
            "has_conflicts": bool(display_conflicts),
            # Clarity (replaces dead-end "Unknown" state)
            "clarity_reason": pi.get("clarity_reason", ""),
            "clarity_action": pi.get("clarity_action", ""),
            "is_unclear": bool(pi.get("clarity_reason")),
            # Action category + signal interpretation
            "action_category": pi.get("action_category", "performance"),
            "is_clarity_action": pi.get("action_category") == "clarity",
            "signal_interpretation": pi.get("signal_interpretation", ""),
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


class IntakeLogAction(LoginRequiredMixin, View):
    """HTMX POST endpoint to log medicine dose from dashboard.

    Matches canonical IntakeTakeView behavior:
    - Sets scheduled_time on log
    - Uses mark_taken() for late/on-time classification
    - Decrements supply if tracked
    - Fires medication taken event
    """

    def post(self, request, schedule_id):
        from apps.core.events.domain_events import EventTypes, safe_emit_event
        from apps.core.utils import get_user_today
        from apps.health.models import IntakeLog, IntakeSchedule

        schedule = get_object_or_404(
            IntakeSchedule.objects.select_related("intake"),
            pk=schedule_id,
            intake__user=request.user,
        )
        today = get_user_today(request.user)
        medicine = schedule.intake

        # Validate schedule applies to today
        if not schedule.applies_to_day(today.weekday()):
            return _render_action_center(request)

        # Check if already logged
        existing = IntakeLog.objects.filter(
            user=request.user,
            intake=medicine,
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
            log, _created = IntakeLog.objects.get_or_create(
                user=request.user,
                intake=medicine,
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
        result = toggle_routine_completion(request.user, schedule, today)

        # Defensive: the helper currently returns plain status dicts for
        # every successful path, but any future blocking condition that
        # returns an `error` key must NOT silently no-op the UI. Surface it
        # at WARNING so production logs show when a toggle request was
        # refused — otherwise users see an unchanged checkbox with no clue.
        if isinstance(result, dict) and result.get('error'):
            logger.warning(
                "ROUTINE_TOGGLE_REFUSED user=%s schedule_id=%s "
                "routine=%s status=%s error=%s",
                request.user.id, schedule.pk,
                getattr(schedule.routine, 'name', ''),
                result.get('status'), result.get('error'),
            )

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


class IntakeGroupLogAction(LoginRequiredMixin, View):
    """HTMX POST endpoint to log/unlog all medicines in a time_of_day group.

    Matches canonical IntakeBulkTakeView behavior:
    - Filters by days_of_week (only schedules applicable today)
    - Sets scheduled_time on each log
    - Uses mark_taken() for late/on-time classification
    - Decrements supply per medicine
    - Fires medication taken event
    """

    def post(self, request, time_of_day):
        from apps.core.events.domain_events import EventTypes, safe_emit_event
        from apps.health.models import Intake, IntakeLog, IntakeSchedule

        today = get_user_today(request.user)

        # Get all active, non-PRN schedules for this time_of_day
        schedules = list(
            IntakeSchedule.objects.filter(
                intake__user=request.user,
                intake__intake_status=Intake.STATUS_ACTIVE,
                intake__is_prn=False,
                is_active=True,
                time_of_day=time_of_day,
            ).select_related("intake")
        )

        # Filter to schedules that apply today (day-of-week check)
        applicable = [s for s in schedules if s.applies_to_day(today.weekday())]

        if not applicable:
            return _render_action_center(request)

        applicable_pks = {s.pk for s in applicable}

        # Check if ALL applicable are already logged
        today_logs = set(
            IntakeLog.objects.filter(
                user=request.user,
                scheduled_date=today,
                log_status__in=["taken", "late"],
                schedule_id__in=applicable_pks,
            ).values_list("schedule_id", flat=True)
        )
        all_taken = len(today_logs) >= len(applicable)

        if all_taken:
            # Undo: delete logs and restore supply
            logs_to_delete = IntakeLog.objects.filter(
                user=request.user,
                scheduled_date=today,
                log_status__in=["taken", "late"],
                schedule_id__in=applicable_pks,
            ).select_related("intake")

            # Restore supply per medicine before deleting
            for log in logs_to_delete:
                med = log.intake
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
                existing_log = IntakeLog.objects.filter(
                    intake=schedule.intake,
                    schedule=schedule,
                    scheduled_date=today,
                ).first()

                if existing_log and existing_log.log_status in [
                    IntakeLog.STATUS_TAKEN,
                    IntakeLog.STATUS_LATE,
                    IntakeLog.STATUS_SKIPPED,
                ]:
                    continue  # Already handled (skipped counts as handled)

                # Create or update log with canonical fields
                log, _created = IntakeLog.objects.get_or_create(
                    user=request.user,
                    intake=schedule.intake,
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
                med = schedule.intake
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
