"""
Dashboard Views - AI-Driven Command Center

The dashboard is now the AI-powered heart of the app, providing:
- Personalized daily insights
- Gentle accountability nudges
- Pattern recognition and celebrations
- Weekly reflection summaries

Individual module pages handle their own stats and actions.
"""
import json
import random
from datetime import timedelta
from django.db import models
from django.db.models import Count, Avg
from django.contrib.auth.mixins import LoginRequiredMixin
from django.utils import timezone
from django.views.generic import TemplateView, View
from django.http import HttpResponse, JsonResponse
from django.conf import settings

from .models import DailyEncouragement


class DashboardView(LoginRequiredMixin, TemplateView):
    """
    AI-Driven Dashboard - Your personalized command center.
    """
    template_name = "dashboard/home.html"
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        user = self.request.user
        prefs = user.preferences
        
        # Basic info
        context["current_date"] = timezone.now()
        context["greeting"] = self._get_greeting()
        context["faith_enabled"] = prefs.faith_enabled
        
        # Get daily encouragement (fallback if AI unavailable)
        context["encouragement"] = self._get_daily_encouragement(prefs.faith_enabled)
        
        # Gather all user data for AI
        user_data = self._gather_comprehensive_data(user, prefs)
        context["user_data"] = user_data
        
        # AI Insights (if enabled)
        context["ai_enabled"] = prefs.ai_enabled
        if prefs.ai_enabled:
            context["ai_insights"] = self._get_ai_insights(user, prefs, user_data)
        else:
            context["ai_insights"] = None

        # Quick stats for the header
        context["quick_stats"] = self._get_quick_stats(user_data)
        
        # Module enabled flags for conditional display
        context["journal_enabled"] = prefs.journal_enabled
        context["health_enabled"] = prefs.health_enabled
        context["life_enabled"] = prefs.life_enabled
        context["purpose_enabled"] = prefs.purpose_enabled
        
        return context
    
    def _get_greeting(self):
        """Get time-appropriate greeting in user's timezone."""
        import pytz
        user_tz = pytz.timezone(self.request.user.preferences.timezone)
        user_time = timezone.now().astimezone(user_tz)
        hour = user_time.hour
        if hour < 12:
            return "Good morning"
        elif hour < 17:
            return "Good afternoon"
        else:
            return "Good evening"
    
    def _get_daily_encouragement(self, faith_enabled):
        """Get daily encouragement message."""
        today = timezone.now()
        queryset = DailyEncouragement.objects.filter(is_active=True)
        
        if not faith_enabled:
            queryset = queryset.filter(is_faith_specific=False)
        
        # Try to match day of week or month
        targeted = queryset.filter(
            models.Q(day_of_week=today.weekday()) |
            models.Q(month=today.month)
        )
        
        if targeted.exists():
            return random.choice(list(targeted))
        
        if queryset.exists():
            return random.choice(list(queryset))
        
        return None
    
    def _gather_comprehensive_data(self, user, prefs):
        """Gather all user data for AI analysis."""
        now = timezone.now()
        today = now.date()
        week_ago = now - timedelta(days=7)
        month_ago = now - timedelta(days=30)
        
        data = {
            "today": today,
            "week_ago": week_ago,
        }
        
        # Journal data
        if prefs.journal_enabled:
            data.update(self._get_journal_data(user, today, week_ago, month_ago))
        
        # Faith data
        if prefs.faith_enabled:
            data.update(self._get_faith_data(user))
        
        # Health data
        if prefs.health_enabled:
            data.update(self._get_health_data(user, today, month_ago))
        
        # Life data
        if prefs.life_enabled:
            data.update(self._get_life_data(user, today))
        
        # Purpose data
        if prefs.purpose_enabled:
            data.update(self._get_purpose_data(user))
        
        return data
    
    def _get_journal_data(self, user, today, week_ago, month_ago):
        """Get journal-related data."""
        from apps.journal.models import JournalEntry
        
        entries = JournalEntry.objects.filter(user=user)
        entries_week = entries.filter(created_at__gte=week_ago)
        
        last_entry = entries.order_by('-entry_date').first()
        days_since_journal = None
        if last_entry:
            days_since_journal = (today - last_entry.entry_date).days
        
        # Calculate streak
        streak = self._calculate_journal_streak(user, today)
        
        # Get mood distribution this week
        moods = entries_week.exclude(mood='').values('mood').annotate(
            count=Count('mood')
        ).order_by('-count')
        top_mood = moods[0]['mood'] if moods else None
        
        # Recent entries for context
        recent_entries = list(entries.order_by('-entry_date')[:5].values(
            'title', 'entry_date', 'mood', 'body'
        ))
        
        return {
            "journal_total": entries.count(),
            "journal_this_week": entries_week.count(),
            "journal_this_month": entries.filter(created_at__gte=month_ago).count(),
            "last_journal_date": last_entry.entry_date if last_entry else None,
            "days_since_journal": days_since_journal,
            "journal_streak": streak,
            "top_mood_this_week": top_mood,
            "recent_entries": recent_entries,
        }
    
    def _calculate_journal_streak(self, user, today):
        """Calculate consecutive days of journaling."""
        from apps.journal.models import JournalEntry
        
        entries = JournalEntry.objects.filter(
            user=user
        ).order_by('-entry_date').values_list('entry_date', flat=True).distinct()[:60]
        
        if not entries:
            return 0
        
        streak = 0
        expected_date = today
        
        for entry_date in entries:
            if entry_date == expected_date:
                streak += 1
                expected_date -= timedelta(days=1)
            elif entry_date < expected_date:
                break
        
        return streak
    
    def _get_faith_data(self, user):
        """Get faith-related data."""
        from apps.faith.models import PrayerRequest, FaithMilestone
        
        prayers = PrayerRequest.objects.filter(user=user)
        active_prayers = prayers.filter(is_answered=False)
        answered_prayers = prayers.filter(is_answered=True)
        
        # Recent answered prayers
        recent_answered = answered_prayers.order_by('-answered_at').first()
        
        return {
            "active_prayers": active_prayers.count(),
            "answered_prayers": answered_prayers.count(),
            "total_milestones": FaithMilestone.objects.filter(user=user).count(),
            "recent_answered_prayer": recent_answered,
        }
    
    def _get_health_data(self, user, today, month_ago):
        """Get health-related data."""
        from apps.health.models import WeightEntry, FastingWindow, GlucoseEntry
        
        # Weight
        weights = WeightEntry.objects.filter(user=user)
        latest_weight = weights.order_by('-recorded_at').first()
        
        weight_change = None
        weight_trend = None
        if latest_weight and weights.count() >= 2:
            month_ago_weight = weights.filter(
                recorded_at__lte=timezone.now() - timedelta(days=25),
                recorded_at__gte=timezone.now() - timedelta(days=35)
            ).order_by('-recorded_at').first()
            if month_ago_weight:
                weight_change = round(latest_weight.value_in_lb - month_ago_weight.value_in_lb, 1)
                weight_trend = 'down' if weight_change < 0 else 'up' if weight_change > 0 else 'stable'
        
        # Fasting
        fasting = FastingWindow.objects.filter(user=user)
        active_fast = fasting.filter(ended_at__isnull=True).first()
        completed_fasts_month = fasting.filter(
            ended_at__isnull=False,
            started_at__gte=month_ago
        ).count()
        
        # Glucose
        glucose = GlucoseEntry.objects.filter(user=user)
        latest_glucose = glucose.order_by('-recorded_at').first()
        
        return {
            "latest_weight": latest_weight,
            "weight_change": weight_change,
            "weight_trend": weight_trend,
            "weight_entries_month": weights.filter(recorded_at__gte=month_ago).count(),
            "active_fast": active_fast,
            "fasting_active": active_fast is not None,
            "completed_fasts_month": completed_fasts_month,
            "latest_glucose": latest_glucose,
        }
    
    def _get_life_data(self, user, today):
        """Get life-related data."""
        from apps.life.models import Project, Task, LifeEvent
        
        week_ahead = today + timedelta(days=7)
        
        # Projects
        projects = Project.objects.filter(user=user)
        active_projects = projects.filter(status='active')
        
        # Tasks
        tasks = Task.objects.filter(user=user, is_completed=False)
        overdue_tasks = tasks.filter(due_date__lt=today)
        due_soon = tasks.filter(due_date__gte=today, due_date__lte=week_ahead)
        
        # Tasks completed today
        completed_today = Task.objects.filter(
            user=user,
            is_completed=True,
            completed_at__date=today
        ).count()
        
        # Upcoming events
        upcoming_events = LifeEvent.objects.filter(
            user=user,
            start_date__gte=today,
            start_date__lte=week_ahead
        ).order_by('start_date')[:5]
        
        return {
            "active_projects": active_projects.count(),
            "incomplete_tasks": tasks.count(),
            "overdue_tasks": overdue_tasks.count(),
            "tasks_due_soon": due_soon.count(),
            "completed_tasks_today": completed_today,
            "upcoming_events": list(upcoming_events),
            "upcoming_events_count": upcoming_events.count(),
        }
    
    def _get_purpose_data(self, user):
        """Get purpose-related data."""
        from apps.purpose.models import AnnualDirection, LifeGoal, ChangeIntention
        
        current_year = timezone.now().year
        
        direction = AnnualDirection.objects.filter(
            user=user, year=current_year
        ).first()
        
        goals = LifeGoal.objects.filter(user=user)
        active_goals = goals.filter(status='active')
        
        intentions = ChangeIntention.objects.filter(user=user, status='active')
        
        return {
            "word_of_year": direction.word_of_year if direction else None,
            "annual_direction": direction,
            "active_goals": active_goals.count(),
            "completed_goals": goals.filter(status='completed').count(),
            "active_intentions": intentions.count(),
        }
    
    def _get_ai_insights(self, user, prefs, user_data):
        """Get AI-generated insights."""
        try:
            from apps.ai.dashboard_ai import DashboardAI
            
            dashboard_ai = DashboardAI(user)
            
            # Get or generate daily insight
            daily_insight = dashboard_ai.get_daily_insight()
            
            # Get weekly summary if it's been generated
            weekly_summary = dashboard_ai.get_weekly_summary()
            
            # Check for things to celebrate
            celebrations = self._check_for_celebrations(user_data)
            
            # Check for accountability nudges
            nudges = self._check_for_nudges(user_data, prefs)
            
            return {
                "daily_insight": daily_insight,
                "weekly_summary": weekly_summary,
                "celebrations": celebrations,
                "nudges": nudges,
            }
        except Exception as e:
            import logging
            logging.error(f"AI insights error: {e}")
            return None
    
    def _check_for_celebrations(self, user_data):
        """Check for things worth celebrating."""
        celebrations = []
        
        # Journal streak
        streak = user_data.get("journal_streak", 0)
        if streak >= 7:
            celebrations.append({
                "type": "streak",
                "title": f"🔥 {streak}-Day Journal Streak!",
                "detail": "You're building a powerful reflection habit."
            })
        elif streak >= 3:
            celebrations.append({
                "type": "streak", 
                "title": f"📝 {streak} Days in a Row!",
                "detail": "Keep the momentum going."
            })
        
        # Tasks completed today
        completed = user_data.get("completed_tasks_today", 0)
        if completed >= 5:
            celebrations.append({
                "type": "tasks",
                "title": f"⚡ {completed} Tasks Done Today!",
                "detail": "You're crushing it."
            })
        elif completed >= 3:
            celebrations.append({
                "type": "tasks",
                "title": f"✓ {completed} Tasks Completed",
                "detail": "Solid progress today."
            })
        
        # Weight trend
        if user_data.get("weight_trend") == "down" and user_data.get("weight_change"):
            celebrations.append({
                "type": "health",
                "title": f"📉 Down {abs(user_data['weight_change'])} lbs",
                "detail": "Your consistency is paying off."
            })
        
        # Answered prayers
        if user_data.get("recent_answered_prayer"):
            celebrations.append({
                "type": "faith",
                "title": "🙏 Prayer Answered",
                "detail": "God is faithful."
            })
        
        return celebrations[:3]  # Max 3 celebrations
    
    def _check_for_nudges(self, user_data, prefs):
        """Check for gentle accountability nudges."""
        nudges = []
        
        # Journal gap
        days_since = user_data.get("days_since_journal")
        if days_since and days_since >= 3:
            nudges.append({
                "type": "journal",
                "days": days_since,
                "action_url": "/journal/new/",
                "action_text": "Write Now"
            })
        
        # Overdue tasks
        overdue = user_data.get("overdue_tasks", 0)
        if overdue > 0:
            nudges.append({
                "type": "tasks",
                "count": overdue,
                "action_url": "/life/tasks/",
                "action_text": "View Tasks"
            })
        
        # No active goals (if purpose enabled)
        if prefs.purpose_enabled and user_data.get("active_goals", 0) == 0:
            nudges.append({
                "type": "goals",
                "action_url": "/purpose/goals/new/",
                "action_text": "Set a Goal"
            })
        
        return nudges[:2]  # Max 2 nudges
    
    def _get_quick_stats(self, user_data):
        """Get quick stats for the header."""
        return {
            "journal_streak": user_data.get("journal_streak", 0),
            "active_goals": user_data.get("active_goals", 0),
            "tasks_today": user_data.get("completed_tasks_today", 0),
            "active_prayers": user_data.get("active_prayers", 0),
        }


