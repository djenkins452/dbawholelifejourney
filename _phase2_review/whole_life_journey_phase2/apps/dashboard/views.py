"""
Dashboard Views - The main landing experience.
"""

import random
from datetime import timedelta

from django.contrib.auth.mixins import LoginRequiredMixin
from django.db.models import Count
from django.utils import timezone
from django.views.generic import TemplateView, View
from django.http import HttpResponse

from .models import DailyEncouragement


class DashboardView(LoginRequiredMixin, TemplateView):
    """
    Main dashboard view - the calm landing space.
    
    Displays:
    - Daily encouragement (with Scripture if Faith enabled)
    - Summary tiles for active modules
    - Quick actions
    """

    template_name = "dashboard/home.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        user = self.request.user
        prefs = user.preferences

        # Get daily encouragement
        context["encouragement"] = self.get_daily_encouragement(prefs.faith_enabled)

        # Get journal stats
        context["journal_stats"] = self.get_journal_stats(user)

        # Dashboard configuration
        context["dashboard_config"] = prefs.dashboard_config or self.get_default_config()

        # Current date/time info
        context["current_date"] = timezone.now()
        context["greeting"] = self.get_greeting()

        return context

    def get_daily_encouragement(self, faith_enabled):
        """
        Get an appropriate encouragement message for today.
        
        If Faith is enabled, may include Scripture.
        Otherwise, returns a general, uplifting message.
        """
        today = timezone.now()
        
        # Build query
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
        
        # Fall back to any applicable message
        if queryset.exists():
            return random.choice(list(queryset))
        
        # Default message if no curated content
        return {
            "message": "Take a moment to breathe. You're exactly where you need to be.",
            "scripture_reference": "",
            "scripture_text": "",
        }

    def get_journal_stats(self, user):
        """Get journal statistics for the dashboard."""
        from apps.journal.models import JournalEntry
        
        now = timezone.now()
        week_ago = now - timedelta(days=7)
        month_ago = now - timedelta(days=30)
        
        entries = JournalEntry.objects.filter(user=user)
        
        return {
            "total": entries.count(),
            "this_week": entries.filter(created_at__gte=week_ago).count(),
            "this_month": entries.filter(created_at__gte=month_ago).count(),
            "recent": entries.order_by("-entry_date")[:3],
        }

    def get_greeting(self):
        """Get a time-appropriate greeting."""
        hour = timezone.now().hour
        if hour < 12:
            return "Good morning"
        elif hour < 17:
            return "Good afternoon"
        else:
            return "Good evening"

    def get_default_config(self):
        """Default dashboard tile configuration."""
        return {
            "tiles": [
                {"type": "encouragement", "visible": True, "order": 1},
                {"type": "journal_summary", "visible": True, "order": 2},
                {"type": "quick_actions", "visible": True, "order": 3},
            ]
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
        import json
        
        try:
            config = json.loads(request.body)
            prefs = request.user.preferences
            prefs.dashboard_config = config
            prefs.save(update_fields=["dashboard_config", "updated_at"])
            return HttpResponse(status=200)
        except (json.JSONDecodeError, KeyError):
            return HttpResponse(status=400)


class JournalSummaryTileView(LoginRequiredMixin, TemplateView):
    """
    HTMX endpoint for journal summary tile.
    
    Returns just the tile content for dynamic updates.
    """

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
    """
    HTMX endpoint for encouragement tile.
    
    Can be used to refresh the encouragement without full page reload.
    """

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
