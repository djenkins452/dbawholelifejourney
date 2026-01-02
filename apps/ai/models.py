# ==============================================================================
# File: models.py
# Project: Whole Life Journey - Django 5.x Personal Wellness/Journaling App
# Description: AI Models - Insights caching, coaching styles, prompt configs
# Owner: Danny Jenkins (dannyjenkins71@gmail.com)
# Created: 2025-01-01
# Last Updated: 2025-12-31 (Added system prompt cache invalidation)
# ==============================================================================
"""
AI Models - Store generated insights for caching and history.

Caching Strategy (2025-12-31):
- CoachingStyle: Cached 1 hour, invalidates on save
- AIPromptConfig: Cached 1 hour, invalidates on save
- Both also invalidate system_prompt_* cache keys on save
"""
from django.core.cache import cache
from django.db import models
from django.conf import settings


def invalidate_system_prompt_cache():
    """
    Invalidate all cached system prompts.

    Called when CoachingStyle or AIPromptConfig is updated.
    System prompts are cached with keys like:
    - system_prompt_supportive_True
    - system_prompt_supportive_False
    - system_prompt_direct_True
    - etc.
    """
    # Get all active coaching style keys
    styles = ['supportive', 'gentle', 'direct', 'cheerleader', 'mentor', 'companion', 'coach']
    for style in styles:
        for faith in [True, False]:
            cache.delete(f'system_prompt_{style}_{faith}')


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

        # Also invalidate system prompt cache (uses coaching style)
        invalidate_system_prompt_cache()

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
        verbose_name = "AI Insight"
        verbose_name_plural = "AI Insights"

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

        # Also invalidate system prompt cache (uses prompt configs)
        invalidate_system_prompt_cache()

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
        verbose_name = "AI Usage Log"
        verbose_name_plural = "AI Usage Logs"

    def __str__(self):
        return f"{self.endpoint} - {self.user} - {self.total_tokens} tokens"


# =============================================================================
# DASHBOARD AI PERSONAL ASSISTANT MODELS
# =============================================================================

class AssistantConversation(models.Model):
    """
    Conversation session with the Dashboard AI Personal Assistant.

    Groups related messages together for context continuity.
    """
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='assistant_conversations'
    )

    # Conversation metadata
    title = models.CharField(
        max_length=200,
        blank=True,
        help_text="Auto-generated or user-provided conversation title"
    )

    # Session type
    SESSION_TYPE_CHOICES = [
        ('daily_checkin', 'Daily Check-in'),
        ('reflection', 'Reflection Session'),
        ('planning', 'Planning Session'),
        ('accountability', 'Accountability Check'),
        ('celebration', 'Celebration'),
        ('general', 'General Conversation'),
    ]
    session_type = models.CharField(
        max_length=20,
        choices=SESSION_TYPE_CHOICES,
        default='general'
    )

    # State tracking
    is_active = models.BooleanField(
        default=True,
        help_text="Whether this conversation is currently active"
    )

    # Context summary for AI continuity
    context_summary = models.TextField(
        blank=True,
        help_text="AI-generated summary of conversation for continuity"
    )

    # Timestamps
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-updated_at']
        verbose_name = "Assistant Conversation"
        verbose_name_plural = "Assistant Conversations"
        indexes = [
            models.Index(fields=['user', '-updated_at']),
            models.Index(fields=['user', 'is_active']),
        ]

    def __str__(self):
        return f"{self.user.email} - {self.title or self.get_session_type_display()} ({self.created_at.date()})"

    @classmethod
    def get_or_create_active(cls, user):
        """Get or create an active conversation for today."""
        from django.utils import timezone
        from apps.core.utils import get_user_today

        today = get_user_today(user)

        # Look for active conversation from today
        conversation = cls.objects.filter(
            user=user,
            is_active=True,
            created_at__date=today
        ).first()

        if not conversation:
            conversation = cls.objects.create(
                user=user,
                session_type='daily_checkin',
                is_active=True
            )

        return conversation


