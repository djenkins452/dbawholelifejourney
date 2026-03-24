"""
Sports Domain — Views

All views gated on sports_enabled preference.
Hub view reads followed teams directly (lightweight query) and
optionally enriches with cached GameEvent data when available.
"""
import logging
from collections import OrderedDict
from datetime import timedelta

from django.contrib.auth.mixins import LoginRequiredMixin
from django.db.models import Q
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect
from django.utils import timezone
from django.views import View
from django.views.generic import TemplateView

from apps.sports.models import GameEvent, League, Team, UserTeamFollow

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

    Displays followed teams grouped by league, with next game info
    when GameEvent data exists. Works with or without game data.
    """
    template_name = "sports/my_teams.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        user = self.request.user
        now = timezone.now()

        follows = (
            UserTeamFollow.objects.filter(user=user, is_active=True)
            .select_related("team__league__sport")
            .order_by("team__league__sport__name", "team__league__name", "priority", "team__location")
        )

        if not follows.exists():
            context["has_teams"] = False
            context["leagues_with_teams"] = {}
            return context

        context["has_teams"] = True

        # Collect followed team IDs for game lookup
        team_ids = [f.team_id for f in follows]

        # Find next upcoming game per team (single query, bounded)
        upcoming_games = (
            GameEvent.objects.filter(
                Q(home_team_id__in=team_ids) | Q(away_team_id__in=team_ids),
                start_time__gte=now,
                status__in=[GameEvent.STATUS_SCHEDULED, GameEvent.STATUS_LIVE],
            )
            .select_related("home_team", "away_team")
            .order_by("start_time")
        )

        # Find last completed game per team
        recent_games = (
            GameEvent.objects.filter(
                Q(home_team_id__in=team_ids) | Q(away_team_id__in=team_ids),
                status=GameEvent.STATUS_FINAL,
            )
            .select_related("home_team", "away_team")
            .order_by("-start_time")
        )

        # Build next-game lookup: team_id → GameEvent
        next_game_map = {}
        for game in upcoming_games:
            for tid in [game.home_team_id, game.away_team_id]:
                if tid in team_ids and tid not in next_game_map:
                    next_game_map[tid] = game

        # Build last-result lookup: team_id → GameEvent
        last_result_map = {}
        for game in recent_games:
            for tid in [game.home_team_id, game.away_team_id]:
                if tid in team_ids and tid not in last_result_map:
                    last_result_map[tid] = game

        # Batch compute streaks (single query for all teams)
        from apps.sports.services.streaks import compute_streaks_for_teams
        streak_map = compute_streaks_for_teams(team_ids)

        # Group follows by league
        leagues_with_teams = OrderedDict()
        for follow in follows:
            team = follow.team
            league = team.league
            league_key = league.abbreviation

            if league_key not in leagues_with_teams:
                leagues_with_teams[league_key] = {
                    "league": league,
                    "sport": league.sport.name,
                    "teams": [],
                }

            # Build team info dict
            next_game = next_game_map.get(team.id)
            last_game = last_result_map.get(team.id)

            team_info = {
                "team": team,
                "follow": follow,
                "record": team.record_display,
                "streak": streak_map.get(team.id, ""),
                "next_game": None,
                "context_line": "",
                "pitcher": "",
            }

            if next_game:
                opponent = next_game.get_opponent(team)
                opp_name = str(opponent) if opponent else "TBD"
                is_home = next_game.home_team_id == team.id

                # Compute urgency level for badges/highlighting
                if next_game.status == GameEvent.STATUS_LIVE:
                    urgency = "live"
                elif next_game.start_time <= now + timedelta(hours=1):
                    urgency = "starting_soon"
                elif next_game.start_time.date() == now.date():
                    urgency = "today"
                else:
                    urgency = "upcoming"

                # Pitcher (baseball only)
                pitcher = ""
                if is_home and next_game.home_probable_pitcher:
                    pitcher = next_game.home_probable_pitcher
                elif not is_home and next_game.away_probable_pitcher:
                    pitcher = next_game.away_probable_pitcher

                team_info["next_game"] = {
                    "opponent": opp_name,
                    "start_time": next_game.start_time,
                    "venue": next_game.venue,
                    "is_home": is_home,
                    "status": next_game.status,
                    "score": next_game.get_score_display() if next_game.is_live else "",
                    "urgency": urgency,
                }
                team_info["pitcher"] = pitcher

                # Build plain-English context line
                if urgency == "live":
                    score = next_game.get_score_display()
                    team_info["context_line"] = f"Live vs {opp_name}" + (f" · {score}" if score else "")
                elif urgency == "starting_soon":
                    team_info["context_line"] = f"Starting soon vs {opp_name} · {next_game.start_time.strftime('%-I:%M %p')}"
                elif urgency == "today":
                    where = "Home" if is_home else "Away"
                    team_info["context_line"] = f"Playing {opp_name} tonight · {next_game.start_time.strftime('%-I:%M %p')}"
                else:
                    team_info["context_line"] = f"Next: {next_game.start_time.strftime('%a')} vs {opp_name} · {next_game.start_time.strftime('%-I:%M %p')}"
            else:
                team_info["context_line"] = "No upcoming games"

            leagues_with_teams[league_key]["teams"].append(team_info)

        context["leagues_with_teams"] = leagues_with_teams

        # Pick ONE focus game: highest urgency, then highest follow priority
        urgency_rank = {"live": 0, "starting_soon": 1, "today": 2}
        focus_game = None
        focus_rank = 99

        for league_data in leagues_with_teams.values():
            for item in league_data["teams"]:
                ng = item.get("next_game")
                if not ng or ng.get("urgency") not in urgency_rank:
                    continue
                rank = urgency_rank[ng["urgency"]]
                priority = item["follow"].priority
                if rank < focus_rank or (rank == focus_rank and priority < getattr(focus_game, "_priority", 99)):
                    focus_game = {
                        "team": item["team"],
                        "opponent": ng["opponent"],
                        "urgency": ng["urgency"],
                        "start_time": ng["start_time"],
                        "venue": ng.get("venue", ""),
                        "score": ng.get("score", ""),
                        "is_home": ng.get("is_home", True),
                        "league": item["team"].league.abbreviation,
                        "_priority": priority,
                    }
                    focus_rank = rank

        if focus_game:
            focus_game.pop("_priority", None)
        context["focus_game"] = focus_game

        # Last updated timestamp — scoped to user's followed teams only
        context["last_updated"] = _get_last_updated(team_ids, now)

        # Provider label for data source indicator
        from apps.sports.services.provider_adapter import get_provider
        provider = get_provider()
        context["data_source"] = "Live data" if provider.provider_name() != "fixture" else "Simulated"

        return context


def _get_last_updated(team_ids, now):
    """
    Get the most recent data update timestamp.

    Checks: sync_health cache (background sync) and most recent
    GameEvent.last_updated for the user's followed teams.
    Returns a dict with 'timestamp' and 'relative' (human-readable).
    Returns None if no data available.
    """
    from apps.sports.services.cache_manager import get_sync_health

    latest = None

    # Check sync health cache
    sync_health = get_sync_health()
    if sync_health and sync_health.get("last_run"):
        try:
            from django.utils.dateparse import parse_datetime
            sync_ts = parse_datetime(sync_health["last_run"])
            if sync_ts:
                latest = sync_ts
        except (ValueError, TypeError):
            pass

    # Check most recent GameEvent for user's teams
    if team_ids:
        from django.db.models import Max, Q
        max_updated = GameEvent.objects.filter(
            Q(home_team_id__in=team_ids) | Q(away_team_id__in=team_ids)
        ).aggregate(latest=Max("last_updated"))["latest"]
        if max_updated and (latest is None or max_updated > latest):
            latest = max_updated

    if not latest:
        return None

    # Compute relative time
    delta = now - latest
    total_seconds = int(delta.total_seconds())

    if total_seconds < 60:
        relative = "just now"
    elif total_seconds < 3600:
        minutes = total_seconds // 60
        relative = f"{minutes} minute{'s' if minutes != 1 else ''} ago"
    elif total_seconds < 86400:
        hours = total_seconds // 3600
        relative = f"{hours} hour{'s' if hours != 1 else ''} ago"
    else:
        relative = latest.strftime("%b %d, %I:%M %p")

    return {"timestamp": latest, "relative": relative}


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
