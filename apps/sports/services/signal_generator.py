"""
Sports Domain — Signal Generation

Generates sports signals ONLY from GameEvent + Team data.
All signals are deterministic, timestamped, and respect time windows.

SIGNALS (7 total):
  1. game_live         — a followed team's game is in progress
  2. game_starting_soon — game starts within 60 minutes
  3. game_today        — game is scheduled for today
  4. game_upcoming     — game scheduled within 7 days
  5. game_final        — most recent completed game for a followed team
  6. win_streak        — team has won 3+ consecutive games
  7. losing_streak     — team has lost 3+ consecutive games

No extra signals. No player stats. No analytics.

Architecture rule: This is the ONLY place sports signals are created.
State builder and CoS context consume these signals — never re-derive.
"""
import logging
from datetime import timedelta

from django.db.models import Q
from django.utils import timezone

from apps.sports.models import GameEvent, UserTeamFollow
from apps.sports.services.time_windows import GameTimeWindow

logger = logging.getLogger(__name__)

# Signal type constants
SIGNAL_GAME_LIVE = "game_live"
SIGNAL_GAME_STARTING_SOON = "game_starting_soon"
SIGNAL_GAME_TODAY = "game_today"
SIGNAL_GAME_UPCOMING = "game_upcoming"
SIGNAL_GAME_FINAL = "game_final"
SIGNAL_WIN_STREAK = "win_streak"
SIGNAL_LOSING_STREAK = "losing_streak"

# Legacy exports for any existing imports
SIGNAL_GAME_COMPLETED = "game_completed"
SIGNAL_TEAM_WIN = "team_win"
SIGNAL_TEAM_LOSS = "team_loss"

# Streak threshold
STREAK_THRESHOLD = 3


