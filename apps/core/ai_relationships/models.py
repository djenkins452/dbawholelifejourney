"""
Whole Life Journey - Relationship Intelligence Models

Project: Whole Life Journey
Path: apps/core/ai_relationships/models.py
Purpose: Track people, relationships, and interaction signals for CoS

Description:
    Minimal models for relationship intelligence. Person records are
    created through conversation, journal extraction, or calendar events.
    InteractionSignals track when a person is mentioned or interacted with.
    Relationship records define the user's connection and desired cadence.

Models:
    - Person: A person in the user's life
    - Relationship: User's relationship with a Person (type, importance, cadence)
    - InteractionSignal: Extracted signal of interaction with a Person

Copyright:
    (c) Whole Life Journey. All rights reserved.
"""

from django.conf import settings
from django.db import models


# =============================================================================
# PERSON
# =============================================================================


class Person(models.Model):
    """
    A person in the user's life.

    Created through conversation, journal extraction, or manual entry.
    Linked to InteractionSignals and optionally to SignificantEvents.
    """

    PERSON_TYPE_CHOICES = [
        ('family', 'Family'),
        ('friend', 'Friend'),
        ('colleague', 'Colleague'),
        ('mentor', 'Mentor'),
        ('other', 'Other'),
    ]

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='known_people',
    )

    display_name = models.CharField(
        max_length=200,
        help_text="How the user refers to this person",
    )

    person_type = models.CharField(
        max_length=20,
        choices=PERSON_TYPE_CHOICES,
        default='other',
    )

    notes = models.TextField(
        blank=True,
        help_text="Optional notes about this person",
    )

    is_active = models.BooleanField(
        default=True,
        help_text="Inactive people are hidden but not deleted",
    )

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['display_name']
        verbose_name = "Person"
        verbose_name_plural = "People"
        indexes = [
            models.Index(fields=['user', 'is_active']),
        ]

    def __str__(self):
        return f"{self.display_name} ({self.person_type})"


# =============================================================================
# RELATIONSHIP
# =============================================================================


class Relationship(models.Model):
    """
    User's relationship with a Person.

    Defines relationship type, importance tier (1=innermost circle, 3=outer),
    and desired interaction cadence. Used by the relational drift detector.
    """

    CADENCE_CHOICES = [
        ('daily', 'Daily'),
        ('weekly', 'Weekly'),
        ('biweekly', 'Biweekly'),
        ('monthly', 'Monthly'),
        ('quarterly', 'Quarterly'),
    ]

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='relationships',
    )

    person = models.ForeignKey(
        Person,
        on_delete=models.CASCADE,
        related_name='relationships',
    )

    relationship_type = models.CharField(
        max_length=50,
        help_text="Specific relationship: spouse, child, parent, friend, boss, etc.",
    )

    importance_tier = models.PositiveSmallIntegerField(
        default=3,
        help_text="1=innermost circle, 2=close, 3=outer circle",
    )

    cadence_target = models.CharField(
        max_length=15,
        choices=CADENCE_CHOICES,
        blank=True,
        help_text="How often the user wants to connect with this person",
    )

    last_interaction = models.DateField(
        null=True,
        blank=True,
        help_text="Date of most recent interaction signal",
    )

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = ['user', 'person']
        ordering = ['importance_tier', 'person__display_name']
        verbose_name = "Relationship"
        verbose_name_plural = "Relationships"

    def __str__(self):
        return f"{self.relationship_type} with {self.person.display_name} (T{self.importance_tier})"


# =============================================================================
# INTERACTION SIGNAL
# =============================================================================


class InteractionSignal(models.Model):
    """
    Extracted signal of interaction with a Person.

    Created when a person is mentioned in journal entries, calendar events,
    reflection answers, or manually noted. Confidence indicates how sure
    the system is about the match.
    """

    SIGNAL_TYPE_CHOICES = [
        ('mention', 'Mention in text'),
        ('event', 'Calendar event'),
        ('call', 'Phone call'),
        ('message', 'Message'),
        ('manual', 'Manual entry'),
    ]

    SOURCE_TYPE_CHOICES = [
        ('journal', 'Journal Entry'),
        ('calendar', 'Calendar Event'),
        ('reflection', 'Reflection Answer'),
        ('manual', 'Manual Entry'),
        ('chat', 'Chat Conversation'),
    ]

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='interaction_signals',
    )

    person = models.ForeignKey(
        Person,
        on_delete=models.CASCADE,
        related_name='interactions',
    )

    signal_date = models.DateField()

    signal_type = models.CharField(
        max_length=20,
        choices=SIGNAL_TYPE_CHOICES,
        default='mention',
    )

    confidence = models.FloatField(
        default=0.8,
        help_text="How confident the system is in this match (0.0-1.0)",
    )

    source_type = models.CharField(
        max_length=20,
        choices=SOURCE_TYPE_CHOICES,
    )

    source_id = models.CharField(
        max_length=100,
        blank=True,
        help_text="ID of the source record",
    )

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-signal_date']
        verbose_name = "Interaction Signal"
        verbose_name_plural = "Interaction Signals"
        indexes = [
            models.Index(fields=['user', 'person', 'signal_date']),
        ]

    def __str__(self):
        return (
            f"{self.signal_type} with {self.person.display_name} "
            f"on {self.signal_date} ({self.confidence:.0%})"
        )
