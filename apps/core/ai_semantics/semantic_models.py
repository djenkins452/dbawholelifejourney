"""
SUE -- Semantic Decision Log Model.

Stores every semantic interpretation decision for audit, debugging,
and future model improvement. Never deleted -- append-only log.
"""

from django.conf import settings
from django.db import models


class SemanticDecisionLog(models.Model):
    """
    Append-only audit log for SUE interpretation decisions.

    Every call to interpret() produces a log entry recording
    what SUE understood, what it was unsure about, and what
    confidence it assigned.
    """

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="semantic_decisions",
    )

    # Input
    raw_text = models.TextField(
        help_text="The raw user input that was interpreted",
    )
    page_context = models.JSONField(
        default=dict,
        blank=True,
        help_text="Page context dict at time of interpretation",
    )

    # Interpretation result
    parsed_intent = models.CharField(
        max_length=100,
        blank=True,
        help_text="Primary intent detected (e.g., 'log_weight', 'create_goal')",
    )
    parsed_domain = models.CharField(
        max_length=50,
        blank=True,
        help_text="Domain module resolved (e.g., 'health', 'faith')",
    )
    parsed_entities = models.JSONField(
        default=dict,
        blank=True,
        help_text="Structured entities extracted {name: value}",
    )
    parsed_time_expression = models.CharField(
        max_length=200,
        blank=True,
        help_text="Time expression detected (before HTIE resolution)",
    )

    # Confidence
    overall_confidence = models.FloatField(
        default=0.0,
        help_text="Overall interpretation confidence (0.0-1.0)",
    )
    intent_confidence = models.FloatField(
        default=0.0,
        help_text="Intent-specific confidence (0.0-1.0)",
    )
    entity_confidence = models.FloatField(
        default=0.0,
        help_text="Entity extraction confidence (0.0-1.0)",
    )

    # Ambiguity
    is_ambiguous = models.BooleanField(
        default=False,
        help_text="Whether the input was flagged as ambiguous",
    )
    ambiguity_type = models.CharField(
        max_length=50,
        blank=True,
        help_text="Type of ambiguity detected (intent, entity, domain, multi_intent)",
    )
    clarification_question = models.TextField(
        blank=True,
        help_text="Clarification question generated (if ambiguous)",
    )
    alternative_intents = models.JSONField(
        default=list,
        blank=True,
        help_text="Alternative intent candidates [{intent, confidence}]",
    )

    # Resolution sources used
    used_slcme = models.BooleanField(
        default=False,
        help_text="Whether SLCME contributed to resolution",
    )
    used_sae = models.BooleanField(
        default=False,
        help_text="Whether SAE state contributed to resolution",
    )
    used_context = models.BooleanField(
        default=False,
        help_text="Whether page context contributed to resolution",
    )

    # Outcome (updated after execution)
    was_correct = models.BooleanField(
        null=True,
        blank=True,
        help_text="Whether the interpretation was correct (set after execution)",
    )
    correction_applied = models.CharField(
        max_length=100,
        blank=True,
        help_text="What the user actually meant (if corrected)",
    )

    # Timestamps
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        app_label = "core"
        db_table = "core_semantic_decision_log"
        ordering = ["-created_at"]
        verbose_name = "Semantic Decision Log"
        verbose_name_plural = "Semantic Decision Logs"
        indexes = [
            models.Index(fields=["user", "-created_at"]),
            models.Index(fields=["parsed_intent", "-created_at"]),
            models.Index(fields=["is_ambiguous", "-created_at"]),
        ]

    def __str__(self):
        return (
            f"SUE: '{self.raw_text[:50]}' -> {self.parsed_intent or '?'} "
            f"({self.overall_confidence:.0%})"
        )
