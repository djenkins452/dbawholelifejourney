"""
Help System Models

Contains:
1. HelpTopic - User-facing context-aware help (shown via "?" icon on pages)
2. AdminHelpTopic - Technical/admin help (for Django admin and Admin Console)
3. HelpCategory - Categories for organizing help articles (WLJ Assistant)
4. HelpArticle - Searchable help articles for WLJ Assistant chat bot
5. HelpConversation - Chat sessions with users
6. HelpMessage - Individual messages in a chat conversation
"""

from django.conf import settings
from django.db import models
from django.core.cache import cache
from django.utils import timezone


# =============================================================================
# CONTEXT-AWARE HELP (Page-specific help displayed via "?" icon)
# =============================================================================


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


# =============================================================================
# WLJ ASSISTANT CHAT BOT (Searchable help with chat interface)
# =============================================================================

class HelpCategory(models.Model):
    """
    Categories for organizing help articles.

    Examples: Getting Started, Features, Troubleshooting, FAQ
    """

    name = models.CharField(
        max_length=100,
        help_text="Display name (e.g., 'Getting Started')"
    )
    slug = models.SlugField(
        max_length=100,
        unique=True,
        help_text="URL-friendly identifier"
    )
    description = models.TextField(
        blank=True,
        help_text="Brief description of this category"
    )
    icon = models.CharField(
        max_length=10,
        default="📚",
        help_text="Emoji icon for display"
    )
    sort_order = models.PositiveIntegerField(
        default=0,
        help_text="Display order (lower = first)"
    )
    is_active = models.BooleanField(
        default=True,
        help_text="Show this category"
    )

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['sort_order', 'name']
        verbose_name = "Help Category"
        verbose_name_plural = "Help Categories"

    def __str__(self):
        return self.name

    def save(self, *args, **kwargs):
        super().save(*args, **kwargs)
        cache.delete('help_categories_active')

    @classmethod
    def get_active_categories(cls):
        """Get all active categories, cached."""
        cache_key = 'help_categories_active'
        categories = cache.get(cache_key)
        if categories is None:
            categories = list(cls.objects.filter(is_active=True))
            cache.set(cache_key, categories, 3600)
        return categories


class HelpArticle(models.Model):
    """
    Individual help documentation articles.

    Each article can be tagged with a module for contextual help.
    """

    MODULE_CHOICES = [
        ('general', 'General / App-wide'),
        ('dashboard', 'Dashboard'),
        ('journal', 'Journal'),
        ('health', 'Health'),
        ('faith', 'Faith'),
        ('life', 'Life'),
        ('purpose', 'Purpose'),
        ('settings', 'Settings'),
    ]

    # Core fields
    title = models.CharField(
        max_length=200,
        help_text="Article title"
    )
    slug = models.SlugField(
        max_length=200,
        unique=True,
        help_text="URL-friendly identifier"
    )

    # Content
    summary = models.CharField(
        max_length=300,
        help_text="Short 1-2 sentence summary for chat responses"
    )
    content = models.TextField(
        help_text="Full help content (Markdown supported)"
    )

    # Organization
    category = models.ForeignKey(
        HelpCategory,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='articles',
        help_text="Category this article belongs to"
    )
    module = models.CharField(
        max_length=20,
        choices=MODULE_CHOICES,
        default='general',
        help_text="Which app module this relates to"
    )

    # Search optimization
    keywords = models.TextField(
        blank=True,
        help_text="Comma-separated keywords for search (e.g., 'login, password, account')"
    )

    # Related articles
    related_articles = models.ManyToManyField(
        'self',
        blank=True,
        symmetrical=False,
        help_text="Related articles to suggest"
    )

    # Status
    is_active = models.BooleanField(
        default=True,
        help_text="Publish this article"
    )
    sort_order = models.PositiveIntegerField(
        default=0,
        help_text="Order within category"
    )

    # Metadata
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['category', 'sort_order', 'title']
        verbose_name = "Help Article"
        verbose_name_plural = "Help Articles"

    def __str__(self):
        return self.title

    def save(self, *args, **kwargs):
        super().save(*args, **kwargs)
        # Clear search cache
        cache.delete('help_articles_all')
        cache.delete(f'help_articles_module_{self.module}')

    @property
    def keywords_list(self):
        """Return keywords as a list."""
        if not self.keywords:
            return []
        return [k.strip().lower() for k in self.keywords.split(',') if k.strip()]

    @classmethod
    def get_active_articles(cls):
        """Get all active articles, cached."""
        cache_key = 'help_articles_all'
        articles = cache.get(cache_key)
        if articles is None:
            articles = list(cls.objects.filter(is_active=True).select_related('category'))
            cache.set(cache_key, articles, 3600)
        return articles

    @classmethod
    def get_by_module(cls, module):
        """Get articles for a specific module, cached."""
        cache_key = f'help_articles_module_{module}'
        articles = cache.get(cache_key)
        if articles is None:
            articles = list(
                cls.objects.filter(is_active=True, module=module)
                .select_related('category')
            )
            cache.set(cache_key, articles, 3600)
        return articles


class HelpConversation(models.Model):
    """
    A chat session between a user and the WLJ Assistant.

    Conversations are ephemeral - they can be emailed to the user
    and then deleted when the chat is closed.
    """

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='help_conversations'
    )

    # Session tracking
    started_at = models.DateTimeField(auto_now_add=True)
    last_activity = models.DateTimeField(auto_now=True)

    # Context (which page/module user was on when starting chat)
    context_module = models.CharField(
        max_length=20,
        blank=True,
        help_text="Module user was viewing when starting chat"
    )
    context_url = models.CharField(
        max_length=500,
        blank=True,
        help_text="URL user was on when starting chat"
    )

    # Email tracking
    emailed_at = models.DateTimeField(
        null=True,
        blank=True,
        help_text="When conversation was emailed to user"
    )

    class Meta:
        ordering = ['-started_at']
        verbose_name = "Help Conversation"
        verbose_name_plural = "Help Conversations"

    def __str__(self):
        return f"Chat with {self.user} - {self.started_at.strftime('%Y-%m-%d %H:%M')}"

    @property
    def message_count(self):
        return self.messages.count()

    def get_messages_for_email(self):
        """Get all messages formatted for email."""
        messages = self.messages.order_by('created_at')
        lines = []
        for msg in messages:
            sender = "You" if msg.is_user else "WLJ Assistant"
            timestamp = msg.created_at.strftime('%I:%M %p')
            lines.append(f"[{timestamp}] {sender}:\n{msg.content}\n")
        return "\n".join(lines)


class HelpMessage(models.Model):
    """
    Individual messages in a help conversation.
    """

    conversation = models.ForeignKey(
        HelpConversation,
        on_delete=models.CASCADE,
        related_name='messages'
    )

    # Message content
    content = models.TextField(
        help_text="Message text"
    )
    is_user = models.BooleanField(
        default=True,
        help_text="True if from user, False if from assistant"
    )

    # For bot responses - which article(s) were used
    source_articles = models.ManyToManyField(
        HelpArticle,
        blank=True,
        help_text="Articles used to generate this response"
    )

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['created_at']
        verbose_name = "Help Message"
        verbose_name_plural = "Help Messages"

    def __str__(self):
        sender = "User" if self.is_user else "Assistant"
        preview = self.content[:50] + "..." if len(self.content) > 50 else self.content
        return f"{sender}: {preview}"
