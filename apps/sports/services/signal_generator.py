"""
Sports Domain — Signal Generation

Generates sports signals ONLY from GameEvent + Team data.
All signals are deterministic, timestamped, and respect time windows.

REQUIRED SIGNALS ONLY (5 total):
  1. game_live       — a followed team's game is in progress
  2. game_starting_soon — game starts within 60 minutes
  3. game_today      — game is scheduled for today
  4. win_streak      — team has won 3+ consecutive games
  5. losing_streak   — team has lost 3+ consecutive games

No extra signals. No player stats. No analytics.

Architecture rule: This is the ONLY place sports signals are created.
State builder and CoS context consume these signals — never re-derive.
"""
import logging

from django.db.models import Q
from django.utils import timezone

from apps.sports.models import GameEvent, UserTeamFollow
from apps.sports.services.time_windows import GameTimeWindow

logger = logging.getLogger(__name__)

# Signal type constants — ONLY these 5 exist
SIGNAL_GAME_LIVE = "game_live"
SIGNAL_GAME_STARTING_SOON = "game_starting_soon"
SIGNAL_GAME_TODAY = "game_today"
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

    Returns list of signal dicts:
    [
        {
            "signal_type": "game_today",
            "team_id": 1,
            "team_name": "Atlanta Braves",
            "game_id": 42,       # null for streak signals
            "timestamp": "2026-03-24T19:00:00Z",
            "priority": 1,
            "data": {
                "opponent": "Los Angeles Dodgers",
                "start_time": "2026-03-24T23:10:00Z",
                "venue": "Truist Park",
            },
        },
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

    # ── EVENT SIGNALS (from active/upcoming games) ──────────────────
    from datetime import timedelta
    window_end = now + timedelta(hours=48)

    games = GameEvent.objects.filter(
        Q(home_team_id__in=team_ids) | Q(away_team_id__in=team_ids),
        start_time__gte=now - timedelta(hours=3),  # Include recently started
        start_time__lte=window_end,
        status__in=[GameEvent.STATUS_SCHEDULED, GameEvent.STATUS_LIVE],
    ).select_related("home_team", "away_team").order_by("start_time")

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
            base_data = {
                "opponent": opponent.full_name if opponent else "",
                "start_time": game.start_time.isoformat(),
                "venue": game.venue,
            }

            if tw.window == GameTimeWindow.ACTIVE:
                signals.append(_make_signal(
                    SIGNAL_GAME_LIVE, team, game, follow, now,
                    data={
                        **base_data,
                        "score": game.get_score_display(),
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
            "data": {"streak_length": streak_count},
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
