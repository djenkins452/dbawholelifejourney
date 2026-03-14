# ==============================================================================
# File: apps/purpose/models.py
# Project: Whole Life Journey - Django 5.x Personal Wellness/Journaling App
# Description: Purpose module models including life goals, habit goals, and reflections
# Owner: Danny Jenkins (admin@wholelifejourney.com)
# Created: 2024-01-01
# Last Updated: 2026-01-03
# ==============================================================================
"""
Purpose Module Models

The Purpose module serves as the strategic and spiritual compass for WLJ.
It helps users reflect deeply, plan intentionally, and define long-term direction.

This is the map and compass, not the daily log.
Visited seasonally, not daily.

Also includes HabitGoal for shorter-term habit tracking with visual matrix display.
"""

import math
from django.core.exceptions import ValidationError
from django.db import models
from django.urls import reverse
from django.utils import timezone

from apps.core.models import UserOwnedModel
from apps.core.utils import get_user_today


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

    # Commitment level
    COMMITMENT_LEVEL_CHOICES = [
        ('optional', 'Optional'),
        ('important', 'Important'),
        ('non_negotiable', 'Non-Negotiable'),
    ]
    commitment_level = models.CharField(
        max_length=20,
        choices=COMMITMENT_LEVEL_CHOICES,
        default='important',
        help_text="How committed are you to this goal?",
    )
    
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

    # =========================================================================
    # Milestone Progress Properties
    # =========================================================================

    @property
    def milestone_count(self):
        """Total number of milestones for this goal."""
        return self.milestones.count()

    @property
    def completed_milestone_count(self):
        """Number of completed milestones."""
        return self.milestones.filter(completed=True).count()

    @property
    def milestone_progress_percent(self):
        """Progress percentage based on completed milestones (0-100)."""
        total = self.milestone_count
        if total == 0:
            return 0
        return int((self.completed_milestone_count / total) * 100)

    @property
    def has_milestones(self):
        """Whether this goal has any milestones defined."""
        return self.milestone_count > 0

    @property
    def all_milestones_complete(self):
        """Whether all milestones are completed."""
        return self.has_milestones and self.completed_milestone_count == self.milestone_count

    @property
    def next_milestone(self):
        """Get the next incomplete milestone by target date, then sort order."""
        return self.milestones.filter(completed=False).order_by(
            models.F('target_date').asc(nulls_last=True),
            'sort_order'
        ).first()

    @property
    def upcoming_milestones(self):
        """Get incomplete milestones due in the next 7 days."""
        today = timezone.now().date()
        week_from_now = today + timezone.timedelta(days=7)
        return self.milestones.filter(
            completed=False,
            target_date__isnull=False,
            target_date__gte=today,
            target_date__lte=week_from_now
        ).order_by('target_date')

    @property
    def overdue_milestones(self):
        """Get incomplete milestones past their target date."""
        today = timezone.now().date()
        return self.milestones.filter(
            completed=False,
            target_date__isnull=False,
            target_date__lt=today
        ).order_by('target_date')

    # =========================================================================
    # Deadline Properties (for goal-level target_date)
    # =========================================================================

    @property
    def is_overdue(self):
        """Check if goal is past target date and not completed."""
        if self.status == 'completed' or not self.target_date:
            return False
        return self.target_date < timezone.now().date()

    @property
    def days_until_due(self):
        """Days until target date (negative if overdue). None if no target date."""
        if not self.target_date:
            return None
        return (self.target_date - timezone.now().date()).days

    @property
    def deadline_urgency(self):
        """
        Get deadline urgency level for badge display.

        Returns:
            - 'completed': Goal is completed (celebrate!)
            - 'overdue': Past target date (gentle reminder)
            - 'urgent': 0-7 days remaining
            - 'soon': 8-14 days remaining
            - 'approaching': 15-30 days remaining
            - None: No target date or 30+ days away
        """
        if self.status == 'completed':
            return 'completed'

        if not self.target_date:
            return None

        days = self.days_until_due

        if days < 0:
            return 'overdue'
        elif days <= 7:
            return 'urgent'
        elif days <= 14:
            return 'soon'
        elif days <= 30:
            return 'approaching'
        else:
            return None

    @property
    def deadline_badge_text(self):
        """
        Get human-friendly text for deadline badge.

        Returns encouraging, non-shaming text.
        """
        urgency = self.deadline_urgency

        if urgency == 'completed':
            return "🎉 Completed!"
        elif urgency == 'overdue':
            return "Past target date"
        elif urgency is None:
            return None

        days = self.days_until_due
        if days == 0:
            return "Due today"
        elif days == 1:
            return "Due tomorrow"
        else:
            return f"Due in {days} days"


