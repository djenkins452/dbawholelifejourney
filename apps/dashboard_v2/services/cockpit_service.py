"""
Goal Cockpit Service — computes dynamic life-domain scores for the cockpit dials.

Domains are determined dynamically from the user's active LifeGoals and HabitGoals,
plus any domains with recent high-confidence signals in SAE state. No domains are
hardcoded — the cockpit shows what matters to THIS user.

Specialized scorers exist for Faith, Health, and Work/Purpose. All other domains
use a generic scorer based on milestone progress + habit completion + task completion.

Architecture:
  - 100% deterministic (no LLM)
  - Health reads ONLY from SAE canonical state (single source of truth)
  - Faith uses Execution Truth Engine
  - Work uses Task/LifeGoal models directly
  - Generic domains use milestone + habit + task completion
  - Domain activation: Raw Data → SAE Signals → Domain Activation → UI
"""

import logging
from datetime import timedelta

from apps.core.utils import get_user_today

logger = logging.getLogger(__name__)

# Trend threshold — difference must exceed this to show ↑ or ↓
TREND_THRESHOLD = 5

# Maximum number of dials to show (prevents UI clutter)
MAX_COCKPIT_DIALS = 5

# ── Domain-to-SAE Signal Mapping ──────────────────────────────────────
# Maps LifeDomain slugs to SAE module keys and the fields that indicate
# "recent high-confidence activity" (used for signal-based activation).
# A domain is signal-active if ANY of its signal_fields returns a truthy value.
DOMAIN_SAE_MAP = {
    'health': {
        'modules': ['health', 'fitness', 'medicine', 'nutrition', 'fasting'],
        'signal_fields': [
            ('health', 'sleep_entries_7d'),
            ('health', 'steps_entries_7d'),
            ('health', 'water_tracked_days_7d'),
            ('health', 'weight_entries_90d'),
            ('fitness', 'workouts_7d'),
            ('medicine', 'adherence_score_7d'),
        ],
    },
    'faith': {
        'modules': ['faith'],
        'signal_fields': [
            ('faith', 'reading_streak'),
            ('faith', 'active_reading_plans'),
        ],
    },
    'work': {
        'modules': ['tasks', 'goals'],
        'signal_fields': [
            ('tasks', 'completed_today'),
            ('tasks', 'tasks_now'),
            ('goals', 'active_goal_count'),
        ],
    },
    'finances': {
        'modules': ['finance'],
        'signal_fields': [
            ('finance', '_contract.summary.account_count'),
        ],
    },
    'personal-growth': {
        'modules': ['habits', 'journal'],
        'signal_fields': [
            ('habits', 'active_habit_count'),
            ('journal', 'entries_7d'),
        ],
    },
    'learning': {
        'modules': ['brain_training'],
        'signal_fields': [
            ('brain_training', '_contract.summary.sessions_this_week'),
        ],
    },
    'relationships': {
        'modules': ['relationships'],
        'signal_fields': [
            ('relationships', '_contract.summary.active_count'),
        ],
    },
    # 'family' has no dedicated SAE module — activates only via LifeGoal/HabitGoal
}


