# ==============================================================================
# File: apps/faith/models.py
# Project: Whole Life Journey - Django 5.x Personal Wellness/Journaling App
# Description: Faith module models including Scripture, prayers, reading plans,
#              and Bible study tools
# Owner: Danny Jenkins (admin@wholelifejourney.com)
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

from django.db import models
from django.utils import timezone

from apps.core.models import UserOwnedModel


# =============================================================================
# BIBLE TRANSLATION CHOICES
# =============================================================================
# Common choices used across all models that reference Bible translations.
# This list includes major English translations available through Bible APIs.

BIBLE_TRANSLATION_CHOICES = [
    ("ESV", "English Standard Version"),
    ("NIV", "New International Version"),
    ("KJV", "King James Version"),
    ("NKJV", "New King James Version"),
    ("NLT", "New Living Translation"),
    ("NASB", "New American Standard Bible"),
    ("CSB", "Christian Standard Bible"),
    ("BSB", "Berean Standard Bible"),
    ("AMP", "Amplified Bible"),
    ("MSG", "The Message"),
    ("NET", "New English Translation"),
    ("RSV", "Revised Standard Version"),
    ("NRSV", "New Revised Standard Version"),
    ("CEV", "Contemporary English Version"),
    ("GNT", "Good News Translation"),
    ("HCSB", "Holman Christian Standard Bible"),
    ("WEB", "World English Bible"),
    ("YLT", "Young's Literal Translation"),
    ("ASV", "American Standard Version"),
    ("DRA", "Douay-Rheims Bible"),
]


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

    # Source and series grouping
    source = models.CharField(
        max_length=200,
        blank=True,
        help_text="Source of the content (e.g., 'Seymour Heights Christian Church')",
    )
    source_abbreviation = models.CharField(
        max_length=20,
        blank=True,
        help_text="Short form for display (e.g., 'SHCC')",
    )
    series = models.CharField(
        max_length=200,
        blank=True,
        help_text="Series name within the source (e.g., 'Blind Spots')",
    )
    series_order = models.PositiveIntegerField(
        default=0,
        help_text="Order within series (e.g., 1 for Week 1, 2 for Week 2)",
    )

    # Access control for copyrighted content
    allowed_emails = models.JSONField(
        default=list,
        blank=True,
        help_text="List of email addresses allowed to access this plan. Empty = public.",
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
    along with optional reflection prompts. Supports three difficulty
    levels (beginner, intermediate, advanced) with different content
    depth for each level.
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

    # Inline scripture content with red letter support
    # JSON structure: [{"reference": "Matthew 5:1-12", "text": "...", "red_letter_ranges": [[start, end], ...]}]
    # red_letter_ranges are character positions in the text where Jesus is speaking
    scripture_content = models.JSONField(
        default=list,
        blank=True,
        help_text="Inline scripture with text and red letter ranges for Jesus' words",
    )

    # Context summary shown before scripture
    # Who is speaking, who they're speaking to, time frame, what to get from reading
    context_summary = models.TextField(
        blank=True,
        help_text="High-level context: who is speaking, audience, time frame, key takeaway",
    )

    # Difficulty-specific commentary content
    # Beginner: Simple explanations for those new to the Bible
    commentary_beginner = models.TextField(
        blank=True,
        help_text="Simple explanations for those new to Bible study",
    )
    # Intermediate: More depth for regular Bible readers who want explanation
    commentary_intermediate = models.TextField(
        blank=True,
        help_text="Deeper context for those familiar with the Bible but wanting more understanding",
    )
    # Advanced: Scholarly insights, Greek/Hebrew, historical context, cross-references
    commentary_advanced = models.TextField(
        blank=True,
        help_text="Scholarly depth: word studies, historical context, cross-references",
    )

    # Optional devotional content (legacy field, still supported)
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

    def get_commentary_for_level(self, level):
        """Return the appropriate commentary based on difficulty level."""
        if level == "beginner":
            return self.commentary_beginner or self.devotional_text
        elif level == "advanced":
            return self.commentary_advanced or self.devotional_text
        else:  # intermediate is default
            return self.commentary_intermediate or self.devotional_text


class UserReadingPlan(UserOwnedModel):
    """
    User's active or completed reading plan instance.

    When a user starts a reading plan, an instance is created
    to track their progress through the plan.
    """

    PLAN_STATUS_CHOICES = [
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

    # Progress tracking - named plan_status to avoid conflict with SoftDeleteModel.status
    plan_status = models.CharField(
        max_length=20,
        choices=PLAN_STATUS_CHOICES,
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
        self.plan_status = "completed"
        self.completed_at = timezone.now()
        self.save(update_fields=["plan_status", "completed_at", "updated_at"])


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
# READING PLAN ASSESSMENTS
# =============================================================================


class ReadingPlanAssessment(models.Model):
    """
    An interactive assessment embedded within a reading plan day.

    Assessments can have multiple questions with scored responses,
    allowing users to evaluate themselves and see results with
    interpretive feedback.
    """

    plan_day = models.ForeignKey(
        ReadingPlanDay,
        on_delete=models.CASCADE,
        related_name="assessments",
    )
    title = models.CharField(
        max_length=200,
        help_text="e.g., 'Control Freak Assessment'",
    )
    description = models.TextField(
        blank=True,
        help_text="Instructions or context for the assessment",
    )

    # Questions stored as JSON array:
    # [
    #   {"id": 1, "text": "Do you help other people drive?", "min_label": "Never", "max_label": "Always"},
    #   {"id": 2, "text": "Do you over-plan simple activities?", "min_label": "Never", "max_label": "Always"},
    # ]
    questions = models.JSONField(
        default=list,
        help_text="List of questions with id, text, min_label, max_label",
    )

    # Score ranges stored as JSON array:
    # [
    #   {"min": 40, "max": 50, "label": "Control Freak", "description": "You have significant control issues..."},
    #   {"min": 30, "max": 39, "label": "Control Issues", "description": "You have some control tendencies..."},
    # ]
    score_ranges = models.JSONField(
        default=list,
        help_text="Score interpretation ranges with label and description",
    )

    # Scoring configuration
    min_score_per_question = models.PositiveIntegerField(
        default=1,
        help_text="Minimum score value (e.g., 1)",
    )
    max_score_per_question = models.PositiveIntegerField(
        default=5,
        help_text="Maximum score value (e.g., 5)",
    )

    # Reflection-only assessments don't calculate scores
    is_reflection_only = models.BooleanField(
        default=False,
        help_text="If true, just collect answers without scoring",
    )

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["plan_day", "pk"]
        verbose_name = "reading plan assessment"
        verbose_name_plural = "reading plan assessments"

    def __str__(self):
        return f"{self.plan_day} - {self.title}"

    @property
    def max_possible_score(self):
        """Calculate maximum possible score based on questions."""
        return len(self.questions) * self.max_score_per_question

    def get_score_interpretation(self, score):
        """Return the interpretation for a given score."""
        for range_info in self.score_ranges:
            if range_info["min"] <= score <= range_info["max"]:
                return range_info
        return None


class UserAssessmentResponse(UserOwnedModel):
    """
    Stores a user's responses to a reading plan assessment.

    Responses are stored as a JSON object mapping question IDs to scores.
    """

    assessment = models.ForeignKey(
        ReadingPlanAssessment,
        on_delete=models.CASCADE,
        related_name="responses",
    )
    user_plan = models.ForeignKey(
        UserReadingPlan,
        on_delete=models.CASCADE,
        related_name="assessment_responses",
    )

    # Responses stored as JSON: {"1": 3, "2": 5, "3": 2, ...}
    responses = models.JSONField(
        default=dict,
        help_text="Question ID to score mapping",
    )

    # Calculated total score
    total_score = models.PositiveIntegerField(
        default=0,
        help_text="Sum of all response scores",
    )

    completed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-completed_at"]
        unique_together = ["user", "assessment", "user_plan"]
        verbose_name = "assessment response"
        verbose_name_plural = "assessment responses"

    def __str__(self):
        return f"{self.user.email}: {self.assessment.title} - Score: {self.total_score}"

    def _parse_response_value(self, value):
        """
        Parse a response value to an integer score.
        Handles: integers, numeric strings, True/False, and text choices.
        """
        # Already an int
        if isinstance(value, int):
            return value

        # Try parsing as integer string
        if isinstance(value, str):
            # Handle True/False strings (from radio buttons)
            if value.lower() == 'true':
                return 1
            elif value.lower() == 'false':
                return 0

            # Try numeric conversion
            try:
                return int(value)
            except ValueError:
                pass

            # Non-numeric text responses (like "Leave it", "Confront them")
            # These are choice-based questions - score is 0 (or could look up from options)
            return 0

        return 0

    def calculate_score(self):
        """Calculate and save the total score from responses."""
        self.total_score = sum(self._parse_response_value(v) for v in self.responses.values())
        return self.total_score

    def save(self, *args, **kwargs):
        # Auto-calculate score on save
        if self.responses:
            self.total_score = sum(self._parse_response_value(v) for v in self.responses.values())
        super().save(*args, **kwargs)

    @property
    def interpretation(self):
        """Get score interpretation from the assessment."""
        return self.assessment.get_score_interpretation(self.total_score)


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
        choices=BIBLE_TRANSLATION_CHOICES,
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
        choices=BIBLE_TRANSLATION_CHOICES,
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
        choices=BIBLE_TRANSLATION_CHOICES,
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