class AssistantMessage(models.Model):
    """
    Individual message in a Dashboard AI conversation.
    """
    conversation = models.ForeignKey(
        AssistantConversation,
        on_delete=models.CASCADE,
        related_name='messages'
    )

    # Message role
    ROLE_CHOICES = [
        ('user', 'User'),
        ('assistant', 'Assistant'),
        ('system', 'System'),
    ]
    role = models.CharField(
        max_length=10,
        choices=ROLE_CHOICES
    )

    # Message content
    content = models.TextField()

    # Message type for special handling
    MESSAGE_TYPE_CHOICES = [
        ('text', 'Text Message'),
        ('insight', 'AI Insight'),
        ('nudge', 'Accountability Nudge'),
        ('celebration', 'Celebration'),
        ('action_suggestion', 'Action Suggestion'),
        ('reflection_prompt', 'Reflection Prompt'),
        ('scripture', 'Scripture Reference'),
        ('priority_list', 'Priority List'),
        ('state_assessment', 'State Assessment'),
    ]
    message_type = models.CharField(
        max_length=20,
        choices=MESSAGE_TYPE_CHOICES,
        default='text'
    )

    # Metadata for special message types (JSON for flexibility)
    metadata = models.JSONField(
        default=dict,
        blank=True,
        help_text="Additional data for message (e.g., action URLs, priorities)"
    )

    # User feedback
    was_helpful = models.BooleanField(null=True, blank=True)

    # Timestamps
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['created_at']
        verbose_name = "Assistant Message"
        verbose_name_plural = "Assistant Messages"
        indexes = [
            models.Index(fields=['conversation', 'created_at']),
        ]

    def __str__(self):
        return f"{self.get_role_display()}: {self.content[:50]}..."


class UserStateSnapshot(models.Model):
    """
    Daily snapshot of user's state for AI assessment.

    Captures the state of all user data at a point in time for:
    - Trend analysis
    - Pattern detection
    - Drift identification
    - Accountability tracking
    """
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='state_snapshots'
    )

    # Date of snapshot (one per day)
    snapshot_date = models.DateField()

    # Journal metrics
    journal_count_total = models.PositiveIntegerField(default=0)
    journal_count_week = models.PositiveIntegerField(default=0)
    journal_streak = models.PositiveIntegerField(default=0)
    dominant_mood = models.CharField(max_length=20, blank=True)

    # Task metrics
    tasks_completed_today = models.PositiveIntegerField(default=0)
    tasks_completed_week = models.PositiveIntegerField(default=0)
    tasks_overdue = models.PositiveIntegerField(default=0)
    tasks_due_today = models.PositiveIntegerField(default=0)

    # Goal metrics
    active_goals = models.PositiveIntegerField(default=0)
    completed_goals_month = models.PositiveIntegerField(default=0)
    goal_progress_notes = models.TextField(blank=True)

    # Faith metrics (if enabled)
    active_prayers = models.PositiveIntegerField(default=0)
    answered_prayers_month = models.PositiveIntegerField(default=0)
    bible_study_entries_week = models.PositiveIntegerField(default=0)

    # Health metrics
    weight_current = models.DecimalField(max_digits=5, decimal_places=1, null=True, blank=True)
    weight_trend = models.CharField(max_length=10, blank=True)  # up, down, stable
    fasts_completed_week = models.PositiveIntegerField(default=0)
    workouts_week = models.PositiveIntegerField(default=0)
    workout_streak = models.PositiveIntegerField(default=0)
    medicine_adherence = models.PositiveIntegerField(null=True, blank=True)  # percentage

    # Change intention tracking
    active_intentions = models.PositiveIntegerField(default=0)
    intention_alignment_score = models.PositiveIntegerField(
        null=True, blank=True,
        help_text="AI-assessed alignment with stated intentions (0-100)"
    )

    # Habit goal tracking
    active_habit_goals = models.PositiveIntegerField(default=0)
    habit_completion_rate = models.DecimalField(
        max_digits=5, decimal_places=1, null=True, blank=True,
        help_text="Average completion rate across active habit goals"
    )
    habit_current_streak = models.PositiveIntegerField(
        default=0,
        help_text="Current longest streak across habit goals"
    )
    habit_goals_data = models.JSONField(
        default=list,
        blank=True,
        help_text="Detailed habit goal data for AI analysis"
    )

    # AI-generated assessments (stored for trend analysis)
    ai_assessment = models.TextField(
        blank=True,
        help_text="AI's assessment of user state this day"
    )
    alignment_gaps = models.JSONField(
        default=list,
        blank=True,
        help_text="Areas where behavior doesn't match stated intentions"
    )
    celebration_worthy = models.JSONField(
        default=list,
        blank=True,
        help_text="Achievements worth celebrating"
    )

    # Timestamps
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-snapshot_date']
        unique_together = ['user', 'snapshot_date']
        verbose_name = "User State Snapshot"
        verbose_name_plural = "User State Snapshots"
        indexes = [
            models.Index(fields=['user', '-snapshot_date']),
        ]

    def __str__(self):
        return f"{self.user.email} - {self.snapshot_date}"