class GoalCockpitService:
    """Computes dynamic goal-driven cockpit dials."""

    def __init__(self, user):
        self.user = user
        self.today = get_user_today(user)

    def get_cockpit_data(self):
        """
        Returns ordered list of domain dicts for active domains.
        Each dict: {slug, label, color, icon, score, trend, trend_delta, priority, components, goal_progress, sort_key}
        """
        active_domains = self._get_active_domains()

        results = []
        for domain in active_domains:
            scorer_cls = DOMAIN_SCORERS.get(domain.slug, GenericDomainScorer)
            try:
                data = scorer_cls(self.user, domain, self.today).compute()
                results.append(data)
            except Exception:
                logger.warning("Cockpit: scorer failed for %s", domain.slug, exc_info=True)
                results.append(_empty_domain(domain))

        # Sort: foundational goals first, then by score descending, then domain sort_order
        results.sort(key=lambda d: d.get('sort_key', (1, 0, 999)))

        return results[:MAX_COCKPIT_DIALS]

    def get_domain_detail(self, domain_slug):
        """Returns expanded panel data for a single domain."""
        try:
            from apps.purpose.models import LifeDomain
            domain = LifeDomain.objects.get(slug=domain_slug, is_active=True)
        except Exception:
            return _empty_domain_from_slug(domain_slug)

        scorer_cls = DOMAIN_SCORERS.get(domain_slug, GenericDomainScorer)
        try:
            return scorer_cls(self.user, domain, self.today).compute()
        except Exception:
            logger.warning("Cockpit: detail scorer failed for %s", domain_slug, exc_info=True)
            return _empty_domain(domain)

    def get_active_domain_slugs(self):
        """Returns set of active domain slugs for validation."""
        return {d.slug for d in self._get_active_domains()}

    def _get_active_domains(self):
        """
        Determine which domains should appear in the cockpit.

        A domain is active if:
        1. The user has active LifeGoals OR HabitGoals in that domain, OR
        2. The domain has recent high-confidence signals in SAE state.

        No hardcoded domain exceptions.
        """
        from apps.purpose.models import HabitGoal, LifeDomain, LifeGoal

        # Rule 1: Domains with active goals or habits
        goal_domain_ids = set(
            LifeGoal.objects.filter(user=self.user, status='active')
            .exclude(domain__isnull=True)
            .values_list('domain_id', flat=True)
            .distinct()
        )
        habit_domain_ids = set(
            HabitGoal.objects.filter(user=self.user, status='active')
            .exclude(domain__isnull=True)
            .values_list('domain_id', flat=True)
            .distinct()
        )
        active_ids = goal_domain_ids | habit_domain_ids

        # Rule 2: Domains with recent SAE signals
        signal_domain_slugs = self._get_signal_active_domains()

        # Combine: get LifeDomain objects for all active domains
        all_domains = LifeDomain.objects.filter(is_active=True)

        result = []
        for domain in all_domains:
            if domain.id in active_ids or domain.slug in signal_domain_slugs:
                result.append(domain)

        # Sort by sort_order
        result.sort(key=lambda d: d.sort_order)
        return result

    def _get_signal_active_domains(self):
        """
        Check SAE state for domains with recent high-confidence signals.
        Returns set of domain slugs that have signal activity.

        Uses cached SAE state — no DB queries. O(1) per field check.
        """
        try:
            from apps.core.ai_state.state_engine import get_state_value
        except ImportError:
            return set()

        active_slugs = set()

        for domain_slug, config in DOMAIN_SAE_MAP.items():
            for module_key, field_key in config['signal_fields']:
                try:
                    value = get_state_value(self.user, f'{module_key}.{field_key}')
                    if value and value not in (0, '0', None, False):
                        active_slugs.add(domain_slug)
                        break  # One signal is enough
                except Exception:
                    continue

        return active_slugs


# ── Scorer Base Class ──────────────────────────────────────────────────