# =============================================================================
# Goal Milestones
# =============================================================================

class GoalMilestone(models.Model):
    """
    Milestone checkpoints for LifeGoal progress tracking.

    Milestones are optional intermediate steps toward completing a goal.
    Research shows people who break goals into milestones are 42% more likely
    to achieve them (Dominican University study).
    """
    goal = models.ForeignKey(
        LifeGoal,
        on_delete=models.CASCADE,
        related_name='milestones'
    )

    # Core fields
    title = models.CharField(
        max_length=200,
        help_text="What needs to be accomplished?"
    )
    description = models.TextField(
        blank=True,
        help_text="Additional details about this milestone"
    )

    # Target date (optional)
    target_date = models.DateField(
        null=True,
        blank=True,
        help_text="When do you want to complete this milestone?"
    )

    # Completion tracking
    completed = models.BooleanField(default=False)
    completed_date = models.DateField(null=True, blank=True)

    # Ordering
    sort_order = models.PositiveIntegerField(default=0)

    # Timestamps
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = [
            models.F('target_date').asc(nulls_last=True),
            'sort_order',
            'created_at'
        ]
        verbose_name = "Goal Milestone"
        verbose_name_plural = "Goal Milestones"

    def __str__(self):
        status = "✓" if self.completed else "○"
        return f"{status} {self.title}"

    def mark_complete(self):
        """Mark milestone as completed."""
        self.completed = True
        self.completed_date = timezone.now().date()
        self.save(update_fields=['completed', 'completed_date', 'updated_at'])

    def mark_incomplete(self):
        """Mark milestone as incomplete."""
        self.completed = False
        self.completed_date = None
        self.save(update_fields=['completed', 'completed_date', 'updated_at'])

    @property
    def is_overdue(self):
        """Check if milestone is past due date and not completed."""
        if self.completed or not self.target_date:
            return False
        return self.target_date < timezone.now().date()

    @property
    def days_until_due(self):
        """Days until target date (negative if overdue)."""
        if not self.target_date:
            return None
        return (self.target_date - timezone.now().date()).days


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


# =============================================================================
# Habit Goals (Measurement-Driven Goal Engine)
# =============================================================================

# Measurement type choices for the Goal Engine
MEASUREMENT_TYPE_CHOICES = [
    ('binary', 'Binary (Yes/No)'),
    ('duration', 'Duration'),
    ('count', 'Count'),
    ('target', 'Target Value'),
]

# Frequency type choices
FREQUENCY_TYPE_CHOICES = [
    ('daily', 'Daily'),
    ('weekly', 'Weekly'),
    ('monthly', 'Monthly'),
]


