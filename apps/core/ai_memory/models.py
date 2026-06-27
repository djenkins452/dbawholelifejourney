"""
SLCME Database Models — Persistent storage for learned meanings and context.

Four models:
- PersonalFact: Persistent biographical facts learned from conversations
- LearnedMapping: Phrase → meaning associations learned from user clarification
- ContextSnapshot: Current user context (what page, what entry they're viewing)
- ClarificationLog: Audit trail of all clarification exchanges
"""

from django.conf import settings
from django.db import models


class PersonalFact(models.Model):
    """
    Persistent storage for biographical life facts learned from conversations.

    These are meaningful, lasting personal details that the CoS should always
    remember: family relationships, deaths, milestones, life circumstances.

    Unlike ConversationMemory (which is pruned), PersonalFacts are permanent
    and deterministic — they are never auto-pruned and are always available
    for system prompt injection.

    Examples:
    - fact_type="family_relationship", subject_name="Linda (Nana)",
      fact_text="Linda (Nana) is Danny's wife's mother"
    - fact_type="death", subject_name="Linda (Nana)",
      fact_text="Nana (Linda) passed away several years ago"
    - fact_type="family_relationship", subject_name="Sarah",
      fact_text="Sarah is Danny's wife"
    """

    FACT_TYPE_CHOICES = [
        ("family_relationship", "Family Relationship"),
        ("death", "Death / Loss"),
        ("health_condition", "Health Condition"),
        ("life_milestone", "Life Milestone"),
        ("personal_value", "Personal Value"),
        ("life_circumstance", "Life Circumstance"),
        ("preference", "Preference"),
        ("other", "Other"),
    ]

    SOURCE_CHOICES = [
        ("conversation", "Extracted from conversation"),
        ("manual", "User-provided directly"),
    ]

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="personal_facts",
    )
    fact_type = models.CharField(
        max_length=50,
        choices=FACT_TYPE_CHOICES,
        help_text="Category of personal fact",
    )
    subject_name = models.CharField(
        max_length=200,
        blank=True,
        default="",
        help_text="Name of the person or subject (e.g., 'Nana', 'Sarah', 'Dad')",
    )
    relationship = models.CharField(
        max_length=100,
        blank=True,
        default="",
        help_text="Relationship to user (e.g., 'wife\\'s mother', 'daughter', 'spouse')",
    )
    fact_text = models.TextField(
        help_text="Human-readable fact (e.g., 'Nana (Linda) passed away several years ago')",
    )
    confidence = models.FloatField(
        default=0.8,
        help_text="AI extraction confidence (0.0 to 1.0)",
    )
    source = models.CharField(
        max_length=20,
        choices=SOURCE_CHOICES,
        default="conversation",
    )
    is_active = models.BooleanField(
        default=True,
        help_text="User can deactivate facts they don't want used",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        app_label = "core"
        db_table = "core_personal_fact"
        indexes = [
            models.Index(
                fields=["user", "fact_type", "is_active"],
                name="idx_pfact_user_type_active",
            ),
            models.Index(
                fields=["user", "is_active"],
                name="idx_pfact_user_active",
            ),
        ]
        ordering = ["fact_type", "-created_at"]

    def __str__(self):
        subject = f" ({self.subject_name})" if self.subject_name else ""
        return f"[{self.fact_type}]{subject}: {self.fact_text[:80]}"


class LearnedMapping(models.Model):
    """
    Stores a learned association between a user phrase and its resolved meaning.

    Example: "the scripture" → meaning_type="scripture", meaning_identifier="John 3:16"
    Confidence grows with each successful reuse.
    """

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="learned_mappings",
    )
    phrase = models.CharField(
        max_length=255,
        help_text="The user's original phrase (e.g., 'the scripture', 'my goal')",
    )
    meaning_type = models.CharField(
        max_length=100,
        help_text="Category of meaning (e.g., 'scripture', 'goal', 'health_entry')",
    )
    meaning_identifier = models.CharField(
        max_length=255,
        help_text="Specific identifier (e.g., 'John 3:16', 'goal_id:42')",
    )
    confidence_score = models.FloatField(
        default=0.8,
        help_text="0.0 to 1.0 — grows with usage, must meet threshold to auto-use",
    )
    usage_count = models.IntegerField(
        default=1,
        help_text="Number of times this mapping has been used",
    )
    last_used_at = models.DateTimeField(
        null=True,
        blank=True,
        help_text="Last time this mapping was applied",
    )
    is_active = models.BooleanField(
        default=True,
        help_text="Soft disable without deleting",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        app_label = "core"
        db_table = "core_learned_mapping"
        indexes = [
            models.Index(fields=["user", "phrase"], name="idx_mapping_user_phrase"),
            models.Index(
                fields=["user", "confidence_score"],
                name="idx_mapping_user_confidence",
            ),
            models.Index(
                fields=["user", "meaning_type"],
                name="idx_mapping_user_type",
            ),
        ]
        ordering = ["-confidence_score", "-usage_count"]

    def __str__(self):
        return f"{self.phrase} → {self.meaning_type}:{self.meaning_identifier} ({self.confidence_score:.2f})"


class ContextSnapshot(models.Model):
    """
    Tracks the user's current context — what they're looking at right now.

    Examples:
    - context_type="scripture_page", context_identifier="John 3"
    - context_type="health_entry", context_identifier="weight_entry:123"
    - context_type="goal", context_identifier="goal:42"
    """

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="context_snapshots",
    )
    context_type = models.CharField(
        max_length=100,
        help_text="Type of context (e.g., 'scripture_page', 'health_entry', 'goal')",
    )
    context_identifier = models.CharField(
        max_length=255,
        help_text="Specific identifier for this context",
    )
    metadata = models.JSONField(
        default=dict,
        blank=True,
        help_text="Additional context data (page title, entry details, etc.)",
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        app_label = "core"
        db_table = "core_context_snapshot"
        indexes = [
            models.Index(
                fields=["user", "context_type", "-created_at"],
                name="idx_ctx_user_type_date",
            ),
        ]
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.context_type}:{self.context_identifier}"