class BaseDomainScorer:
    """Base class for domain-specific cockpit scorers."""

    def __init__(self, user, domain, today):
        self.user = user
        self.domain = domain
        self.today = today

    def compute(self):
        """Compute and return the domain data dict."""
        score, components = self._score()
        trend, trend_delta = self._trend(score)

        # Determine sort key: foundational goals first, then score desc
        has_foundational = self._has_foundational_goal()

        return {
            'slug': self.domain.slug,
            'label': self.domain.name,
            'color': self.domain.color,
            'icon': getattr(self.domain, 'icon', ''),
            'score': score,
            'trend': trend,
            'trend_delta': trend_delta,
            'priority': score < 60,
            'components': components,
            'goal_progress': self._goal_progress(),
            'sort_key': (0 if has_foundational else 1, -score, self.domain.sort_order),
        }

    def _score(self):
        """Return (score_int, components_dict). Override in subclasses."""
        return 0, {}

    def _trend(self, current_score):
        """Default trend calculation. Override for domain-specific logic."""
        return 'flat', 0

    def _has_foundational_goal(self):
        """Check if user has foundational-level goals in this domain."""
        from apps.purpose.models import LifeGoal
        return LifeGoal.objects.filter(
            user=self.user, status='active',
            domain=self.domain, commitment_level='foundational',
        ).exists()

    def _goal_progress(self):
        """Lifetime milestone progress for this domain."""
        try:
            from apps.purpose.models import GoalMilestone, LifeGoal

            goals = LifeGoal.objects.filter(
                user=self.user, status='active', domain=self.domain,
            )
            if not goals.exists():
                return None

            total = GoalMilestone.objects.filter(goal__in=goals).count()
            completed = GoalMilestone.objects.filter(
                goal__in=goals, completed=True,
            ).count()

            if total == 0:
                return None

            return {
                'total': total,
                'completed': completed,
                'percent': round((completed / total) * 100),
            }
        except Exception:
            return None

    @staticmethod
    def _calc_trend(current, previous):
        """Compare two scores and return (trend_str, delta_int)."""
        delta = current - previous
        if delta > TREND_THRESHOLD:
            return 'up', delta
        elif delta < -TREND_THRESHOLD:
            return 'down', delta
        return 'flat', delta


# ── Faith Scorer ───────────────────────────────────────────────────────


class FaithDomainScorer(BaseDomainScorer):
    """Faith scoring: Bible reading + prayer consistency, 8-day window."""

    def _score(self):
        window_days = 8
        full_start = self.today - timedelta(days=15)
        bible_dates, prayer_dates = self._faith_completion_dates(full_start, self.today)

        current_start = self.today - timedelta(days=7)
        current = self._split_faith_window(current_start, self.today, bible_dates, prayer_dates)

        bible_days = current['bible_days']
        prayer_days = current['prayer_days']
        score = round((bible_days / window_days * 50) + (prayer_days / window_days * 50))

        return score, {
            'bible_days': bible_days,
            'prayer_days': prayer_days,
            'bible_daily': current['bible_daily'],
            'prayer_daily': current['prayer_daily'],
        }

    def _trend(self, current_score):
        window_days = 8
        full_start = self.today - timedelta(days=15)
        bible_dates, prayer_dates = self._faith_completion_dates(full_start, self.today)

        prev_start = self.today - timedelta(days=15)
        prev_end = self.today - timedelta(days=8)
        previous = self._split_faith_window(prev_start, prev_end, bible_dates, prayer_dates)
        prev_score = round((previous['bible_days'] / window_days * 50) + (previous['prayer_days'] / window_days * 50))

        return self._calc_trend(current_score, prev_score)

    def _faith_completion_dates(self, start_date, end_date):
        """
        Batch-load Bible and prayer completion dates for a date range.
        Uses the same sources as Execution Truth Engine's faith bridge.
        """
        from apps.core.execution.execution_truth_engine import (
            FAITH_BIBLE_NAMES, FAITH_PRAYER_NAMES,
        )

        bible_dates = set()
        prayer_dates = set()

        # 1. Bible via ReadingPlanProgress
        try:
            from apps.faith.models import UserReadingPlan, UserReadingProgress
            active_plans = UserReadingPlan.objects.filter(
                user=self.user, plan_status='active',
            ).exclude(status='deleted')
            if active_plans.exists():
                progress_dates = (
                    UserReadingProgress.objects.filter(
                        user_plan__in=active_plans,
                        is_completed=True,
                        completed_at__date__gte=start_date,
                        completed_at__date__lte=end_date,
                    )
                    .values_list('completed_at__date', flat=True)
                    .distinct()
                )
                bible_dates.update(progress_dates)
        except ImportError:
            pass

        # 2. Prayer via faith-module Task completion
        try:
            from apps.life.models import Task
            task_dates = (
                Task.objects.filter(
                    user=self.user,
                    module='faith',
                    completion_status='completed',
                    completed_at__date__gte=start_date,
                    completed_at__date__lte=end_date,
                )
                .values_list('completed_at__date', flat=True)
                .distinct()
            )
            prayer_dates.update(task_dates)
        except ImportError:
            pass

        # 3. Bible/Prayer via RoutineLog (the faith bridge)
        try:
            from apps.life.models import RoutineLog, RoutineSchedule
            all_faith_names = FAITH_BIBLE_NAMES | FAITH_PRAYER_NAMES
            faith_schedule_ids = [
                sched.id
                for sched in RoutineSchedule.objects.filter(
                    routine__user=self.user,
                    routine__is_active=True,
                ).exclude(routine__status='deleted').only('id', 'name')
                if sched.name.lower().strip() in all_faith_names
            ]

            if faith_schedule_ids:
                completed_logs = RoutineLog.objects.filter(
                    schedule_id__in=faith_schedule_ids,
                    scheduled_date__gte=start_date,
                    scheduled_date__lte=end_date,
                    log_status__in=(
                        RoutineLog.STATUS_COMPLETED,
                        RoutineLog.STATUS_COMPLETED_LATE,
                    ),
                ).select_related('schedule').only(
                    'scheduled_date', 'schedule__name', 'log_status',
                )

                for log in completed_logs:
                    item_name = (log.schedule.name or '').lower().strip()
                    if item_name in FAITH_BIBLE_NAMES:
                        bible_dates.add(log.scheduled_date)
                    if item_name in FAITH_PRAYER_NAMES:
                        prayer_dates.add(log.scheduled_date)
        except ImportError:
            pass

        return bible_dates, prayer_dates

    def _split_faith_window(self, start_date, end_date, bible_dates, prayer_dates):
        """Split pre-loaded faith dates into a window result dict."""
        bible_days = 0
        prayer_days = 0
        bible_daily = []
        prayer_daily = []
        day = start_date
        while day <= end_date:
            b = 1 if day in bible_dates else 0
            p = 1 if day in prayer_dates else 0
            bible_days += b
            prayer_days += p
            bible_daily.append(b)
            prayer_daily.append(p)
            day += timedelta(days=1)

        return {
            'bible_days': bible_days,
            'prayer_days': prayer_days,
            'bible_daily': bible_daily,
            'prayer_daily': prayer_daily,
        }


