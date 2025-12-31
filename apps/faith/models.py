"""
Faith Models - Scripture verses and faith-specific content.

The Faith module provides:
- Curated Scripture verses with themes and contexts
- Daily verse selection
- Faith-specific journal prompts (via Journal app)
- Prayer request tracking
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