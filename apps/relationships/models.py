"""
Whole Life Journey - Relationship Intelligence Models

Project: Whole Life Journey
Path: apps/relationships/models.py
Purpose: Canonical Person model and cross-platform interaction tracking

Description:
    Platform infrastructure for relational intelligence. Person is the
    canonical contact model, referenceable from any module via @mentions,
    GenericForeignKey interactions, and direct associations.

Models:
    - Person: A contact in the user's life (canonical, owner-scoped)
    - RelationshipInteraction: Cross-module interaction record (GenericFK)
    - Mention: @mention linkage from any content object to a Person

Copyright:
    (c) Whole Life Journey. All rights reserved.
"""

from django.conf import settings
from django.contrib.contenttypes.fields import GenericForeignKey
from django.contrib.contenttypes.models import ContentType
from django.db import models

from apps.core.models import SoftDeleteManager, SoftDeleteModel, TimeStampedModel


# =============================================================================
# PERSON — Canonical Contact Model
# =============================================================================


class Person(SoftDeleteModel):
    """
    A person in the user's life.

    This is the canonical contact model for the entire platform.
    Contacts are user-scoped (private by default), with optional
    household sharing. Referenced by Mentions and RelationshipInteractions
    across all modules.
    """

    RELATIONSHIP_TYPE_CHOICES = [
        ('spouse', 'Spouse'),
        ('family', 'Family'),
        ('friend', 'Friend'),
        ('coworker', 'Coworker'),
        ('church', 'Church'),
        ('mentor', 'Mentor'),
        ('other', 'Other'),
    ]

    owner = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='contacts',
        help_text="User who owns this contact",
    )

    first_name = models.CharField(
        max_length=100,
        help_text="First name",
    )
    last_name = models.CharField(
        max_length=100,
        blank=True,
        help_text="Last name (optional)",
    )
    display_name = models.CharField(
        max_length=200,
        blank=True,
        help_text="How the user refers to this person (auto-generated if blank)",
    )
    email = models.EmailField(
        blank=True,
        null=True,
        help_text="Email address (optional)",
    )
    phone = models.CharField(
        max_length=20,
        blank=True,
        null=True,
        help_text="Phone number (optional)",
    )
    relationship_type = models.CharField(
        max_length=20,
        choices=RELATIONSHIP_TYPE_CHOICES,
        default='other',
    )
    notes = models.TextField(
        blank=True,
        help_text="Private notes about this person",
    )

    # Optional household link for shared contacts
    household = models.ForeignKey(
        'meals.Household',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='shared_contacts',
        help_text="Link to household for shared visibility",
    )

    # Interaction metadata (denormalized for fast queries)
    last_interaction_date = models.DateField(
        null=True,
        blank=True,
        help_text="Date of most recent interaction (auto-updated)",
    )
    interaction_count = models.PositiveIntegerField(
        default=0,
        help_text="Total interaction count (auto-updated)",
    )

    objects = SoftDeleteManager()
    all_objects = models.Manager()

    class Meta:
        ordering = ['first_name', 'last_name']
        verbose_name = "Person"
        verbose_name_plural = "People"
        indexes = [
            models.Index(fields=['owner', 'status']),
            models.Index(fields=['owner', 'first_name', 'last_name']),
            models.Index(fields=['owner', 'last_interaction_date']),
            models.Index(fields=['household']),
        ]
        constraints = [
            models.UniqueConstraint(
                fields=['owner', 'first_name', 'last_name'],
                condition=models.Q(status='active'),
                name='unique_active_person_per_owner',
            ),
        ]

    def __str__(self):
        return f"{self.get_display_name()} ({self.relationship_type})"

    def save(self, *args, **kwargs):
        if not self.display_name:
            self.display_name = self.get_display_name()
        super().save(*args, **kwargs)

    def get_display_name(self):
        """Generate display name from first + last name."""
        if self.last_name:
            return f"{self.first_name} {self.last_name}"
        return self.first_name

    @property
    def full_name(self):
        return self.get_display_name()


# =============================================================================
# RELATIONSHIP INTERACTION — Cross-Module Interaction Tracking
# =============================================================================


class RelationshipInteraction(TimeStampedModel):
    """
    Records an interaction with a Person from any module.

    Uses Django GenericForeignKey to link to the source object
    (JournalEntry, Task, MealPlan, PrayerRequest, LifeEvent, etc.).
    """

    CONTEXT_TYPE_CHOICES = [
        ('journal', 'Journal'),
        ('task', 'Task'),
        ('meal', 'Meal'),
        ('prayer', 'Prayer'),
        ('event', 'Event'),
        ('chat', 'Chat'),
        ('manual', 'Manual'),
        ('other', 'Other'),
    ]

    person = models.ForeignKey(
        Person,
        on_delete=models.CASCADE,
        related_name='interactions',
    )
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='relationship_interactions',
    )
    context_type_label = models.CharField(
        max_length=20,
        choices=CONTEXT_TYPE_CHOICES,
        help_text="Human-readable context category",
    )
    interaction_date = models.DateField(
        help_text="Date of the interaction",
    )

    # GenericForeignKey to source object
    content_type = models.ForeignKey(
        ContentType,
        on_delete=models.CASCADE,
        null=True,
        blank=True,
    )
    object_id = models.PositiveIntegerField(null=True, blank=True)
    source_object = GenericForeignKey('content_type', 'object_id')

    class Meta:
        ordering = ['-interaction_date', '-created_at']
        verbose_name = "Relationship Interaction"
        verbose_name_plural = "Relationship Interactions"
        indexes = [
            models.Index(fields=['user', 'person', 'interaction_date']),
            models.Index(fields=['user', 'context_type_label']),
            models.Index(fields=['content_type', 'object_id']),
            models.Index(fields=['interaction_date']),
        ]

    def __str__(self):
        return (
            f"{self.context_type_label} interaction with "
            f"{self.person.get_display_name()} on {self.interaction_date}"
        )


# =============================================================================
# MENTION — @Mention Linkage
# =============================================================================


class Mention(TimeStampedModel):
    """
    Records an @mention of a Person in any content object.

    Created by MentionParserService when "@Name" is detected in text fields.
    Links via GenericForeignKey to the source object (JournalEntry, Task, etc.).
    """

    person = models.ForeignKey(
        Person,
        on_delete=models.CASCADE,
        related_name='mentions',
    )

    # GenericForeignKey to the content object containing the mention
    content_type = models.ForeignKey(
        ContentType,
        on_delete=models.CASCADE,
    )
    object_id = models.PositiveIntegerField()
    content_object = GenericForeignKey('content_type', 'object_id')

    class Meta:
        ordering = ['-created_at']
        verbose_name = "Mention"
        verbose_name_plural = "Mentions"
        indexes = [
            models.Index(fields=['person']),
            models.Index(fields=['content_type', 'object_id']),
        ]
        constraints = [
            models.UniqueConstraint(
                fields=['person', 'content_type', 'object_id'],
                name='unique_mention_per_object',
            ),
        ]

    def __str__(self):
        return f"@{self.person.get_display_name()} in {self.content_type.model} #{self.object_id}"