# ── Health Scorer ──────────────────────────────────────────────────────


class HealthDomainScorer(BaseDomainScorer):
    """Health scoring from HealthScoreService (7-domain composite) via SAE."""

    def _score(self):
        from apps.core.ai_state.state_engine import get_state_value

        user = self.user

        # Primary: HealthScoreService composite
        score = get_state_value(user, 'health.health_score')
        drivers = get_state_value(user, 'health.health_score_drivers', {})

        # Fallback: behavioral sub-scores
        if score is None:
            score, drivers = self._fallback_health_score(user)
            if score is None:
                return 0, {}

        domains = drivers.get('domains', {})

        components = {
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
            'vitals': {
                'bp_systolic': get_state_value(user, 'health.bp_systolic'),
                'bp_diastolic': get_state_value(user, 'health.bp_diastolic'),
                'heart_rate_avg': get_state_value(user, 'health.heart_rate_avg_7d'),
                'glucose_avg': get_state_value(user, 'health.glucose_avg_7d'),
                'blood_oxygen_avg': get_state_value(user, 'health.blood_oxygen_avg_7d'),
                'recovery_score': get_state_value(user, 'health.recovery_score_today'),
            },
            'score_domains': domains,
            'missing_signals': drivers.get('missing_signals', []),
            'med_score': get_state_value(user, 'medicine.adherence_score_7d'),
            'workout_score': get_state_value(user, 'fitness.workout_adherence_score'),
            'sleep_score': get_state_value(user, 'health.sleep_consistency_score'),
            'water_score': get_state_value(user, 'health.water_consistency_score'),
        }

        return score, components

    def _trend(self, current_score):
        from apps.core.ai_state.state_engine import get_state_value

        prev_score = get_state_value(self.user, 'health.health_score_prev_7d')
        if prev_score is not None:
            return self._calc_trend(current_score, prev_score)
        adh_delta = get_state_value(self.user, 'behavior.adherence_delta', 0)
        return self._calc_trend(current_score, current_score - adh_delta)

    @staticmethod
    def _fallback_health_score(user):
        """Basic health score from behavioral sub-scores when composite unavailable."""
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


