"""
AI Models - Store generated insights for caching and history.
"""
from django.core.cache import cache
from django.db import models
from django.conf import settings


class CoachingStyle(models.Model):
    """
    Database-driven coaching styles for AI personality customization.

    Allows admin to add, edit, or disable coaching styles without code deploys.
    """
    key = models.SlugField(
        max_length=50,
        unique=True,
        help_text="Unique identifier (e.g., 'southern_belle', 'texas_rancher')"
    )
    name = models.CharField(
        max_length=100,
        help_text="Display name shown to users"
    )
    description = models.CharField(
        max_length=300,
        help_text="Brief description shown when user selects style"
    )
    icon = models.CharField(
        max_length=10,
        default="🤝",
        help_text="Emoji icon displayed in the UI"
    )
    prompt_instructions = models.TextField(
        help_text="Full AI prompt instructions for this coaching style"
    )
    is_active = models.BooleanField(
        default=True,
        help_text="Whether this style is available for users to select"
    )
    is_default = models.BooleanField(
        default=False,
        help_text="Use this style as fallback if user's style is unavailable"
    )
    sort_order = models.PositiveIntegerField(
        default=0,
        help_text="Order in which styles appear in selection UI"
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['sort_order', 'name']
        verbose_name = "Coaching Style"
        verbose_name_plural = "Coaching Styles"

    def __str__(self):
        status = "" if self.is_active else " (inactive)"
        return f"{self.name}{status}"

    def save(self, *args, **kwargs):
        # Clear cache when style is updated
        cache.delete('coaching_styles_all')
        cache.delete(f'coaching_style_{self.key}')

        # Ensure only one default
        if self.is_default:
            CoachingStyle.objects.filter(is_default=True).exclude(pk=self.pk).update(is_default=False)

        super().save(*args, **kwargs)

    @classmethod
    def get_active_styles(cls):
        """Get all active styles, with caching."""
        cache_key = 'coaching_styles_all'
        styles = cache.get(cache_key)
        if styles is None:
            styles = list(cls.objects.filter(is_active=True))
            cache.set(cache_key, styles, 3600)  # Cache for 1 hour
        return styles

    @classmethod
    def get_by_key(cls, key):
        """Get a style by key, with caching and fallback."""
        cache_key = f'coaching_style_{key}'
        style = cache.get(cache_key)
        if style is None:
            style = cls.objects.filter(key=key, is_active=True).first()
            if style:
                cache.set(cache_key, style, 3600)

        # Fallback to default if style not found
        if not style:
            style = cls.objects.filter(is_default=True, is_active=True).first()

        # Ultimate fallback - get any active style
        if not style:
            style = cls.objects.filter(is_active=True).first()

        return style

    @classmethod
    def get_choices(cls):
        """Get choices tuple for form fields."""
        return [(s.key, s.name) for s in cls.get_active_styles()]


class AIInsight(models.Model):
    """
    Cached AI-generated insights.
    
    Insights are cached to:
    - Reduce API costs (don't regenerate same insight repeatedly)
    - Allow users to see past insights
    - Enable async generation
    """
    
    INSIGHT_TYPES = [
        ('daily', 'Daily Dashboard Insight'),
        ('weekly_summary', 'Weekly Journal Summary'),
        ('monthly_summary', 'Monthly Journal Summary'),
        ('reflection_prompt', 'Reflection Prompt'),
        ('goal_encouragement', 'Goal Encouragement'),
        ('health_insight', 'Health Insight'),
        ('prayer_encouragement', 'Prayer Encouragement'),
        ('entry_reflection', 'Journal Entry Reflection'),
    ]
    
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='ai_insights'
    )
    insight_type = models.CharField(max_length=30, choices=INSIGHT_TYPES)
    content = models.TextField()
    
    # Optional reference to related object
    related_object_type = models.CharField(max_length=50, blank=True)
    related_object_id = models.PositiveIntegerField(null=True, blank=True)
    
    # Context used to generate (for debugging/transparency)
    context_summary = models.TextField(blank=True, help_text="Summary of data used to generate")

    # Coaching style used when generating (for cache invalidation)
    coaching_style = models.CharField(
        max_length=20,
        blank=True,
        default='supportive',
        help_text="Coaching style used when generating this insight"
    )
    
    # Timestamps
    created_at = models.DateTimeField(auto_now_add=True)
    valid_until = models.DateTimeField(
        null=True, blank=True,
        help_text="When this insight should be refreshed"
    )
    
    # User feedback
    was_helpful = models.BooleanField(null=True, blank=True)
    
    class Meta:
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['user', 'insight_type', '-created_at']),
            models.Index(fields=['user', 'valid_until']),
        ]
    
    def __str__(self):
        return f"{self.get_insight_type_display()} for {self.user} ({self.created_at.date()})"
    
    @property
    def is_valid(self):
        """Check if insight is still valid (not expired)."""
        from django.utils import timezone
        if not self.valid_until:
            return True
        return timezone.now() < self.valid_until


