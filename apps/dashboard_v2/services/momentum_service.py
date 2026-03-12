"""
Goal Momentum Service — computes momentum and progress per LifeGoal.

Momentum (0-100): "How strongly am I moving toward this goal RIGHT NOW?"
  Composed of 5 weighted components:
    Habits (30%) + Tasks (20%) + Domain Signals (20%) + Discipline (15%) + Recency (15%)

Progress (0-100): "How far along the journey?" (milestone-based)
  Uses existing LifeGoal.milestone_progress_percent.

All data is read from existing engines/services — no logic duplication.
"""

import logging
import math
from datetime import timedelta

from django.core.cache import cache

from apps.core.utils import get_user_today

logger = logging.getLogger(__name__)

# Cache settings
CACHE_KEY_TEMPLATE = "dashboard_v2:{user_id}:momentum"
CACHE_TTL = 300  # 5 minutes

# Component weights (sum = 100)
WEIGHTS = {
    "habits": 30,
    "tasks": 20,
    "domain_signals": 20,
    "discipline": 15,
    "recency": 15,
}

# When a domain has no SAE signals, redistribute domain_signals weight
REDISTRIBUTED_WEIGHTS = {
    "habits": 40,
    "tasks": 30,
    "domain_signals": 0,
    "discipline": 15,
    "recency": 15,
}

# Recency decay constant (days) — score = 100 * exp(-days / DECAY_CONSTANT)
DECAY_CONSTANT = 3.0

# Discipline: streak-to-score mapping (interpolated)
DISCIPLINE_BREAKPOINTS = [
    (0, 0),
    (3, 25),
    (7, 50),
    (14, 75),
    (30, 90),
    (60, 100),
]

# Domain slug → SAE builder keys and signal mappings
DOMAIN_SIGNAL_MAP = {
    "health": {
        "sae_builders": ["health", "fitness", "nutrition", "fasting"],
        "task_module": "health",
        "signals": {
            "workouts_7d": {"max_val": 7, "label_fmt": "{val} workouts this week"},
            "macro_compliance_score": {"max_val": 100, "label_fmt": "Nutrition compliance: {val}%"},
            "fasting_compliance_score": {"max_val": 100, "label_fmt": "Fasting compliance: {val}%"},
            "workout_consistency_score": {"max_val": 100, "label_fmt": "Workout consistency: {val}%"},
        },
    },
    "faith": {
        "sae_builders": ["faith"],
        "task_module": "faith",
        "signals": {
            "reading_streak": {"max_val": 30, "label_fmt": "{val}-day reading streak"},
            "active_reading_plans": {"max_val": 3, "label_fmt": "{val} active Bible plans"},
        },
    },
    "work": {
        "sae_builders": ["goals"],
        "task_module": "purpose",
        "signals": {
            "completion_rate": {"max_val": 100, "label_fmt": "Milestone completion: {val}%"},
        },
    },
    "personal-growth": {
        "sae_builders": ["journal"],
        "task_module": "journal",
        "signals": {
            "entry_frequency": {"max_val": 7, "label_fmt": "{val} entries/week"},
        },
    },
    # Domains with no SAE signals — weight redistributes to habits/tasks
    "family": {
        "sae_builders": [],
        "task_module": "life",
        "signals": {},
    },
    "finances": {
        "sae_builders": [],
        "task_module": "life",
        "signals": {},
    },
    "learning": {
        "sae_builders": [],
        "task_module": "life",
        "signals": {},
    },
}

# Domain color defaults (fallback if LifeDomain.color is empty)
DOMAIN_COLORS = {
    "health": "#22c55e",
    "faith": "#8b5cf6",
    "work": "#3b82f6",
    "family": "#f59e0b",
    "finances": "#10b981",
    "personal-growth": "#6366f1",
    "learning": "#06b6d4",
}


