"""
AI Models - Store generated insights for caching and history.
"""
from django.db import models
from django.conf import settings


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