class HabitGoal(UserOwnedModel):
    """
    Measurement-driven goal with flexible tracking types.

    Supports four measurement types:
    - BINARY: Simple yes/no daily completion (original behavior)
    - DURATION: Timed sessions with minute tracking and timer engine
    - COUNT: Numeric counting (reps, pages, glasses, etc.)
    - TARGET: Running total toward a numeric target

    The visual habit matrix works for all types. The detail page renders
    context-aware UI based on measurement_type (timer, counter, toggle, input).

    See docs/goal_engine_architecture.md for full specification.
    """
    STATUS_CHOICES = [
        ('active', 'Active'),
        ('paused', 'Paused'),
        ('completed', 'Completed'),
        ('abandoned', 'Abandoned'),
    ]

    # Core required fields
    name = models.CharField(
        max_length=200,
        help_text="The goal name/title"
    )
    purpose = models.TextField(
        help_text="Why this goal matters - the deeper meaning"
    )
    start_date = models.DateField(
        help_text="When the goal period begins"
    )
    end_date = models.DateField(
        help_text="When the goal period ends"
    )
    habit_required = models.BooleanField(
        default=True,
        help_text="Whether this goal requires daily habit tracking"
    )

    # ── Measurement Configuration ──
    measurement_type = models.CharField(
        max_length=20,
        choices=MEASUREMENT_TYPE_CHOICES,
        default='binary',
        help_text="How this goal is measured"
    )
    frequency_type = models.CharField(
        max_length=20,
        choices=FREQUENCY_TYPE_CHOICES,
        default='daily',
        help_text="How often this goal should be tracked"
    )
    target_value = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        null=True,
        blank=True,
        help_text="Target per session (minutes for duration, reps for count, etc.)"
    )
    target_unit = models.CharField(
        max_length=50,
        blank=True,
        default='',
        help_text="Unit label for display (e.g., 'minutes', 'pages', 'glasses')"
    )
    sessions_per_week = models.PositiveIntegerField(
        null=True,
        blank=True,
        help_text="Target number of sessions per week"
    )
    category = models.CharField(
        max_length=100,
        blank=True,
        default='',
        help_text="Flexible categorization (e.g., 'reading', 'fitness')"
    )

    # Optional fields
    description = models.TextField(
        blank=True,
        help_text="Additional details about the goal"
    )
    success_criteria = models.TextField(
        blank=True,
        help_text="What does success look like?"
    )
    domain = models.ForeignKey(
        LifeDomain,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='habit_goals',
        help_text="Life area this goal belongs to"
    )
    status = models.CharField(
        max_length=20,
        choices=STATUS_CHOICES,
        default='active'
    )

    # Commitment level — shared concept with Task
    COMMITMENT_LEVEL_CHOICES = [
        ('optional', 'Optional'),
        ('important', 'Important'),
        ('non_negotiable', 'Non-Negotiable'),
    ]
    commitment_level = models.CharField(
        max_length=20,
        choices=COMMITMENT_LEVEL_CHOICES,
        default='important',
        help_text="Non-negotiable habits trigger coaching if missed. "
                  "Used by compensatory reasoning engine.",
    )

    # Link to annual direction
    annual_direction = models.ForeignKey(
        AnnualDirection,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='habit_goals',
        help_text="Link this goal to a year's direction"
    )

    class Meta:
        ordering = ['-start_date', 'name']
        verbose_name = "Habit Goal"
        verbose_name_plural = "Habit Goals"
        indexes = [
            models.Index(fields=['user', 'status'], name='idx_habitgoal_user_status'),
            models.Index(fields=['measurement_type'], name='idx_habitgoal_mtype'),
        ]

    def __str__(self):
        return self.name

    def get_absolute_url(self):
        return reverse('purpose:habit_goal_detail', kwargs={'pk': self.pk})

    def clean(self):
        """Validate goal data."""
        super().clean()

        # Validate date range
        if self.end_date and self.start_date and self.end_date < self.start_date:
            raise ValidationError({
                'end_date': "End date must be on or after start date."
            })

        # Validate purpose for habit goals
        if self.habit_required and not (self.purpose and self.purpose.strip()):
            raise ValidationError({
                'purpose': "Purpose is required for habit-tracking goals."
            })

    def save(self, *args, **kwargs):
        self.full_clean()
        super().save(*args, **kwargs)

    # =========================================================================
    # Habit Matrix Sizing Methods
    # =========================================================================

    @property
    def total_days(self):
        """Calculate total days in the goal period (inclusive)."""
        if not self.start_date or not self.end_date:
            return 0
        return (self.end_date - self.start_date).days + 1

    @property
    def elapsed_days(self):
        """Calculate days elapsed from start to today (opportunities for completion).

        Returns the number of days that have passed where the user could have
        completed the habit. This is used for Success Rate calculation.
        - Before start_date: 0
        - After end_date: same as total_days
        - Otherwise: days from start_date to today (inclusive)
        """
        if not self.start_date or not self.end_date:
            return 0

        today = get_user_today(self.user)

        if today < self.start_date:
            return 0
        if today > self.end_date:
            return self.total_days

        return (today - self.start_date).days + 1

    @property
    def matrix_rows(self):
        """Calculate optimal number of rows for the habit matrix.

        Uses floor(sqrt(total_days)) for a nearly-square layout.
        """
        if self.total_days <= 0:
            return 0
        return math.floor(math.sqrt(self.total_days))

    @property
    def matrix_columns(self):
        """Calculate optimal number of columns for the habit matrix.

        Uses ceil(total_days / rows) to ensure all days fit.
        """
        if self.total_days <= 0 or self.matrix_rows <= 0:
            return 0
        return math.ceil(self.total_days / self.matrix_rows)

    @property
    def total_boxes(self):
        """Total boxes in the matrix grid (rows × columns)."""
        return self.matrix_rows * self.matrix_columns

    @property
    def disabled_boxes(self):
        """Number of disabled boxes (total_boxes - total_days)."""
        return max(0, self.total_boxes - self.total_days)

    def get_matrix_data(self):
        """Generate the complete matrix data for rendering.

        Returns a list of box dictionaries with state information:
        - box_number: Sequential number (1-based)
        - date: The date this box represents (or None if disabled)
        - state: One of 'completed', 'missed', 'today', 'future', 'disabled'
        - day_number: Day number within the goal (1-based)
        """
        if not self.habit_required or self.total_days <= 0:
            return []

        today = get_user_today(self.user)

        # Get all habit entries for this goal
        entries_by_date = {
            entry.date: entry
            for entry in self.habit_entries.all()
        }

        matrix = []

        for box_num in range(1, self.total_boxes + 1):
            if box_num <= self.total_days:
                # This is a valid date box
                day_number = box_num
                box_date = self.start_date + timezone.timedelta(days=box_num - 1)

                # Determine state
                entry = entries_by_date.get(box_date)

                if entry and entry.completed:
                    state = 'completed'
                elif box_date > today:
                    state = 'future'
                elif box_date == today:
                    state = 'today'
                else:
                    # Past date with no completed entry
                    state = 'missed'

                matrix.append({
                    'box_number': box_num,
                    'date': box_date,
                    'state': state,
                    'day_number': day_number,
                    'row': (box_num - 1) // self.matrix_columns,
                    'column': (box_num - 1) % self.matrix_columns,
                })
            else:
                # Disabled box (for grid alignment)
                matrix.append({
                    'box_number': box_num,
                    'date': None,
                    'state': 'disabled',
                    'day_number': None,
                    'row': (box_num - 1) // self.matrix_columns,
                    'column': (box_num - 1) % self.matrix_columns,
                })

        return matrix

    def get_matrix_as_rows(self):
        """Get matrix data organized into rows for template rendering."""
        matrix = self.get_matrix_data()
        if not matrix:
            return []

        rows = []
        for row_num in range(self.matrix_rows):
            row_boxes = [
                box for box in matrix
                if box['row'] == row_num
            ]
            rows.append(row_boxes)

        return rows

    # =========================================================================
    # Statistics Methods
    # =========================================================================

    @property
    def completed_days(self):
        """Count of days marked as completed."""
        return self.habit_entries.filter(completed=True).count()

    @property
    def completion_rate(self):
        """Percentage of completed days based on elapsed days (opportunities).

        Success Rate = (completed_days / elapsed_days) * 100
        For a goal on day 4 with 3 completions, this returns 75%.
        """
        if self.elapsed_days <= 0:
            return 0.0

        return (self.completed_days / self.elapsed_days) * 100

    @property
    def current_streak(self):
        """Calculate current consecutive completion streak.

        Delegates to streak_service for single source of truth.
        Handles daily, weekly, and monthly frequency types.
        """
        from apps.purpose.services.streak_service import get_current_streak
        return get_current_streak(self)

    # =========================================================================
    # Measurement Type Helpers
    # =========================================================================

    @property
    def is_binary(self):
        """Goal uses simple yes/no tracking."""
        return self.measurement_type == 'binary'

    @property
    def is_duration(self):
        """Goal tracks timed sessions in minutes."""
        return self.measurement_type == 'duration'

    @property
    def is_count(self):
        """Goal tracks numeric counts."""
        return self.measurement_type == 'count'

    @property
    def is_target(self):
        """Goal tracks a running total toward a target."""
        return self.measurement_type == 'target'

    @property
    def measurement_icon(self):
        """Return emoji icon for display based on measurement type."""
        icons = {
            'binary': '✓',
            'duration': '⏱',
            'count': '#',
            'target': '🎯',
        }
        return icons.get(self.measurement_type, '✓')

    @property
    def target_unit_display(self):
        """Return unit label, with smart defaults for duration goals."""
        if self.target_unit:
            return self.target_unit
        if self.is_duration:
            return 'minutes'
        return ''

    def get_weekly_session_count(self):
        """Count completed sessions in the current week (Mon-Sun)."""
        today = get_user_today(self.user)
        # Monday of current week
        week_start = today - timezone.timedelta(days=today.weekday())
        return self.habit_entries.filter(
            date__gte=week_start,
            date__lte=today,
            completed=True,
        ).count()

    @property
    def weekly_progress_percent(self):
        """Percentage toward weekly sessions goal (0-100)."""
        if not self.sessions_per_week:
            return 0
        count = self.get_weekly_session_count()
        return min(100, int((count / self.sessions_per_week) * 100))

    @property
    def avg_duration(self):
        """Average duration in minutes across all completed entries (DURATION goals)."""
        if not self.is_duration:
            return None
        from django.db.models import Avg
        result = self.habit_entries.filter(
            completed=True,
            duration_minutes__isnull=False,
        ).aggregate(avg=Avg('duration_minutes'))
        return float(result['avg']) if result['avg'] else 0.0

    @property
    def total_count(self):
        """Sum of all count values (COUNT goals)."""
        if not self.is_count:
            return None
        from django.db.models import Sum
        result = self.habit_entries.filter(
            completed=True,
            count_value__isnull=False,
        ).aggregate(total=Sum('count_value'))
        return float(result['total']) if result['total'] else 0.0

    @property
    def running_total(self):
        """Running total of target values (TARGET goals)."""
        if not self.is_target:
            return None
        from django.db.models import Sum
        result = self.habit_entries.filter(
            target_value__isnull=False,
        ).aggregate(total=Sum('target_value'))
        return float(result['total']) if result['total'] else 0.0


