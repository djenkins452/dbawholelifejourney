"""
Goal Cockpit Service — computes three life-domain scores for the cockpit dials.

Domains:
  - Faith (Bible reading + prayer consistency, 7-day window)
  - Health (medication + workout + sleep + water, 7-day window)
  - Work/Purpose (task completion + session consistency + milestone progress, 7-day window)

Architecture:
  - 100% deterministic (no LLM)
  - Reuses existing data sources (Execution Truth Engine, behavior_score_engine, DailyHealthSummary)
  - Accepts pre-computed adherence_data from the view to avoid duplicate queries
"""

import logging
from datetime import timedelta

from apps.core.utils import get_user_today

logger = logging.getLogger(__name__)

# Trend threshold — difference must exceed this to show ↑ or ↓
TREND_THRESHOLD = 5


class GoalCockpitService:
    """Computes the three domain dials for the goal-based cockpit."""

    def __init__(self, user, adherence_data=None):
        self.user = user
        self.today = get_user_today(user)
        self._adherence = adherence_data

    def get_cockpit_data(self):
        """
        Returns dict with faith, health, work keys.
        Each value is a dict: {score, trend, trend_delta, priority, label, color, components}
        """
        return {
            'faith': self._compute_faith(),
            'health': self._compute_health(),
            'work': self._compute_work(),
        }

    def get_domain_detail(self, domain):
        """Returns expanded panel data for a single domain."""
        method = {
            'faith': self._compute_faith,
            'health': self._compute_health,
            'work': self._compute_work,
        }.get(domain)
        if method:
            return method()
        return self._empty_domain('Unknown', '#888')

    # ── Faith ─────────────────────────────────────────────

    def _compute_faith(self):
        try:
            from apps.core.execution.execution_truth_engine import get_execution_truth
        except ImportError:
            return self._empty_domain('Faith', '#3b82f6')

        try:
            current = self._faith_window(self.today - timedelta(days=6), self.today)
            previous = self._faith_window(self.today - timedelta(days=13), self.today - timedelta(days=7))

            bible_days = current['bible_days']
            prayer_days = current['prayer_days']
            score = round((bible_days / 7 * 50) + (prayer_days / 7 * 50))

            prev_score = round((previous['bible_days'] / 7 * 50) + (previous['prayer_days'] / 7 * 50))
            trend, trend_delta = self._calc_trend(score, prev_score)

            return {
                'score': score,
                'trend': trend,
                'trend_delta': trend_delta,
                'priority': score < 60,
                'label': 'Faith',
                'color': '#3b82f6',
                'components': {
                    'bible_days': bible_days,
                    'prayer_days': prayer_days,
                    'bible_daily': current['bible_daily'],
                    'prayer_daily': current['prayer_daily'],
                },
            }
        except Exception:
            logger.warning("Cockpit: faith score failed", exc_info=True)
            return self._empty_domain('Faith', '#3b82f6')

    def _faith_window(self, start_date, end_date):
        """Count Bible reading and prayer days in a date range."""
        from apps.core.execution.execution_truth_engine import get_execution_truth

        bible_days = 0
        prayer_days = 0
        bible_daily = []
        prayer_daily = []
        day = start_date
        while day <= end_date:
            try:
                truth = get_execution_truth(self.user, day)
                faith = truth.get('domains', {}).get('faith', {})
                bible_done = bool(faith.get('bible_reading_completed'))
                prayer_done = bool(faith.get('prayer_completed'))
                if bible_done:
                    bible_days += 1
                if prayer_done:
                    prayer_days += 1
                bible_daily.append(1 if bible_done else 0)
                prayer_daily.append(1 if prayer_done else 0)
            except Exception:
                bible_daily.append(0)
                prayer_daily.append(0)
            day += timedelta(days=1)

        return {
            'bible_days': bible_days,
            'prayer_days': prayer_days,
            'bible_daily': bible_daily,
            'prayer_daily': prayer_daily,
        }

    # ── Health ────────────────────────────────────────────

    def _compute_health(self):
        try:
            # Medication + workout adherence from pre-computed data
            med_score = None
            workout_score = None
            med_detail = {}
            workout_detail = {}

            if self._adherence and self._adherence.get('domain_scores'):
                ds = self._adherence['domain_scores']
                med_data = ds.get('medication', {})
                med_score = med_data.get('score')
                med_detail = {
                    'completed': med_data.get('completed', 0),
                    'expected': med_data.get('expected', 0),
                    'missed': med_data.get('missed', 0),
                }
                wk_data = ds.get('workout', {})
                workout_score = wk_data.get('score')
                workout_detail = {
                    'completed': wk_data.get('completed', 0),
                    'expected': wk_data.get('expected', 0),
                    'missed': wk_data.get('missed', 0),
                }

            # Sleep + water from DailyHealthSummary
            sleep_score, sleep_detail = self._compute_sleep_consistency()
            water_score, water_detail = self._compute_water_consistency()

            # Weighted average with redistribution for missing components
            weights = {}
            scores_map = {}
            if med_score is not None:
                weights['medication'] = 30
                scores_map['medication'] = med_score
            if workout_score is not None:
                weights['workout'] = 25
                scores_map['workout'] = workout_score
            if sleep_score is not None:
                weights['sleep'] = 25
                scores_map['sleep'] = sleep_score
            if water_score is not None:
                weights['water'] = 20
                scores_map['water'] = water_score

            if weights:
                weight_sum = sum(weights.values())
                score = round(sum(
                    scores_map[k] * (w / weight_sum)
                    for k, w in weights.items()
                ))
            else:
                score = 0

            # Trend: use adherence delta if available, else flat
            trend = 'flat'
            trend_delta = 0
            if self._adherence:
                adh_delta = self._adherence.get('delta', 0)
                trend, trend_delta = self._calc_trend(score, score - adh_delta)

            return {
                'score': score,
                'trend': trend,
                'trend_delta': trend_delta,
                'priority': score < 60,
                'label': 'Health',
                'color': '#22c55e',
                'components': {
                    'medication': med_detail,
                    'workout': workout_detail,
                    'sleep': sleep_detail,
                    'water': water_detail,
                    'med_score': med_score,
                    'workout_score': workout_score,
                    'sleep_score': sleep_score,
                    'water_score': water_score,
                },
            }
        except Exception:
            logger.warning("Cockpit: health score failed", exc_info=True)
            return self._empty_domain('Health', '#22c55e')

    def _compute_sleep_consistency(self):
        """Count nights with ≥7h sleep in last 7 days via DailyHealthSummary."""
        try:
            from apps.health.models import DailyHealthSummary

            start = self.today - timedelta(days=6)
            summaries = DailyHealthSummary.objects.filter(
                user=self.user,
                summary_date__gte=start,
                summary_date__lte=self.today,
                sleep_hours__isnull=False,
            ).values_list('summary_date', 'sleep_hours')

            if not summaries:
                return None, {'avg_hours': None, 'good_nights': 0, 'tracked_nights': 0}

            good_nights = sum(1 for _, hours in summaries if hours and hours >= 7)
            tracked = len(summaries)
            avg_hours = round(sum(float(h) for _, h in summaries if h) / tracked, 1) if tracked else 0

            score = round((good_nights / 7) * 100)
            return score, {
                'avg_hours': avg_hours,
                'good_nights': good_nights,
                'tracked_nights': tracked,
            }
        except Exception:
            logger.debug("Cockpit: sleep query failed", exc_info=True)
            return None, {'avg_hours': None, 'good_nights': 0, 'tracked_nights': 0}

    def _compute_water_consistency(self):
        """Count days meeting water goal (64oz default) in last 7 days."""
        try:
            from apps.health.models import DailyHealthSummary

            start = self.today - timedelta(days=6)
            summaries = DailyHealthSummary.objects.filter(
                user=self.user,
                summary_date__gte=start,
                summary_date__lte=self.today,
                water_oz__isnull=False,
            ).values_list('summary_date', 'water_oz')

            if not summaries:
                return None, {'avg_oz': None, 'good_days': 0, 'tracked_days': 0}

            # Default water goal: 64oz
            water_goal = 64
            try:
                prefs = self.user.preferences
                if hasattr(prefs, 'water_goal_oz') and prefs.water_goal_oz:
                    water_goal = float(prefs.water_goal_oz)
            except Exception:
                pass

            good_days = sum(1 for _, oz in summaries if oz and float(oz) >= water_goal)
            tracked = len(summaries)
            avg_oz = round(sum(float(o) for _, o in summaries if o) / tracked, 1) if tracked else 0

            score = round((good_days / 7) * 100)
            return score, {
                'avg_oz': avg_oz,
                'good_days': good_days,
                'tracked_days': tracked,
                'goal_oz': water_goal,
            }
        except Exception:
            logger.debug("Cockpit: water query failed", exc_info=True)
            return None, {'avg_oz': None, 'good_days': 0, 'tracked_days': 0}

    # ── Work / Purpose ────────────────────────────────────

    def _compute_work(self):
        try:
            task_score, task_detail = self._compute_task_completion()
            session_score, session_detail = self._compute_session_consistency()
            milestone_score, milestone_detail = self._compute_milestone_progress()

            # Weighted average with redistribution
            weights = {}
            scores_map = {}
            if task_score is not None:
                weights['tasks'] = 40
                scores_map['tasks'] = task_score
            if session_score is not None:
                weights['sessions'] = 30
                scores_map['sessions'] = session_score
            if milestone_score is not None:
                weights['milestones'] = 30
                scores_map['milestones'] = milestone_score

            if weights:
                weight_sum = sum(weights.values())
                score = round(sum(
                    scores_map[k] * (w / weight_sum)
                    for k, w in weights.items()
                ))
            else:
                score = 0

            # Trend: compare current vs prior 7d task rate
            prev_task_score, _ = self._compute_task_completion(
                start=self.today - timedelta(days=13),
                end=self.today - timedelta(days=7),
            )
            prev_score = prev_task_score if prev_task_score is not None else 0
            trend, trend_delta = self._calc_trend(score, prev_score)

            return {
                'score': score,
                'trend': trend,
                'trend_delta': trend_delta,
                'priority': score < 60,
                'label': 'Work / Purpose',
                'color': '#f59e0b',
                'components': {
                    'tasks': task_detail,
                    'sessions': session_detail,
                    'milestones': milestone_detail,
                    'task_score': task_score,
                    'session_score': session_score,
                    'milestone_score': milestone_score,
                },
            }
        except Exception:
            logger.warning("Cockpit: work score failed", exc_info=True)
            return self._empty_domain('Work / Purpose', '#f59e0b')

    def _compute_task_completion(self, start=None, end=None):
        """Non-routine task completion rate over a date range."""
        try:
            from apps.life.models import Task

            if start is None:
                start = self.today - timedelta(days=6)
            if end is None:
                end = self.today

            due_tasks = Task.objects.filter(
                user=self.user,
                is_routine=False,
                due_date__gte=start,
                due_date__lte=end,
            ).exclude(status='deleted')

            total = due_tasks.count()
            completed = due_tasks.filter(completion_status='completed').count()

            if total == 0:
                return None, {'completed': 0, 'total': 0}

            score = round((completed / total) * 100)
            return score, {'completed': completed, 'total': total}
        except Exception:
            logger.debug("Cockpit: task query failed", exc_info=True)
            return None, {'completed': 0, 'total': 0}

    def _compute_session_consistency(self):
        """Count distinct days with completed tasks in last 7 days."""
        try:
            from apps.life.models import Task

            start = self.today - timedelta(days=6)
            days_with_tasks = (
                Task.objects.filter(
                    user=self.user,
                    is_routine=False,
                    completion_status='completed',
                    completed_at__date__gte=start,
                    completed_at__date__lte=self.today,
                )
                .exclude(status='deleted')
                .values_list('completed_at__date', flat=True)
                .distinct()
                .count()
            )

            score = round((days_with_tasks / 7) * 100)

            # Find last worked date
            last_task = (
                Task.objects.filter(
                    user=self.user,
                    is_routine=False,
                    completion_status='completed',
                )
                .exclude(status='deleted')
                .order_by('-completed_at')
                .values_list('completed_at', flat=True)
                .first()
            )
            last_worked = last_task.date() if last_task else None

            return score, {
                'days_active': days_with_tasks,
                'last_worked': last_worked,
            }
        except Exception:
            logger.debug("Cockpit: session query failed", exc_info=True)
            return None, {'days_active': 0, 'last_worked': None}

    def _compute_milestone_progress(self):
        """Average milestone completion across active life goals."""
        try:
            from apps.purpose.models import LifeGoal

            goals = LifeGoal.objects.filter(
                user=self.user,
                status='active',
            )

            if not goals.exists():
                return None, {'total_milestones': 0, 'completed_milestones': 0, 'active_goals': 0}

            total_m = 0
            completed_m = 0
            goal_count = 0
            for goal in goals:
                mc = goal.milestone_count
                if mc > 0:
                    total_m += mc
                    completed_m += goal.completed_milestone_count
                    goal_count += 1

            if total_m == 0:
                return None, {'total_milestones': 0, 'completed_milestones': 0, 'active_goals': goals.count()}

            score = round((completed_m / total_m) * 100)
            return score, {
                'total_milestones': total_m,
                'completed_milestones': completed_m,
                'active_goals': goals.count(),
            }
        except Exception:
            logger.debug("Cockpit: milestone query failed", exc_info=True)
            return None, {'total_milestones': 0, 'completed_milestones': 0, 'active_goals': 0}

    # ── Helpers ───────────────────────────────────────────

    def _calc_trend(self, current, previous):
        """Compare two scores and return (trend_str, delta_int)."""
        delta = current - previous
        if delta > TREND_THRESHOLD:
            return 'up', delta
        elif delta < -TREND_THRESHOLD:
            return 'down', delta
        return 'flat', delta

    def _empty_domain(self, label, color):
        return {
            'score': 0,
            'trend': 'flat',
            'trend_delta': 0,
            'priority': False,
            'label': label,
            'color': color,
            'components': {},
        }
