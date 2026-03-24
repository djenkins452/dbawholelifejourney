"""
Sports Domain — Streak Computation

Computes win/loss streaks from completed GameEvent data.
Never relies on external API for streak — always derived internally.

Usage:
    from apps.sports.services.streaks import compute_streak
    streak = compute_streak(team)  # Returns "W3", "L2", or ""
"""
from django.db.models import Q

from apps.sports.models import GameEvent


def compute_streak(team, max_games=10):
    """
    Compute current win/loss streak for a team.

    Examines up to `max_games` most recent completed games.
    Returns a string like "W3", "L5", or "" if no streak or no games.

    Args:
        team: Team instance
        max_games: Maximum completed games to look back (default 10)

    Returns:
        str — "W3", "L2", etc. Empty string if fewer than 1 game.
    """
    recent_games = (
        GameEvent.objects.filter(
            Q(home_team=team) | Q(away_team=team),
            status=GameEvent.STATUS_FINAL,
        )
        .order_by("-start_time")[:max_games]
    )

    if not recent_games:
        return ""

    streak_type = None
    streak_count = 0

    for game in recent_games:
        if game.user_team_won(team):
            result = "W"
        elif game.user_team_lost(team):
            result = "L"
        else:
            break  # Tie breaks the streak

        if streak_type is None:
            streak_type = result
            streak_count = 1
        elif result == streak_type:
            streak_count += 1
        else:
            break  # Streak broken

    if not streak_type or streak_count == 0:
        return ""

    return f"{streak_type}{streak_count}"


def compute_streaks_for_teams(team_ids, max_games=10):
    """
    Batch compute streaks for multiple teams.

    More efficient than calling compute_streak() per team — fetches
    all games in one query, then computes per-team.

    Args:
        team_ids: list of Team IDs
        max_games: Maximum completed games to look back per team

    Returns:
        dict — {team_id: "W3", team_id: "L2", ...}
    """
    if not team_ids:
        return {}

    # Fetch recent completed games for all teams at once
    all_games = (
        GameEvent.objects.filter(
            Q(home_team_id__in=team_ids) | Q(away_team_id__in=team_ids),
            status=GameEvent.STATUS_FINAL,
        )
        .select_related("home_team", "away_team")
        .order_by("-start_time")
    )

    # Group games by team
    team_games = {tid: [] for tid in team_ids}
    for game in all_games:
        for tid in [game.home_team_id, game.away_team_id]:
            if tid in team_games and len(team_games[tid]) < max_games:
                team_games[tid].append(game)

    # Compute streak per team
    results = {}
    for tid, games in team_games.items():
        if not games:
            results[tid] = ""
            continue

        streak_type = None
        streak_count = 0

        for game in games:
            # Determine W/L for this team
            winner = game.get_winner()
            if winner is None:
                break
            if winner.id == tid:
                result = "W"
            else:
                result = "L"

            if streak_type is None:
                streak_type = result
                streak_count = 1
            elif result == streak_type:
                streak_count += 1
            else:
                break

        results[tid] = f"{streak_type}{streak_count}" if streak_type and streak_count > 0 else ""

    return results