class ConfigureDashboardView(LoginRequiredMixin, TemplateView):
    """
    Dashboard configuration view.
    
    Allows users to:
    - Show/hide tiles
    - Reorder tiles
    - Choose tile sizes (future)
    """
    template_name = "dashboard/configure.html"
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        prefs = self.request.user.preferences
        context["current_config"] = prefs.dashboard_config or {}
        context["available_tiles"] = self.get_available_tiles()
        return context
    
    def get_available_tiles(self):
        """Get list of available tile types."""
        tiles = [
            {
                "type": "encouragement",
                "name": "Daily Encouragement",
                "description": "An uplifting message to start your day",
            },
            {
                "type": "journal_summary",
                "name": "Journal Summary",
                "description": "Recent journal activity and quick entry",
            },
            {
                "type": "quick_actions",
                "name": "Quick Actions",
                "description": "Fast access to common tasks",
            },
        ]
        
        # Add faith-specific tiles if enabled
        if self.request.user.preferences.faith_enabled:
            tiles.append({
                "type": "scripture",
                "name": "Daily Scripture",
                "description": "A verse to reflect on today",
            })
        
        return tiles
    
    def post(self, request, *args, **kwargs):
        """Save dashboard configuration."""
        try:
            config = json.loads(request.body)
            prefs = request.user.preferences
            prefs.dashboard_config = config
            prefs.save(update_fields=["dashboard_config", "updated_at"])
            return HttpResponse(status=200)
        except (json.JSONDecodeError, KeyError):
            return HttpResponse(status=400)


