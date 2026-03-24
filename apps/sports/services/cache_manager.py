"""
Sports Domain — Cache Manager

Manages cached sports data to keep request paths fast.
All views and state builders read from cache — never from raw GameEvent queries.
"""
import logging

from django.core.cache import cache

logger = logging.getLogger(__name__)

# Cache key patterns
USER_TODAY_GAMES_KEY = "wlj:sports:user:{user_id}:today_games"
USER_TEAM_SUMMARIES_KEY = "wlj:sports:user:{user_id}:team_summaries"
GAME_STATUS_KEY = "wlj:sports:game:{game_id}:status"
SYNC_HEALTH_KEY = "wlj:sports:sync_health"

# TTLs (seconds)
TODAY_GAMES_TTL = 300        # 5 minutes
TEAM_SUMMARIES_TTL = 900     # 15 minutes
LIVE_GAME_TTL = 120          # 2 minutes
SYNC_HEALTH_TTL = 3600       # 1 hour


def get_user_sports_summary(user):
    """
    Get cached team summaries for a user.

    Returns list of dicts:
    [
        {
            "team_id": 1,
            "team_name": "Kansas City Chiefs",
            "league": "NFL",
            "priority": 1,
            "next_game": {"opponent": "...", "time": "...", "venue": "..."},
            "last_result": {"opponent": "...", "result": "W", "score": "27-20"},
            "status": "upcoming",  # upcoming | live | final
            "active_signals": ["game_today"],
        },
        ...
    ]
    """
    key = USER_TEAM_SUMMARIES_KEY.format(user_id=user.id)
    cached = cache.get(key)
    if cached is not None:
        return cached
    return []  # No data yet — background task populates this


def set_user_sports_summary(user_id, summaries):
    """Store computed team summaries in cache."""
    key = USER_TEAM_SUMMARIES_KEY.format(user_id=user_id)
    cache.set(key, summaries, TEAM_SUMMARIES_TTL)


def get_user_today_games(user):
    """Get cached today's games for a user."""
    key = USER_TODAY_GAMES_KEY.format(user_id=user.id)
    cached = cache.get(key)
    if cached is not None:
        return cached
    return []


def set_user_today_games(user_id, games):
    """Store today's games in cache."""
    key = USER_TODAY_GAMES_KEY.format(user_id=user_id)
    cache.set(key, games, TODAY_GAMES_TTL)


def invalidate_user_caches_for_game(game_event):
    """
    Invalidate caches for all users following teams in this game.

    Called from post_save signal on GameEvent.
    """
    from apps.sports.models import UserTeamFollow

    team_ids = [game_event.home_team_id, game_event.away_team_id]
    user_ids = UserTeamFollow.objects.filter(
        team_id__in=team_ids, is_active=True
    ).values_list("user_id", flat=True).distinct()

    for user_id in user_ids:
        cache.delete(USER_TODAY_GAMES_KEY.format(user_id=user_id))
        cache.delete(USER_TEAM_SUMMARIES_KEY.format(user_id=user_id))


def set_sync_health(data):
    """Record sync health telemetry."""
    cache.set(SYNC_HEALTH_KEY, data, SYNC_HEALTH_TTL)


def get_sync_health():
    """Read sync health telemetry."""
    return cache.get(SYNC_HEALTH_KEY)
