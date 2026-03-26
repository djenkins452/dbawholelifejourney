"""
Goal Cockpit Service — computes three life-domain scores for the cockpit dials.

Domains:
  - Faith (Bible reading + prayer consistency, 7-day window)
  - Health (medication + workout + sleep + water, 7-day window)
  - Work/Purpose (task completion + session consistency + milestone progress, 7-day window)

Architecture:
  - 100% deterministic (no LLM)
  - Health reads ONLY from SAE canonical state (single source of truth)
  - Faith uses Execution Truth Engine
  - Work uses Task/LifeGoal models directly
"""

import logging
from datetime import timedelta

from apps.core.utils import get_user_today

logger = logging.getLogger(__name__)

# Trend threshold — difference must exceed this to show ↑ or ↓
TREND_THRESHOLD = 5


class GoalCockpitService:
    """Computes the three domain dials for the goal-based cockpit."""

    def __init__(self, user):
        self.user = user
        self.today = get_user_today(user)

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
        """
        Health score from HealthScoreService (7-domain composite) via SAE.

        Primary: HealthScoreService composite (sleep, recovery, glucose,
        weight, workout, nutrition, activity — adaptive weighting).
        Fallback: weighted average of available behavioral sub-scores from
        SAE (medication, workout, sleep, water) when composite not yet
        available (baseline collecting or stale state).
        """
        try:
            from apps.core.ai_state.state_engine import get_state_value

            user = self.user

            # Primary score: HealthScoreService composite stored in SAE
            score = get_state_value(user, 'health.health_score')
            drivers = get_state_value(user, 'health.health_score_drivers', {})

            # Fallback: if HealthScoreService hasn't computed yet (baseline
            # not ready, or DailyHealthSummary not scored), derive a basic
            # score from available behavioral sub-scores in SAE.
            if score is None:
                score, drivers = self._fallback_health_score(user)
                if score is None:
                    return self._empty_domain('Health', '#22c55e')

            # Trend from HealthScoreService previous-week delta
            prev_score = get_state_value(user, 'health.health_score_prev_7d')
            if prev_score is not None:
                trend, trend_delta = self._calc_trend(score, prev_score)
            else:
                adh_delta = get_state_value(user, 'behavior.adherence_delta', 0)
                trend, trend_delta = self._calc_trend(score, score - adh_delta)

            # Score domain breakdown from HealthScoreService
            domains = drivers.get('domains', {})

            # Component details for expanded health panel
            components = {
                # Behavioral detail cards (existing)
                'medication': {
                    'completed': get_state_value(user, 'medicine.completed_7d', 0),
                    'expected': get_state_value(user, 'medicine.expected_7d', 0),
                    'missed': get_state_value(user, 'medicine.missed_7d', 0),
                },
                'workout': {
                    'completed': get_state_value(user, 'fitness.workout_completed_7d', 0),
                    'expected': get_state_value(user, 'fitness.workout_expected_7d', 0),
                    'missed': get_state_value(user, 'fitness.workout_missed_7d', 0),
                },
                'sleep': {
                    'avg_hours': get_state_value(user, 'health.sleep_avg_hours_7d'),
                    'good_nights': get_state_value(user, 'health.sleep_good_nights_7d', 0),
                    'tracked_nights': get_state_value(user, 'health.sleep_entries_7d', 0),
                },
                'water': {
                    'avg_oz': get_state_value(user, 'health.water_avg_oz_7d'),
                    'good_days': get_state_value(user, 'health.water_good_days_7d', 0),
                    'tracked_days': get_state_value(user, 'health.water_tracked_days_7d', 0),
                    'goal_oz': get_state_value(user, 'health.water_goal_oz', 64),
                },
                # Vitals snapshot
                'vitals': {
                    'bp_systolic': get_state_value(user, 'health.bp_systolic'),
                    'bp_diastolic': get_state_value(user, 'health.bp_diastolic'),
                    'heart_rate_avg': get_state_value(user, 'health.heart_rate_avg_7d'),
                    'glucose_avg': get_state_value(user, 'health.glucose_avg_7d'),
                    'blood_oxygen_avg': get_state_value(user, 'health.blood_oxygen_avg_7d'),
                    'recovery_score': get_state_value(user, 'health.recovery_score_today'),
                },
                # HealthScoreService domain breakdown
                'score_domains': domains,
                'missing_signals': drivers.get('missing_signals', []),
                # Individual sub-scores for template compatibility
                'med_score': get_state_value(user, 'medicine.adherence_score_7d'),
                'workout_score': get_state_value(user, 'fitness.workout_adherence_score'),
                'sleep_score': get_state_value(user, 'health.sleep_consistency_score'),
                'water_score': get_state_value(user, 'health.water_consistency_score'),
            }

            return {
                'score': score,
                'trend': trend,
                'trend_delta': trend_delta,
                'priority': score < 60,
                'label': 'Health',
                'color': '#22c55e',
                'components': components,
            }
        except Exception:
            logger.warning("Cockpit: health score failed", exc_info=True)
            return self._empty_domain('Health', '#22c55e')

    @staticmethod
    def _fallback_health_score(user):
        """
        Basic health score from behavioral sub-scores when HealthScoreService
        composite is not available (baseline collecting or stale state).

        Uses SAE fields only — no raw queries.
        """
        from apps.core.ai_state.state_engine import get_state_value

        weights = {}
        scores = {}

        med = get_state_value(user, 'medicine.adherence_score_7d')
        if med is not None:
            weights['medication'] = 30
            scores['medication'] = med

        wk = get_state_value(user, 'fitness.workout_adherence_score')
        if wk is not None:
            weights['workout'] = 25
            scores['workout'] = wk

        sl = get_state_value(user, 'health.sleep_consistency_score')
        if sl is not None:
            weights['sleep'] = 25
            scores['sleep'] = sl

        wa = get_state_value(user, 'health.water_consistency_score')
        if wa is not None:
            weights['water'] = 20
            scores['water'] = wa

        if not weights:
            return None, {}

        total_w = sum(weights.values())
        score = round(sum(scores[k] * (weights[k] / total_w) for k in weights))
        drivers = {
            'domains': {
                k: {'score': scores[k], 'weight': weights[k], 'detail': f'{k} adherence'}
                for k in weights
            },
            'missing_signals': [],
            'status': 'fallback',
        }
        return score, drivers

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
        """
        Milestone completion across active life goals.

        Only counts milestones that are due (target_date <= today) or have
        no target_date. Future milestones are excluded — you shouldn't be
        penalized for milestones that aren't due yet.
        """
        try:
            from django.db.models import Q

            from apps.purpose.models import GoalMilestone, LifeGoal

            goals = LifeGoal.objects.filter(
                user=self.user,
                status='active',
            )

            if not goals.exists():
                return None, {'total_milestones': 0, 'completed_milestones': 0, 'active_goals': 0}

            # Only milestones that are due or have no deadline
            due_milestones = GoalMilestone.objects.filter(
                goal__in=goals,
            ).filter(
                Q(target_date__isnull=True) | Q(target_date__lte=self.today)
            )

            total_m = due_milestones.count()
            completed_m = due_milestones.filter(completed=True).count()

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