class HabitGoalLink(models.Model):
    """
    Structural attribution: this habit serves these goals.

    Part of the WLJ Architecture Evolution (Phase 1).
    Links a HabitGoal to one or more LifeGoals for attribution purposes.
    Connects the habit *definition* to goals, not the completion record.
    Momentum flows through signals, not directly from this link.
    """
    habit = models.ForeignKey(
        HabitGoal,
        on_delete=models.CASCADE,
        related_name='goal_links',
    )
    goal = models.ForeignKey(
        LifeGoal,
        on_delete=models.CASCADE,
        related_name='habit_links',
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = ['habit', 'goal']
        verbose_name = "Habit-Goal Link"
        verbose_name_plural = "Habit-Goal Links"

    def __str__(self):
        return f"{self.habit.name} → {self.goal.title}"


class GoalSignalSource(models.Model):
    """
    Configures which signal types feed into a goal's momentum calculation
    and with what weight.

    Part of the WLJ Architecture Evolution (Phase 5).
    Auto-populated with domain defaults when a goal is created.
    Can be overridden by the user or by Beth.

    Weights should sum to ~1.0 for a goal, but this is not enforced
    at the database level to allow flexible tuning.
    """
    goal = models.ForeignKey(
        LifeGoal,
        on_delete=models.CASCADE,
        related_name='signal_sources',
    )
    signal_type = models.CharField(
        max_length=30,
        help_text="Signal type from taxonomy (e.g., health_activity, faith_practice)",
    )
    weight = models.FloatField(
        help_text="Relative importance 0.0-1.0. Weights should sum to ~1.0 per goal.",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = ['goal', 'signal_type']
        verbose_name = "Goal Signal Source"
        verbose_name_plural = "Goal Signal Sources"

    def __str__(self):
        return f"{self.goal.title} ← {self.signal_type} (weight={self.weight})"


class HabitEntry(models.Model):
    """
    Goal log entry supporting all measurement types.

    For BINARY goals: one entry per day with completed=True/False (original behavior).
    For DURATION goals: duration_minutes is populated, completed is set when target met.
    For COUNT goals: count_value is populated, completed when target met.
    For TARGET goals: target_value is populated per entry.

    Multiple sessions per day are supported via session_number for non-binary goals.
    """
    goal = models.ForeignKey(
        HabitGoal,
        on_delete=models.CASCADE,
        related_name='habit_entries'
    )
    date = models.DateField(
        help_text="The calendar date for this entry"
    )
    completed = models.BooleanField(
        default=True,
        help_text="Whether the session met the goal target"
    )
    notes = models.TextField(
        blank=True,
        help_text="Optional notes about this session"
    )

    # ── Measurement Data (nullable — only populated for non-binary goals) ──
    duration_minutes = models.DecimalField(
        max_digits=8,
        decimal_places=2,
        null=True,
        blank=True,
        help_text="Duration in minutes (for DURATION goals)"
    )
    count_value = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        null=True,
        blank=True,
        help_text="Count value (for COUNT goals)"
    )
    target_value = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        null=True,
        blank=True,
        help_text="Measured value (for TARGET goals)"
    )

    # Timer metadata
    timer_started_at = models.DateTimeField(
        null=True,
        blank=True,
        help_text="When the timer was started (for DURATION goals)"
    )

    # Session tracking for multiple sessions per day
    session_number = models.PositiveIntegerField(
        default=1,
        help_text="Session number for goals with multiple daily sessions"
    )

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = ['goal', 'date', 'session_number']
        ordering = ['-date', '-session_number']
        verbose_name = "Habit Entry"
        verbose_name_plural = "Habit Entries"
        indexes = [
            models.Index(fields=['goal', 'date'], name='idx_habitentry_goal_date'),
            models.Index(fields=['date', 'completed'], name='idx_habitentry_date_done'),
        ]

    def __str__(self):
        status = "✓" if self.completed else "✗"
        extra = ''
        if self.duration_minutes:
            extra = f' ({self.duration_minutes}m)'
        elif self.count_value:
            extra = f' (×{self.count_value})'
        elif self.target_value:
            extra = f' ({self.target_value})'
        return f"{self.goal.name} - {self.date} [{status}]{extra}"

    def clean(self):
        """Validate habit entry data."""
        super().clean()

        if not self.goal_id:
            return

        # Validate goal has habit tracking enabled
        if not self.goal.habit_required:
            raise ValidationError(
                "This goal does not have habit tracking enabled."
            )

        # Validate date is within goal range
        if self.date < self.goal.start_date:
            raise ValidationError({
                'date': "Date cannot be before goal start date."
            })
        if self.date > self.goal.end_date:
            raise ValidationError({
                'date': "Date cannot be after goal end date."
            })

        # Validate not future date
        today = get_user_today(self.goal.user)
        if self.date > today:
            raise ValidationError({
                'date': "Cannot create habit entries for future dates."
            })

    def save(self, *args, **kwargs):
        # Auto-set completed based on measurement type and target
        if self.goal_id and self.goal.target_value:
            if self.goal.is_duration and self.duration_minutes is not None:
                self.completed = self.duration_minutes >= self.goal.target_value
            elif self.goal.is_count and self.count_value is not None:
                self.completed = self.count_value >= self.goal.target_value
        self.full_clean()
        super().save(*args, **kwargs)

    def get_next_session_number(self):
        """Get the next available session number for this goal+date."""
        last = HabitEntry.objects.filter(
            goal=self.goal,
            date=self.date,
        ).aggregate(max_session=models.Max('session_number'))
        return (last['max_session'] or 0) + 1


