# ==============================================================================
# File: apps/purpose/models.py
# Project: Whole Life Journey - Django 5.x Personal Wellness/Journaling App
# Description: Purpose module models including life goals, habit goals, and reflections
# Owner: Danny Jenkins (dannyjenkins71@gmail.com)
# Created: 2024-01-01
# Last Updated: 2026-01-02
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
from django.conf import settings
from django.core.exceptions import ValidationError
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


# =============================================================================
# Habit Goals (Short-term with Daily Tracking)
# =============================================================================

class HabitGoal(UserOwnedModel):
    """
    Short-term habit goals with daily tracking and visual matrix display.

    Unlike LifeGoal (12-36 month direction), HabitGoal is for focused daily execution
    over a defined period with visual progress tracking via a habit matrix.

    See docs/wlj_goals_habit_rules.md for full specification.
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

        today = timezone.now().date()

        # Get all habit entries for this goal
        entries_by_date = {
            entry.date: entry
            for entry in self.habit_entries.all()
        }

        matrix = []
        current_date = self.start_date

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
        """Percentage of completed days (up to today)."""
        today = timezone.now().date()

        # Only count days up to today (not future days)
        end = min(self.end_date, today)
        if end < self.start_date:
            return 0.0

        trackable_days = (end - self.start_date).days + 1
        if trackable_days <= 0:
            return 0.0

        return (self.completed_days / trackable_days) * 100

    @property
    def current_streak(self):
        """Calculate current consecutive completion streak."""
        today = timezone.now().date()

        # Get completed entries ordered by date descending
        completed_dates = set(
            self.habit_entries.filter(completed=True)
            .values_list('date', flat=True)
        )

        if not completed_dates:
            return 0

        # Start from today or end_date (whichever is earlier)
        check_date = min(today, self.end_date)
        streak = 0

        while check_date >= self.start_date:
            if check_date in completed_dates:
                streak += 1
                check_date -= timezone.timedelta(days=1)
            elif check_date > today:
                # Skip future dates
                check_date -= timezone.timedelta(days=1)
            else:
                break

        return streak


class HabitEntry(models.Model):
    """
    Daily habit completion entry for a HabitGoal.

    One entry per goal per calendar day.
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
        help_text="Whether the habit was completed"
    )
    notes = models.TextField(
        blank=True,
        help_text="Optional notes about this day"
    )

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = ['goal', 'date']
        ordering = ['-date']
        verbose_name = "Habit Entry"
        verbose_name_plural = "Habit Entries"

    def __str__(self):
        status = "✓" if self.completed else "✗"
        return f"{self.goal.name} - {self.date} [{status}]"

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
        today = timezone.now().date()
        if self.date > today:
            raise ValidationError({
                'date': "Cannot create habit entries for future dates."
            })

    def save(self, *args, **kwargs):
        self.full_clean()
        super().save(*args, **kwargs)