class DailyPriority(models.Model):
    """
    AI-suggested daily priorities based on user's goals and current state.

    These are the 3-5 things the AI recommends focusing on today.
    """
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='daily_priorities'
    )

    # Date
    priority_date = models.DateField()

    # Priority type
    PRIORITY_TYPE_CHOICES = [
        ('faith', 'Faith & Spiritual'),
        ('purpose', 'Purpose & Goals'),
        ('commitment', 'Existing Commitment'),
        ('maintenance', 'Maintenance Task'),
        ('health', 'Health & Wellness'),
        ('relationship', 'Relationship'),
        ('work', 'Work & Career'),
        ('personal', 'Personal Growth'),
    ]
    priority_type = models.CharField(
        max_length=20,
        choices=PRIORITY_TYPE_CHOICES
    )

    # Priority content
    title = models.CharField(max_length=200)
    description = models.TextField(blank=True)
    why_important = models.TextField(
        blank=True,
        help_text="Connection to user's stated purpose/goals"
    )

    # Linked items (optional)
    linked_task_id = models.PositiveIntegerField(null=True, blank=True)
    linked_goal_id = models.PositiveIntegerField(null=True, blank=True)
    linked_intention_id = models.PositiveIntegerField(null=True, blank=True)

    # Ordering
    sort_order = models.PositiveIntegerField(default=0)

    # User interaction
    is_completed = models.BooleanField(default=False)
    completed_at = models.DateTimeField(null=True, blank=True)
    user_dismissed = models.BooleanField(default=False)

    # AI generation metadata
    generated_by_ai = models.BooleanField(default=True)
    generation_context = models.TextField(blank=True)

    # Timestamps
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['priority_date', 'sort_order']
        verbose_name = "Daily Priority"
        verbose_name_plural = "Daily Priorities"
        indexes = [
            models.Index(fields=['user', 'priority_date']),
            models.Index(fields=['user', 'priority_date', 'is_completed']),
        ]

    def __str__(self):
        return f"{self.priority_date}: {self.title}"

    def mark_complete(self):
        """Mark this priority as completed."""
        from django.utils import timezone
        self.is_completed = True
        self.completed_at = timezone.now()
        self.save(update_fields=['is_completed', 'completed_at', 'updated_at'])

    @classmethod
    def get_completion_stats(cls, user, days=7):
        """
        Get completion statistics for the user over the specified number of days.
        Returns dict with completion counts and rates.
        """
        from django.utils import timezone
        from django.db.models import Count, Q
        from datetime import timedelta

        end_date = timezone.now().date()
        start_date = end_date - timedelta(days=days - 1)

        priorities = cls.objects.filter(
            user=user,
            priority_date__gte=start_date,
            priority_date__lte=end_date,
            user_dismissed=False
        )

        total = priorities.count()
        completed = priorities.filter(is_completed=True).count()

        # Get daily breakdown
        daily_stats = priorities.values('priority_date').annotate(
            total=Count('id'),
            completed=Count('id', filter=Q(is_completed=True))
        ).order_by('priority_date')

        # Get stats by type
        type_stats = priorities.values('priority_type').annotate(
            total=Count('id'),
            completed=Count('id', filter=Q(is_completed=True))
        )

        return {
            'total': total,
            'completed': completed,
            'completion_rate': round((completed / total * 100) if total > 0 else 0, 1),
            'daily_stats': list(daily_stats),
            'type_stats': list(type_stats),
            'days': days,
        }