# ── Work/Purpose Scorer ────────────────────────────────────────────────


class WorkDomainScorer(BaseDomainScorer):
    """Work/Purpose scoring: task completion + session consistency + milestone progress."""

    def _score(self):
        task_score, task_detail = self._compute_task_completion()
        session_score, session_detail = self._compute_session_consistency()
        milestone_score, milestone_detail = self._compute_milestone_progress()

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

        return score, {
            'tasks': task_detail,
            'sessions': session_detail,
            'milestones': milestone_detail,
            'task_score': task_score,
            'session_score': session_score,
            'milestone_score': milestone_score,
        }

    def _trend(self, current_score):
        prev_task_score, _ = self._compute_task_completion(
            start=self.today - timedelta(days=13),
            end=self.today - timedelta(days=7),
        )
        prev_score = prev_task_score if prev_task_score is not None else 0
        return self._calc_trend(current_score, prev_score)

    def _compute_task_completion(self, start=None, end=None):
        """Non-routine task completion rate over a date range."""
        try:
            from django.db.models import Q
            from apps.life.models import Task

            if start is None:
                start = self.today - timedelta(days=6)
            if end is None:
                end = self.today

            base_tasks = Task.objects.filter(
                user=self.user,
                is_routine=False,
                due_date__gte=start,
                due_date__lte=end,
            ).exclude(status='deleted')

            countable_tasks = base_tasks.filter(
                Q(due_date__lt=self.today)
                | Q(completion_status='completed')
            )

            total = countable_tasks.count()
            completed = countable_tasks.filter(completion_status='completed').count()

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
        """Milestone completion across active life goals."""
        try:
            from django.db.models import Q
            from apps.purpose.models import GoalMilestone, LifeGoal

            goals = LifeGoal.objects.filter(
                user=self.user, status='active',
            )

            if not goals.exists():
                return None, {'total_milestones': 0, 'completed_milestones': 0, 'active_goals': 0}

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


# ── Generic Domain Scorer ──────────────────────────────────────────────