class ClarificationLog(models.Model):
    """
    Audit trail of every clarification exchange between user and AI.

    This is write-only for audit purposes — never delete these records.
    """

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="clarification_logs",
    )
    original_input = models.TextField(
        help_text="What the user originally said",
    )
    clarification_question = models.TextField(
        help_text="What the AI asked for clarification",
    )
    user_response = models.TextField(
        help_text="The user's clarifying response",
    )
    resolved_meaning = models.TextField(
        help_text="The final resolved meaning after clarification",
    )
    learned_mapping = models.ForeignKey(
        LearnedMapping,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="clarification_logs",
        help_text="The mapping created/updated from this clarification",
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        app_label = "core"
        db_table = "core_clarification_log"
        indexes = [
            models.Index(
                fields=["user", "-created_at"],
                name="idx_clarify_user_date",
            ),
        ]
        ordering = ["-created_at"]

    def __str__(self):
        return f"Clarification: {self.original_input[:50]}..."


class BehaviorDirective(models.Model):
    """P36 Layer-4 Behavior Guidance — the ONE thing the existing knowledge stores
    lacked: a learned item that answers "why should this change how Beth behaves?".

    Unlike PersonalFact/ExtractedFact (which RECORD facts), a directive CHANGES
    behavior downstream. One row per (user, key) — re-learning REINFORCES (compression),
    contradiction WEAKENS. Consumed by the Executive Interpretation Engine."""

    LAYER_CHOICES = [
        ("identity", "Identity"),       # stable truths
        ("preference", "Preference"),   # learned likes/dislikes
        ("pattern", "Pattern"),         # repeated longitudinal observations
        ("guidance", "Guidance"),       # explicit behavior guidance
    ]
    SOURCE_CHOICES = [
        ("told", "Told by Danny"),
        ("observed", "Observed repeatedly"),
        ("derived", "Derived from analysis"),
        ("confirmed", "Confirmed by Danny"),
        ("corrected", "Corrected by Danny"),
    ]
    STATUS_CHOICES = [("active", "Active"), ("weak", "Weak"), ("retired", "Retired")]
    # Starting confidence by source (different evidence -> different confidence).
    SOURCE_WEIGHT = {"told": 0.85, "confirmed": 0.95, "observed": 0.55,
                     "derived": 0.5, "corrected": 0.85}

    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE,
                             related_name="behavior_directives")
    layer = models.CharField(max_length=16, choices=LAYER_CHOICES, default="preference")
    # Structured behavior key — the COMPRESSION unit AND the behavior instruction
    # (e.g. "deprioritize:shower", "tone:direct", "recovery_activity:motorcycle").
    key = models.CharField(max_length=80)
    observation = models.TextField(help_text="What was noticed.")
    meaning = models.TextField(blank=True, help_text="Why it matters.")
    behavior_change = models.TextField(help_text="How Beth should behave differently.")
    confidence = models.FloatField(default=0.5)
    source = models.CharField(max_length=16, choices=SOURCE_CHOICES, default="observed")
    evidence = models.TextField(blank=True, help_text="Supports 'why do you think that?'")
    evidence_count = models.PositiveIntegerField(default=1)
    status = models.CharField(max_length=12, choices=STATUS_CHOICES, default="active")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    last_reinforced_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        constraints = [models.UniqueConstraint(fields=["user", "key"],
                                               name="uniq_behavior_directive_user_key")]
        indexes = [models.Index(fields=["user", "status"]),
                   models.Index(fields=["user", "-confidence"])]
        ordering = ["-confidence", "-evidence_count"]

    def __str__(self):
        return f"[{self.layer}] {self.key} ({self.confidence:.2f}, {self.status})"

    def reinforce(self, source=None, by=0.15):
        from django.utils import timezone
        self.confidence = min(1.0, round(self.confidence + by, 3))
        self.evidence_count += 1
        self.last_reinforced_at = timezone.now()
        self.status = "active"
        if source and source in self.SOURCE_WEIGHT:
            # an explicit/confirmed source can lift a weakly-observed directive
            self.confidence = max(self.confidence, self.SOURCE_WEIGHT[source])
            self.source = source

    def weaken(self, by=0.3):
        self.confidence = max(0.0, round(self.confidence - by, 3))
        if self.confidence < 0.25:
            self.status = "retired"
        elif self.confidence < 0.5:
            self.status = "weak"

    def explain(self):
        pct = int(round(self.confidence * 100))
        bc = (self.behavior_change or "").strip().rstrip(".")
        return (f"Because {self.observation.rstrip('.')}"
                f" ({self.get_source_display().lower()}; seen {self.evidence_count}×; "
                f"{pct}% confident), {bc[0].lower() + bc[1:] if bc else 'I adapt'}.")