class WeightChartDataView(LoginRequiredMixin, View):
    """API endpoint for weight chart data."""
    
    def get(self, request, *args, **kwargs):
        from apps.health.models import WeightEntry
        
        days = int(request.GET.get('days', 30))
        since = timezone.now() - timedelta(days=days)
        
        entries = WeightEntry.objects.filter(
            user=request.user,
            recorded_at__gte=since
        ).order_by('recorded_at')
        
        data = {
            'labels': [e.recorded_at.strftime('%b %d') for e in entries],
            'values': [float(e.value_in_lb) for e in entries],
        }
        
        return JsonResponse(data)


class JournalSummaryTileView(LoginRequiredMixin, TemplateView):
    """HTMX endpoint for journal summary tile."""
    template_name = "dashboard/tiles/journal_summary.html"
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        from apps.journal.models import JournalEntry
        
        user = self.request.user
        entries = JournalEntry.objects.filter(user=user)
        
        context["recent_entries"] = entries.order_by("-entry_date")[:3]
        context["total_count"] = entries.count()
        
        return context


class EncouragementTileView(LoginRequiredMixin, TemplateView):
    """HTMX endpoint for encouragement tile."""
    template_name = "dashboard/tiles/encouragement.html"
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        faith_enabled = self.request.user.preferences.faith_enabled
        
        queryset = DailyEncouragement.objects.filter(is_active=True)
        if not faith_enabled:
            queryset = queryset.filter(is_faith_specific=False)
        
        if queryset.exists():
            context["encouragement"] = random.choice(list(queryset))
        else:
            context["encouragement"] = {
                "message": "Take a moment to breathe. You're exactly where you need to be.",
            }
        
        return context