class GoalMomentumService:
    """Computes goal momentum for all active LifeGoals."""

    def __init__(self, user):
        self.user = user
        self.today = get_user_today(user)
        self._sae_cache = {}

    def get_all_momentum(self):
        """
        Return momentum for all active goals.
        Tries cache first, then computes live.

        Returns list of dicts with goal_id, title, domain, momentum, progress, etc.
        """
        cache_key = CACHE_KEY_TEMPLATE.format(user_id=self.user.pk)
        cached = cache.get(cache_key)
        if cached is not None:
            return cached

        result = self._compute_all()
        cache.set(cache_key, result, CACHE_TTL)
        return result

    def _compute_all(self):
        from apps.purpose.models import LifeGoal

        goals = (
            LifeGoal.objects.filter(user=self.user, status="active")
            .select_related("domain")
            .prefetch_related("milestones")
        )

        results = []
        for goal in goals:
            try:
                result = self.compute_momentum(goal)
                results.append(result)
            except Exception:
                logger.error(
                    "Failed to compute momentum for goal %s (user %s)",
                    goal.pk,
                    self.user.pk,
                    exc_info=True,
                )
        return results

    def compute_momentum(self, goal):
        """Compute momentum + progress for a single LifeGoal."""
        domain_slug = goal.domain.slug if goal.domain else "life"
        domain_config = DOMAIN_SIGNAL_MAP.get(domain_slug, DOMAIN_SIGNAL_MAP.get("family", {}))
        has_domain_signals = bool(domain_config.get("signals"))

        # Choose weight set based on whether domain has signals
        weights = WEIGHTS if has_domain_signals else REDISTRIBUTED_WEIGHTS

        # Compute each component
        habits_result = self._compute_habits(goal, domain_slug)
        tasks_result = self._compute_tasks(goal, domain_config)
        domain_result = self._compute_domain_signals(domain_config)
        discipline_result = self._compute_discipline(goal, domain_slug)
        recency_result = self._compute_recency(goal, domain_config)

        # Weighted momentum score
        raw_score = (
            habits_result["score"] * weights["habits"]
            + tasks_result["score"] * weights["tasks"]
            + domain_result["score"] * weights["domain_signals"]
            + discipline_result["score"] * weights["discipline"]
            + recency_result["score"] * weights["recency"]
        ) / 100

        momentum_score = min(100, max(0, round(raw_score)))

        # Progress score from milestones
        progress_score = goal.milestone_progress_percent
        if not goal.has_milestones and goal.target_date:
            # Fallback: time-elapsed proxy
            total_days = (goal.target_date - goal.created_at.date()).days
            elapsed_days = (self.today - goal.created_at.date()).days
            if total_days > 0:
                progress_score = min(100, max(0, round(elapsed_days / total_days * 100)))

        # Trend (from historical snapshots)
        momentum_trend = self._compute_trend(goal, momentum_score)

        # Domain color
        domain_color = DOMAIN_COLORS.get(domain_slug, "#6b7280")
        if goal.domain and goal.domain.color:
            domain_color = goal.domain.color

        return {
            "goal_id": goal.pk,
            "goal_title": goal.title,
            "domain": goal.domain.name if goal.domain else "Life",
            "domain_slug": domain_slug,
            "domain_color": domain_color,
            "momentum": momentum_score,
            "progress": progress_score,
            "momentum_trend": momentum_trend,
            "drivers": {
                "habits": habits_result,
                "tasks": tasks_result,
                "domain_signals": domain_result,
                "discipline": discipline_result,
                "recency": recency_result,
            },
        }

    def _get_sae_state(self, builder_name):
        """Get SAE state, cached per request."""
        if builder_name not in self._sae_cache:
            try:
                from apps.core.ai_state import state_builder

                builder_fn = getattr(state_builder, f"build_{builder_name}_state", None)
                if builder_fn:
                    self._sae_cache[builder_name] = builder_fn(self.user)
                else:
                    self._sae_cache[builder_name] = {}
            except Exception:
                logger.error("SAE builder %s failed", builder_name, exc_info=True)
                self._sae_cache[builder_name] = {}
        return self._sae_cache[builder_name]

    def _compute_habits(self, goal, domain_slug):
        """Habits component: average 7-day completion rate of linked habits."""
        try:
            from apps.purpose.models import HabitGoal

            habits = HabitGoal.objects.filter(
                user=self.user,
                status="active",
            )

            # Filter habits that might relate to this goal's domain
            # HabitGoal doesn't have a domain FK — we use name/purpose keyword matching
            # as a heuristic, or fall back to all active habits
            habit_scores = []
            for habit in habits:
                try:
                    from apps.purpose.services.streak_service import get_streak_data

                    streak_data = get_streak_data(habit)
                    # Use streak as a proxy for recent completion rate
                    # Current streak / 7 days gives a 0-1 rate
                    rate = min(1.0, streak_data.current / 7.0) if streak_data.current > 0 else 0
                    habit_scores.append(rate)
                except Exception:
                    continue

            if not habit_scores:
                return {"score": 50, "label": "No habits tracked"}

            avg_rate = sum(habit_scores) / len(habit_scores)
            score = round(avg_rate * 100)
            active_count = len(habit_scores)
            good_count = sum(1 for s in habit_scores if s >= 0.5)

            return {
                "score": score,
                "label": f"{good_count}/{active_count} habits on track",
            }
        except Exception:
            logger.error("Habits computation failed", exc_info=True)
            return {"score": 0, "label": "Unable to compute"}

    def _compute_tasks(self, goal, domain_config):
        """Tasks component: completion rate of domain-related tasks in last 7 days."""
        try:
            from apps.life.models import Task

            task_module = domain_config.get("task_module", "life")
            cutoff = self.today - timedelta(days=7)

            # Tasks due in the last 7 days for this domain
            base_qs = Task.objects.filter(
                user=self.user,
                module=task_module,
            ).exclude(is_deleted=True)

            total_due = base_qs.filter(
                due_date__gte=cutoff,
                due_date__lte=self.today,
            ).count()

            completed = base_qs.filter(
                completion_status="completed",
                completed_at__date__gte=cutoff,
            ).count()

            if total_due == 0:
                # Fall back to any completed tasks in the period
                if completed > 0:
                    return {"score": min(100, completed * 20), "label": f"{completed} tasks completed"}
                return {"score": 50, "label": "No tasks due"}

            rate = min(1.0, completed / total_due)
            score = round(rate * 100)
            return {"score": score, "label": f"{completed}/{total_due} tasks completed"}
        except Exception:
            logger.error("Tasks computation failed", exc_info=True)
            return {"score": 0, "label": "Unable to compute"}

    def _compute_domain_signals(self, domain_config):
        """Domain-specific signals from SAE state builders."""
        signals = domain_config.get("signals", {})
        if not signals:
            return {"score": 0, "label": "No domain signals"}

        signal_scores = []
        signal_labels = []

        for builder_name in domain_config.get("sae_builders", []):
            state = self._get_sae_state(builder_name)
            for signal_key, config in signals.items():
                val = state.get(signal_key)
                if val is not None:
                    try:
                        val = float(val)
                        max_val = config["max_val"]
                        normalized = min(1.0, max(0, val / max_val)) * 100
                        signal_scores.append(normalized)
                        label = config["label_fmt"].format(val=round(val, 1))
                        signal_labels.append(label)
                    except (TypeError, ValueError):
                        continue

        if not signal_scores:
            return {"score": 50, "label": "Insufficient data"}

        avg_score = round(sum(signal_scores) / len(signal_scores))
        top_label = signal_labels[0] if signal_labels else "Domain signals active"
        return {"score": avg_score, "label": top_label}

    def _compute_discipline(self, goal, domain_slug):
        """Discipline component: streak length mapped to 0-100."""
        try:
            from apps.purpose.models import HabitGoal
            from apps.purpose.services.streak_service import get_streak_data

            habits = HabitGoal.objects.filter(user=self.user, status="active")
            max_streak = 0
            for habit in habits:
                try:
                    streak = get_streak_data(habit)
                    max_streak = max(max_streak, streak.current)
                except Exception:
                    continue

            score = self._streak_to_score(max_streak)
            if max_streak > 0:
                return {"score": score, "label": f"{max_streak}-day streak"}
            return {"score": 0, "label": "No active streaks"}
        except Exception:
            logger.error("Discipline computation failed", exc_info=True)
            return {"score": 0, "label": "Unable to compute"}

    def _compute_recency(self, goal, domain_config):
        """Recency component: exponential decay based on last action date."""
        try:
            last_action_dates = []

            # Check tasks
            from apps.life.models import Task

            task_module = domain_config.get("task_module", "life")
            last_task = (
                Task.objects.filter(
                    user=self.user,
                    module=task_module,
                    completion_status="completed",
                )
                .exclude(is_deleted=True)
                .order_by("-completed_at")
                .values_list("completed_at", flat=True)
                .first()
            )
            if last_task:
                last_action_dates.append(last_task.date())

            # Check habit entries
            from apps.purpose.models import HabitGoal

            last_habit = (
                HabitGoal.objects.filter(user=self.user, status="active")
                .order_by("-updated_at")
                .values_list("updated_at", flat=True)
                .first()
            )
            if last_habit:
                last_action_dates.append(last_habit.date())

            if not last_action_dates:
                return {"score": 0, "label": "No recent activity"}

            most_recent = max(last_action_dates)
            days_since = (self.today - most_recent).days
            score = round(100 * math.exp(-days_since / DECAY_CONSTANT))
            score = min(100, max(0, score))

            if days_since == 0:
                label = "Active today"
            elif days_since == 1:
                label = "Active yesterday"
            else:
                label = f"Last active {days_since} days ago"

            return {"score": score, "label": label}
        except Exception:
            logger.error("Recency computation failed", exc_info=True)
            return {"score": 0, "label": "Unable to compute"}

    def _compute_trend(self, goal, current_score):
        """Compute trend by comparing current to 7-day average from snapshots."""
        from apps.dashboard_v2.models import GoalMomentumSnapshot

        cutoff = self.today - timedelta(days=7)
        snapshots = GoalMomentumSnapshot.objects.filter(
            user=self.user,
            goal=goal,
            snapshot_date__gte=cutoff,
            snapshot_date__lt=self.today,
        ).values_list("momentum_score", flat=True)

        if not snapshots:
            return "stable"

        avg = sum(snapshots) / len(snapshots)
        if current_score > avg + 10:
            return "rising"
        elif current_score < avg - 10:
            return "falling"
        return "stable"

    @staticmethod
    def _streak_to_score(streak_days):
        """Map streak length to 0-100 score via linear interpolation."""
        if streak_days <= 0:
            return 0
        for i in range(len(DISCIPLINE_BREAKPOINTS) - 1):
            low_days, low_score = DISCIPLINE_BREAKPOINTS[i]
            high_days, high_score = DISCIPLINE_BREAKPOINTS[i + 1]
            if streak_days <= high_days:
                ratio = (streak_days - low_days) / (high_days - low_days)
                return round(low_score + ratio * (high_score - low_score))
        return 100

    def compute_and_persist(self):
        """
        Called by nightly Celery task.
        Computes momentum for all active goals and saves GoalMomentumSnapshot rows.
        """
        from apps.dashboard_v2.models import GoalMomentumSnapshot
        from apps.purpose.models import LifeGoal

        goals = LifeGoal.objects.filter(user=self.user, status="active").select_related(
            "domain"
        ).prefetch_related("milestones")

        for goal in goals:
            try:
                data = self.compute_momentum(goal)
                # Compute 7d average including today
                cutoff = self.today - timedelta(days=7)
                prior_scores = list(
                    GoalMomentumSnapshot.objects.filter(
                        user=self.user,
                        goal=goal,
                        snapshot_date__gte=cutoff,
                        snapshot_date__lt=self.today,
                    ).values_list("momentum_score", flat=True)
                )
                all_scores = prior_scores + [data["momentum"]]
                avg_7d = round(sum(all_scores) / len(all_scores))

                GoalMomentumSnapshot.objects.update_or_create(
                    user=self.user,
                    goal=goal,
                    snapshot_date=self.today,
                    defaults={
                        "momentum_score": data["momentum"],
                        "progress_score": data["progress"],
                        "drivers": data["drivers"],
                        "momentum_7d_avg": avg_7d,
                        "momentum_trend": data["momentum_trend"],
                    },
                )
            except Exception:
                logger.error(
                    "Failed to persist momentum for goal %s", goal.pk, exc_info=True
                )