# =============================================================================
# Goal Insights (Recommendations & Celebrations)
# =============================================================================

class GoalInsight(models.Model):
    """
    AI-generated or rule-based insight/recommendation for a goal.

    Insights are generated by the RecommendationService and displayed
    on the goal detail page. Users can dismiss or apply suggestions.
    """
    INSIGHT_TYPE_CHOICES = [
        ('encouragement', 'Encouragement'),
        ('warning', 'Warning'),
        ('optimization', 'Optimization'),
        ('milestone', 'Milestone Celebration'),
        ('pattern', 'Pattern Detected'),
    ]

    goal = models.ForeignKey(
        HabitGoal,
        on_delete=models.CASCADE,
        related_name='insights'
    )
    insight_type = models.CharField(
        max_length=20,
        choices=INSIGHT_TYPE_CHOICES
    )
    title = models.CharField(max_length=200)
    message = models.TextField()
    suggestion_data = models.JSONField(
        default=dict,
        blank=True,
        help_text="Structured suggestion data (e.g., {'new_target': 35})"
    )
    is_dismissed = models.BooleanField(default=False)
    is_applied = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']
        verbose_name = "Goal Insight"
        verbose_name_plural = "Goal Insights"

    def __str__(self):
        return f"{self.get_insight_type_display()}: {self.title}"
