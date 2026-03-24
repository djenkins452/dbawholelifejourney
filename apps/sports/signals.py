"""
Sports Domain — Django model signals.

Post-save hooks for cache invalidation when game or follow data changes.
"""
import logging

from django.core.cache import cache
from django.db.models.signals import post_save
from django.dispatch import receiver

from apps.sports.models import GameEvent, UserTeamFollow

logger = logging.getLogger(__name__)


@receiver(post_save, sender=GameEvent)
def invalidate_game_cache(sender, instance, **kwargs):
    """Invalidate cached game data when a GameEvent is updated."""
    from apps.sports.services.cache_manager import invalidate_user_caches_for_game
    try:
        invalidate_user_caches_for_game(instance)
    except Exception:
        logger.warning("Failed to invalidate sports cache for game %s", instance.id, exc_info=True)


@receiver(post_save, sender=UserTeamFollow)
def invalidate_follow_cache(sender, instance, **kwargs):
    """Invalidate user's cached summaries when they follow/unfollow a team."""
    from apps.sports.services.cache_manager import (
        USER_TEAM_SUMMARIES_KEY,
        USER_TODAY_GAMES_KEY,
    )
    try:
        user_id = instance.user_id
        cache.delete(USER_TODAY_GAMES_KEY.format(user_id=user_id))
        cache.delete(USER_TEAM_SUMMARIES_KEY.format(user_id=user_id))
    except Exception:
        logger.warning("Failed to invalidate sports cache for follow %s", instance.id, exc_info=True)
