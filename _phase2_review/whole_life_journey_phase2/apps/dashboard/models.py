"""
Dashboard Models - Supporting models for dashboard functionality.

The Dashboard primarily displays derived data from other modules.
These models support dashboard-specific features like:
- Daily encouragement messages
- Scripture verses (for Faith-enabled users)
"""

from django.db import models


class DailyEncouragement(models.Model):
    """
    Curated daily encouragement messages.
    
    These are displayed on the dashboard. When Faith is enabled,
    they may include Scripture references.
    """

    message = models.TextField()
    scripture_reference = models.CharField(
        max_length=100,
        blank=True,
        help_text="e.g., 'Philippians 4:6-7'",
    )
    scripture_text = models.TextField(blank=True)
    translation = models.CharField(
        max_length=10,
        default="ESV",
        help_text="Bible translation (ESV, NIV, BSB)",
    )
    
    # Categorization
    is_faith_specific = models.BooleanField(
        default=False,
        help_text="Only show when Faith module is enabled",
    )
    themes = models.JSONField(
        default=list,
        blank=True,
        help_text="Themes like 'peace', 'trust', 'gratitude', 'strength'",
    )
    
    # When to show (optional targeting)
    day_of_week = models.IntegerField(
        null=True,
        blank=True,
        help_text="0=Monday, 6=Sunday. Null = any day",
    )
    month = models.IntegerField(
        null=True,
        blank=True,
        help_text="1=January, 12=December. Null = any month",
    )
    
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "daily encouragement"
        verbose_name_plural = "daily encouragements"

    def __str__(self):
        preview = self.message[:50]
        if self.scripture_reference:
            return f"{preview}... ({self.scripture_reference})"
        return f"{preview}..."
