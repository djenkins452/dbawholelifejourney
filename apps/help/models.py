"""
Help System Models

Two types of help content:
1. HelpTopic - User-facing help (how to use the application)
2. AdminHelpTopic - Technical/admin help (how to configure the system)

Both use HELP_CONTEXT_ID for context-aware display.
"""

from django.db import models
from django.core.cache import cache


class HelpTopic(models.Model):
    """
    User-facing help content.

    Displayed when users click the "?" icon on regular application pages.
    Contains step-by-step instructions for using features.
    """

    # Identification
    context_id = models.CharField(
        max_length=100,
        unique=True,
        db_index=True,
        help_text="Unique identifier matching HELP_CONTEXT_ID (e.g., DASHBOARD_HOME, HEALTH_WORKOUT_CREATE)"
    )
    help_id = models.SlugField(
        max_length=100,
        unique=True,
        help_text="URL-friendly identifier (e.g., dashboard-overview, health-log-workout)"
    )

    # Content
    title = models.CharField(
        max_length=200,
        help_text="Help topic title (e.g., 'How to Log a Workout')"
    )
    description = models.TextField(
        blank=True,
        help_text="Brief description of what this help covers"
    )
    content = models.TextField(
        help_text="Full help content with step-by-step instructions (supports Markdown)"
    )

    # Organization
    app_name = models.CharField(
        max_length=50,
        blank=True,
        help_text="App this help belongs to (e.g., dashboard, health, journal)"
    )
    order = models.PositiveIntegerField(
        default=0,
        help_text="Display order within app (lower = first)"
    )

    # Status
    is_active = models.BooleanField(
        default=True,
        help_text="Show this help topic"
    )

    # Related topics
    related_topics = models.ManyToManyField(
        'self',
        blank=True,
        symmetrical=False,
        help_text="Related help topics to suggest"
    )

    # Metadata
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['app_name', 'order', 'title']
        verbose_name = "Help Topic"
        verbose_name_plural = "Help Topics"

    def __str__(self):
        return f"{self.context_id}: {self.title}"

    def save(self, *args, **kwargs):
        super().save(*args, **kwargs)
        # Clear cache
        cache.delete(f'help_topic_{self.context_id}')
        cache.delete('help_topics_all')

    @classmethod
    def get_by_context(cls, context_id):
        """
        Get help topic by context ID, with caching.
        """
        cache_key = f'help_topic_{context_id}'
        topic = cache.get(cache_key)
        if topic is None:
            try:
                topic = cls.objects.get(context_id=context_id, is_active=True)
                cache.set(cache_key, topic, 60 * 60)  # Cache 1 hour
            except cls.DoesNotExist:
                topic = None
        return topic

    @classmethod
    def get_all_active(cls):
        """Get all active help topics, grouped by app."""
        cache_key = 'help_topics_all'
        topics = cache.get(cache_key)
        if topics is None:
            topics = list(cls.objects.filter(is_active=True))
            cache.set(cache_key, topics, 60 * 60)
        return topics


class AdminHelpTopic(models.Model):
    """
    Technical/admin help content.

    Displayed when admins click the "?" icon in Django admin or Admin Console.
    Contains instructions for configuring and managing the system.
    """

    # Identification
    context_id = models.CharField(
        max_length=100,
        unique=True,
        db_index=True,
        help_text="Unique identifier for admin context (e.g., ADMIN_AI_PROMPTS, ADMIN_THEMES)"
    )
    help_id = models.SlugField(
        max_length=100,
        unique=True,
        help_text="URL-friendly identifier (e.g., admin-ai-prompts, admin-themes)"
    )

    # Content
    title = models.CharField(
        max_length=200,
        help_text="Help topic title (e.g., 'Configuring AI Prompts')"
    )
    description = models.TextField(
        blank=True,
        help_text="Brief description of what this admin help covers"
    )
    content = models.TextField(
        help_text="Full technical help content (supports Markdown)"
    )

    # Organization
    category = models.CharField(
        max_length=50,
        blank=True,
        help_text="Category (e.g., 'AI Configuration', 'User Management', 'System Settings')"
    )
    order = models.PositiveIntegerField(
        default=0,
        help_text="Display order within category (lower = first)"
    )

    # Status
    is_active = models.BooleanField(
        default=True,
        help_text="Show this admin help topic"
    )

    # Related topics
    related_topics = models.ManyToManyField(
        'self',
        blank=True,
        symmetrical=False,
        help_text="Related admin help topics to suggest"
    )

    # Metadata
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['category', 'order', 'title']
        verbose_name = "Admin Help Topic"
        verbose_name_plural = "Admin Help Topics"

    def __str__(self):
        return f"{self.context_id}: {self.title}"

    def save(self, *args, **kwargs):
        super().save(*args, **kwargs)
        # Clear cache
        cache.delete(f'admin_help_topic_{self.context_id}')
        cache.delete('admin_help_topics_all')

    @classmethod
    def get_by_context(cls, context_id):
        """
        Get admin help topic by context ID, with caching.
        """
        cache_key = f'admin_help_topic_{context_id}'
        topic = cache.get(cache_key)
        if topic is None:
            try:
                topic = cls.objects.get(context_id=context_id, is_active=True)
                cache.set(cache_key, topic, 60 * 60)  # Cache 1 hour
            except cls.DoesNotExist:
                topic = None
        return topic

    @classmethod
    def get_all_active(cls):
        """Get all active admin help topics, grouped by category."""
        cache_key = 'admin_help_topics_all'
        topics = cache.get(cache_key)
        if topics is None:
            topics = list(cls.objects.filter(is_active=True))
            cache.set(cache_key, topics, 60 * 60)
        return topics
