"""
Daily Progress Service — tracks daily execution completeness.

Computes component scores dynamically based on what's actually due today:
- Routines: Task.is_routine completion rate (only if routines exist today)
- Medicine: medicine_utils adherence (only if doses scheduled today)
- Tasks: Non-routine task completion (only if tasks due today)
- Workout: WorkoutSession (only if scheduled in active workout plan)
- Journaling: JournalEntry logged today
- Faith: Bible reading / prayer activity today

Weights are redistributed proportionally when a component has nothing due,
so the score reflects completion of what's actually expected.
"""

import logging

from apps.core.utils import get_user_today

logger = logging.getLogger(__name__)

# Base weights — redistributed proportionally among active components
BASE_WEIGHTS = {
    "routines": 25,
    "medicine": 20,
    "tasks": 20,
    "workout": 15,
    "journaling": 10,
    "faith": 10,
}


class DailyProgressService:
    """Tracks how much of today's expected activity has been completed."""

    def __init__(self, user):
        self.user = user
        self.today = get_user_today(user)

    def get_today(self):
        """
        Get today's progress snapshot. Creates one if it doesn't exist.
        Returns dict with overall_score and per-component breakdown.
        """
        from apps.dashboard_v2.models import DailyProgressSnapshot

        snapshot, created = DailyProgressSnapshot.objects.get_or_create(
            user=self.user,
            snapshot_date=self.today,
            defaults={"components": {}},
        )

        # Always recompute — the cache layer above (2-min TTL) prevents
        # excessive calls.  Without this, snapshots created at midnight
        # or first load never reflect later task/medicine completions.
        self.recompute(snapshot)
        snapshot.refresh_from_db()

        return {
            "overall_score": snapshot.overall_score,
            "routines": {"score": snapshot.routines_score, **self._component_data(snapshot, "routines")},
            "medicine": {"score": snapshot.medicine_score, **self._component_data(snapshot, "medicine")},
            "tasks": {"score": snapshot.tasks_score, **self._component_data(snapshot, "tasks")},
            "workout": {"score": snapshot.workout_score, **self._component_data(snapshot, "workout")},
            "journaling": {"score": snapshot.journaling_score, **self._component_data(snapshot, "journaling")},
            "faith": {"score": snapshot.faith_score, **self._component_data(snapshot, "faith")},
        }

    def _component_data(self, snapshot, key):
        """Extract raw component data from the components JSON field."""
        components = snapshot.components or {}
        return {
            "done": components.get(f"{key}_done", 0),
            "total": components.get(f"{key}_total", 0),
        }

    def recompute(self, snapshot=None):
        """
        Full recompute of today's progress.
        Uses existing services — never re-derives calculations.
        Weights are redistributed among components that are actually due today.
        """
        from apps.dashboard_v2.models import DailyProgressSnapshot

        if snapshot is None:
            snapshot, _ = DailyProgressSnapshot.objects.get_or_create(
                user=self.user,
                snapshot_date=self.today,
                defaults={"components": {}},
            )

        components = {}

        # Compute all component scores
        scores = {}
        compute_methods = {
            "routines": self._compute_routines,
            "medicine": self._compute_medicine,
            "tasks": self._compute_tasks,
            "workout": self._compute_workout,
            "journaling": self._compute_journaling,
            "faith": self._compute_faith,
        }

        for key, method in compute_methods.items():
            score, data = method()
            scores[key] = score
            components.update(data)
            setattr(snapshot, f"{key}_score", score)

        # Determine which components are active (have something due today).
        # Components with total == 0 are excluded from weighting so their
        # weight is redistributed proportionally to active components.
        active_weights = {}
        for key, base_weight in BASE_WEIGHTS.items():
            total = components.get(f"{key}_total", 0)
            if total > 0:
                active_weights[key] = base_weight

        # Calculate overall score with redistributed weights
        if active_weights:
            weight_sum = sum(active_weights.values())
            weighted_total = sum(
                scores[key] * (weight / weight_sum * 100)
                for key, weight in active_weights.items()
            )
            snapshot.overall_score = round(weighted_total / 100)
        else:
            # Nothing due today — 100% by default
            snapshot.overall_score = 100

        snapshot.components = components
        snapshot.save()

    def _compute_routines(self):
        """Routine task completion for today."""
        try:
            from apps.life.models import Task

            routines = Task.objects.filter(
                user=self.user,
                is_routine=True,
                due_date=self.today,
            ).exclude(status="deleted")

            total = routines.count()
            done = routines.filter(completion_status="completed").count()

            score = round((done / total) * 100) if total > 0 else 100
            return score, {"routines_done": done, "routines_total": total}
        except Exception:
            logger.error("Routine computation failed", exc_info=True)
            return 0, {"routines_done": 0, "routines_total": 0}

    def _compute_medicine(self):
        """Medicine adherence for today using existing utility."""
        try:
            from apps.health.medicine_utils import calculate_medicine_adherence

            result = calculate_medicine_adherence(self.user, self.today, self.today)
            rate = result.get("adherence_rate")
            if rate is None:
                return 100, {"medicine_done": 0, "medicine_total": 0}
            return round(rate), {
                "medicine_done": result.get("taken_doses", 0),
                "medicine_total": result.get("expected_doses", 0),
            }
        except Exception:
            logger.error("Medicine computation failed", exc_info=True)
            return 0, {"medicine_done": 0, "medicine_total": 0}

    def _compute_tasks(self):
        """Non-routine task completion for today."""
        try:
            from apps.life.models import Task

            tasks = Task.objects.filter(
                user=self.user,
                is_routine=False,
                due_date=self.today,
            ).exclude(status="deleted")

            total = tasks.count()
            done = tasks.filter(completion_status="completed").count()

            if total == 0:
                return 100, {"tasks_done": 0, "tasks_total": 0}
            score = round((done / total) * 100)
            return score, {"tasks_done": done, "tasks_total": total}
        except Exception:
            logger.error("Tasks computation failed", exc_info=True)
            return 0, {"tasks_done": 0, "tasks_total": 0}

    def _compute_workout(self):
        """Whether a workout was logged today, respecting the user's schedule."""
        try:
            from apps.health.models import WorkoutPlan, WorkoutSession

            # Check if today is a scheduled workout day
            day_of_week = self.today.weekday()  # 0=Monday, 6=Sunday
            active_plan = (
                WorkoutPlan.objects.filter(user=self.user, is_active=True).first()
            )

            if active_plan:
                schedule_entry = active_plan.schedule_entries.filter(
                    day_of_week=day_of_week
                ).first()
                # Rest day or no entry for today — no workout expected
                if not schedule_entry or schedule_entry.is_rest_day:
                    return 100, {"workout_done": 0, "workout_total": 0}

            done = WorkoutSession.objects.filter(
                user=self.user,
                date=self.today,
            ).exists()

            score = 100 if done else 0
            return score, {"workout_done": 1 if done else 0, "workout_total": 1}
        except Exception:
            logger.error("Workout computation failed", exc_info=True)
            return 0, {"workout_done": 0, "workout_total": 1}

    def _compute_journaling(self):
        """Whether a journal entry was made today."""
        try:
            from apps.journal.models import JournalEntry

            done = JournalEntry.objects.filter(
                user=self.user,
                entry_date=self.today,
            ).exists()

            score = 100 if done else 0
            return score, {"journaling_done": 1 if done else 0, "journaling_total": 1}
        except Exception:
            logger.error("Journaling computation failed", exc_info=True)
            return 0, {"journaling_done": 0, "journaling_total": 1}

    def _compute_faith(self):
        """
        Bible reading or prayer activity today.

        Uses the Execution Truth Engine as the SINGLE source of truth.
        This includes cross-domain bridges (routine "Prayer Time" → faith).
        """
        try:
            from apps.core.execution.execution_truth_engine import get_execution_truth
            truth = get_execution_truth(self.user, self.today)
            faith = truth['domains']['faith']
            faith_done = faith['prayer_completed'] or faith['bible_reading_completed']
            score = 100 if faith_done else 0
            return score, {"faith_done": 1 if faith_done else 0, "faith_total": 1}
        except Exception:
            logger.error("Faith computation failed", exc_info=True)
            return 0, {"faith_done": 0, "faith_total": 1}
