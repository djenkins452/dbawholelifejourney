# ==============================================================================
# File: apps/faith/models.py
# Project: Whole Life Journey - Django 5.x Personal Wellness/Journaling App
# Description: Faith module models including Scripture, prayers, reading plans,
#              and Bible study tools
# Owner: Danny Jenkins (dannyjenkins71@gmail.com)
# Created: 2024-01-01
# Last Updated: 2026-01-01
# ==============================================================================
"""
Faith Models - Scripture verses and faith-specific content.

The Faith module provides:
- Curated Scripture verses with themes and contexts
- Daily verse selection
- Faith-specific journal prompts (via Journal app)
- Prayer request tracking
- Bible reading plans with progress tracking
- Bible study tools (highlights, bookmarks, notes)
"""

from django.conf import settings
from django.db import models
from django.utils import timezone

from apps.core.models import UserOwnedModel


class ScriptureVerse(models.Model):
    """
    Curated Scripture verses for daily encouragement and prompts.
    
    Verses are tagged with themes and contexts to allow
    intelligent selection based on user's situation or mood.
    """

    TRANSLATION_CHOICES = [
        ("ESV", "English Standard Version"),
        ("NIV", "New International Version"),
        ("BSB", "Berean Standard Bible"),
        ("NKJV", "New King James Version"),
        ("NLT", "New Living Translation"),
    ]

    reference = models.CharField(
        max_length=100,
        help_text="e.g., 'Philippians 4:6-7'",
    )
    text = models.TextField()
    translation = models.CharField(
        max_length=10,
        choices=TRANSLATION_CHOICES,
        default="ESV",
    )
    
    # Book details for ordering
    book_name = models.CharField(max_length=50)
    book_order = models.PositiveIntegerField(
        help_text="Order in the Bible (Genesis=1, Revelation=66)",
    )
    chapter = models.PositiveIntegerField()
    verse_start = models.PositiveIntegerField()
    verse_end = models.PositiveIntegerField(null=True, blank=True)
    
    # Categorization for intelligent selection
    themes = models.JSONField(
        default=list,
        help_text="Themes like 'peace', 'trust', 'strength', 'comfort', 'guidance'",
    )
    contexts = models.JSONField(
        default=list,
        help_text="Contexts like 'anxiety', 'grief', 'gratitude', 'morning', 'evening'",
    )
    
    # Usage tracking
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["book_order", "chapter", "verse_start"]
        verbose_name = "scripture verse"
        verbose_name_plural = "scripture verses"

    def __str__(self):
        return f"{self.reference} ({self.translation})"


