"""
Sports Domain — Django model signals.

Post-save hooks for cache invalidation when game data changes.
"""
import logging

from django.db.models.signals import post_save
from django.dispatch import receiver

from apps.sports.models import GameEvent

logger = logging.getLogger(__name__)


@receiver(post_save, sender=GameEvent)
def invalidate_game_cache(sender, instance, **kwargs):
    """Invalidate cached game data when a GameEvent is updated."""
    from apps.sports.services.cache_manager import invalidate_user_caches_for_game
    try:
        invalidate_user_caches_for_game(instance)
    except Exception:
        logger.warning("Failed to invalidate sports cache for game %s", instance.id, exc_info=True)
