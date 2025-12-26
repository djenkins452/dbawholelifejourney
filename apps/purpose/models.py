"""
Purpose Module Models

The Purpose module serves as the strategic and spiritual compass for WLJ.
It helps users reflect deeply, plan intentionally, and define long-term direction.

This is the map and compass, not the daily log.
Visited seasonally, not daily.
"""

from django.conf import settings
from django.db import models
from django.urls import reverse
from django.utils import timezone

from apps.core.models import UserOwnedModel


# =============================================================================
# Configuration / Lookup Tables (Admin-Managed)
# =============================================================================

class LifeDomain(models.Model):
    """
    Configurable life domains for organizing goals.
    
    Default domains: Faith, Health, Family, Work, Finances, Learning, Personal Growth
    Admin can add/modify domains.
    """
    name = models.CharField(max_length=100, unique=True)
    slug = models.SlugField(max_length=100, unique=True)
    description = models.TextField(blank=True)
    icon = models.CharField(
        max_length=50,
        blank=True,
        help_text="Icon name or emoji for display"
    )
    color = models.CharField(
        max_length=7,
        blank=True,
        help_text="Hex color code (e.g., #6366f1)"
    )
    sort_order = models.PositiveIntegerField(default=0)
    is_active = models.BooleanField(default=True)
    
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        ordering = ['sort_order', 'name']
        verbose_name = "Life Domain"
        verbose_name_plural = "Life Domains"
    
    def __str__(self):
        return self.name


class ReflectionPrompt(models.Model):
    """
    Configurable reflection prompts for end-of-year and planning.
    
    Prompts can be categorized by type and customized by admin.
    """
    PROMPT_TYPE_CHOICES = [
        ('year_end', 'End of Year Reflection'),
        ('year_start', 'New Year Planning'),
        ('quarterly', 'Quarterly Review'),
        ('monthly', 'Monthly Check-in'),
        ('custom', 'Custom'),
    ]
    
    prompt_type = models.CharField(
        max_length=20,
        choices=PROMPT_TYPE_CHOICES,
        default='year_end'
    )
    question = models.TextField(
        help_text="The reflection question to ask the user"
    )
    description = models.TextField(
        blank=True,
        help_text="Optional guidance or context for this prompt"
    )
    sort_order = models.PositiveIntegerField(default=0)
    is_active = models.BooleanField(default=True)
    
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        ordering = ['prompt_type', 'sort_order']
        verbose_name = "Reflection Prompt"
        verbose_name_plural = "Reflection Prompts"
    
    def __str__(self):
        return f"{self.get_prompt_type_display()}: {self.question[:50]}..."


# =============================================================================
# Annual Direction
# =============================================================================

class AnnualDirection(UserOwnedModel):
    """
    The user's annual focus and Word of the Year.
    
    This becomes a decision filter across the app.
    Other modules can reference it contextually.
    """
    year = models.PositiveIntegerField(
        help_text="The year this direction applies to"
    )
    
    # Word of the Year
    word_of_year = models.CharField(
        max_length=50,
        help_text="Your guiding word for this year"
    )
    word_explanation = models.TextField(
        blank=True,
        help_text="Why did you choose this word? What does it mean to you?"
    )
    
    # Annual Theme
    theme = models.CharField(
        max_length=200,
        blank=True,
        help_text="Optional annual theme or focus area"
    )
    theme_description = models.TextField(
        blank=True,
        help_text="Expand on your theme"
    )
    
    # Anchor - Scripture or Quote
    anchor_text = models.TextField(
        blank=True,
        help_text="A scripture, quote, or phrase to anchor your year"
    )
    anchor_source = models.CharField(
        max_length=200,
        blank=True,
        help_text="Source of the anchor (e.g., Proverbs 3:5-6, Author name)"
    )
    
    # Status
    is_current = models.BooleanField(
        default=False,
        help_text="Is this the current year's direction?"
    )
    
    class Meta:
        ordering = ['-year']
        unique_together = ['user', 'year']
        verbose_name = "Annual Direction"
        verbose_name_plural = "Annual Directions"
    
    def __str__(self):
        return f"{self.year}: {self.word_of_year}"
    
    def get_absolute_url(self):
        return reverse('purpose:direction_detail', kwargs={'pk': self.pk})
    
    def save(self, *args, **kwargs):
        # If marking as current, unset other current directions for this user
        if self.is_current:
            AnnualDirection.objects.filter(
                user=self.user,
                is_current=True
            ).exclude(pk=self.pk).update(is_current=False)
        super().save(*args, **kwargs)


