"""
Whole Life Journey - Journal Models

Project: Whole Life Journey
Path: apps/journal/models.py
Purpose: Core data models for journal entries and writing prompts

Description:
    Defines the JournalEntry model for user reflections and the
    JournalPrompt model for curated writing inspiration. Entries
    support categories, tags, mood tracking, and soft delete.

Key Models:
    - JournalPrompt: Curated prompts with optional Scripture references
    - JournalEntry: User journal entries with categories, tags, and mood

Design Notes:
    - JournalEntry extends UserOwnedModel for soft delete and ownership
    - Entries can have multiple categories and custom tags
    - Mood is optional and uses predefined choices with emoji
    - Prompts can be targeted to Faith-enabled users

Copyright:
    (c) Whole Life Journey. All rights reserved.
    This code is proprietary and may not be copied, modified, or distributed
    without explicit permission.
"""

from django.db import models
from django.urls import reverse
from django.utils import timezone

from apps.core.models import Category, Tag, UserOwnedModel


class Emotion(models.Model):
    """
    Predefined emotions for journal entries with emoji representation.

    Users can select multiple emotions per entry. System-wide, not user-specific.
    """

    name = models.CharField(max_length=50, unique=True)
    slug = models.SlugField(max_length=50, unique=True)
    emoji = models.CharField(max_length=10, help_text="Emoji representation")
    description = models.CharField(max_length=200, blank=True)
    order = models.PositiveIntegerField(default=0)
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ["order", "name"]

    def __str__(self):
        return f"{self.emoji} {self.name}"


class JournalPrompt(models.Model):
    """
    Curated prompts to inspire journal entries.
    
    Prompts can be general or category-specific.
    Faith-specific prompts may include Scripture.
    """

    text = models.TextField()
    category = models.ForeignKey(
        Category,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="prompts",
    )

    # Faith-specific prompts
    is_faith_specific = models.BooleanField(
        default=False,
        help_text="Only show when Faith module is enabled",
    )
    scripture_reference = models.CharField(max_length=100, blank=True)
    scripture_text = models.TextField(blank=True)

    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["category", "-created_at"]

    def __str__(self):
        preview = self.text[:50]
        return f"{preview}..."


class JournalEntry(UserOwnedModel):
    """
    A journal entry - the core content model.
    
    Entries belong to a user and can be:
    - Tagged with multiple categories
    - Associated with custom tags
    - Linked to other entries (cross-module)
    - Archived or deleted
    """

    MOOD_CHOICES = [
        ("great", "Great"),
        ("good", "Good"),
        ("okay", "Okay"),
        ("low", "Low"),
        ("difficult", "Difficult"),
    ]

    # Core content
    title = models.CharField(max_length=200)
    body = models.TextField()

    # The date this entry is "about" (may differ from created_at)
    entry_date = models.DateField(default=timezone.now)

    # Optional mood tracking (lightweight)
    mood = models.CharField(
        max_length=20,
        choices=MOOD_CHOICES,
        blank=True,
    )

    # Categories (multi-select)
    categories = models.ManyToManyField(
        Category,
        blank=True,
        related_name="journal_entries",
    )

    # User-defined tags
    tags = models.ManyToManyField(
        Tag,
        blank=True,
        related_name="journal_entries",
    )

    # Emotions (multi-select)
    emotions = models.ManyToManyField(
        Emotion,
        blank=True,
        related_name="journal_entries",
        help_text="How you're feeling (select multiple)",
    )

    # Prompt that inspired this entry (optional)
    prompt = models.ForeignKey(
        JournalPrompt,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="entries",
    )

    # Word count (computed on save)
    word_count = models.PositiveIntegerField(default=0)

    class Meta:
        ordering = ["-entry_date", "-created_at"]
        verbose_name = "journal entry"
        verbose_name_plural = "journal entries"

    def __str__(self):
        return f"{self.title} ({self.entry_date})"

    def save(self, *args, **kwargs):
        # Compute word count
        if self.body:
            self.word_count = len(self.body.split())

        # Set default title if not provided
        if not self.title:
            self.title = self.entry_date.strftime("%A, %B %d, %Y")

        super().save(*args, **kwargs)

    def get_absolute_url(self):
        return reverse("journal:entry_detail", kwargs={"pk": self.pk})

    @property
    def body_preview(self):
        """Return first 150 characters of body for list views."""
        if len(self.body) <= 150:
            return self.body
        return self.body[:150].rsplit(" ", 1)[0] + "..."

    @property
    def mood_emoji(self):
        """Return an emoji representation of mood."""
        mood_emojis = {
            "great": "😊",
            "good": "🙂",
            "okay": "😐",
            "low": "😔",
            "difficult": "😢",
        }
        return mood_emojis.get(self.mood, "")

    @property
    def emotions_display(self):
        """Return a string of all selected emotion emojis."""
        return " ".join(e.emoji for e in self.emotions.all())


class JournalSignal(models.Model):
    """
    NLP-extracted behavioral signal from a journal entry.

    Stores signals extracted via OpenAI from journal text, feeding
    inferred_behavior signals into the signal persistence layer.

    Part of the WLJ Architecture Evolution — Phase 7 (Journal NLP Integration).
    """

    entry = models.ForeignKey(
        JournalEntry,
        on_delete=models.CASCADE,
        related_name='signals',
    )
    signal_type = models.CharField(
        max_length=30,
        help_text='Signal taxonomy type (e.g., health_activity, faith_practice)',
    )
    domain = models.CharField(
        max_length=20,
        help_text='LifeDomain slug (e.g., health, faith, mind)',
    )
    confidence = models.FloatField(
        help_text='Extraction confidence 0.0-1.0',
    )
    extracted_text = models.TextField(
        help_text='The exact phrase from the journal that indicates this behavior',
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        indexes = [
            models.Index(fields=['entry', 'signal_type']),
        ]
        ordering = ['-created_at']

    def __str__(self):
        return f"JournalSignal({self.signal_type}, {self.confidence:.2f}) for entry {self.entry_id}"


class EntryLink(models.Model):
    """
    Link between entries (cross-module connections).
    
    Allows journal entries to reference other entries,
    such as linking a reflection to a fasting window.
    """

    LINK_TYPE_CHOICES = [
        ("related", "Related"),
        ("inspired_by", "Inspired By"),
        ("during", "During"),
        ("reflection_on", "Reflection On"),
    ]

    source = models.ForeignKey(
        JournalEntry,
        on_delete=models.CASCADE,
        related_name="outgoing_links",
    )
    target_type = models.CharField(
        max_length=50,
        help_text="The model type of the target (e.g., 'journal.JournalEntry', 'health.FastingWindow')",
    )
    target_id = models.PositiveIntegerField()
    link_type = models.CharField(
        max_length=20,
        choices=LINK_TYPE_CHOICES,
        default="related",
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]
        unique_together = ["source", "target_type", "target_id"]

    def __str__(self):
        return f"{self.source} -> {self.target_type}:{self.target_id}"