class GenericDomainScorer(BaseDomainScorer):
    """
    Generic scorer for any domain without specialized logic.

    Score = weighted average of:
      - Milestone completion (50%) — from LifeGoal milestones in this domain
      - Habit completion rate (30%) — from HabitGoal entries in this domain
      - Task completion (20%) — from Tasks assigned to this domain's module
    """

    def _score(self):
        milestone_score, milestone_detail = self._milestone_completion()
        habit_score, habit_detail = self._habit_completion()
        task_score, task_detail = self._task_completion()

        weights = {}
        scores_map = {}
        if milestone_score is not None:
            weights['milestones'] = 50
            scores_map['milestones'] = milestone_score
        if habit_score is not None:
            weights['habits'] = 30
            scores_map['habits'] = habit_score
        if task_score is not None:
            weights['tasks'] = 20
            scores_map['tasks'] = task_score

        if weights:
            weight_sum = sum(weights.values())
            score = round(sum(
                scores_map[k] * (w / weight_sum)
                for k, w in weights.items()
            ))
        else:
            score = 0

        return score, {
            'milestones': milestone_detail,
            'habits': habit_detail,
            'tasks': task_detail,
            'milestone_score': milestone_score,
            'habit_score': habit_score,
            'task_score': task_score,
        }

    def _trend(self, current_score):
        # Generic domains use flat trend (no historical comparison yet)
        return 'flat', 0

    def _milestone_completion(self):
        """Milestone completion for goals in this domain."""
        try:
            from django.db.models import Q
            from apps.purpose.models import GoalMilestone, LifeGoal

            goals = LifeGoal.objects.filter(
                user=self.user, status='active', domain=self.domain,
            )
            if not goals.exists():
                return None, {'total': 0, 'completed': 0}

            due = GoalMilestone.objects.filter(goal__in=goals).filter(
                Q(target_date__isnull=True) | Q(target_date__lte=self.today)
            )
            total = due.count()
            completed = due.filter(completed=True).count()

            if total == 0:
                return None, {'total': 0, 'completed': 0, 'active_goals': goals.count()}

            return round((completed / total) * 100), {
                'total': total,
                'completed': completed,
                'active_goals': goals.count(),
            }
        except Exception:
            return None, {'total': 0, 'completed': 0}

    def _habit_completion(self):
        """7-day habit completion rate for habits in this domain."""
        try:
            from apps.purpose.models import HabitEntry, HabitGoal

            habits = HabitGoal.objects.filter(
                user=self.user, status='active', domain=self.domain,
            )
            if not habits.exists():
                return None, {'active_habits': 0, 'completion_rate': 0}

            start = self.today - timedelta(days=6)
            entries = HabitEntry.objects.filter(
                goal__in=habits,
                date__gte=start,
                date__lte=self.today,
            )
            total = entries.count()
            completed = entries.filter(completed=True).count()

            if total == 0:
                return None, {'active_habits': habits.count(), 'completion_rate': 0}

            rate = round((completed / total) * 100)
            return rate, {
                'active_habits': habits.count(),
                'completed_entries': completed,
                'total_entries': total,
                'completion_rate': rate,
            }
        except Exception:
            return None, {'active_habits': 0, 'completion_rate': 0}

    def _task_completion(self):
        """7-day task completion for tasks linked to this domain."""
        try:
            from django.db.models import Q
            from apps.life.models import Task

            # Map domain slugs to task module names
            module_map = {
                'faith': 'faith',
                'health': 'health',
                'work': 'purpose',
                'finances': 'finance',
                'family': 'life',
                'learning': 'life',
                'personal-growth': 'life',
                'relationships': 'life',
            }
            module = module_map.get(self.domain.slug, 'life')

            start = self.today - timedelta(days=6)
            tasks = Task.objects.filter(
                user=self.user,
                module=module,
                is_routine=False,
                due_date__gte=start,
                due_date__lte=self.today,
            ).exclude(status='deleted').filter(
                Q(due_date__lt=self.today) | Q(completion_status='completed')
            )

            total = tasks.count()
            completed = tasks.filter(completion_status='completed').count()

            if total == 0:
                return None, {'completed': 0, 'total': 0}

            return round((completed / total) * 100), {
                'completed': completed,
                'total': total,
            }
        except Exception:
            return None, {'completed': 0, 'total': 0}


# ── Scorer Registry ────────────────────────────────────────────────────

DOMAIN_SCORERS = {
    'faith': FaithDomainScorer,
    'health': HealthDomainScorer,
    'work': WorkDomainScorer,
}


# ── Helpers ────────────────────────────────────────────────────────────


def _empty_domain(domain):
    """Zero-state fallback for a LifeDomain object."""
    return {
        'slug': domain.slug,
        'label': domain.name,
        'color': domain.color,
        'icon': getattr(domain, 'icon', ''),
        'score': 0,
        'trend': 'flat',
        'trend_delta': 0,
        'priority': False,
        'components': {},
        'goal_progress': None,
        'sort_key': (1, 0, domain.sort_order),
    }


def _empty_domain_from_slug(slug):
    """Zero-state fallback when LifeDomain lookup fails."""
    return {
        'slug': slug,
        'label': slug.replace('-', ' ').title(),
        'color': '#888888',
        'icon': '',
        'score': 0,
        'trend': 'flat',
        'trend_delta': 0,
        'priority': False,
        'components': {},
        'goal_progress': None,
        'sort_key': (1, 0, 999),
    }