# =============================================================================
# Life Goals
# =============================================================================

class LifeGoal(UserOwnedModel):
    """
    Medium to long-term life goals (12-36 month view).
    
    Goals are organized by life domain and focus on direction, not execution.
    This is NOT a task list - no daily checkboxes.
    """
    STATUS_CHOICES = [
        ('active', 'Active'),
        ('paused', 'Paused'),
        ('completed', 'Completed'),
        ('released', 'Released'),  # Intentionally let go
    ]
    
    TIMEFRAME_CHOICES = [
        ('year_1', 'Within 1 Year'),
        ('year_2', '1-2 Years'),
        ('year_3', '2-3 Years'),
        ('ongoing', 'Ongoing'),
    ]
    
    # Core
    title = models.CharField(max_length=200)
    description = models.TextField(
        blank=True,
        help_text="What is this goal about?"
    )
    
    # Why it matters
    why_it_matters = models.TextField(
        blank=True,
        help_text="Why is this goal important to you?"
    )
    
    # Success definition
    success_looks_like = models.TextField(
        blank=True,
        help_text="What does success look like? How will you know you've achieved this?"
    )
    
    # Organization
    domain = models.ForeignKey(
        LifeDomain,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='goals',
        help_text="Which life area does this goal belong to?"
    )
    
    # Timeframe
    timeframe = models.CharField(
        max_length=20,
        choices=TIMEFRAME_CHOICES,
        default='year_1'
    )
    target_date = models.DateField(
        null=True,
        blank=True,
        help_text="Optional target completion date"
    )
    
    # Status
    status = models.CharField(
        max_length=20,
        choices=STATUS_CHOICES,
        default='active'
    )
    completed_date = models.DateField(null=True, blank=True)
    
    # Reflection on completion or release
    reflection = models.TextField(
        blank=True,
        help_text="Reflection after completing or releasing this goal"
    )
    
    # Link to annual direction
    annual_direction = models.ForeignKey(
        AnnualDirection,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='goals',
        help_text="Link this goal to a year's direction"
    )
    
    # Ordering
    sort_order = models.PositiveIntegerField(default=0)
    
    class Meta:
        ordering = ['domain', 'sort_order', '-created_at']
        verbose_name = "Life Goal"
        verbose_name_plural = "Life Goals"
    
    def __str__(self):
        return self.title
    
    def get_absolute_url(self):
        return reverse('purpose:goal_detail', kwargs={'pk': self.pk})
    
    def mark_complete(self):
        """Mark goal as completed."""
        self.status = 'completed'
        self.completed_date = timezone.now().date()
        self.save(update_fields=['status', 'completed_date', 'updated_at'])
    
    def mark_released(self):
        """Mark goal as intentionally released."""
        self.status = 'released'
        self.save(update_fields=['status', 'updated_at'])


# =============================================================================
# Change Intentions (Identity-Based)
# =============================================================================

class ChangeIntention(UserOwnedModel):
    """
    Identity and behavior shifts, not measurable goals.
    
    Examples:
    - "Be more present"
    - "Build margin"
    - "Respond, don't react"
    
    These are used by AI to detect alignment or drift.
    """
    STATUS_CHOICES = [
        ('active', 'Active'),
        ('integrated', 'Integrated'),  # Has become natural
        ('paused', 'Paused'),
        ('released', 'Released'),
    ]
    
    # Core
    intention = models.CharField(
        max_length=200,
        help_text="The change you want to embody"
    )
    description = models.TextField(
        blank=True,
        help_text="What does this look like in practice?"
    )
    
    # Why
    motivation = models.TextField(
        blank=True,
        help_text="Why is this change important to you?"
    )
    
    # Status
    status = models.CharField(
        max_length=20,
        choices=STATUS_CHOICES,
        default='active'
    )
    
    # Link to annual direction
    annual_direction = models.ForeignKey(
        AnnualDirection,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='intentions',
        help_text="Link this intention to a year's direction"
    )
    
    # Ordering
    sort_order = models.PositiveIntegerField(default=0)
    
    class Meta:
        ordering = ['sort_order', '-created_at']
        verbose_name = "Change Intention"
        verbose_name_plural = "Change Intentions"
    
    def __str__(self):
        return self.intention
    
    def get_absolute_url(self):
        return reverse('purpose:intention_detail', kwargs={'pk': self.pk})