class TrendAnalysis(models.Model):
    """
    Stores AI-generated trend analysis over time periods.

    Used for weekly/monthly summaries and pattern detection.
    """
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='trend_analyses'
    )

    # Analysis period
    PERIOD_CHOICES = [
        ('week', 'Weekly'),
        ('month', 'Monthly'),
        ('quarter', 'Quarterly'),
        ('year', 'Annual'),
    ]
    period_type = models.CharField(
        max_length=10,
        choices=PERIOD_CHOICES
    )
    period_start = models.DateField()
    period_end = models.DateField()

    # Analysis type
    ANALYSIS_TYPE_CHOICES = [
        ('overall', 'Overall Wellness'),
        ('journal', 'Journaling Patterns'),
        ('productivity', 'Productivity & Tasks'),
        ('faith', 'Faith Journey'),
        ('health', 'Health & Fitness'),
        ('goals', 'Goal Progress'),
        ('mood', 'Mood Patterns'),
    ]
    analysis_type = models.CharField(
        max_length=20,
        choices=ANALYSIS_TYPE_CHOICES
    )

    # Analysis content
    summary = models.TextField(
        help_text="AI-generated summary of the period"
    )
    patterns_detected = models.JSONField(
        default=list,
        help_text="Patterns identified during this period"
    )
    recommendations = models.JSONField(
        default=list,
        help_text="AI recommendations based on analysis"
    )
    comparison_to_previous = models.TextField(
        blank=True,
        help_text="How this period compares to the previous period"
    )

    # Key metrics
    metrics = models.JSONField(
        default=dict,
        help_text="Key metrics for this period"
    )

    # User feedback
    was_helpful = models.BooleanField(null=True, blank=True)
    user_notes = models.TextField(blank=True)

    # Timestamps
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-period_end', '-created_at']
        verbose_name = "Trend Analysis"
        verbose_name_plural = "Trend Analyses"
        indexes = [
            models.Index(fields=['user', '-period_end']),
            models.Index(fields=['user', 'period_type', '-period_end']),
        ]

    def __str__(self):
        return f"{self.user.email} - {self.get_analysis_type_display()} ({self.period_start} to {self.period_end})"


class ReflectionPromptQueue(models.Model):
    """
    Queue of AI-generated reflection prompts for journaling.

    The AI generates personalized prompts based on user's current state,
    goals, and recent activity. These are queued and shown when appropriate.
    """
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='reflection_prompts'
    )

    # Prompt content
    prompt_text = models.TextField()

    # Context
    PROMPT_CONTEXT_CHOICES = [
        ('morning', 'Morning Reflection'),
        ('evening', 'Evening Reflection'),
        ('weekly', 'Weekly Review'),
        ('goal_related', 'Goal-Related'),
        ('intention_check', 'Intention Check'),
        ('gratitude', 'Gratitude'),
        ('faith', 'Faith & Spiritual'),
        ('challenge', 'Challenge Processing'),
        ('celebration', 'Celebration'),
        ('general', 'General Reflection'),
    ]
    prompt_context = models.CharField(
        max_length=20,
        choices=PROMPT_CONTEXT_CHOICES,
        default='general'
    )

    # Why this prompt
    relevance_reason = models.TextField(
        blank=True,
        help_text="Why this prompt is relevant to the user right now"
    )

    # Linked to specific data (optional)
    linked_goal_id = models.PositiveIntegerField(null=True, blank=True)
    linked_intention_id = models.PositiveIntegerField(null=True, blank=True)
    linked_entry_id = models.PositiveIntegerField(null=True, blank=True)

    # Queue management
    is_shown = models.BooleanField(default=False)
    shown_at = models.DateTimeField(null=True, blank=True)
    is_used = models.BooleanField(
        default=False,
        help_text="Whether user started journaling with this prompt"
    )
    used_at = models.DateTimeField(null=True, blank=True)

    # Expiration
    valid_until = models.DateTimeField(
        null=True, blank=True,
        help_text="Some prompts are time-sensitive"
    )

    # Timestamps
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']
        verbose_name = "Reflection Prompt"
        verbose_name_plural = "Reflection Prompts"
        indexes = [
            models.Index(fields=['user', 'is_shown', '-created_at']),
        ]

    def __str__(self):
        return f"{self.get_prompt_context_display()}: {self.prompt_text[:50]}..."

    def mark_shown(self):
        """Mark this prompt as shown to the user."""
        from django.utils import timezone
        self.is_shown = True
        self.shown_at = timezone.now()
        self.save(update_fields=['is_shown', 'shown_at'])

    def mark_used(self):
        """Mark this prompt as used (user started journaling with it)."""
        from django.utils import timezone
        self.is_used = True
        self.used_at = timezone.now()
        self.save(update_fields=['is_used', 'used_at'])
