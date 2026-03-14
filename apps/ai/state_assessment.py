"""
State Assessment Mixin — Extracted from PersonalAssistant.

Contains all state gathering, assessment, and snapshot logic:
- assess_current_state() — main entry point
- _build_state_from_sae() — SAE canonical read
- _gather_comprehensive_state() — flat-key state for AI assessment
- _get_*_state() — domain-specific metric gatherers
- _calculate_*_streak() — streak computations
- _generate_ai_assessment() — AI-synthesized assessment
- _snapshot_to_dict() — USS snapshot → dict conversion

Architecture: SAE (Layer 3) is the canonical source for live metrics.
USS (UserStateSnapshot) caches AI assessments only.
"""

import logging
from datetime import timedelta
from decimal import Decimal
from typing import Optional, Dict, Any

from .models import UserStateSnapshot
from .services import ai_service, AIService

logger = logging.getLogger(__name__)


class StateAssessmentMixin:
    """State assessment methods for PersonalAssistant.

    Expects the host class to provide:
    - self.user, self.prefs, self.faith_enabled, self.coaching_style
    - self._build_system_prompt()
    """

    def assess_current_state(self, force_refresh: bool = False) -> Dict[str, Any]:
        """
        Assess the user's current state across all dimensions.

        Architecture (Phase 3 migration):
        - METRICS come from SAE UserState (always fresh, signal-updated)
        - AI ASSESSMENT is cached in UserStateSnapshot (regenerated every 2hrs)
        - Falls back to direct queries if SAE has no data

        Returns a comprehensive assessment including:
        - Current metrics from all modules (from SAE)
        - AI-generated assessment (cached in USS)
        - Alignment gaps (intention vs reality)
        - Celebration-worthy achievements
        """
        import time as _t
        _acs_start = _t.monotonic()
        from apps.core.utils import get_user_today, get_user_now

        today = get_user_today(self.user)

        # ── Step 1: Read live metrics from SAE (canonical source) ──
        sae_result = self._build_state_from_sae()
        if sae_result:
            # Overlay fresh task counts (SAE tasks may be slightly behind
            # signal delivery in the same request)
            if self.prefs.life_enabled:
                fresh_task_data = self._get_task_state(today, today - timedelta(days=7))
                sae_result['tasks'] = {
                    'completed_today': fresh_task_data.get('tasks_completed_today', 0),
                    'completed_week': fresh_task_data.get('tasks_completed_week', 0),
                    'overdue': fresh_task_data.get('tasks_overdue', 0),
                    'due_today': fresh_task_data.get('tasks_due_today', 0),
                }
            # Overlay today-specific ephemeral data
            sae_result['faith'].update(self._get_fresh_today_faith(today))
            sae_result['health']['workout_today'] = self._get_workout_today(today)
        else:
            # SAE has no data — fall back to USS path (legacy)
            logger.info("ASSESS_STATE user=%s — SAE empty, falling back to USS", self.user.id)

        # ── Step 2: Check AI assessment cache (stored in USS) ──
        snapshot = UserStateSnapshot.objects.filter(
            user=self.user,
            snapshot_date=today,
        ).first()

        need_ai_regen = force_refresh
        if not need_ai_regen and snapshot:
            # Check coaching style change
            snapshot_metadata = snapshot.alignment_gaps or []
            stored_style = None
            for item in snapshot_metadata:
                if isinstance(item, dict) and item.get('_coaching_style'):
                    stored_style = item.get('_coaching_style')
                    break
            if stored_style is None or stored_style != self.coaching_style:
                need_ai_regen = True
                logger.info(
                    "AI assessment regen: coaching style changed %s → %s",
                    stored_style, self.coaching_style,
                )

            # Check time staleness (>2 hours)
            if not need_ai_regen:
                user_now = get_user_now(self.user)
                hours_old = (user_now - snapshot.updated_at.astimezone(
                    user_now.tzinfo
                )).total_seconds() / 3600
                if hours_old >= 2:
                    need_ai_regen = True
                    logger.info("AI assessment regen: %.1f hours old", hours_old)
        elif not snapshot:
            need_ai_regen = True

        # ── Step 3: Regenerate AI assessment if needed ──
        if need_ai_regen:
            # Use _gather_comprehensive_state for AI assessment (needs flat keys)
            state_data = self._gather_comprehensive_state()

            ai_assessment = ""
            alignment_gaps = []
            celebration_worthy = []

            if self.prefs.ai_enabled and AIService.check_user_consent(self.user):
                ai_result = self._generate_ai_assessment(state_data)
                ai_assessment = ai_result.get('assessment', '')
                alignment_gaps = ai_result.get('gaps', [])
                celebration_worthy = ai_result.get('celebrations', [])

            # Store coaching style marker
            alignment_gaps_with_style = list(alignment_gaps) if alignment_gaps else []
            alignment_gaps_with_style.append({'_coaching_style': self.coaching_style})

            # Update USS (AI assessment cache only — metrics are in SAE now)
            snapshot, _ = UserStateSnapshot.objects.update_or_create(
                user=self.user,
                snapshot_date=today,
                defaults={
                    'journal_count_total': state_data.get('journal_total', 0),
                    'journal_count_week': state_data.get('journal_week', 0),
                    'journal_streak': state_data.get('journal_streak', 0),
                    'dominant_mood': state_data.get('dominant_mood', ''),
                    'tasks_completed_today': state_data.get('tasks_completed_today', 0),
                    'tasks_completed_week': state_data.get('tasks_completed_week', 0),
                    'tasks_overdue': state_data.get('tasks_overdue', 0),
                    'tasks_due_today': state_data.get('tasks_due_today', 0),
                    'active_goals': state_data.get('active_goals', 0),
                    'completed_goals_month': state_data.get('completed_goals_month', 0),
                    'active_prayers': state_data.get('active_prayers', 0),
                    'answered_prayers_month': state_data.get('answered_prayers_month', 0),
                    'weight_current': state_data.get('weight_current'),
                    'weight_trend': state_data.get('weight_trend', ''),
                    'fasts_completed_week': state_data.get('fasts_week', 0),
                    'workouts_week': state_data.get('workouts_week', 0),
                    'workout_streak': state_data.get('workout_streak', 0),
                    'medicine_adherence': state_data.get('medicine_adherence'),
                    'active_intentions': state_data.get('active_intentions', 0),
                    'active_habit_goals': state_data.get('active_habit_goals', 0),
                    'habit_completion_rate': state_data.get('habit_completion_rate'),
                    'habit_current_streak': state_data.get('habit_current_streak', 0),
                    'habit_goals_data': state_data.get('habit_goals_data', []),
                    'ai_assessment': ai_assessment,
                    'alignment_gaps': alignment_gaps_with_style,
                    'celebration_worthy': celebration_worthy,
                }
            )

        # ── Step 4: Build final result ──
        if sae_result:
            # SAE metrics + USS AI assessment
            if snapshot:
                sae_result['ai_assessment'] = snapshot.ai_assessment
                sae_result['alignment_gaps'] = snapshot.alignment_gaps
                sae_result['celebration_worthy'] = snapshot.celebration_worthy
            result = sae_result
        else:
            # Full USS fallback (no SAE data)
            result = self._snapshot_to_dict(snapshot) if snapshot else {}
            if result:
                if self.prefs.life_enabled:
                    fresh_task_data = self._get_task_state(today, today - timedelta(days=7))
                    result['tasks'] = {
                        'completed_today': fresh_task_data.get('tasks_completed_today', 0),
                        'completed_week': fresh_task_data.get('tasks_completed_week', 0),
                        'overdue': fresh_task_data.get('tasks_overdue', 0),
                        'due_today': fresh_task_data.get('tasks_due_today', 0),
                    }
                result['faith'].update(self._get_fresh_today_faith(today))
                result['health']['workout_today'] = self._get_workout_today(today)

        _tasks = result.get('tasks', {}) if result else {}
        _source = 'sae' if sae_result else 'uss'
        logger.info(
            "ASSESS_STATE user=%s source=%s ai_regen=%s due_today=%s overdue=%s (%.0fms)",
            self.user.id, _source, need_ai_regen,
            _tasks.get('due_today', '?'), _tasks.get('overdue', '?'),
            (_t.monotonic() - _acs_start) * 1000,
        )
        return result or {}

    def _get_fresh_today_faith(self, today) -> Dict:
        """Get today-specific faith data (reading plan + task engagement)."""
        try:
            from apps.faith.models import UserReadingPlan
            from apps.faith.engagement import get_faith_engagement_details

            active_plans = UserReadingPlan.objects.filter(
                user=self.user, plan_status='active'
            ).exclude(status='deleted')

            engagement = get_faith_engagement_details(self.user, today)

            return {
                'active_reading_plans': active_plans.count(),
                'reading_completed_today': engagement['reading_completed_today'],
                'faith_engaged_today': engagement['faith_engaged_today'],
            }
        except Exception:
            return {}

    def _get_workout_today(self, today) -> bool:
        """Check if user has logged a workout today.

        Truth source: WorkoutSession records ONLY. Explicitly excludes
        soft-deleted records for defense-in-depth (matches executive_briefing.py).
        Calendar projections and task completion status are NOT consulted.
        """
        try:
            from apps.health.models import WorkoutSession
            return WorkoutSession.objects.filter(
                user=self.user, date=today
            ).exclude(status='deleted').exists()
        except Exception:
            return False

    def _gather_comprehensive_state(self) -> Dict[str, Any]:
        """Gather all user data for state assessment."""
        from apps.core.utils import get_user_today, get_user_now

        get_user_now(self.user)
        today = get_user_today(self.user)
        week_ago = today - timedelta(days=7)
        month_ago = today - timedelta(days=30)

        data = {}

        # Journal data
        if self.prefs.journal_enabled:
            data.update(self._get_journal_state(today, week_ago, month_ago))

        # Task data
        if self.prefs.life_enabled:
            data.update(self._get_task_state(today, week_ago))

        # Goal data
        if self.prefs.purpose_enabled:
            data.update(self._get_purpose_state(today, month_ago))

        # Faith data
        if self.faith_enabled:
            data.update(self._get_faith_state(month_ago))

        # Health data
        if self.prefs.health_enabled:
            data.update(self._get_health_state(today, week_ago))

        return data

    def _get_journal_state(self, today, week_ago, month_ago) -> Dict:
        """Get journal-related metrics via canonical JournalMetricsService."""
        from apps.journal.services.metrics import get_journal_metrics
        return get_journal_metrics(self.user)

    def _get_task_state(self, today, week_ago) -> Dict:
        """Get task-related metrics using priority-based grouping.

        Uses the same queryset pattern as the Organize page so counts match.
        """
        import time as _t
        _ts = _t.monotonic()
        from apps.life.models import Task
        from apps.life.views import _refresh_stale_task_priorities

        _refresh_stale_task_priorities(self.user)

        tasks = Task.objects.filter(user=self.user)
        incomplete = tasks.filter(completion_status='pending')

        result = {
            'tasks_total': tasks.count(),
            'tasks_completed_today': tasks.filter(
                completion_status='completed',
                completed_at__date=today
            ).count(),
            'tasks_completed_week': tasks.filter(
                completion_status='completed',
                completed_at__date__gte=week_ago
            ).count(),
            # Priority-based counts — matches Organize page buckets
            'due_today': incomplete.filter(priority='now').count(),
            'overdue': incomplete.filter(priority='now', due_date__lt=today).count(),
            'tasks_due_today': incomplete.filter(priority='now').count(),
            'tasks_overdue': incomplete.filter(priority='now', due_date__lt=today).count(),
            'tasks_due_week': incomplete.filter(priority__in=['now', 'soon']).count(),
        }
        logger.info(
            "TASK_STATE user=%s due_today=%s overdue=%s completed_today=%s (%.0fms)",
            self.user.id, result['due_today'], result['overdue'],
            result['tasks_completed_today'], (_t.monotonic() - _ts) * 1000,
        )
        return result

    def _get_purpose_state(self, today, month_ago) -> Dict:
        """Get purpose/goals-related metrics including habit goals."""
        from apps.purpose.models import (
            AnnualDirection, LifeGoal, ChangeIntention
        )

        current_year = today.year

        # Annual direction
        direction = AnnualDirection.objects.filter(
            user=self.user,
            year=current_year
        ).first()

        goals = LifeGoal.objects.filter(user=self.user)
        intentions = ChangeIntention.objects.filter(user=self.user, status='active')

        # Habit goals data
        habit_data = self._get_habit_goals_data(today)

        return {
            'word_of_year': direction.word_of_year if direction else None,
            'annual_theme': direction.theme if direction else None,
            'active_goals': goals.filter(status='active').count(),
            'completed_goals_month': goals.filter(
                status='completed',
                completed_date__gte=month_ago
            ).count(),
            'active_intentions': intentions.count(),
            'goals_list': list(goals.filter(status='active').values(
                'id', 'title', 'why_it_matters', 'domain__name'
            )[:5]),
            'intentions_list': list(intentions.values(
                'id', 'intention', 'motivation'
            )[:5]),
            # Habit goal metrics
            'active_habit_goals': habit_data['active_count'],
            'habit_completion_rate': habit_data['avg_completion_rate'],
            'habit_current_streak': habit_data['max_streak'],
            'habit_goals_data': habit_data['goals_detail'],
        }

    def _get_habit_goals_data(self, today) -> Dict:
        """
        Get detailed habit goal data for AI analysis.

        Returns:
            Dict with:
            - active_count: Number of active habit goals
            - avg_completion_rate: Average completion percentage
            - max_streak: Longest current streak across all goals
            - goals_detail: List of habit goal details for AI context
        """
        from apps.purpose.models import HabitGoal

        habit_goals = HabitGoal.objects.filter(
            user=self.user,
            status='active',
            habit_required=True
        )

        active_count = habit_goals.count()
        if active_count == 0:
            return {
                'active_count': 0,
                'avg_completion_rate': None,
                'max_streak': 0,
                'goals_detail': [],
            }

        total_rate = 0
        max_streak = 0
        goals_detail = []

        for goal in habit_goals:
            # Calculate stats for each goal
            completion_rate = goal.completion_rate
            current_streak = goal.current_streak
            total_days = goal.total_days
            completed_days = goal.completed_days

            # Calculate days_elapsed and days_remaining (not properties on model)
            end_check = min(goal.end_date, today)
            days_elapsed = max(0, (end_check - goal.start_date).days + 1) if end_check >= goal.start_date else 0
            days_remaining = max(0, (goal.end_date - today).days) if goal.end_date > today else 0
            days_without_entry = max(0, days_elapsed - completed_days)

            total_rate += completion_rate
            if current_streak > max_streak:
                max_streak = current_streak

            # Build goal detail for AI context (non-judgmental language)
            goal_info = {
                'name': goal.name,
                'purpose': goal.purpose,
                'start_date': goal.start_date.isoformat(),
                'end_date': goal.end_date.isoformat(),
                'total_days': total_days,
                'days_elapsed': days_elapsed,
                'days_remaining': days_remaining,
                'completed_days': completed_days,
                'days_without_entry': days_without_entry,  # Non-judgmental: not "missed"
                'completion_rate': round(completion_rate, 1),
                'current_streak': current_streak,
                # Recovery pattern: days since last missed day
                'recovery_opportunity': self._calculate_recovery_pattern(goal, today),
            }
            goals_detail.append(goal_info)

        avg_completion = total_rate / active_count if active_count > 0 else 0

        return {
            'active_count': active_count,
            'avg_completion_rate': round(avg_completion, 1),
            'max_streak': max_streak,
            'goals_detail': goals_detail,
        }

    def _calculate_recovery_pattern(self, goal, today) -> Dict:
        """
        Calculate recovery patterns for a habit goal.

        Identifies patterns in how the user recovers after missing days,
        which helps the AI provide supportive guidance.

        Returns dict with:
        - days_since_last_gap: Days since last day without entry
        - longest_recovery: Longest streak after a gap
        - typical_recovery: Average streak length after gaps
        """
        from datetime import timedelta

        entries = goal.habit_entries.filter(completed=True).order_by('date')
        if not entries.exists():
            return {
                'days_since_last_gap': None,
                'has_recovered_before': False,
                'message': 'No entries yet - great opportunity to start!',
            }

        entry_dates = set(e.date for e in entries)
        gaps = []
        recovery_streaks = []

        # Analyze the date range
        current_date = goal.start_date
        end_date = min(goal.end_date, today)
        in_gap = False
        current_streak = 0

        while current_date <= end_date:
            if current_date in entry_dates:
                if in_gap:
                    # Recovered from gap
                    in_gap = False
                current_streak += 1
            else:
                if not in_gap and current_streak > 0:
                    # Just started a gap, record the streak before
                    recovery_streaks.append(current_streak)
                    current_streak = 0
                in_gap = True
                gaps.append(current_date)
            current_date += timedelta(days=1)

        # Final streak if exists
        if current_streak > 0 and gaps:
            recovery_streaks.append(current_streak)

        # Days since last gap
        days_since_last_gap = None
        if gaps:
            last_gap = max(gaps)
            days_since_last_gap = (today - last_gap).days

        return {
            'days_since_last_gap': days_since_last_gap,
            'has_recovered_before': len(recovery_streaks) > 0,
            'recovery_count': len(recovery_streaks),
            'avg_recovery_streak': round(sum(recovery_streaks) / len(recovery_streaks), 1) if recovery_streaks else 0,
        }

    def _get_faith_state(self, month_ago) -> Dict:
        """Get faith-related metrics via canonical FaithMetricsService."""
        from apps.faith.services import get_faith_metrics
        return get_faith_metrics(self.user)

    def _get_health_state(self, today, week_ago) -> Dict:
        """Get health-related metrics across all health models."""
        from apps.health.models import (
            WeightEntry, FastingWindow, WorkoutSession,
            MedicineLog, StepsEntry, HeartRateEntry, SleepEntry,
            BloodPressureEntry, GlucoseEntry, BloodOxygenEntry,
        )

        data = {}

        # Weight
        weights = WeightEntry.objects.filter(user=self.user).order_by('-recorded_at')
        latest = weights.first()
        if latest:
            data['weight_current'] = Decimal(str(latest.value_in_lb))

            # Trend calculation
            month_weights = list(weights[:10])
            if len(month_weights) >= 2:
                if month_weights[0].value_in_lb < month_weights[-1].value_in_lb:
                    data['weight_trend'] = 'down'
                elif month_weights[0].value_in_lb > month_weights[-1].value_in_lb:
                    data['weight_trend'] = 'up'
                else:
                    data['weight_trend'] = 'stable'

        # Fasting
        data['fasts_week'] = FastingWindow.objects.filter(
            user=self.user,
            ended_at__isnull=False,
            started_at__date__gte=week_ago
        ).count()

        # Workouts — exclude soft-deleted records for defense-in-depth
        workouts = WorkoutSession.objects.filter(user=self.user).exclude(status='deleted')
        data['workouts_week'] = workouts.filter(date__gte=week_ago).count()
        data['workout_today'] = workouts.filter(date=today).exists()
        data['workout_streak'] = self._calculate_workout_streak(today)

        # Medicine adherence (correct: expected vs taken from schedules)
        from apps.health.medicine_utils import calculate_medicine_adherence
        adherence = calculate_medicine_adherence(self.user, week_ago, today)
        data['medicine_adherence'] = adherence['adherence_rate']

        # Steps
        steps_week = StepsEntry.objects.filter(
            user=self.user, logged_date__gte=week_ago
        )
        if steps_week.exists():
            from django.db.models import Avg
            avg_steps = steps_week.aggregate(avg=Avg('count'))['avg']
            data['steps_avg_7d'] = int(avg_steps) if avg_steps else 0
            latest_steps = steps_week.order_by('-logged_date').first()
            if latest_steps:
                data['steps_latest'] = latest_steps.count
                data['steps_latest_date'] = latest_steps.logged_date

        # Heart Rate
        hr_entries = HeartRateEntry.objects.filter(
            user=self.user, recorded_at__date__gte=week_ago
        )
        if hr_entries.exists():
            from django.db.models import Avg, Min, Max
            hr_agg = hr_entries.aggregate(avg=Avg('bpm'), lo=Min('bpm'), hi=Max('bpm'))
            data['heart_rate_avg_7d'] = round(float(hr_agg['avg']), 0) if hr_agg['avg'] else None
            data['heart_rate_range_7d'] = f"{hr_agg['lo']}-{hr_agg['hi']}" if hr_agg['lo'] else None

        # Sleep
        sleep_entries = SleepEntry.objects.filter(
            user=self.user, sleep_date__gte=week_ago
        )
        if sleep_entries.exists():
            from django.db.models import Avg
            avg_sleep = sleep_entries.aggregate(avg=Avg('asleep_duration_minutes'))['avg']
            data['sleep_avg_hours_7d'] = round(float(avg_sleep) / 60, 1) if avg_sleep else None
            latest_sleep = sleep_entries.order_by('-sleep_date').first()
            if latest_sleep and latest_sleep.asleep_duration_minutes:
                data['sleep_latest_hours'] = round(latest_sleep.asleep_duration_minutes / 60, 1)

        # Blood Pressure
        bp_entries = BloodPressureEntry.objects.filter(
            user=self.user, recorded_at__date__gte=week_ago
        )
        if bp_entries.exists():
            from django.db.models import Avg
            bp_agg = bp_entries.aggregate(
                avg_sys=Avg('systolic'), avg_dia=Avg('diastolic')
            )
            data['bp_avg_7d'] = f"{round(float(bp_agg['avg_sys']))}/{round(float(bp_agg['avg_dia']))}" if bp_agg['avg_sys'] else None

        # Glucose
        glucose_entries = GlucoseEntry.objects.filter(
            user=self.user, recorded_at__date__gte=week_ago
        )
        if glucose_entries.exists():
            from django.db.models import Avg
            avg_glucose = glucose_entries.aggregate(avg=Avg('value'))['avg']
            data['glucose_avg_7d'] = round(float(avg_glucose), 0) if avg_glucose else None

        # Blood Oxygen
        spo2_entries = BloodOxygenEntry.objects.filter(
            user=self.user, recorded_at__date__gte=week_ago
        )
        if spo2_entries.exists():
            from django.db.models import Avg
            avg_spo2 = spo2_entries.aggregate(avg=Avg('spo2'))['avg']
            data['blood_oxygen_avg_7d'] = round(float(avg_spo2), 1) if avg_spo2 else None

        # Heart rate events (clinically significant — always include count)
        try:
            from apps.health.models import HeartRateEventEntry
            hr_events_week = HeartRateEventEntry.objects.filter(
                user=self.user, recorded_at__date__gte=week_ago
            ).count()
            if hr_events_week > 0:
                data['heart_rate_events_7d'] = hr_events_week
        except ImportError:
            pass  # HeartRateEventEntry model may not exist yet
        except Exception as _hr_err:
            logger.warning(
                "STATE_HEART_RATE user=%s — heart rate event query failed: %s",
                self.user.id, _hr_err, exc_info=True,
            )

        return data

    def _calculate_journal_streak(self, today) -> int:
        """Calculate consecutive days of journaling (excludes today)."""
        from apps.journal.models import JournalEntry

        entries = JournalEntry.objects.filter(
            user=self.user
        ).order_by('-entry_date').values_list('entry_date', flat=True).distinct()[:60]

        if not entries:
            return 0

        streak = 0
        # Start from yesterday - today doesn't count toward the streak
        expected = today - timedelta(days=1)

        for entry_date in entries:
            if entry_date == expected:
                streak += 1
                expected -= timedelta(days=1)
            elif entry_date < expected:
                break

        return streak

    def _calculate_workout_streak(self, today) -> int:
        """Calculate consecutive days with workouts."""
        from apps.health.models import WorkoutSession

        dates = WorkoutSession.objects.filter(
            user=self.user
        ).order_by('-date').values_list('date', flat=True).distinct()[:60]

        if not dates:
            return 0

        streak = 0
        expected = today

        for workout_date in dates:
            if workout_date == expected:
                streak += 1
                expected -= timedelta(days=1)
            elif workout_date < expected:
                break

        return streak

    def _generate_ai_assessment(self, state_data: Dict) -> Dict:
        """Generate AI assessment of user state - focused on what REMAINS to be done."""
        from apps.core.cos.prompt_builder import STATE_ASSESSMENT_PROMPT

        if not ai_service.is_available:
            return {'assessment': '', 'gaps': [], 'celebrations': []}

        # Build context for AI - prioritize REMAINING items and gaps
        context_parts = []

        # Get time context for urgency - use day_status not exact hours (assessment gets cached)
        time_context = self._get_time_context()
        context_parts.append(f"Time: {time_context['current_time']} ({time_context['day_status'].replace('_', ' ')})")

        # Task context - overdue and due today are most important
        overdue = state_data.get('tasks_overdue', 0)
        due_today = state_data.get('tasks_due_today', 0)
        remaining = overdue + due_today
        if overdue > 0:
            context_parts.append(f"URGENT: {overdue} overdue tasks need action NOW")
        if due_today > 0:
            context_parts.append(f"{due_today} tasks STILL due today")
        if remaining == 0 and state_data.get('tasks_due_week', 0) > 0:
            context_parts.append(f"{state_data['tasks_due_week']} tasks coming up this week")

        # Journal gap - only if it's an issue
        last_journal = state_data.get('last_journal_date')
        if last_journal:
            from apps.core.utils import get_user_today
            user_today = get_user_today(self.user)
            days_ago = (user_today - last_journal).days
            if days_ago >= 2:
                context_parts.append(f"Haven't journaled in {days_ago} days")

        # Goal context - focus on active goals that need progress
        if state_data.get('active_goals', 0) > 0:
            context_parts.append(f"{state_data['active_goals']} active life goals awaiting progress")

        # Faith context
        if self.faith_enabled:
            prayers = state_data.get('active_prayers', 0)
            if prayers > 0:
                context_parts.append(f"{prayers} active prayer requests")

        # Health gaps
        adherence = state_data.get('medicine_adherence')
        if adherence is not None and adherence < 80:
            context_parts.append(f"Medicine adherence at {adherence}% - needs attention")

        # Word of year for context
        if state_data.get('word_of_year'):
            context_parts.append(f"Word of year: {state_data['word_of_year']}")

        # Active intentions
        intentions = state_data.get('intentions_list', [])
        if intentions:
            intention_text = ", ".join([i['intention'] for i in intentions[:2]])
            context_parts.append(f"Active intentions: {intention_text}")

        # Build system prompt with coaching style
        system_prompt = self._build_system_prompt(include_time_context=True)
        system_prompt += "\n\n" + STATE_ASSESSMENT_PROMPT

        user_prompt = f"""User's current state - focus on what REMAINS:
{chr(10).join('- ' + p for p in context_parts)}

What STILL needs the user's attention today? Be direct, actionable, and mindful of time remaining. Use your coaching style ({self.coaching_style})."""

        try:
            response = ai_service._call_api(system_prompt, user_prompt, max_tokens=150)

            # Identify gaps from data - focus on action items
            gaps = []

            if overdue > 0:
                gaps.append({
                    'area': 'tasks',
                    'description': f'{overdue} overdue tasks need attention',
                    'action_url': '/life/tasks/',
                    'action_text': 'View Tasks'
                })

            if last_journal:
                from apps.core.utils import get_user_today
                user_today = get_user_today(self.user)
                days = (user_today - last_journal).days
                if days >= 3:
                    gaps.append({
                        'area': 'journal',
                        'description': f"Haven't journaled in {days} days",
                        'action_url': '/journal/new/',
                        'action_text': 'Journal Now'
                    })

            if adherence is not None and adherence < 80:
                gaps.append({
                    'area': 'health',
                    'description': f'Medicine adherence at {adherence}%',
                    'action_url': '/health/medicine/',
                    'action_text': 'Check Medicine'
                })

            # Celebrations are minimal - only for dashboard display, not assistant focus
            celebrations = []

            return {
                'assessment': response or '',
                'gaps': gaps,
                'celebrations': celebrations  # Kept minimal for dashboard, not assistant focus
            }

        except Exception as e:
            logger.error(f"AI assessment error: {e}")
            return {'assessment': '', 'gaps': [], 'celebrations': []}

    def _snapshot_to_dict(self, snapshot: 'UserStateSnapshot') -> Dict:
        """Convert snapshot model to dictionary."""
        return {
            'date': snapshot.snapshot_date,
            'journal': {
                'total': snapshot.journal_count_total,
                'week': snapshot.journal_count_week,
                'streak': snapshot.journal_streak,
                'dominant_mood': snapshot.dominant_mood,
            },
            'tasks': {
                'completed_today': snapshot.tasks_completed_today,
                'completed_week': snapshot.tasks_completed_week,
                'overdue': snapshot.tasks_overdue,
                'due_today': snapshot.tasks_due_today,
            },
            'goals': {
                'active': snapshot.active_goals,
                'completed_month': snapshot.completed_goals_month,
            },
            'faith': {
                'active_prayers': snapshot.active_prayers,
                'answered_month': snapshot.answered_prayers_month,
            },
            'health': {
                'weight_current': float(snapshot.weight_current) if snapshot.weight_current else None,
                'weight_trend': snapshot.weight_trend,
                'fasts_week': snapshot.fasts_completed_week,
                'workouts_week': snapshot.workouts_week,
                'workout_streak': snapshot.workout_streak,
                'medicine_adherence': snapshot.medicine_adherence,
            },
            'intentions': {
                'active': snapshot.active_intentions,
                'alignment_score': snapshot.intention_alignment_score,
            },
            'ai_assessment': snapshot.ai_assessment,
            'alignment_gaps': snapshot.alignment_gaps,
            'celebration_worthy': snapshot.celebration_worthy,
        }

    def _build_state_from_sae(self) -> Optional[Dict]:
        """Read live state from SAE UserState and map to Beth's dict format.

        Returns the same dict structure as _snapshot_to_dict() but sourced
        from SAE (always fresh, updated by signals). Returns None if SAE
        has no data for this user.

        This is the CANONICAL state read path. _snapshot_to_dict() is only
        used as a fallback when SAE data is unavailable.
        """
        try:
            from apps.core.ai_state.models import UserState
            sae = UserState.objects.filter(user=self.user).first()
            if not sae or not sae.state_data:
                return None

            sd = sae.state_data
            tasks = sd.get('tasks', {})
            health = sd.get('health', {})
            fitness = sd.get('fitness', {})
            fasting = sd.get('fasting', {})
            medicine = sd.get('medicine', {})
            journal = sd.get('journal', {})
            goals = sd.get('goals', {})
            faith = sd.get('faith', {})
            habits = sd.get('habits', {})

            # Extract dominant mood from mood_distribution
            mood_dist = journal.get('mood_distribution', {})
            dominant_mood = ''
            if mood_dist:
                dominant_mood = max(mood_dist, key=mood_dist.get, default='')

            # Map SAE → Beth dict format
            from apps.core.utils import get_user_today
            today = get_user_today(self.user)

            return {
                'date': today,
                'journal': {
                    'total': journal.get('entries_30d', 0),  # Approximate
                    'week': round(journal.get('entry_frequency', 0)),
                    'streak': 0,  # SAE doesn't track streaks; overlaid later if needed
                    'dominant_mood': dominant_mood,
                },
                'tasks': {
                    'completed_today': tasks.get('completed_today', 0),
                    'completed_week': 0,  # Not in SAE; acceptable approximation
                    'overdue': tasks.get('overdue_count', 0),
                    'due_today': tasks.get('tasks_now', 0),
                },
                'goals': {
                    'active': goals.get('active_goal_count', 0),
                    'completed_month': 0,  # Not in SAE; minor field
                },
                'faith': {
                    'active_prayers': faith.get('unanswered_prayers', 0),
                    'answered_month': 0,  # Not in SAE; minor field
                },
                'health': {
                    'weight_current': health.get('weight_current'),
                    'weight_trend': health.get('weight_trend', ''),
                    'fasts_week': fasting.get('fasts_7d', 0),
                    'workouts_week': fitness.get('workouts_7d', 0),
                    'workout_streak': 0,  # Not in SAE
                    'medicine_adherence': (
                        round(medicine.get('adherence_7d', 0) * 100)
                        if medicine.get('adherence_7d') is not None else None
                    ),
                },
                'intentions': {
                    'active': 0,
                    'alignment_score': 0,
                },
                'habits': {
                    'active': habits.get('active_habit_count', 0),
                    'completion_rate': (
                        round(habits.get('avg_completion_rate', 0) * 100, 1)
                        if habits.get('avg_completion_rate') is not None else None
                    ),
                    'streak': habits.get('longest_streak', 0),
                },
                # AI assessment fields — NOT in SAE, must be merged from USS
                'ai_assessment': '',
                'alignment_gaps': [],
                'celebration_worthy': [],
                '_source': 'sae',
            }
        except Exception as _sae_err:
            logger.warning(
                "SAE_STATE_READ user=%s — failed, will fall back to USS: %s",
                self.user.id, _sae_err, exc_info=True,
            )
            return None