# =============================================================================
# Reflections
# =============================================================================

class Reflection(UserOwnedModel):
    """
    Structured reflections for end-of-year or planning periods.
    
    Captures responses to reflection prompts.
    """
    REFLECTION_TYPE_CHOICES = [
        ('year_end', 'End of Year'),
        ('year_start', 'New Year'),
        ('quarterly', 'Quarterly'),
        ('custom', 'Custom'),
    ]
    
    # Type and timing
    reflection_type = models.CharField(
        max_length=20,
        choices=REFLECTION_TYPE_CHOICES,
        default='year_end'
    )
    year = models.PositiveIntegerField(
        help_text="The year being reflected upon"
    )
    quarter = models.PositiveIntegerField(
        null=True,
        blank=True,
        help_text="Quarter (1-4) if quarterly reflection"
    )
    
    # Title for custom reflections
    title = models.CharField(
        max_length=200,
        blank=True,
        help_text="Optional title for this reflection"
    )
    
    # Status
    is_complete = models.BooleanField(
        default=False,
        help_text="Have you finished this reflection?"
    )
    completed_at = models.DateTimeField(null=True, blank=True)
    
    # AI Summary (future-ready)
    ai_summary = models.TextField(
        blank=True,
        help_text="AI-generated summary of this reflection"
    )
    
    class Meta:
        ordering = ['-year', '-created_at']
        verbose_name = "Reflection"
        verbose_name_plural = "Reflections"
    
    def __str__(self):
        if self.title:
            return f"{self.title} ({self.year})"
        return f"{self.get_reflection_type_display()} {self.year}"
    
    def get_absolute_url(self):
        return reverse('purpose:reflection_detail', kwargs={'pk': self.pk})
    
    def mark_complete(self):
        """Mark reflection as complete."""
        self.is_complete = True
        self.completed_at = timezone.now()
        self.save(update_fields=['is_complete', 'completed_at', 'updated_at'])


class ReflectionResponse(models.Model):
    """
    Individual responses to reflection prompts.
    """
    reflection = models.ForeignKey(
        Reflection,
        on_delete=models.CASCADE,
        related_name='responses'
    )
    prompt = models.ForeignKey(
        ReflectionPrompt,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='responses'
    )
    
    # If prompt is deleted or custom question
    question_text = models.TextField(
        help_text="The question that was asked"
    )
    
    # Response
    response = models.TextField(
        blank=True,
        help_text="Your response to this prompt"
    )
    
    # Ordering
    sort_order = models.PositiveIntegerField(default=0)
    
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        ordering = ['sort_order', 'created_at']
    
    def __str__(self):
        return f"Response to: {self.question_text[:50]}..."
    
    def save(self, *args, **kwargs):
        # Copy prompt question text if prompt exists
        if self.prompt and not self.question_text:
            self.question_text = self.prompt.question
        super().save(*args, **kwargs)


# =============================================================================
# Planning Actions (Keep/Stop/Start/Simplify)
# =============================================================================

class PlanningAction(UserOwnedModel):
    """
    Actions identified during year planning.
    
    Categories: Keep, Stop, Start, Simplify
    """
    ACTION_TYPE_CHOICES = [
        ('keep', 'Keep'),
        ('stop', 'Stop'),
        ('start', 'Start'),
        ('simplify', 'Simplify'),
    ]
    
    annual_direction = models.ForeignKey(
        AnnualDirection,
        on_delete=models.CASCADE,
        related_name='planning_actions'
    )
    
    action_type = models.CharField(
        max_length=20,
        choices=ACTION_TYPE_CHOICES
    )
    
    description = models.TextField(
        help_text="What will you keep/stop/start/simplify?"
    )
    
    # Why
    reason = models.TextField(
        blank=True,
        help_text="Why is this important?"
    )
    
    # Ordering
    sort_order = models.PositiveIntegerField(default=0)
    
    class Meta:
        ordering = ['action_type', 'sort_order']
        verbose_name = "Planning Action"
        verbose_name_plural = "Planning Actions"
    
    def __str__(self):
        return f"{self.get_action_type_display()}: {self.description[:50]}..."