class AIPromptConfig(models.Model):
    """
    Database-driven AI prompt configuration.

    Allows admin to customize the AI system prompts, response length,
    and guidance without code changes.
    """
    PROMPT_TYPES = [
        ('system_base', 'System Base Prompt'),
        ('daily_insight', 'Daily Dashboard Insight'),
        ('weekly_summary', 'Weekly Journal Summary'),
        ('journal_reflection', 'Journal Entry Reflection'),
        ('goal_progress', 'Goal Progress Feedback'),
        ('health_encouragement', 'Health Encouragement'),
        ('prayer_encouragement', 'Prayer Encouragement'),
        ('accountability_nudge', 'Accountability Nudge'),
        ('celebration', 'Celebration Message'),
        ('faith_context', 'Faith Context Addition'),
    ]

    prompt_type = models.CharField(
        max_length=30,
        choices=PROMPT_TYPES,
        unique=True,
        help_text="Type of prompt this configuration applies to"
    )
    name = models.CharField(
        max_length=100,
        help_text="Friendly name for this configuration"
    )
    description = models.TextField(
        blank=True,
        help_text="Internal notes about this prompt configuration"
    )

    # The actual prompt content
    system_instructions = models.TextField(
        help_text="Main instructions for the AI. Use {variables} for dynamic content."
    )

    # Response control
    min_sentences = models.PositiveIntegerField(
        default=2,
        help_text="Minimum number of sentences in response"
    )
    max_sentences = models.PositiveIntegerField(
        default=4,
        help_text="Maximum number of sentences in response"
    )
    max_tokens = models.PositiveIntegerField(
        default=150,
        help_text="Maximum tokens for API response"
    )

    # Additional guidance
    tone_guidance = models.TextField(
        blank=True,
        help_text="Additional tone/style guidance (e.g., 'Be warm but not preachy')"
    )
    things_to_avoid = models.TextField(
        blank=True,
        help_text="Things the AI should NOT do (e.g., 'Never shame the user')"
    )
    example_responses = models.TextField(
        blank=True,
        help_text="Example good responses for this prompt type"
    )

    is_active = models.BooleanField(
        default=True,
        help_text="Whether this configuration is currently in use"
    )

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['prompt_type']
        verbose_name = "AI Prompt Configuration"
        verbose_name_plural = "AI Prompt Configurations"

    def __str__(self):
        return f"{self.name} ({self.get_prompt_type_display()})"

    def save(self, *args, **kwargs):
        # Clear cache when config is updated
        cache.delete(f'ai_prompt_config_{self.prompt_type}')
        cache.delete('ai_prompt_configs_all')
        super().save(*args, **kwargs)

    @classmethod
    def get_config(cls, prompt_type):
        """Get configuration for a prompt type, with caching."""
        cache_key = f'ai_prompt_config_{prompt_type}'
        config = cache.get(cache_key)
        if config is None:
            config = cls.objects.filter(prompt_type=prompt_type, is_active=True).first()
            if config:
                cache.set(cache_key, config, 3600)  # Cache for 1 hour
        return config

    def get_full_prompt(self) -> str:
        """Build the complete prompt with all guidance."""
        parts = [self.system_instructions]

        # Add sentence guidance
        if self.min_sentences == self.max_sentences:
            parts.append(f"\nResponse length: Exactly {self.min_sentences} sentences.")
        else:
            parts.append(f"\nResponse length: {self.min_sentences}-{self.max_sentences} sentences.")

        # Add tone guidance
        if self.tone_guidance:
            parts.append(f"\nTone guidance: {self.tone_guidance}")

        # Add things to avoid
        if self.things_to_avoid:
            parts.append(f"\nIMPORTANT - Avoid: {self.things_to_avoid}")

        return "\n".join(parts)


class AIUsageLog(models.Model):
    """
    Track AI API usage for monitoring and cost management.
    """
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='ai_usage_logs'
    )
    endpoint = models.CharField(max_length=50)  # e.g., 'journal_reflection', 'daily_insight'
    model_used = models.CharField(max_length=50)  # e.g., 'gpt-4o-mini'
    
    prompt_tokens = models.PositiveIntegerField(default=0)
    completion_tokens = models.PositiveIntegerField(default=0)
    total_tokens = models.PositiveIntegerField(default=0)
    
    # Estimated cost (for monitoring)
    estimated_cost_usd = models.DecimalField(
        max_digits=10, decimal_places=6, 
        default=0,
        help_text="Estimated cost in USD"
    )
    
    success = models.BooleanField(default=True)
    error_message = models.TextField(blank=True)
    
    created_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        ordering = ['-created_at']
    
    def __str__(self):
        return f"{self.endpoint} - {self.user} - {self.total_tokens} tokens"
