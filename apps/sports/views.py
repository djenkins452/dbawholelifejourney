"""
Sports Domain — Views

All views gated on sports_enabled preference.
Views read from cache/state only — no heavy queries on request path.
"""
import logging

from django.contrib.auth.mixins import LoginRequiredMixin
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect
from django.views import View
from django.views.generic import TemplateView

from apps.sports.models import League, Team, UserTeamFollow
from apps.sports.services.cache_manager import get_user_sports_summary

logger = logging.getLogger(__name__)


class SportsEnabledMixin:
    """Redirect to preferences if sports module is disabled."""

    def dispatch(self, request, *args, **kwargs):
        prefs = getattr(request.user, "preferences", None)
        if not prefs or not prefs.sports_enabled:
            return redirect("users:preferences")
        return super().dispatch(request, *args, **kwargs)


class SportsHubView(LoginRequiredMixin, SportsEnabledMixin, TemplateView):
    """
    My Teams hub page.

    Displays followed teams with next game, status, and last result.
    All data comes from cache — no GameEvent queries on request path.
    """
    template_name = "sports/my_teams.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["team_summaries"] = get_user_sports_summary(
            self.request.user, warm_on_miss=True
        )
        context["has_teams"] = UserTeamFollow.objects.filter(
            user=self.request.user, is_active=True
        ).exists()
        return context


class TeamSelectView(LoginRequiredMixin, SportsEnabledMixin, TemplateView):
    """Browse leagues and select teams to follow."""
    template_name = "sports/team_select.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        leagues = League.objects.select_related("sport").prefetch_related("teams").all()
        # Group by sport
        sports_data = {}
        for league in leagues:
            sport_name = league.sport.name
            if sport_name not in sports_data:
                sports_data[sport_name] = []
            sports_data[sport_name].append(league)
        context["sports_data"] = sports_data
        # Current follows for highlighting
        context["followed_team_ids"] = set(
            UserTeamFollow.objects.filter(
                user=self.request.user, is_active=True
            ).values_list("team_id", flat=True)
        )
        return context


class FollowTeamView(LoginRequiredMixin, SportsEnabledMixin, View):
    """Add a team follow via POST."""

    def post(self, request, *args, **kwargs):
        team_id = request.POST.get("team_id")
        priority = int(request.POST.get("priority", 2))
        if not team_id:
            return JsonResponse({"error": "team_id required"}, status=400)

        team = get_object_or_404(Team, id=team_id)
        priority = max(1, min(3, priority))

        follow, created = UserTeamFollow.objects.update_or_create(
            user=request.user,
            team=team,
            defaults={"priority": priority, "is_active": True},
        )
        if request.headers.get("HX-Request"):
            return JsonResponse({"status": "followed", "team": team.full_name})
        return redirect("sports:team_select")


class UnfollowTeamView(LoginRequiredMixin, SportsEnabledMixin, View):
    """Remove a team follow via POST."""

    def post(self, request, pk, *args, **kwargs):
        follow = get_object_or_404(
            UserTeamFollow, id=pk, user=request.user
        )
        follow.is_active = False
        follow.save(update_fields=["is_active"])
        if request.headers.get("HX-Request"):
            return JsonResponse({"status": "unfollowed"})
        return redirect("sports:hub")