class DailyVerse(models.Model):
    """
    Daily verse assignments.
    
    Each day can have a specific verse assigned for all users,
    or the system can select randomly from curated verses.
    """

    date = models.DateField(unique=True)
    verse = models.ForeignKey(
        ScriptureVerse,
        on_delete=models.CASCADE,
        related_name="daily_assignments",
    )
    theme = models.CharField(
        max_length=50,
        blank=True,
        help_text="Optional theme for the day",
    )
    reflection_prompt = models.TextField(
        blank=True,
        help_text="Optional reflection question for this verse",
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-date"]
        verbose_name = "daily verse"
        verbose_name_plural = "daily verses"

    def __str__(self):
        return f"{self.date}: {self.verse.reference}"


class PrayerRequest(UserOwnedModel):
    """
    Prayer request tracking.
    
    Users can log prayer requests and mark them as answered.
    This provides a way to remember and reflect on God's faithfulness.
    """

    PRIORITY_CHOICES = [
        ("normal", "Normal"),
        ("urgent", "Urgent"),
    ]

    title = models.CharField(max_length=200)
    description = models.TextField(blank=True)
    
    # Prayer categories
    is_personal = models.BooleanField(
        default=True,
        help_text="Personal prayer vs. praying for others",
    )
    person_or_situation = models.CharField(
        max_length=200,
        blank=True,
        help_text="Who or what you're praying for",
    )
    
    priority = models.CharField(
        max_length=10,
        choices=PRIORITY_CHOICES,
        default="normal",
    )
    
    # Answered prayer tracking
    is_answered = models.BooleanField(default=False)
    answered_at = models.DateTimeField(null=True, blank=True)
    answer_notes = models.TextField(
        blank=True,
        help_text="How God answered this prayer",
    )
    
    # Reminders
    remind_daily = models.BooleanField(
        default=False,
        help_text="Include in daily prayer reminders",
    )

    class Meta:
        ordering = ["-created_at"]
        verbose_name = "prayer request"
        verbose_name_plural = "prayer requests"

    def __str__(self):
        return self.title

    def mark_answered(self, notes=""):
        """Mark this prayer as answered."""
        self.is_answered = True
        self.answered_at = timezone.now()
        self.answer_notes = notes
        self.save(update_fields=["is_answered", "answered_at", "answer_notes", "updated_at"])


class SavedVerse(UserOwnedModel):
    """
    User's personal saved Scripture verses.

    Each user has their own collection of saved verses that they've
    looked up and saved from the Bible API. This ensures saved verses
    are private to each user.
    """

    TRANSLATION_CHOICES = [
        ("ESV", "English Standard Version"),
        ("NIV", "New International Version"),
        ("BSB", "Berean Standard Bible"),
        ("NKJV", "New King James Version"),
        ("NLT", "New Living Translation"),
        ("KJV", "King James Version"),
    ]

    reference = models.CharField(
        max_length=100,
        help_text="e.g., 'Philippians 4:6-7'",
    )
    text = models.TextField()
    translation = models.CharField(
        max_length=10,
        choices=TRANSLATION_CHOICES,
        default="ESV",
    )

    # Book details for ordering
    book_name = models.CharField(max_length=50)
    book_order = models.PositiveIntegerField(
        help_text="Order in the Bible (Genesis=1, Revelation=66)",
    )
    chapter = models.PositiveIntegerField()
    verse_start = models.PositiveIntegerField()
    verse_end = models.PositiveIntegerField(null=True, blank=True)

    # Personal categorization
    themes = models.JSONField(
        default=list,
        help_text="Personal themes like 'peace', 'trust', 'strength'",
    )
    notes = models.TextField(
        blank=True,
        help_text="Personal notes about this verse",
    )

    # Memory Verse tracking
    is_memory_verse = models.BooleanField(
        default=False,
        help_text="Mark this verse as a memory verse to display on the dashboard",
    )

    class Meta:
        ordering = ["book_order", "chapter", "verse_start"]
        verbose_name = "saved verse"
        verbose_name_plural = "saved verses"

    def __str__(self):
        return f"{self.reference} ({self.translation})"


class FaithMilestone(UserOwnedModel):
    """
    Significant moments in the user's faith journey.

    These could be:
    - Salvation date
    - Baptism
    - Meaningful encounters with God
    - Spiritual breakthroughs
    """

    MILESTONE_TYPES = [
        ("salvation", "Accepted Christ"),
        ("baptism", "Baptism"),
        ("rededication", "Rededication"),
        ("answered_prayer", "Answered Prayer"),
        ("spiritual_insight", "Spiritual Insight"),
        ("community", "Church/Community Moment"),
        ("other", "Other"),
    ]

    title = models.CharField(max_length=200)
    milestone_type = models.CharField(
        max_length=20,
        choices=MILESTONE_TYPES,
        default="other",
    )
    date = models.DateField()
    description = models.TextField(blank=True)
    scripture_reference = models.CharField(
        max_length=100,
        blank=True,
        help_text="A verse connected to this milestone",
    )

    class Meta:
        ordering = ["-date"]
        verbose_name = "faith milestone"
        verbose_name_plural = "faith milestones"

    def __str__(self):
        return f"{self.title} ({self.date})"


# =============================================================================
# BIBLE READING PLANS
# =============================================================================


class ReadingPlanTemplate(models.Model):
    """
    System-wide reading plan templates (e.g., Forgiveness, Prayer, Stress).

    These templates define the structure of a reading plan including
    the Scripture readings and their order. Users can start a plan
    based on these templates.
    """

    CATEGORY_CHOICES = [
        ("topical", "Topical Study"),
        ("book", "Book Study"),
        ("chronological", "Chronological"),
        ("devotional", "Devotional"),
    ]

    DIFFICULTY_CHOICES = [
        ("beginner", "Beginner"),
        ("intermediate", "Intermediate"),
        ("advanced", "Advanced"),
    ]

    title = models.CharField(max_length=200)
    slug = models.SlugField(unique=True)
    description = models.TextField()
    category = models.CharField(
        max_length=20,
        choices=CATEGORY_CHOICES,
        default="topical",
    )
    difficulty = models.CharField(
        max_length=20,
        choices=DIFFICULTY_CHOICES,
        default="beginner",
    )

    # Plan metadata
    duration_days = models.PositiveIntegerField(
        help_text="Total days to complete the plan",
    )
    image_url = models.URLField(
        blank=True,
        help_text="Optional cover image URL for the plan",
    )
    topics = models.JSONField(
        default=list,
        help_text="Topics covered: forgiveness, prayer, stress, marriage, etc.",
    )

    # Status
    is_active = models.BooleanField(default=True)
    is_featured = models.BooleanField(
        default=False,
        help_text="Show prominently on reading plans page",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-is_featured", "title"]
        verbose_name = "reading plan template"
        verbose_name_plural = "reading plan templates"

    def __str__(self):
        return self.title


class ReadingPlanDay(models.Model):
    """
    A single day's readings within a reading plan template.

    Each day can have multiple Scripture passages to read,
    along with optional reflection prompts.
    """

    plan = models.ForeignKey(
        ReadingPlanTemplate,
        on_delete=models.CASCADE,
        related_name="days",
    )
    day_number = models.PositiveIntegerField(
        help_text="Which day in the plan (1, 2, 3...)",
    )
    title = models.CharField(
        max_length=200,
        blank=True,
        help_text="Optional title for this day's reading",
    )

    # Scripture references (stored as JSON list for flexibility)
    # e.g., ["Matthew 6:5-15", "Luke 11:1-4"]
    scripture_references = models.JSONField(
        default=list,
        help_text="List of Scripture references for this day",
    )

    # Optional devotional content
    reflection_prompt = models.TextField(
        blank=True,
        help_text="Reflection question or prompt for this day",
    )
    devotional_text = models.TextField(
        blank=True,
        help_text="Optional devotional/commentary text",
    )

    class Meta:
        ordering = ["plan", "day_number"]
        unique_together = ["plan", "day_number"]
        verbose_name = "reading plan day"
        verbose_name_plural = "reading plan days"

    def __str__(self):
        return f"{self.plan.title} - Day {self.day_number}"


class UserReadingPlan(UserOwnedModel):
    """
    User's active or completed reading plan instance.

    When a user starts a reading plan, an instance is created
    to track their progress through the plan.
    """

    STATUS_CHOICES = [
        ("active", "In Progress"),
        ("completed", "Completed"),
        ("paused", "Paused"),
        ("abandoned", "Abandoned"),
    ]

    template = models.ForeignKey(
        ReadingPlanTemplate,
        on_delete=models.PROTECT,
        related_name="user_plans",
    )

    # Progress tracking
    status = models.CharField(
        max_length=20,
        choices=STATUS_CHOICES,
        default="active",
    )
    started_at = models.DateTimeField(default=timezone.now)
    completed_at = models.DateTimeField(null=True, blank=True)

    # Current position
    current_day = models.PositiveIntegerField(default=1)

    # Scheduling preferences
    reminder_time = models.TimeField(
        null=True,
        blank=True,
        help_text="Daily reminder time for this plan",
    )

    class Meta:
        ordering = ["-started_at"]
        verbose_name = "user reading plan"
        verbose_name_plural = "user reading plans"

    def __str__(self):
        return f"{self.user.email}: {self.template.title}"

    @property
    def progress_percentage(self):
        """Calculate completion percentage."""
        total_days = self.template.duration_days
        if total_days == 0:
            return 100
        completed = self.day_completions.filter(is_completed=True).count()
        return int((completed / total_days) * 100)

    @property
    def days_completed(self):
        """Number of days marked as complete."""
        return self.day_completions.filter(is_completed=True).count()

    @property
    def is_complete(self):
        """Check if the entire plan is complete."""
        return self.days_completed >= self.template.duration_days

    def mark_complete(self):
        """Mark the plan as completed."""
        self.status = "completed"
        self.completed_at = timezone.now()
        self.save(update_fields=["status", "completed_at", "updated_at"])


class UserReadingProgress(UserOwnedModel):
    """
    Track which days of a reading plan the user has completed.
    """

    user_plan = models.ForeignKey(
        UserReadingPlan,
        on_delete=models.CASCADE,
        related_name="day_completions",
    )
    plan_day = models.ForeignKey(
        ReadingPlanDay,
        on_delete=models.CASCADE,
        related_name="completions",
    )

    # Completion tracking
    is_completed = models.BooleanField(default=False)
    completed_at = models.DateTimeField(null=True, blank=True)

    # User reflection/notes for this day
    notes = models.TextField(
        blank=True,
        help_text="Personal notes or reflections for this day's reading",
    )

    class Meta:
        ordering = ["user_plan", "plan_day__day_number"]
        unique_together = ["user_plan", "plan_day"]
        verbose_name = "reading progress"
        verbose_name_plural = "reading progress entries"

    def __str__(self):
        status = "Complete" if self.is_completed else "Pending"
        return f"{self.user_plan.template.title} Day {self.plan_day.day_number}: {status}"

    def mark_complete(self):
        """Mark this day as completed."""
        self.is_completed = True
        self.completed_at = timezone.now()
        self.save(update_fields=["is_completed", "completed_at", "updated_at"])

        # Update current day on parent plan
        plan = self.user_plan
        if self.plan_day.day_number >= plan.current_day:
            plan.current_day = self.plan_day.day_number + 1
            plan.save(update_fields=["current_day", "updated_at"])

        # Check if plan is complete
        if plan.is_complete:
            plan.mark_complete()


# =============================================================================
# BIBLE STUDY TOOLS - Highlights, Bookmarks, Notes
# =============================================================================


class BibleHighlight(UserOwnedModel):
    """
    Highlighted passages within the Bible.

    Users can highlight verses while reading and categorize
    them with different colors.
    """

    COLOR_CHOICES = [
        ("yellow", "Yellow"),
        ("green", "Green"),
        ("blue", "Blue"),
        ("pink", "Pink"),
        ("purple", "Purple"),
        ("orange", "Orange"),
    ]

    # Scripture location
    reference = models.CharField(
        max_length=100,
        help_text="e.g., 'John 3:16' or 'Romans 8:28-30'",
    )
    text = models.TextField(
        help_text="The highlighted text content",
    )
    translation = models.CharField(
        max_length=10,
        default="ESV",
    )

    # Book details for ordering and filtering
    book_name = models.CharField(max_length=50)
    book_order = models.PositiveIntegerField(
        help_text="Order in the Bible (Genesis=1, Revelation=66)",
    )
    chapter = models.PositiveIntegerField()
    verse_start = models.PositiveIntegerField()
    verse_end = models.PositiveIntegerField(null=True, blank=True)

    # Highlight properties
    color = models.CharField(
        max_length=20,
        choices=COLOR_CHOICES,
        default="yellow",
    )

    class Meta:
        ordering = ["book_order", "chapter", "verse_start"]
        verbose_name = "Bible highlight"
        verbose_name_plural = "Bible highlights"

    def __str__(self):
        return f"{self.reference} ({self.color})"


class BibleBookmark(UserOwnedModel):
    """
    Bookmarked locations in the Bible.

    Users can bookmark specific chapters or verses to easily
    return to them later.
    """

    # Scripture location
    reference = models.CharField(
        max_length=100,
        help_text="e.g., 'John 3' or 'Romans 8:28'",
    )
    translation = models.CharField(
        max_length=10,
        default="ESV",
    )

    # Book details for ordering
    book_name = models.CharField(max_length=50)
    book_order = models.PositiveIntegerField(
        help_text="Order in the Bible (Genesis=1, Revelation=66)",
    )
    chapter = models.PositiveIntegerField()
    verse = models.PositiveIntegerField(
        null=True,
        blank=True,
        help_text="Optional: specific verse within chapter",
    )

    # Bookmark metadata
    title = models.CharField(
        max_length=200,
        blank=True,
        help_text="Optional label for this bookmark",
    )
    notes = models.TextField(
        blank=True,
        help_text="Why you bookmarked this passage",
    )

    class Meta:
        ordering = ["-created_at"]
        verbose_name = "Bible bookmark"
        verbose_name_plural = "Bible bookmarks"

    def __str__(self):
        if self.title:
            return f"{self.title}: {self.reference}"
        return self.reference


class BibleStudyNote(UserOwnedModel):
    """
    Study notes attached to specific Scripture passages.

    These are longer-form notes for Bible study, different
    from the brief notes on SavedVerse.
    """

    # Scripture location
    reference = models.CharField(
        max_length=100,
        help_text="e.g., 'John 3:16-21'",
    )
    translation = models.CharField(
        max_length=10,
        default="ESV",
    )

    # Book details for ordering
    book_name = models.CharField(max_length=50)
    book_order = models.PositiveIntegerField(
        help_text="Order in the Bible (Genesis=1, Revelation=66)",
    )
    chapter = models.PositiveIntegerField()
    verse_start = models.PositiveIntegerField()
    verse_end = models.PositiveIntegerField(null=True, blank=True)

    # The study note itself
    title = models.CharField(
        max_length=200,
        blank=True,
        help_text="Optional title for this note",
    )
    content = models.TextField(
        help_text="Your study notes",
    )

    # Optional categorization
    tags = models.JSONField(
        default=list,
        help_text="Tags for organizing notes: theology, application, context, etc.",
    )

    class Meta:
        ordering = ["-created_at"]
        verbose_name = "Bible study note"
        verbose_name_plural = "Bible study notes"

    def __str__(self):
        if self.title:
            return f"{self.title}: {self.reference}"
        return f"Note on {self.reference}"