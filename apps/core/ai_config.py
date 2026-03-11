"""
AI Configuration — Centralized, DB-backed configuration for AI thresholds.

Project: Whole Life Journey
Path: apps/core/ai_config.py
Purpose: Provides a singleton configuration model for AI engine thresholds
         that are currently hard-coded across multiple engine files.

This replaces scattered hard-coded constants with a single database-backed
configuration that can be adjusted without code deployment.

Usage:
    from apps.core.ai_config import get_ai_config

    config = get_ai_config()
    threshold = config.confidence_min_chat  # 0.40

    # Or access via the helper function:
    from apps.core.ai_config import get_threshold
    threshold = get_threshold("confidence_min_chat", default=0.40)

Copyright:
    (c) Whole Life Journey. All rights reserved.
"""

import logging
from functools import lru_cache

from django.core.cache import cache
from django.db import models

logger = logging.getLogger(__name__)

# Cache key for the singleton config
_CONFIG_CACHE_KEY = "wlj:ai_config:active"
_CONFIG_CACHE_TTL = 300  # 5 minutes


class AIThresholdConfig(models.Model):
    """
    Centralized AI threshold configuration (singleton pattern).

    Groups the most commonly tuned thresholds that were previously
    hard-coded across engine files. Follows the same singleton pattern
    as PressureWeightConfig.

    Thresholds are organized by category:
    - Confidence: Min confidence for different channels
    - Capacity: User capacity assessment thresholds
    - Delivery: Per-channel message budget limits
    - Fatigue: Intervention fatigue thresholds
    - Cache: TTL values for caching layers
    """

    # ---- Confidence Thresholds ----
    confidence_min_chat = models.FloatField(
        default=0.40,
        help_text="Minimum confidence to surface in chat (EAE)",
    )
    confidence_min_push = models.FloatField(
        default=0.60,
        help_text="Minimum confidence for push notifications (EAE)",
    )
    confidence_min_briefing = models.FloatField(
        default=0.30,
        help_text="Minimum confidence for briefing inclusion (EAE)",
    )
    confidence_high_threshold = models.FloatField(
        default=0.85,
        help_text="High confidence threshold (EAE)",
    )
    confidence_low_threshold = models.FloatField(
        default=0.50,
        help_text="Low confidence threshold (EAE)",
    )

    # ---- Capacity Thresholds ----
    capacity_high_threshold = models.FloatField(
        default=0.75,
        help_text="User is in high-capacity state (UAL/EAE)",
    )
    capacity_normal_threshold = models.FloatField(
        default=0.45,
        help_text="User is in normal-capacity state (UAL/EAE)",
    )
    capacity_low_threshold = models.FloatField(
        default=0.25,
        help_text="User is in low-capacity state (UAL/EAE)",
    )

    # ---- Delivery Budget Limits ----
    budget_chat = models.PositiveSmallIntegerField(
        default=3,
        help_text="Default cognitive units per chat session (EAE)",
    )
    budget_push = models.PositiveSmallIntegerField(
        default=1,
        help_text="Default cognitive units per push notification (EAE)",
    )
    budget_global_daily = models.PositiveSmallIntegerField(
        default=8,
        help_text="Global daily cognitive unit cap across all channels (EAE)",
    )

    # ---- Fatigue & Intervention ----
    high_fatigue_threshold = models.FloatField(
        default=0.60,
        help_text="Fatigue score above which interventions are suppressed",
    )
    low_fatigue_threshold = models.FloatField(
        default=0.30,
        help_text="Fatigue score below which full intervention is allowed",
    )

    # ---- Protective Thresholds ----
    breach_probability_threshold = models.FloatField(
        default=0.60,
        help_text="Breach probability threshold for protective alerts",
    )
    dne_max_alerts_per_hour = models.PositiveSmallIntegerField(
        default=3,
        help_text="Maximum protective alerts per hour",
    )
    dne_max_alerts_per_day = models.PositiveSmallIntegerField(
        default=10,
        help_text="Maximum protective alerts per day",
    )

    # ---- Cache TTLs (seconds) ----
    cos_context_cache_ttl = models.PositiveIntegerField(
        default=45,
        help_text="CoS context cache TTL in seconds (fast-changing data)",
    )
    stable_cache_ttl = models.PositiveIntegerField(
        default=300,
        help_text="Stable data cache TTL in seconds (slowly-changing data)",
    )

    # ---- Metadata ----
    active = models.BooleanField(
        default=True,
        help_text="Only one config should be active at a time",
    )
    notes = models.TextField(
        blank=True,
        default="",
        help_text="Reason for this configuration change",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "AI Threshold Config"
        verbose_name_plural = "AI Threshold Configs"
        app_label = "core"

    def __str__(self):
        return (
            f"AIThresholdConfig "
            f"[chat={self.confidence_min_chat}, push={self.confidence_min_push}] "
            f"{'(active)' if self.active else '(inactive)'}"
        )

    def save(self, *args, **kwargs):
        # Invalidate cache on save
        cache.delete(_CONFIG_CACHE_KEY)
        super().save(*args, **kwargs)

    @classmethod
    def get_active(cls):
        """
        Get the active config, with caching.

        Falls back to defaults if no database record exists (e.g., during
        initial setup or testing). This ensures engines never fail due to
        missing configuration.
        """
        # Try cache first
        cached = cache.get(_CONFIG_CACHE_KEY)
        if cached is not None:
            return cached

        try:
            config = cls.objects.filter(active=True).first()
            if config is None:
                # Create default config if none exists
                config = cls.objects.create(active=True)
                logger.info("AIThresholdConfig: created default configuration")

            cache.set(_CONFIG_CACHE_KEY, config, _CONFIG_CACHE_TTL)
            return config
        except Exception as e:
            # Database might not be ready (migrations pending, tests, etc.)
            # Return a default instance without saving
            logger.debug("AIThresholdConfig: DB not ready, using defaults: %s", e)
            return cls()


def get_ai_config() -> AIThresholdConfig:
    """Get the active AI threshold configuration (cached)."""
    return AIThresholdConfig.get_active()


def get_threshold(name: str, default=None):
    """
    Get a specific threshold value by name.

    Safe to call anywhere — returns the default if the config
    can't be loaded (e.g., before migrations run).

    Args:
        name: Attribute name on AIThresholdConfig (e.g., "confidence_min_chat")
        default: Fallback value if attribute doesn't exist

    Returns:
        The threshold value, or default.
    """
    try:
        config = get_ai_config()
        return getattr(config, name, default)
    except Exception:
        return default
