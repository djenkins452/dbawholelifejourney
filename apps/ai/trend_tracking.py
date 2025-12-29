# ==============================================================================
# File: trend_tracking.py
# Project: Whole Life Journey - Django 5.x Personal Wellness/Journaling App
# Description: Trend analysis and pattern detection for Dashboard AI
# Owner: Danny Jenkins (dannyjenkins71@gmail.com)
# Created: 2025-12-29
# Last Updated: 2025-12-29
# ==============================================================================
"""
Trend Tracking Service

Analyzes user data over time to:
- Detect patterns in behavior
- Identify drift from stated intentions
- Track progress toward goals
- Generate periodic summaries
- Provide accountability insights
"""

import logging
from datetime import timedelta
from typing import Dict, List, Optional, Any

from django.db import models
from django.db.models import Count, Avg, Sum, F
from django.utils import timezone

from .services import ai_service, AIService
from .models import (
    UserStateSnapshot, TrendAnalysis, DailyPriority,
    AIInsight
)

logger = logging.getLogger(__name__)


class TrendTracker:
    """
    Analyzes user trends over time for the Dashboard AI.

    Provides:
    - Weekly/monthly trend analysis
    - Pattern detection
    - Drift identification
    - Progress tracking
    - Comparative analysis
    """

    def __init__(self, user):
        self.user = user
        self.prefs = user.preferences
        self.faith_enabled = self.prefs.faith_enabled
        self.coaching_style = getattr(self.prefs, 'ai_coaching_style', 'supportive')

    # =========================================================================
    # WEEKLY ANALYSIS
    # =========================================================================

    def generate_weekly_analysis(self, force_refresh: bool = False) -> Optional[TrendAnalysis]:
        """
        Generate weekly trend analysis.

        Returns existing analysis if generated today, otherwise creates new one.
        """
        from apps.core.utils import get_user_today

        today = get_user_today(self.user)
        week_start = today - timedelta(days=today.weekday())  # Monday
        week_end = today

        # Check for existing analysis
        existing = TrendAnalysis.objects.filter(
            user=self.user,
            period_type='week',
            period_start=week_start,
            period_end=week_end,
            analysis_type='overall'
        ).first()

        if existing and not force_refresh:
            return existing

        # Gather weekly data
        week_data = self._gather_week_data(week_start, week_end)

        # Get previous week for comparison
        prev_week_start = week_start - timedelta(days=7)
        prev_week_end = week_start - timedelta(days=1)
        prev_week_data = self._gather_week_data(prev_week_start, prev_week_end)

        # Detect patterns
        patterns = self._detect_patterns(week_data, 'week')

        # Generate AI summary if available
        summary = self._generate_ai_summary(week_data, prev_week_data, patterns, 'week')

        # Compare to previous
        comparison = self._compare_periods(week_data, prev_week_data)

        # Generate recommendations
        recommendations = self._generate_recommendations(week_data, patterns)

        # Create or update analysis
        analysis, created = TrendAnalysis.objects.update_or_create(
            user=self.user,
            period_type='week',
            period_start=week_start,
            period_end=week_end,
            analysis_type='overall',
            defaults={
                'summary': summary,
                'patterns_detected': patterns,
                'recommendations': recommendations,
                'comparison_to_previous': comparison,
                'metrics': week_data,
            }
        )

        return analysis

    def _gather_week_data(self, start_date, end_date) -> Dict[str, Any]:
        """Gather all metrics for a week."""
        data = {
            'period_start': str(start_date),
            'period_end': str(end_date),
        }

        # Get snapshots for the period
        snapshots = UserStateSnapshot.objects.filter(
            user=self.user,
            snapshot_date__gte=start_date,
            snapshot_date__lte=end_date
        )

        if not snapshots.exists():
            # Generate snapshots if missing
            data['snapshots_available'] = False
            data.update(self._gather_raw_week_data(start_date, end_date))
        else:
            data['snapshots_available'] = True
            data.update(self._aggregate_snapshots(snapshots))

        return data

    def _gather_raw_week_data(self, start_date, end_date) -> Dict:
        """Gather raw data when snapshots aren't available."""
        from apps.journal.models import JournalEntry
        from apps.life.models import Task
        from apps.purpose.models import LifeGoal
        from apps.health.models import WorkoutSession, MedicineLog

        data = {}

        # Journal metrics
        if self.prefs.journal_enabled:
            entries = JournalEntry.objects.filter(
                user=self.user,
                entry_date__gte=start_date,
                entry_date__lte=end_date
            )
            data['journal_entries'] = entries.count()
            data['journal_days'] = entries.values('entry_date').distinct().count()

            # Mood distribution
            moods = entries.exclude(mood='').values('mood').annotate(
                count=Count('mood')
            )
            data['mood_distribution'] = {m['mood']: m['count'] for m in moods}

        # Task metrics
        if self.prefs.life_enabled:
            tasks = Task.objects.filter(
                user=self.user,
                is_completed=True,
                completed_at__date__gte=start_date,
                completed_at__date__lte=end_date
            )
            data['tasks_completed'] = tasks.count()

        # Goal metrics
        if self.prefs.purpose_enabled:
            goals = LifeGoal.objects.filter(
                user=self.user,
                status='completed',
                completed_date__gte=start_date,
                completed_date__lte=end_date
            )
            data['goals_completed'] = goals.count()

        # Health metrics
        if self.prefs.health_enabled:
            workouts = WorkoutSession.objects.filter(
                user=self.user,
                date__gte=start_date,
                date__lte=end_date
            )
            data['workouts'] = workouts.count()

            # Medicine adherence
            logs = MedicineLog.objects.filter(
                user=self.user,
                scheduled_date__gte=start_date,
                scheduled_date__lte=end_date
            )
            taken = logs.filter(log_status__in=['taken', 'late']).count()
            total = logs.filter(log_status__in=['taken', 'late', 'missed']).count()
            data['medicine_adherence'] = round((taken / total) * 100) if total > 0 else None

        # Faith metrics
        if self.faith_enabled:
            from apps.faith.models import PrayerRequest
            prayers = PrayerRequest.objects.filter(
                user=self.user,
                is_answered=True,
                answered_at__date__gte=start_date,
                answered_at__date__lte=end_date
            )
            data['prayers_answered'] = prayers.count()

        return data

    def _aggregate_snapshots(self, snapshots) -> Dict:
        """Aggregate data from daily snapshots."""
        data = {}

        # Journal
        data['journal_entries'] = snapshots.aggregate(
            total=Sum('journal_count_week')
        )['total'] or 0
        data['max_journal_streak'] = snapshots.aggregate(
            max=models.Max('journal_streak')
        )['max'] or 0

        # Tasks
        data['tasks_completed'] = snapshots.aggregate(
            total=Sum('tasks_completed_week')
        )['total'] or 0
        data['avg_overdue'] = round(snapshots.aggregate(
            avg=Avg('tasks_overdue')
        )['avg'] or 0, 1)

        # Goals
        data['avg_active_goals'] = round(snapshots.aggregate(
            avg=Avg('active_goals')
        )['avg'] or 0, 1)
        data['goals_completed'] = snapshots.aggregate(
            total=Sum('completed_goals_month')
        )['total'] or 0

        # Health
        data['workouts'] = snapshots.aggregate(
            total=Sum('workouts_week')
        )['total'] or 0
        data['max_workout_streak'] = snapshots.aggregate(
            max=models.Max('workout_streak')
        )['max'] or 0

        # Medicine
        adherence_values = [s.medicine_adherence for s in snapshots if s.medicine_adherence is not None]
        if adherence_values:
            data['avg_medicine_adherence'] = round(sum(adherence_values) / len(adherence_values))

        # Faith
        if self.faith_enabled:
            data['prayers_answered'] = snapshots.aggregate(
                total=Sum('answered_prayers_month')
            )['total'] or 0

        return data

    def _detect_patterns(self, data: Dict, period: str) -> List[Dict]:
        """Detect patterns in the data."""
        patterns = []

        # Journal consistency
        if data.get('journal_entries', 0) > 0:
            days = 7 if period == 'week' else 30
            journal_days = data.get('journal_days', data.get('journal_entries', 0))
            consistency = (journal_days / days) * 100 if days > 0 else 0

            if consistency >= 80:
                patterns.append({
                    'type': 'positive',
                    'area': 'journal',
                    'description': 'Strong journaling consistency',
                    'metric': f'{round(consistency)}% of days'
                })
            elif consistency < 30:
                patterns.append({
                    'type': 'concern',
                    'area': 'journal',
                    'description': 'Low journaling frequency',
                    'metric': f'Only {round(consistency)}% of days'
                })

        # Workout consistency
        if self.prefs.health_enabled:
            workouts = data.get('workouts', 0)
            if workouts >= 5 and period == 'week':
                patterns.append({
                    'type': 'positive',
                    'area': 'health',
                    'description': 'Excellent workout frequency',
                    'metric': f'{workouts} workouts this week'
                })
            elif workouts <= 1 and period == 'week':
                patterns.append({
                    'type': 'concern',
                    'area': 'health',
                    'description': 'Low physical activity',
                    'metric': f'Only {workouts} workout(s) this week'
                })

        # Medicine adherence
        adherence = data.get('avg_medicine_adherence') or data.get('medicine_adherence')
        if adherence is not None:
            if adherence >= 95:
                patterns.append({
                    'type': 'positive',
                    'area': 'health',
                    'description': 'Excellent medicine adherence',
                    'metric': f'{adherence}%'
                })
            elif adherence < 70:
                patterns.append({
                    'type': 'concern',
                    'area': 'health',
                    'description': 'Medicine adherence needs attention',
                    'metric': f'{adherence}%'
                })

        # Task completion vs overdue
        tasks = data.get('tasks_completed', 0)
        overdue = data.get('avg_overdue', 0)
        if tasks > 0 and overdue == 0:
            patterns.append({
                'type': 'positive',
                'area': 'productivity',
                'description': 'No overdue tasks',
                'metric': f'{tasks} tasks completed'
            })
        elif overdue > 5:
            patterns.append({
                'type': 'concern',
                'area': 'productivity',
                'description': 'Accumulating overdue tasks',
                'metric': f'{round(overdue)} overdue on average'
            })

        # Mood patterns
        mood_dist = data.get('mood_distribution', {})
        if mood_dist:
            positive_moods = mood_dist.get('grateful', 0) + mood_dist.get('peaceful', 0) + mood_dist.get('energized', 0)
            negative_moods = mood_dist.get('anxious', 0) + mood_dist.get('sad', 0) + mood_dist.get('frustrated', 0)
            total_moods = sum(mood_dist.values())

            if total_moods > 0:
                if positive_moods / total_moods > 0.6:
                    patterns.append({
                        'type': 'positive',
                        'area': 'mood',
                        'description': 'Predominantly positive mood',
                        'metric': f'{round((positive_moods/total_moods)*100)}% positive'
                    })
                elif negative_moods / total_moods > 0.5:
                    patterns.append({
                        'type': 'concern',
                        'area': 'mood',
                        'description': 'Challenging emotional week',
                        'metric': f'{round((negative_moods/total_moods)*100)}% difficult moods'
                    })

        return patterns

    def _compare_periods(self, current: Dict, previous: Dict) -> str:
        """Generate comparison text between periods."""
        if not previous:
            return "No previous period data available for comparison."

        comparisons = []

        # Journal comparison
        curr_journal = current.get('journal_entries', 0)
        prev_journal = previous.get('journal_entries', 0)
        if prev_journal > 0:
            change = ((curr_journal - prev_journal) / prev_journal) * 100
            if abs(change) > 20:
                direction = "up" if change > 0 else "down"
                comparisons.append(f"Journaling is {direction} {abs(round(change))}% from last week")

        # Workout comparison
        curr_workouts = current.get('workouts', 0)
        prev_workouts = previous.get('workouts', 0)
        if prev_workouts > 0:
            change = ((curr_workouts - prev_workouts) / prev_workouts) * 100
            if abs(change) > 25:
                direction = "up" if change > 0 else "down"
                comparisons.append(f"Workouts are {direction} {abs(round(change))}% from last week")

        # Task comparison
        curr_tasks = current.get('tasks_completed', 0)
        prev_tasks = previous.get('tasks_completed', 0)
        if prev_tasks > 0:
            change = ((curr_tasks - prev_tasks) / prev_tasks) * 100
            if abs(change) > 20:
                direction = "more" if change > 0 else "fewer"
                comparisons.append(f"Completed {abs(round(change))}% {direction} tasks than last week")

        if comparisons:
            return " ".join(comparisons)
        else:
            return "Activity levels are similar to last week."

    def _generate_ai_summary(self, data: Dict, prev_data: Dict, patterns: List, period: str) -> str:
        """Generate AI summary of the period."""
        if not ai_service.is_available or not AIService.check_user_consent(self.user):
            return self._generate_fallback_summary(data, patterns, period)

        system_prompt = """You are a life coach providing a weekly review summary.
Be warm, specific, and encouraging. Focus on patterns, not just numbers.
Keep your response to 2-3 sentences maximum."""

        # Build context
        context_parts = []
        context_parts.append(f"Period: {period}")

        if data.get('journal_entries'):
            context_parts.append(f"Journal entries: {data['journal_entries']}")
        if data.get('tasks_completed'):
            context_parts.append(f"Tasks completed: {data['tasks_completed']}")
        if data.get('workouts'):
            context_parts.append(f"Workouts: {data['workouts']}")
        if data.get('avg_medicine_adherence'):
            context_parts.append(f"Medicine adherence: {data['avg_medicine_adherence']}%")

        for pattern in patterns[:3]:
            context_parts.append(f"Pattern: {pattern['description']} ({pattern['metric']})")

        user_prompt = f"""Weekly data:
{chr(10).join('- ' + p for p in context_parts)}

Provide a brief, warm summary of this week."""

        try:
            return ai_service._call_api(system_prompt, user_prompt, max_tokens=150) or self._generate_fallback_summary(data, patterns, period)
        except Exception as e:
            logger.error(f"AI summary error: {e}")
            return self._generate_fallback_summary(data, patterns, period)

    def _generate_fallback_summary(self, data: Dict, patterns: List, period: str) -> str:
        """Generate fallback summary without AI."""
        positive = [p for p in patterns if p['type'] == 'positive']
        concerns = [p for p in patterns if p['type'] == 'concern']

        if positive and not concerns:
            return f"Strong {period} with good consistency across your tracked areas."
        elif concerns and not positive:
            return f"This {period} had some challenges. Remember that growth isn't linear."
        elif positive and concerns:
            return f"Mixed {period} with both wins and areas for growth. Focus on building on what's working."
        else:
            return f"Keep showing up. Every {period} is a new opportunity."

    def _generate_recommendations(self, data: Dict, patterns: List) -> List[str]:
        """Generate recommendations based on data and patterns."""
        recommendations = []

        concerns = [p for p in patterns if p['type'] == 'concern']

        for concern in concerns[:3]:
            if concern['area'] == 'journal':
                recommendations.append("Try setting a specific time each day for journaling, even just 5 minutes.")
            elif concern['area'] == 'health' and 'workout' in concern['description'].lower():
                recommendations.append("Start with just 10 minutes of movement. Consistency beats intensity.")
            elif concern['area'] == 'health' and 'medicine' in concern['description'].lower():
                recommendations.append("Set phone reminders for medication times. Small systems create big results.")
            elif concern['area'] == 'productivity':
                recommendations.append("Review your task list and identify what can be delegated, delayed, or deleted.")
            elif concern['area'] == 'mood':
                recommendations.append("Consider what activities or people lift your mood. Make space for them.")

        if not recommendations:
            recommendations.append("Keep doing what you're doing. Consistency is building something good.")

        return recommendations

    # =========================================================================
    # MONTHLY ANALYSIS
    # =========================================================================

    def generate_monthly_analysis(self, force_refresh: bool = False) -> Optional[TrendAnalysis]:
        """Generate monthly trend analysis."""
        from apps.core.utils import get_user_today

        today = get_user_today(self.user)
        month_start = today.replace(day=1)
        month_end = today

        # Check for existing
        existing = TrendAnalysis.objects.filter(
            user=self.user,
            period_type='month',
            period_start=month_start,
            analysis_type='overall'
        ).first()

        if existing and not force_refresh and existing.created_at.date() == today:
            return existing

        # Get all weekly analyses for this month
        weekly_analyses = TrendAnalysis.objects.filter(
            user=self.user,
            period_type='week',
            period_start__gte=month_start,
            period_end__lte=month_end
        )

        # Aggregate monthly data
        month_data = self._aggregate_monthly_data(month_start, month_end, weekly_analyses)

        # Get previous month for comparison
        prev_month_end = month_start - timedelta(days=1)
        prev_month_start = prev_month_end.replace(day=1)
        prev_month_data = self._gather_raw_week_data(prev_month_start, prev_month_end)

        # Detect patterns
        patterns = self._detect_patterns(month_data, 'month')

        # Generate summary
        summary = self._generate_ai_summary(month_data, prev_month_data, patterns, 'month')

        # Compare
        comparison = self._compare_periods(month_data, prev_month_data)

        # Recommendations
        recommendations = self._generate_recommendations(month_data, patterns)

        # Create analysis
        analysis, created = TrendAnalysis.objects.update_or_create(
            user=self.user,
            period_type='month',
            period_start=month_start,
            period_end=month_end,
            analysis_type='overall',
            defaults={
                'summary': summary,
                'patterns_detected': patterns,
                'recommendations': recommendations,
                'comparison_to_previous': comparison,
                'metrics': month_data,
            }
        )

        return analysis

    def _aggregate_monthly_data(self, start_date, end_date, weekly_analyses) -> Dict:
        """Aggregate monthly data from weekly analyses and raw data."""
        data = {
            'period_start': str(start_date),
            'period_end': str(end_date),
        }

        # If we have weekly analyses, aggregate them
        if weekly_analyses.exists():
            for analysis in weekly_analyses:
                metrics = analysis.metrics
                for key, value in metrics.items():
                    if isinstance(value, (int, float)):
                        data[key] = data.get(key, 0) + value

        # Also get raw data for the full month
        raw_data = self._gather_raw_week_data(start_date, end_date)
        for key, value in raw_data.items():
            if key not in data:
                data[key] = value

        return data

    # =========================================================================
    # DRIFT DETECTION
    # =========================================================================

    def detect_intention_drift(self) -> List[Dict]:
        """
        Detect drift from stated intentions and goals.

        Returns list of areas where behavior doesn't match stated priorities.
        """
        from apps.purpose.models import ChangeIntention, LifeGoal, AnnualDirection
        from apps.core.utils import get_user_today

        today = get_user_today(self.user)
        week_ago = today - timedelta(days=7)

        drift_areas = []

        # Check annual direction alignment
        direction = AnnualDirection.objects.filter(
            user=self.user,
            year=today.year
        ).first()

        if direction and direction.word_of_year:
            # This is where we'd analyze if recent behavior aligns with word of year
            # For now, we check if there's been journaling about it
            from apps.journal.models import JournalEntry

            recent_entries = JournalEntry.objects.filter(
                user=self.user,
                entry_date__gte=week_ago
            )

            word = direction.word_of_year.lower()
            mentions = recent_entries.filter(
                models.Q(title__icontains=word) | models.Q(body__icontains=word)
            ).count()

            if recent_entries.count() > 0 and mentions == 0:
                drift_areas.append({
                    'type': 'word_of_year',
                    'item': direction.word_of_year,
                    'observation': f'Your word of the year "{direction.word_of_year}" hasn\'t appeared in recent journal entries.',
                    'suggestion': f'Consider reflecting on how "{direction.word_of_year}" is showing up in your life.'
                })

        # Check active intentions
        intentions = ChangeIntention.objects.filter(user=self.user, status='active')

        for intention in intentions:
            # Check for recent activity related to intention
            # This is simplified - a real implementation would be more sophisticated
            drift_areas.append({
                'type': 'intention_check',
                'item': intention.intention,
                'observation': f'Check-in: How are you living out "{intention.intention}"?',
                'suggestion': 'Take a moment to reflect on where this intention has shown up this week.'
            })

        # Check stalled goals
        stalled_goals = LifeGoal.objects.filter(
            user=self.user,
            status='active',
            updated_at__lt=timezone.now() - timedelta(days=14)
        )

        for goal in stalled_goals:
            drift_areas.append({
                'type': 'stalled_goal',
                'item': goal.title,
                'observation': f'Your goal "{goal.title}" hasn\'t been updated in over 2 weeks.',
                'suggestion': 'Consider whether this goal still aligns with your priorities, or what small step you could take today.'
            })

        return drift_areas[:5]  # Limit to 5 most important

    # =========================================================================
    # PROGRESS REPORTS
    # =========================================================================

    def get_goal_progress_report(self) -> Dict:
        """Generate progress report for all active goals."""
        from apps.purpose.models import LifeGoal

        goals = LifeGoal.objects.filter(user=self.user)

        report = {
            'active': [],
            'completed_this_month': [],
            'paused': [],
            'summary': ''
        }

        active = goals.filter(status='active')
        for goal in active:
            days_since_update = (timezone.now() - goal.updated_at).days

            report['active'].append({
                'id': goal.id,
                'title': goal.title,
                'domain': goal.domain.name if goal.domain else 'General',
                'timeframe': goal.get_timeframe_display(),
                'days_since_update': days_since_update,
                'why_it_matters': goal.why_it_matters[:100] if goal.why_it_matters else '',
                'needs_attention': days_since_update > 14
            })

        # Completed this month
        from apps.core.utils import get_user_today
        today = get_user_today(self.user)
        month_start = today.replace(day=1)

        completed = goals.filter(
            status='completed',
            completed_date__gte=month_start
        )
        for goal in completed:
            report['completed_this_month'].append({
                'id': goal.id,
                'title': goal.title,
                'completed_date': str(goal.completed_date),
            })

        # Paused
        paused = goals.filter(status='paused')
        for goal in paused:
            report['paused'].append({
                'id': goal.id,
                'title': goal.title,
            })

        # Summary
        active_count = active.count()
        completed_count = completed.count()
        needs_attention = len([g for g in report['active'] if g['needs_attention']])

        if completed_count > 0:
            report['summary'] = f"Great progress! You've completed {completed_count} goal(s) this month."
        elif needs_attention > 0:
            report['summary'] = f"You have {needs_attention} goal(s) that could use some attention."
        elif active_count > 0:
            report['summary'] = f"You're tracking {active_count} active goal(s). Keep moving forward!"
        else:
            report['summary'] = "Consider setting a meaningful goal to work toward."

        return report


# =============================================================================
# CONVENIENCE FUNCTION
# =============================================================================

def get_trend_tracker(user) -> TrendTracker:
    """Get a TrendTracker instance for a user."""
    return TrendTracker(user)
