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

from apps.core.time_windows import is_window_visible
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
    "streak",
    "plateau",
]

# Module-to-domain mapping for goal connection
MODULE_DOMAIN_MAP = {
    "faith": "faith",
    "health": "health",
    "purpose": "work",
    "journal": "personal-growth",
    "life": "family",
}

# Medicine visibility uses canonical time windows with 1-hour buffer.
# Derived from apps.core.time_windows — do NOT redefine window boundaries here.

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
        self._daily_progress = None  # Set by get_critical_context for action center

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

        # Daily progress BEFORE execution — action center needs this
        progress_service = DailyProgressService(self.user)
        daily_progress = progress_service.get_today()
        self._daily_progress = daily_progress

        # Execution (promoted to critical path, uses _daily_progress for action center)
        exec_context = self.get_execution_context()

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

        # Routine tasks — merge legacy Task-based AND canonical Routine model items
        try:
            from apps.life.services.task_queries import TaskQueries

            routine_tasks = list(
                TaskQueries.routines_for_date(self.user, self.today)
            )
            # Attach goal names, foundational status, engagement, and URLs
            for task in routine_tasks:
                domain_slug = MODULE_DOMAIN_MAP.get(
                    getattr(task, "module", ""), ""
                )
                domain_goal = goals_by_domain.get(domain_slug, {})
                task.goal_name = domain_goal.get("title", "") if isinstance(domain_goal, dict) else ""
                # Foundational precedence: linked goal/domain > task-level fallback
                task._domain_foundational = domain_goal.get("is_foundational", False) if isinstance(domain_goal, dict) else False
                task.engagement_level = self._match_engagement(
                    task.title, engagement
                )
                task.detail_url = self._resolve_task_url(task)
                task.toggle_url = None  # will be set by template via {% url %}
        except Exception:
            logger.error("Failed to load routine tasks", exc_info=True)
            routine_tasks = []

        # Canonical Routine model items (the first-class routine system)
        try:
            canonical_items = self._get_canonical_routine_items(engagement)
            routine_tasks.extend(canonical_items)
        except Exception:
            logger.error("Failed to load canonical routine items", exc_info=True)

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

        # Routine-level completion for routine card checkbox
        from django.urls import reverse as _reverse
        _rc = getattr(self, '_routine_completion', {})
        context["routine_groups"] = [
            {
                'id': rid,
                'name': rc.get('name', ''),
                'all_complete': rc.get('all_complete', False),
                'completed_count': rc.get('completed_count', 0),
                'total_count': rc.get('total_count', 0),
                'toggle_url': _reverse(
                    'dashboard_v2:routine_complete_toggle',
                    kwargs={'routine_id': rid},
                ),
            }
            for rid, rc in _rc.items()
        ]

        # Non-routine tasks (due today or overdue, pending)
        try:
            from apps.life.services.task_queries import TaskQueries

            non_routine_tasks = list(
                TaskQueries.pending(self.user).filter(
                    is_routine=False,
                    due_date__lte=self.today,
                )
                .select_related("project")
                .order_by("due_date", "priority", "title")[:20]
            )
            for task in non_routine_tasks:
                domain_slug = MODULE_DOMAIN_MAP.get(
                    getattr(task, "module", ""), ""
                )
                domain_goal = goals_by_domain.get(domain_slug, {})
                task.goal_name = domain_goal.get("title", "") if isinstance(domain_goal, dict) else ""
                task._domain_foundational = domain_goal.get("is_foundational", False) if isinstance(domain_goal, dict) else False
            context["non_routine_tasks"] = non_routine_tasks
        except Exception:
            logger.error("Failed to load tasks", exc_info=True)
            context["non_routine_tasks"] = []

        # Medicine schedule — grouped by time_of_day
        try:
            from apps.health.models import Intake, IntakeLog, IntakeSchedule

            active_medicines = list(
                Intake.objects.filter(
                    user=self.user,
                    intake_status=Intake.STATUS_ACTIVE,
                )
                .prefetch_related("schedules")
            )

            # Get today's logs for quick lookup
            today_logs = set(
                IntakeLog.objects.filter(
                    user=self.user,
                    scheduled_date=self.today,
                    log_status__in=["taken", "late"],
                ).values_list("intake_id", "schedule_id")
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
                            "order": IntakeSchedule.TIME_OF_DAY_ORDER.get(
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
                health_goal = goals_by_domain.get("health", {})
                g["goal_name"] = health_goal.get("title", "") if isinstance(health_goal, dict) else ""
                g["is_foundational"] = health_goal.get("is_foundational", False) if isinstance(health_goal, dict) else False

            context["medicine_groups"] = medicine_groups
            context["medicine_items"] = medicine_items

            # Filter by canonical time windows — only show relevant stacks
            current_hour = self._get_user_now().hour
            visible_groups = []
            future_groups = []
            for g in medicine_groups:
                tod = g["time_of_day"]
                if g["all_taken"] or is_window_visible(tod, current_hour, buffer_hours=1):
                    visible_groups.append(g)
                else:
                    future_groups.append(g)
            context["visible_medicine_groups"] = visible_groups
            context["future_medicine_groups"] = future_groups
        except Exception:
            logger.error("Failed to load medicines", exc_info=True)
            context["medicine_groups"] = []
            context["medicine_items"] = []
            context["visible_medicine_groups"] = []
            context["future_medicine_groups"] = []

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
                domain_goal = goals_by_domain.get(domain_slug, {})
                event.goal_name = domain_goal.get("title", "") if isinstance(domain_goal, dict) else ""
                event._domain_foundational = domain_goal.get("is_foundational", False) if isinstance(domain_goal, dict) else False
            context["today_events"] = today_events
        except Exception:
            logger.error("Failed to load calendar events", exc_info=True)
            context["today_events"] = []

        # Build unified schedule timeline (tasks + calendar merged)
        timeline = self._build_schedule_timeline(
            context.get("non_routine_tasks", []),
            context.get("today_events", []),
        )
        context["schedule_timeline"] = timeline
        context["schedule_count"] = len(timeline)

        # Phase-grouped schedule lists for NOW/NEXT/LATER rendering
        context["schedule_now"] = [
            i for i in timeline if i.get("phase") == "now" and not i["is_completed"]
        ]
        context["schedule_next"] = [
            i for i in timeline if i.get("phase") == "next" and not i["is_completed"]
        ]
        context["schedule_later"] = [
            i for i in timeline if i.get("phase") == "later" and not i["is_completed"]
        ]
        context["schedule_done"] = [
            i for i in timeline if i["is_completed"]
        ]

        # Completion counts for group headers — ROUTINE-LEVEL (not item-level)
        # A routine is complete only when ALL its items are done (all_complete).
        _rg = context.get("routine_groups", [])
        context["routine_done"] = sum(
            1 for rg in _rg if rg.get("all_complete")
        )
        context["routine_total"] = len(_rg)
        # Count only visible (due) medicine groups — don't penalize for future stacks
        visible_med = context.get("visible_medicine_groups", [])
        context["medicine_done"] = sum(g.get("taken_count", 0) for g in visible_med)
        context["medicine_total"] = sum(g.get("total_count", 0) for g in visible_med)

        # Time phase for section ordering
        context["time_phase"] = self.get_time_phase()

        # ── Action center from authoritative execution contract ──
        # Dashboard calls build_today_execution() directly for live freshness,
        # then uses the shared prioritizer. No separate normalization.
        from apps.core.decision_engine.action_prioritizer import (
            build_grouped_action_center,
            find_next_upcoming,
            group_actions,
            prioritize_execution_items,
        )
        from apps.core.execution.today_execution import build_today_execution

        exec_contract = build_today_execution(self.user)
        context["execution_contract"] = exec_contract

        # Legacy flat action list (still used by CoS context builder)
        action_center = prioritize_execution_items(
            exec_contract['items'],
            self._get_user_now().time(),
            summaries=exec_contract.get('summaries'),
        )

        groups = group_actions(action_center)
        context["action_center"] = action_center
        context["action_now"] = groups["now"]
        context["action_next"] = groups["next"]
        context["action_later"] = groups["later"]
        context["action_foundational"] = [a for a in action_center if a["is_foundational"]]
        context["action_standard"] = [a for a in action_center if not a["is_foundational"]]
        context["next_action"] = action_center[0] if action_center else None

        # ── NEW: Grouped action center (unified execution surface) ──
        # Includes ALL items (completed + pending), grouped by execution group.
        # This replaces the separate routine/medicine/schedule cards.
        ac_data = build_grouped_action_center(
            exec_contract['items'],
            self._get_user_now().time(),
            summaries=exec_contract.get('summaries'),
        )
        context["ac"] = ac_data
        context["all_done"] = ac_data['all_done']

        if context["all_done"] or not action_center:
            context["next_upcoming"] = find_next_upcoming(
                action_center,
                future_medicine_groups=self._normalize_medicine_groups(
                    context.get("future_medicine_groups", [])
                ),
                schedule_later=context.get("schedule_later", []),
            )

        DashboardV2CacheService.set(self.user.pk, "execution", context)
        return context

    def _get_goals_by_domain(self):
        """Pre-fetch active goals indexed by domain slug.

        Returns dict: {domain_slug: {"title": str, "is_foundational": bool}}
        The is_foundational flag is True if ANY active goal in that domain
        is marked foundational — this is the canonical source of truth for
        domain-level foundational priority (not task-level).
        """
        goals_by_domain = {}
        try:
            from apps.purpose.models import LifeGoal

            for goal in LifeGoal.objects.filter(
                user=self.user, status="active"
            ).select_related("domain"):
                if goal.domain:
                    slug = goal.domain.slug
                    existing = goals_by_domain.get(slug)
                    if existing is None:
                        goals_by_domain[slug] = {
                            "title": goal.title,
                            "is_foundational": goal.is_foundational,
                        }
                    else:
                        # If any goal in domain is foundational, domain is foundational
                        if goal.is_foundational:
                            existing["is_foundational"] = True
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

    def _get_user_now(self):
        """Get current datetime in the user's timezone."""
        try:
            user_tz = pytz.timezone(self.prefs.timezone_iana)
            return timezone.now().astimezone(user_tz)
        except Exception:
            return timezone.now()

    @staticmethod
    def _time_diff_minutes(now_time, target_time):
        """
        Calculate minutes from now_time to target_time (positive = future).
        Both are datetime.time objects.
        """
        now_mins = now_time.hour * 60 + now_time.minute
        target_mins = target_time.hour * 60 + target_time.minute
        return target_mins - now_mins

    def _get_canonical_routine_items(self, engagement):
        """
        Load today's routine items from the canonical Routine model
        and wrap them in lightweight objects compatible with the dashboard
        template (which expects Task-like attributes).
        """
        from types import SimpleNamespace

        from django.urls import reverse

        from apps.life.services._routine_internal import get_todays_routine_items

        result = get_todays_routine_items(self.user)
        items = []

        for window_items in result['items_by_window'].values():
            for item in window_items:
                is_completed = item.get('status') == 'completed'
                schedule_id = item['schedule_id']
                proxy = SimpleNamespace(
                    pk=f"rs-{schedule_id}",  # prefixed to avoid Task pk collision
                    title=item['item_name'],
                    scheduled_time=None,  # already formatted in item
                    is_completed=is_completed,
                    is_next=False,
                    goal_name="",
                    engagement_level=self._match_engagement(
                        item['item_name'], engagement
                    ),
                    detail_url=reverse('life:routine_list'),
                    toggle_url=reverse(
                        'dashboard_v2:routine_schedule_toggle',
                        kwargs={'schedule_id': schedule_id},
                    ),
                    _domain_foundational=False,
                    is_foundational=False,
                    commitment_level="",
                    # Extra metadata for action prioritizer
                    _is_canonical_routine=True,
                    _schedule_id=schedule_id,
                    _routine_id=item.get('routine_id'),
                )
                items.append(proxy)

        # Store routine-level completion for dashboard card
        self._routine_completion = result.get('routine_completion', {})

        return items

    # ── Normalization helpers for shared decision engine ────────────
    # These convert ORM objects / dashboard-specific dicts into the
    # pure-dict format expected by action_prioritizer.

    @staticmethod
    def _normalize_pending_routines(pending_routines):
        """Convert Task ORM objects or canonical routine proxies to dicts for the decision engine."""
        result = []
        for task in pending_routines:
            is_foundational = (
                getattr(task, "_domain_foundational", False)
                or getattr(task, "is_foundational", False)
            )
            result.append({
                "pk": task.pk,
                "title": task.title,
                "source_url": getattr(task, "detail_url", ""),
                "is_foundational": is_foundational,
                "commitment_level": getattr(task, "commitment_level", ""),
                "goal_name": getattr(task, "goal_name", ""),
                "toggle_url": getattr(task, "toggle_url", ""),
            })
        return result

    @staticmethod
    def _normalize_medicine_groups(medicine_groups):
        """Convert medicine group dicts to engine-compatible format."""
        result = []
        for g in (medicine_groups or []):
            result.append({
                "title": g.get("label", ""),
                "time_of_day": g.get("time_of_day", ""),
                "is_foundational": g.get("is_foundational", False),
                "goal_name": g.get("goal_name", ""),
                "all_taken": g.get("all_taken", False),
            })
        return result

    @staticmethod
    def _build_binary_actions(daily_progress, goals_by_domain):
        """Build binary action items (journal, faith, workout) from progress data."""
        from django.urls import reverse

        dp = daily_progress or {}
        actions = []

        _BINARY_ITEMS = [
            {
                "source": "journal",
                "key": "journaling",
                "domain": "personal-growth",
                "title": "Write in journal",
                "url_name": "journal:entry_list",
                "url_fallback": "/journal/",
            },
            {
                "source": "faith",
                "key": "faith",
                "domain": "faith",
                "title": "Bible reading",
                "url_name": "faith:reading_plans",
                "url_fallback": "/faith/reading-plans/",
            },
            {
                "source": "workout",
                "key": "workout",
                "domain": "health",
                "title": "Log a workout",
                "url_name": "health:fitness_home",
                "url_fallback": "/health/physical/fitness/",
            },
        ]

        for item in _BINARY_ITEMS:
            done = dp.get(item["key"], {}).get("done", 0)
            domain_goal = goals_by_domain.get(item["domain"], {})
            try:
                url = reverse(item["url_name"])
            except Exception:
                url = item["url_fallback"]

            actions.append({
                "source": item["source"],
                "title": item["title"],
                "source_url": url,
                "is_foundational": (
                    domain_goal.get("is_foundational", False)
                    if isinstance(domain_goal, dict) else False
                ),
                "goal_name": (
                    domain_goal.get("title", "")
                    if isinstance(domain_goal, dict) else ""
                ),
                "is_done": done > 0,
            })

        return actions

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

        # Track task PKs to deduplicate task-backed calendar events
        task_pks = set()

        for task in non_routine_tasks:
            t = task.scheduled_time
            task_pks.add(task.pk)
            # Foundational precedence: domain goal > task fallback
            is_foundational = getattr(task, "_domain_foundational", False) or getattr(task, "is_foundational", False)
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
                "is_foundational": is_foundational,
                "is_all_day": False,
            })

        for event in today_events:
            # Skip calendar events that are projections of tasks already listed
            if getattr(event, "source_type", "") == "task" and event.source_id:
                try:
                    if int(event.source_id) in task_pks:
                        continue
                except (ValueError, TypeError):
                    pass
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
                "is_foundational": getattr(event, "_domain_foundational", False),
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

        # Add time-aware phase (NOW / NEXT / LATER)
        now = self._get_user_now()
        now_time = now.time()
        for item in timeline:
            if item["is_completed"]:
                item["phase"] = "done"
            elif item["time"] is None:
                item["phase"] = "later"
            else:
                delta = self._time_diff_minutes(now_time, item["time"])
                if delta < -15:
                    # Already passed by 15+ min — treat as NOW (overdue)
                    item["phase"] = "now"
                elif delta <= 30:
                    item["phase"] = "now"
                elif delta <= 120:
                    item["phase"] = "next"
                else:
                    item["phase"] = "later"

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

        # Build compact metrics (primary 3 + secondary rest)
        metrics = []
        health_state = context.get("health_state", {})
        fitness_state = context.get("fitness_state", {})
        nutrition_state = context.get("nutrition_state", {})

        if health_state.get("weight_current"):
            unit = health_state.get("weight_unit", "lbs")
            metrics.append({
                "label": "Weight",
                "value": f'{health_state["weight_current"]:.1f}',
                "unit": unit,
                "trend": health_state.get("weight_trend", ""),
                "priority": 1,
                "detail_url": reverse("health:weight_list"),
                "status": "neutral",
            })
        if health_state.get("sleep_display"):
            # Color-code sleep: >= 7h green, 6-7h yellow, < 6h red
            sleep_mins = health_state.get("sleep_avg_duration_7d", 0) or 0
            sleep_hours = sleep_mins / 60 if sleep_mins else 0
            sleep_status = (
                "good" if sleep_hours >= 7
                else "warning" if sleep_hours >= 6
                else "poor"
            )
            metrics.append({
                "label": "Sleep",
                "value": health_state["sleep_display"],
                "unit": "",
                "priority": 2,
                "detail_url": reverse("health:sleep_list"),
                "status": sleep_status,
            })
        if health_state.get("steps_avg_7d"):
            steps = health_state["steps_avg_7d"]
            steps_status = (
                "good" if steps >= 8000
                else "warning" if steps >= 5000
                else "poor"
            )
            metrics.append({
                "label": "Steps",
                "value": f'{steps:.0f}',
                "unit": "",
                "priority": 3,
                "detail_url": reverse("health:steps_list"),
                "status": steps_status,
            })
        if health_state.get("glucose_avg_7d"):
            glucose = health_state["glucose_avg_7d"]
            glucose_status = (
                "good" if glucose <= 140
                else "warning" if glucose <= 180
                else "poor"
            )
            metrics.append({
                "label": "Glucose",
                "value": f'{glucose:.0f}',
                "unit": "mg/dL",
                "priority": 5,
                "detail_url": reverse("health:glucose_dashboard"),
                "status": glucose_status,
            })
        if health_state.get("heart_rate_avg_7d"):
            hr = health_state["heart_rate_avg_7d"]
            hr_status = (
                "good" if hr <= 80
                else "warning" if hr <= 100
                else "poor"
            )
            metrics.append({
                "label": "Heart Rate",
                "value": f'{hr:.0f}',
                "unit": "bpm",
                "priority": 6,
                "detail_url": reverse("health:heartrate_list"),
                "status": hr_status,
            })
        if fitness_state.get("workouts_7d") is not None:
            wk = fitness_state["workouts_7d"]
            wk_status = (
                "good" if wk >= 4
                else "warning" if wk >= 2
                else "poor"
            )
            metrics.append({
                "label": "Workouts",
                "value": str(wk),
                "unit": "7d",
                "priority": 4,
                "detail_url": reverse("health:fitness_home"),
                "status": wk_status,
            })
        if nutrition_state.get("calorie_compliance_pct"):
            nut = nutrition_state["calorie_compliance_pct"]
            nut_status = (
                "good" if nut >= 80
                else "warning" if nut >= 60
                else "poor"
            )
            metrics.append({
                "label": "Nutrition",
                "value": f'{nut:.0f}%',
                "unit": "",
                "priority": 7,
                "detail_url": reverse("health:nutrition_home"),
                "status": nut_status,
            })

        metrics.sort(key=lambda m: m["priority"])
        context["primary_metrics"] = metrics[:3]
        context["secondary_metrics"] = metrics[3:]

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
