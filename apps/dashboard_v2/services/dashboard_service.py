"""
Dashboard V2 Service — central orchestrator for the Life Command Center.

Reads from existing engines. Never duplicates computation.
Provides phased data loading:
  Phase 1 (critical path): Momentum + progress + greeting + execution
  Phase 2 (HTMX lazy):    State, celebration, insights
"""

import datetime
import logging
from datetime import timedelta

import pytz
from django.urls import reverse
from django.utils import timezone

from apps.core.utils import get_user_today

from ..cache import DashboardV2CacheService

logger = logging.getLogger(__name__)

# Diagnostic phrases that should never appear in user-facing UI
DIAGNOSTIC_PHRASES = [
    "Unable to compute",
    "No data",
    "Insufficient",
    "Error",
    "N/A",
    "No domain signals",
]

# Module-to-domain mapping for goal connection
MODULE_DOMAIN_MAP = {
    "faith": "faith",
    "health": "health",
    "purpose": "work",
    "journal": "personal-growth",
    "life": "family",
}

# Engagement strength activity keywords for matching routines
ENGAGEMENT_ACTIVITY_MAP = {
    "journal": ["journal", "journaling", "reflection", "reflect", "diary"],
    "workout": ["workout", "exercise", "gym", "run", "walk", "fitness", "training"],
    "prayer": ["prayer", "pray", "devotion", "devotional", "quiet time"],
    "sleep": ["sleep", "bedtime", "wind down", "rest"],
    "nutrition": ["nutrition", "meal", "diet", "eat", "food", "fast", "fasting"],
}


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
        Includes execution (promoted from lazy to critical path).
        Target: < 200ms total.
        """
        from .daily_progress_service import DailyProgressService
        from .momentum_service import GoalMomentumService

        time_phase = self.get_time_phase()
        greeting = self._get_greeting(time_phase)

        # Goal momentum (cached)
        momentum_service = GoalMomentumService(self.user)
        goal_momentum = momentum_service.get_all_momentum()

        # Execution (promoted to critical path)
        exec_context = self.get_execution_context()

        # Daily progress (from DB snapshot)
        progress_service = DailyProgressService(self.user)
        daily_progress = progress_service.get_today()

        # Quick celebration check (just the flag)
        from .celebration_service import CelebrationDetectionService

        celebration_service = CelebrationDetectionService(self.user)
        has_celebration = celebration_service.get_ready_celebration() is not None

        result = {
            "greeting": greeting,
            "time_phase": time_phase,
            "goal_momentum": goal_momentum,
            "daily_progress": daily_progress,
            "has_celebration": has_celebration,
            "current_date": self.today,
        }
        result.update(exec_context)
        return result

    def get_execution_context(self):
        """
        Today's actionable items: routines, medicine, tasks, calendar.
        Now part of the critical path (not lazy-loaded).
        """
        cached = DashboardV2CacheService.get(self.user.pk, "execution")
        if cached is not None:
            return cached

        context = {}

        # Pre-fetch active goals by domain for goal connection
        goals_by_domain = self._get_goals_by_domain()
        context["goals_by_domain"] = goals_by_domain

        # Pre-compute engagement strength for routine matching
        engagement = self._compute_engagement_strength()
        context["engagement"] = engagement

        # Routine tasks (due today, is_routine=True)
        try:
            from apps.life.models import Task

            routine_tasks = list(
                Task.objects.filter(
                    user=self.user,
                    is_routine=True,
                    due_date=self.today,
                )
                .exclude(status="deleted")
                .order_by("scheduled_time", "title")
            )
            # Attach goal names, engagement levels, and safe URLs
            for task in routine_tasks:
                domain_slug = MODULE_DOMAIN_MAP.get(
                    getattr(task, "module", ""), ""
                )
                task.goal_name = goals_by_domain.get(domain_slug, "")
                task.engagement_level = self._match_engagement(
                    task.title, engagement
                )
                task.detail_url = self._resolve_task_url(task)
            context["routine_tasks"] = routine_tasks

            # Split into completed (compact) and pending (full-size)
            context["completed_routines"] = [
                t for t in routine_tasks if t.is_completed
            ]
            context["pending_routines"] = [
                t for t in routine_tasks if not t.is_completed
            ]
            if context["pending_routines"]:
                context["pending_routines"][0].is_next = True
        except Exception:
            logger.error("Failed to load routine tasks", exc_info=True)
            context["routine_tasks"] = []
            context["completed_routines"] = []
            context["pending_routines"] = []

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
                .exclude(status="deleted")
                .select_related("project")
                .order_by("due_date", "priority", "title")[:20]
            )
            for task in non_routine_tasks:
                domain_slug = MODULE_DOMAIN_MAP.get(
                    getattr(task, "module", ""), ""
                )
                task.goal_name = goals_by_domain.get(domain_slug, "")
            context["non_routine_tasks"] = non_routine_tasks
        except Exception:
            logger.error("Failed to load tasks", exc_info=True)
            context["non_routine_tasks"] = []

        # Medicine schedule — grouped by time_of_day
        try:
            from apps.health.models import Medicine, MedicineLog, MedicineSchedule

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
                    scheduled_date=self.today,
                    log_status__in=["taken", "late"],
                ).values_list("medicine_id", "schedule_id")
            )

            # Group by time_of_day
            groups = {}
            medicine_items = []  # flat list for counts
            for med in active_medicines:
                for schedule in med.schedules.all():
                    tod = schedule.time_of_day or "unscheduled"
                    taken = (med.pk, schedule.pk) in today_logs
                    if tod not in groups:
                        display = (
                            schedule.get_time_of_day_display()
                            if hasattr(schedule, "get_time_of_day_display")
                            else tod.replace("_", " ").title()
                        )
                        groups[tod] = {
                            "time_of_day": tod,
                            "label": f"{display} Stack",
                            "order": MedicineSchedule.TIME_OF_DAY_ORDER.get(
                                tod, 99
                            ),
                            "items": [],
                            "schedule_ids": [],
                            "taken_count": 0,
                            "total_count": 0,
                        }
                    groups[tod]["items"].append(
                        {"medicine": med, "schedule": schedule, "taken": taken}
                    )
                    groups[tod]["schedule_ids"].append(schedule.pk)
                    groups[tod]["total_count"] += 1
                    if taken:
                        groups[tod]["taken_count"] += 1
                    medicine_items.append({"taken": taken})

            medicine_groups = sorted(
                groups.values(), key=lambda g: g["order"]
            )
            for g in medicine_groups:
                g["all_taken"] = g["taken_count"] == g["total_count"]
                g["goal_name"] = goals_by_domain.get("health", "")

            context["medicine_groups"] = medicine_groups
            context["medicine_items"] = medicine_items
        except Exception:
            logger.error("Failed to load medicines", exc_info=True)
            context["medicine_groups"] = []
            context["medicine_items"] = []

        # Calendar events (from CalendarEvent, not LifeEvent)
        try:
            from apps.calendar_engine.models import CalendarEvent

            today_events = list(
                CalendarEvent.objects.filter(
                    user=self.user,
                    start_dt__date=self.today,
                    status="scheduled",
                    deleted_at__isnull=True,
                )
                .select_related("domain")
                .order_by("start_dt")[:10]
            )
            # Attach goal names via domain
            for event in today_events:
                domain_slug = event.domain.slug if event.domain else ""
                event.goal_name = goals_by_domain.get(domain_slug, "")
            context["today_events"] = today_events
        except Exception:
            logger.error("Failed to load calendar events", exc_info=True)
            context["today_events"] = []

        # Build unified schedule timeline (tasks + calendar merged)
        context["schedule_timeline"] = self._build_schedule_timeline(
            context.get("non_routine_tasks", []),
            context.get("today_events", []),
        )
        context["schedule_count"] = len(context["schedule_timeline"])

        # Completion counts for group headers
        context["routine_done"] = sum(
            1 for t in context.get("routine_tasks", []) if t.is_completed
        )
        context["routine_total"] = len(context.get("routine_tasks", []))
        context["medicine_done"] = sum(
            1 for m in context.get("medicine_items", []) if m.get("taken")
        )
        context["medicine_total"] = len(context.get("medicine_items", []))

        # Time phase for section ordering
        context["time_phase"] = self.get_time_phase()

        DashboardV2CacheService.set(self.user.pk, "execution", context)
        return context

    def _get_goals_by_domain(self):
        """Pre-fetch active goals indexed by domain slug."""
        goals_by_domain = {}
        try:
            from apps.purpose.models import LifeGoal

            for goal in LifeGoal.objects.filter(
                user=self.user, status="active"
            ).select_related("domain"):
                if goal.domain:
                    goals_by_domain[goal.domain.slug] = goal.title
        except Exception:
            logger.error("Failed to load goals for domain mapping", exc_info=True)
        return goals_by_domain

    def _compute_engagement_strength(self):
        """
        Compute engagement strength for key activity areas.
        Based on recency + frequency of completion over last 7 days.
        Returns dict: {"journal": "strong", "workout": "moderate", ...}

        Levels: strong (4-5+ of 7 days), moderate (2-3), weak (0-1)
        """
        engagement = {}
        cutoff = self.today - timedelta(days=7)

        try:
            from apps.life.models import Task

            recent_completed = list(
                Task.objects.filter(
                    user=self.user,
                    is_routine=True,
                    completion_status="completed",
                    completed_at__date__gte=cutoff,
                )
                .exclude(status="deleted")
                .values_list("title", "completed_at")
            )

            for activity_key, keywords in ENGAGEMENT_ACTIVITY_MAP.items():
                # Count distinct days with a matching completed routine
                matching_dates = set()
                for title, completed_at in recent_completed:
                    if completed_at and any(
                        kw in title.lower() for kw in keywords
                    ):
                        matching_dates.add(completed_at.date())

                days_active = len(matching_dates)
                if days_active >= 4:
                    engagement[activity_key] = "strong"
                elif days_active >= 2:
                    engagement[activity_key] = "moderate"
                else:
                    engagement[activity_key] = "weak"
        except Exception:
            logger.error("Failed to compute engagement strength", exc_info=True)

        return engagement

    @staticmethod
    def _match_engagement(title, engagement):
        """Match a task title to an engagement activity and return its level."""
        title_lower = title.lower()
        for activity_key, keywords in ENGAGEMENT_ACTIVITY_MAP.items():
            if any(kw in title_lower for kw in keywords):
                return engagement.get(activity_key, "")
        return ""

    def _build_schedule_timeline(self, non_routine_tasks, today_events):
        """
        Merge non-routine tasks and calendar events into a single
        sorted timeline for "Today's Schedule".
        """
        try:
            user_tz = pytz.timezone(self.prefs.timezone_iana)
        except Exception:
            user_tz = pytz.UTC

        timeline = []

        for task in non_routine_tasks:
            t = task.scheduled_time
            timeline.append({
                "type": "task",
                "pk": task.pk,
                "time": t,
                "time_display": t.strftime("%-I:%M %p") if t else "",
                "title": task.title,
                "is_completed": task.is_completed,
                "can_complete": True,
                "source_url": self._resolve_task_url(task),
                "is_overdue": task.is_overdue,
                "commitment_level": getattr(task, "commitment_level", ""),
                "goal_name": getattr(task, "goal_name", ""),
                "is_all_day": False,
            })

        for event in today_events:
            local_time = None
            if event.start_dt and not event.is_all_day:
                local_time = event.start_dt.astimezone(user_tz).time()
            timeline.append({
                "type": "event",
                "pk": event.pk,
                "time": local_time,
                "time_display": (
                    local_time.strftime("%-I:%M %p")
                    if local_time
                    else ("All Day" if event.is_all_day else "")
                ),
                "title": event.title,
                "is_completed": event.status == "completed",
                "can_complete": getattr(event, "source_type", "") == "task",
                "source_url": self._resolve_event_url(event),
                "is_all_day": event.is_all_day,
                "goal_name": getattr(event, "goal_name", ""),
                "is_overdue": False,
                "commitment_level": "",
            })

        # Sort: items with time first (by time), then items without time
        timeline.sort(
            key=lambda x: (
                x["time"] is None,
                x["time"] or datetime.time(23, 59),
            )
        )
        return timeline

    @staticmethod
    def _resolve_task_url(task):
        """Resolve URL for a task, with fallback if task_detail doesn't exist."""
        try:
            return task.get_absolute_url()
        except Exception:
            try:
                return reverse("life:task_update", kwargs={"pk": task.pk})
            except Exception:
                return reverse("life:task_list")

    @staticmethod
    def _resolve_event_url(event):
        """Resolve the best URL for navigating to a calendar event's source."""
        if getattr(event, "source_type", "") == "task" and event.source_id:
            try:
                return reverse(
                    "life:task_update",
                    kwargs={"pk": int(event.source_id)},
                )
            except (ValueError, Exception):
                pass
        return reverse("calendar_engine:dashboard")

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

            health_state = build_health_state(self.user)
            context["fitness_state"] = build_fitness_state(self.user)
            context["nutrition_state"] = build_nutrition_state(self.user)

            # Fix sleep unit: stored in minutes, display as hours+minutes
            sleep_minutes = health_state.get("sleep_avg_duration_7d")
            if sleep_minutes and isinstance(sleep_minutes, (int, float)):
                hours = int(sleep_minutes // 60)
                mins = int(round(sleep_minutes % 60))
                health_state["sleep_display"] = f"{hours}h {mins}m"

            context["health_state"] = health_state
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
        Phase 2 (lazy): Guidance + insights.
        Uses existing get_active_guidance() for dedup/supersession.
        Max 2 guidance items + 1 insight. No predictions.
        """
        context = {}

        # Guidance items via existing engine (handles dedup, supersession, etc.)
        try:
            from apps.core.ai_guidance.guidance_engine import get_active_guidance

            raw_items = get_active_guidance(self.user, limit=4)

            # Filter out diagnostic text
            filtered = []
            for item in raw_items:
                text = f"{item.title} {item.message}".lower()
                if any(phrase.lower() in text for phrase in DIAGNOSTIC_PHRASES):
                    continue
                filtered.append(item)
                if len(filtered) >= 2:
                    break

            context["guidance_items"] = filtered
        except Exception:
            logger.error("Failed to load guidance items", exc_info=True)
            context["guidance_items"] = []

        # Single best insight from PIE (no predictions)
        try:
            from apps.core.ai_insights.models import Insight

            insight = (
                Insight.objects.filter(
                    user=self.user,
                    severity__in=["warning", "critical", "positive"],
                )
                .exclude(status="dismissed")
                .order_by("-created_at")
                .first()
            )
            # Filter out diagnostic text from insight too
            if insight:
                text = f"{getattr(insight, 'title', '')} {getattr(insight, 'message', '')}".lower()
                if any(phrase.lower() in text for phrase in DIAGNOSTIC_PHRASES):
                    insight = None
            context["insight"] = insight
        except Exception:
            context["insight"] = None

        # Only show section when there's meaningful content
        context["has_actionable_insights"] = bool(
            context.get("guidance_items")
        ) or bool(context.get("insight"))

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
