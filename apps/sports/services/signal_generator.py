"""
Sports Domain — Signal Generation

Generates sports signals ONLY from GameEvent data.
All signals are deterministic, timestamped, and respect time windows.

Signal types:
  Event: game_today, game_starting_soon, game_live, game_completed
  Metric: team_win, team_loss
  Pattern: win_streak, losing_streak

Architecture rule: This is the ONLY place sports signals are created.
State builder and CoS context consume these signals — never re-derive.
"""
import logging
from collections import defaultdict
from datetime import timedelta

from django.db.models import Q
from django.utils import timezone

from apps.sports.models import GameEvent, UserTeamFollow
from apps.sports.services.time_windows import GameTimeWindow

logger = logging.getLogger(__name__)

# Signal type constants
SIGNAL_GAME_TODAY = "game_today"
SIGNAL_GAME_STARTING_SOON = "game_starting_soon"
SIGNAL_GAME_LIVE = "game_live"
SIGNAL_GAME_COMPLETED = "game_completed"
SIGNAL_TEAM_WIN = "team_win"
SIGNAL_TEAM_LOSS = "team_loss"
SIGNAL_WIN_STREAK = "win_streak"
SIGNAL_LOSING_STREAK = "losing_streak"

# Pattern detection threshold
STREAK_THRESHOLD = 3


def generate_sports_signals(user):
    """
    Generate all sports signals for a user.

    Returns list of signal dicts:
    [
        {
            "signal_type": "game_today",
            "team_id": 1,
            "team_name": "Kansas City Chiefs",
            "game_id": 42,
            "timestamp": "2026-03-23T19:00:00Z",
            "priority": 1,
            "data": {...},  # Signal-specific payload
        },
        ...
    ]

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

    # Fetch relevant games (today + upcoming 48h + recently completed)
    window_start = now - timedelta(hours=6)  # Include recently completed
    window_end = now + timedelta(hours=48)

    games = GameEvent.objects.filter(
        Q(home_team_id__in=team_ids) | Q(away_team_id__in=team_ids),
        start_time__range=(window_start, window_end),
    ).select_related("home_team", "away_team").order_by("start_time")

    # Generate event signals from games
    for game in games:
        tw = GameTimeWindow(game, now=now)

        # Determine which followed team(s) are in this game
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
            base_data = {
                "game_id": game.id,
                "team_id": team.id,
                "team_name": team.full_name,
                "opponent": opponent.full_name if opponent else "",
                "start_time": game.start_time.isoformat(),
                "venue": game.venue,
                "priority": follow.priority,
            }

            if tw.window == GameTimeWindow.ACTIVE:
                signals.append(_make_signal(
                    SIGNAL_GAME_LIVE, team, game, follow, now,
                    data={
                        **base_data,
                        "home_score": game.home_score,
                        "away_score": game.away_score,
                    },
                ))
            elif tw.window == GameTimeWindow.STARTING_SOON:
                signals.append(_make_signal(
                    SIGNAL_GAME_STARTING_SOON, team, game, follow, now,
                    data=base_data,
                ))
                # Also emit game_today
                signals.append(_make_signal(
                    SIGNAL_GAME_TODAY, team, game, follow, now,
                    data=base_data,
                ))
            elif tw.window == GameTimeWindow.TODAY:
                signals.append(_make_signal(
                    SIGNAL_GAME_TODAY, team, game, follow, now,
                    data=base_data,
                ))
            elif tw.window == GameTimeWindow.PAST and game.is_final:
                # Recently completed game
                signals.append(_make_signal(
                    SIGNAL_GAME_COMPLETED, team, game, follow, now,
                    data={
                        **base_data,
                        "score": game.get_score_display(),
                    },
                ))
                # Win/loss signals
                if game.user_team_won(team):
                    signals.append(_make_signal(
                        SIGNAL_TEAM_WIN, team, game, follow, now,
                        data={**base_data, "score": game.get_score_display()},
                    ))
                elif game.user_team_lost(team):
                    signals.append(_make_signal(
                        SIGNAL_TEAM_LOSS, team, game, follow, now,
                        data={**base_data, "score": game.get_score_display()},
                    ))

    # Generate pattern signals (streaks)
    streak_signals = _detect_streaks(team_ids, team_map, now)
    signals.extend(streak_signals)

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


def _detect_streaks(team_ids, team_map, now):
    """
    Detect win/loss streaks for followed teams.

    Looks at last 10 completed games per team.
    """
    signals = []

    for team_id in team_ids:
        recent_games = GameEvent.objects.filter(
            Q(home_team_id=team_id) | Q(away_team_id=team_id),
            status=GameEvent.STATUS_FINAL,
            start_time__lte=now,
        ).order_by("-start_time")[:10]

        if len(recent_games) < STREAK_THRESHOLD:
            continue

        follow = team_map[team_id]
        team = follow.team

        # Count consecutive wins/losses from most recent
        wins = 0
        losses = 0
        for game in recent_games:
            if game.user_team_won(team):
                if losses > 0:
                    break  # Streak broken
                wins += 1
            elif game.user_team_lost(team):
                if wins > 0:
                    break
                losses += 1
            else:
                break  # Tie or no result — streak broken

        if wins >= STREAK_THRESHOLD:
            signals.append({
                "signal_type": SIGNAL_WIN_STREAK,
                "team_id": team_id,
                "team_name": team.full_name,
                "game_id": None,
                "timestamp": now.isoformat(),
                "priority": follow.priority,
                "data": {"streak_length": wins},
            })
        elif losses >= STREAK_THRESHOLD:
            signals.append({
                "signal_type": SIGNAL_LOSING_STREAK,
                "team_id": team_id,
                "team_name": team.full_name,
                "game_id": None,
                "timestamp": now.isoformat(),
                "priority": follow.priority,
                "data": {"streak_length": losses},
            })

    return signals
