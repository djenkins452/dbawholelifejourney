"""
Dashboard V2 Service — central orchestrator for the Life Command Center.

Reads from existing engines. Never duplicates computation.
Provides phased data loading:
  Phase 1 (critical path): Momentum + progress + greeting
  Phase 2 (HTMX lazy):    Execution, state, celebration, insights
"""

import logging

import pytz
from django.utils import timezone

from apps.core.utils import get_user_today

from ..cache import DashboardV2CacheService

logger = logging.getLogger(__name__)


class DashboardV2Service:
    """Central orchestrator for the Life Command Center dashboard."""

    def __init__(self, user):
        self.user = user
        self.prefs = user.preferences
        self._today = None

    @property
    def today(self):
        if self._today is None:
            self._today = get_user_today(self.user)
        return self._today

    def get_critical_context(self):
        """
        Phase 1: Above-the-fold data for initial page render.
        Target: < 200ms total.
        """
        from .momentum_service import GoalMomentumService
        from .daily_progress_service import DailyProgressService

        time_phase = self.get_time_phase()
        greeting = self._get_greeting(time_phase)

        # Goal momentum (cached)
        momentum_service = GoalMomentumService(self.user)
        goal_momentum = momentum_service.get_all_momentum()

        # Daily progress (from DB snapshot)
        progress_service = DailyProgressService(self.user)
        daily_progress = progress_service.get_today()

        # Quick celebration check (just the flag)
        from .celebration_service import CelebrationDetectionService

        celebration_service = CelebrationDetectionService(self.user)
        has_celebration = celebration_service.get_ready_celebration() is not None

        return {
            "greeting": greeting,
            "time_phase": time_phase,
            "goal_momentum": goal_momentum,
            "daily_progress": daily_progress,
            "has_celebration": has_celebration,
            "current_date": self.today,
        }

    def get_execution_context(self):
        """
        Phase 2 (lazy): Today's actionable items.
        Returns tasks, routines, medicines, calendar events.
        """
        cached = DashboardV2CacheService.get(self.user.pk, "execution")
        if cached is not None:
            return cached

        context = {}

        # Routine tasks (due today, is_routine=True)
        try:
            from apps.life.models import Task

            routine_tasks = list(
                Task.objects.filter(
                    user=self.user,
                    is_routine=True,
                    due_date=self.today,
                )
                .exclude(is_deleted=True)
                .order_by("scheduled_time", "title")
            )
            context["routine_tasks"] = routine_tasks
        except Exception:
            logger.error("Failed to load routine tasks", exc_info=True)
            context["routine_tasks"] = []

        # Non-routine tasks (due today or overdue, pending)
        try:
            from apps.life.models import Task

            non_routine_tasks = list(
                Task.objects.filter(
                    user=self.user,
                    is_routine=False,
                    due_date__lte=self.today,
                    completion_status="pending",
                )
                .exclude(is_deleted=True)
                .select_related("project")
                .order_by("due_date", "priority", "title")[:20]
            )
            context["non_routine_tasks"] = non_routine_tasks
        except Exception:
            logger.error("Failed to load tasks", exc_info=True)
            context["non_routine_tasks"] = []

        # Medicine schedule
        try:
            from apps.health.models import Medicine, MedicineLog

            active_medicines = list(
                Medicine.objects.filter(
                    user=self.user,
                    medicine_status=Medicine.STATUS_ACTIVE,
                )
                .prefetch_related("schedules")
            )

            # Get today's logs for quick lookup
            today_logs = set(
                MedicineLog.objects.filter(
                    user=self.user,
                    log_date=self.today,
                    action__in=["taken", "late"],
                ).values_list("medicine_id", "schedule_id")
            )

            medicine_items = []
            for med in active_medicines:
                for schedule in med.schedules.all():
                    taken = (med.pk, schedule.pk) in today_logs
                    medicine_items.append({
                        "medicine": med,
                        "schedule": schedule,
                        "taken": taken,
                    })
            context["medicine_items"] = medicine_items
        except Exception:
            logger.error("Failed to load medicines", exc_info=True)
            context["medicine_items"] = []

        # Calendar events
        try:
            from apps.life.models import LifeEvent

            today_events = list(
                LifeEvent.objects.filter(
                    user=self.user,
                    date=self.today,
                )
                .exclude(is_deleted=True)
                .order_by("time")[:10]
            )
            context["today_events"] = today_events
        except Exception:
            logger.error("Failed to load events", exc_info=True)
            context["today_events"] = []

        # Time phase for section ordering
        context["time_phase"] = self.get_time_phase()

        DashboardV2CacheService.set(self.user.pk, "execution", context)
        return context

    def get_state_panel_context(self):
        """
        Phase 2 (lazy): Current state telemetry.
        Reads from SAE state builders + DailyHealthSummary.
        """
        cached = DashboardV2CacheService.get(self.user.pk, "state")
        if cached is not None:
            return cached

        context = {}

        # Health state from SAE
        try:
            from apps.core.ai_state.state_builder import (
                build_fitness_state,
                build_health_state,
                build_nutrition_state,
            )

            context["health_state"] = build_health_state(self.user)
            context["fitness_state"] = build_fitness_state(self.user)
            context["nutrition_state"] = build_nutrition_state(self.user)
        except Exception:
            logger.error("SAE state builders failed", exc_info=True)
            context["health_state"] = {}
            context["fitness_state"] = {}
            context["nutrition_state"] = {}

        # Today's health summary (pre-computed by nightly builder)
        try:
            from apps.health.models import DailyHealthSummary

            context["daily_health_summary"] = DailyHealthSummary.objects.filter(
                user=self.user,
                summary_date=self.today,
            ).first()
        except Exception:
            context["daily_health_summary"] = None

        DashboardV2CacheService.set(self.user.pk, "state", context)
        return context

    def get_celebration_context(self):
        """Phase 2 (lazy): Check for ready celebrations."""
        from .celebration_service import CelebrationDetectionService

        service = CelebrationDetectionService(self.user)
        celebration = service.get_ready_celebration()
        return {"celebration": celebration}

    def get_insights_context(self):
        """
        Phase 2 (lazy): Insights, predictions, guidance.
        Reads from PIE, PRIE, PGE engines.
        """
        context = {}

        # Guidance items from PGE
        try:
            from apps.core.ai_guidance.models import GuidanceItem

            context["guidance_items"] = list(
                GuidanceItem.objects.filter(
                    user=self.user,
                    dismissed_at__isnull=True,
                )
                .order_by("-priority", "-created_at")[:5]
            )
        except Exception:
            context["guidance_items"] = []

        # Active predictions from PRIE
        try:
            from apps.core.ai_predictions.models import Prediction

            context["predictions"] = list(
                Prediction.objects.filter(
                    user=self.user,
                    status="active",
                )
                .order_by("-confidence_score")[:5]
            )
        except Exception:
            context["predictions"] = []

        # Recent insights from PIE
        try:
            from apps.core.ai_insights.models import Insight

            context["insights"] = list(
                Insight.objects.filter(user=self.user)
                .order_by("-created_at")[:5]
            )
        except Exception:
            context["insights"] = []

        return context

    def get_time_phase(self):
        """
        Determine current time phase for the user.
        Returns 'morning' (before 12), 'midday' (12-17), 'evening' (17+).
        """
        try:
            user_tz = pytz.timezone(self.prefs.timezone_iana)
            hour = timezone.now().astimezone(user_tz).hour
        except Exception:
            hour = timezone.now().hour

        if hour < 12:
            return "morning"
        elif hour < 17:
            return "midday"
        return "evening"

    def _get_greeting(self, time_phase):
        """Generate time-appropriate greeting."""
        greetings = {
            "morning": "Good morning",
            "midday": "Good afternoon",
            "evening": "Good evening",
        }
        first_name = self.user.first_name or self.user.email.split("@")[0]
        return f"{greetings.get(time_phase, 'Hello')}, {first_name}"