def generate_sports_signals(user):
    """
    Generate all sports signals for a user.

    Returns list of signal dicts with keys:
        signal_type, team_id, team_name, game_id, timestamp, priority, data

    Returns [] if sports_enabled=False or no followed teams.
    """
    # Module gate — STRICT
    prefs = getattr(user, "preferences", None)
    if not prefs or not prefs.sports_enabled:
        return []

    follows = UserTeamFollow.objects.filter(
        user=user, is_active=True
    ).select_related("team", "team__league")

    if not follows.exists():
        return []

    team_map = {f.team_id: f for f in follows}
    team_ids = list(team_map.keys())
    now = timezone.now()

    signals = []

    # ── EVENT SIGNALS (from active/upcoming games) ──────────────────
    window_end = now + timedelta(days=7)

    games = GameEvent.objects.filter(
        Q(home_team_id__in=team_ids) | Q(away_team_id__in=team_ids),
        start_time__gte=now - timedelta(hours=3),  # Include recently started
        start_time__lte=window_end,
        status__in=[GameEvent.STATUS_SCHEDULED, GameEvent.STATUS_LIVE],
    ).select_related("home_team", "away_team", "home_team__league").order_by("start_time")

    for game in games:
        tw = GameTimeWindow(game, now=now)

        # Which followed team(s) are in this game?
        user_teams_in_game = []
        if game.home_team_id in team_map:
            user_teams_in_game.append(
                (game.home_team, team_map[game.home_team_id])
            )
        if game.away_team_id in team_map:
            user_teams_in_game.append(
                (game.away_team, team_map[game.away_team_id])
            )

        for team, follow in user_teams_in_game:
            opponent = game.get_opponent(team)
            is_home = game.home_team_id == team.id
            opp_team = game.away_team if is_home else game.home_team
            base_data = {
                "opponent": opponent.full_name if opponent else "",
                "opponent_logo": opp_team.logo_url or "",
                "start_time": game.start_time.isoformat(),
                "venue": game.venue,
                "is_home": is_home,
                "league": team.league.abbreviation,
                "home_pitcher": game.home_probable_pitcher or "",
                "away_pitcher": game.away_probable_pitcher or "",
            }

            if tw.window == GameTimeWindow.ACTIVE:
                signals.append(_make_signal(
                    SIGNAL_GAME_LIVE, team, game, follow, now,
                    data={
                        **base_data,
                        "score": game.get_score_display(),
                        "home_score": game.home_score or 0,
                        "away_score": game.away_score or 0,
                    },
                ))
            elif tw.window == GameTimeWindow.STARTING_SOON:
                signals.append(_make_signal(
                    SIGNAL_GAME_STARTING_SOON, team, game, follow, now,
                    data=base_data,
                ))
                # Also counts as game_today
                signals.append(_make_signal(
                    SIGNAL_GAME_TODAY, team, game, follow, now,
                    data=base_data,
                ))
            elif tw.window == GameTimeWindow.TODAY:
                signals.append(_make_signal(
                    SIGNAL_GAME_TODAY, team, game, follow, now,
                    data=base_data,
                ))
            elif tw.window in (GameTimeWindow.UPCOMING, GameTimeWindow.FUTURE):
                # Future games within the 7-day window
                signals.append(_make_signal(
                    SIGNAL_GAME_UPCOMING, team, game, follow, now,
                    data=base_data,
                ))

    # ── FINAL SIGNALS (most recent completed game per team) ─────────
    recent_completed = (
        GameEvent.objects.filter(
            Q(home_team_id__in=team_ids) | Q(away_team_id__in=team_ids),
            status=GameEvent.STATUS_FINAL,
        )
        .select_related("home_team", "away_team", "home_team__league", "away_team__league")
        .order_by("-start_time")
    )

    # Track which teams already have a final signal (one per team)
    teams_with_final = set()
    for game in recent_completed:
        if len(teams_with_final) == len(team_ids):
            break  # All teams covered

        for tid in [game.home_team_id, game.away_team_id]:
            if tid in team_map and tid not in teams_with_final:
                teams_with_final.add(tid)
                team = game.home_team if tid == game.home_team_id else game.away_team
                follow = team_map[tid]
                is_home = game.home_team_id == tid
                opp_team = game.away_team if is_home else game.home_team

                won = game.user_team_won(team)
                lost = game.user_team_lost(team)
                result = "W" if won else ("L" if lost else "T")

                signals.append(_make_signal(
                    SIGNAL_GAME_FINAL, team, game, follow, now,
                    data={
                        "opponent": opp_team.full_name,
                        "opponent_logo": opp_team.logo_url or "",
                        "start_time": game.start_time.isoformat(),
                        "venue": game.venue,
                        "is_home": is_home,
                        "league": team.league.abbreviation,
                        "home_score": game.home_score or 0,
                        "away_score": game.away_score or 0,
                        "score": game.get_score_display(),
                        "result": result,
                    },
                ))

    # ── PATTERN SIGNALS (streaks from completed games) ──────────────
    from apps.sports.services.streaks import compute_streaks_for_teams
    streak_map = compute_streaks_for_teams(team_ids)

    for team_id, streak in streak_map.items():
        if not streak or len(streak) < 2:
            continue

        streak_type = streak[0]  # "W" or "L"
        try:
            streak_count = int(streak[1:])
        except ValueError:
            continue

        if streak_count < STREAK_THRESHOLD:
            continue

        follow = team_map[team_id]
        team = follow.team

        signal_type = SIGNAL_WIN_STREAK if streak_type == "W" else SIGNAL_LOSING_STREAK
        signals.append({
            "signal_type": signal_type,
            "team_id": team_id,
            "team_name": team.full_name,
            "game_id": None,
            "timestamp": now.isoformat(),
            "priority": follow.priority,
            "data": {
                "streak_length": streak_count,
                "league": team.league.abbreviation,
            },
        })

    return signals


def _make_signal(signal_type, team, game, follow, now, data=None):
    """Create a standardized signal dict."""
    return {
        "signal_type": signal_type,
        "team_id": team.id,
        "team_name": team.full_name,
        "game_id": game.id,
        "timestamp": now.isoformat(),
        "priority": follow.priority,
        "data": data or {},
    }
