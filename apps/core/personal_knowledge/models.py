# ==============================================================================
# File: apps/core/personal_knowledge/models.py
# Project: Whole Life Journey - Django 5.x Personal Wellness/Journaling App
# Description: The canonical Personal Knowledge authority (M2 foundation)
# Owner: Danny Jenkins (admin@wholelifejourney.com)
# Created: 2026-08-18
# ==============================================================================
"""PersonalKnowledgeFact — what the Chief of Staff knows about the user.

Contract 4 (`docs/WLJ_PERSONALIZATION_PERSONAL_KNOWLEDGE_CONTRACTS.md`).

DESIGN PRINCIPLE (frozen): the natural-language **statement is the payload**; structure
exists ONLY for retrieval and user control, never for interpretation. WLJ stores,
indexes, retrieves and lets the user control. **WLJ never computes what a statement
means** — that is the model's job (Constitution I.4).

Consequently this model contains NO interpretation fields: no `meaning`, no personality
analysis, no inferred verdict, no derived summary, no prose generation. Adding one
requires a Constitutional Review; `test_personal_knowledge_contract.py` fails CI if one
appears.

WHY NOT `PersonalFact`: it is missing 13 of 17 target requirements and 5 structurally
(no canonical entity reference — `subject_name` is a free string, which IS the
shadow-person problem; 8 hardcoded `fact_type` choices; no lineage — `is_active`
DESTROYS correction history; no space scoping; and `fact_text` is PLAINTEXT, so adopting
it would be a privacy regression against today's encrypted blob). It remains a migration
source for M3; nothing may extend it.
"""

from django.conf import settings
from django.db import models

from apps.core.encryption import decrypt_personal_data_safe, encrypt_personal_data
from apps.core.models import UserOwnedModel


class Topic(models.TextChoices):
    """Deterministic knowledge areas — the retrieval + Knowledge Map index.

    EXTENSIBLE BY DESIGN. `topic` is a plain CharField (these are suggestions, not a
    DB constraint) so an EMERGENT topic discovered in a future interview is storable and
    retrievable IMMEDIATELY, without a deploy (Contract 8.4). This is the specific flaw
    that made `PersonalFact.fact_type`'s hardcoded enum unusable for a human life.
    """

    FAMILY = "family", "Family & Important People"
    WORK = "work", "Work & Career"
    HOME = "home", "Home & Lifestyle"
    ROUTINES = "routines", "Routines"
    INTERESTS = "interests", "Interests"
    GOALS = "goals", "Goals & Dreams"
    VALUES = "values", "Values"
    FAITH = "faith", "Faith"
    HISTORY = "history", "Life History"
    HEALTH_CONTEXT = "health_context", "Health Context"
    COMMUNICATION = "communication", "Communication Preferences"
    OTHER = "other", "Other"


class Provenance(models.TextChoices):
    """How the fact was acquired (Contract 4.1). Permanent — never overwritten."""

    INTERVIEW = "interview", "Getting to Know You"              # M4
    EXPLICIT = "explicit", "User said remember this"            # M4
    ABOUT_ME_ENTRY = "about_me_entry", "Added in About Me"      # M3
    CANDIDATE_ACCEPTED = "candidate_accepted", "Accepted from conversation"  # M6
    IMPORTED = "imported", "Imported"
    LEGACY_EXTRACTION = "legacy_extraction", "Legacy extraction (unverified)"  # M3


class Sensitivity(models.TextChoices):
    """Governs RETRIEVAL, not merely storage (Contract 10.5)."""

    NORMAL = "normal", "Normal"
    SENSITIVE = "sensitive", "Sensitive"


class ReviewState(models.TextChoices):
    """Trust state. Only reviewed/user-authored knowledge may enter standing context."""

    UNREVIEWED = "unreviewed", "Unreviewed"          # legacy imports (M3)
    REVIEWED = "reviewed", "Reviewed by user"
    USER_AUTHORED = "user_authored", "Authored by user"


class FactStatus(models.TextChoices):
    """Lifecycle. Correction SUPERSEDES; it never destroys history."""

    ACTIVE = "active", "Active"
    SUPERSEDED = "superseded", "Superseded by a correction"


class PersonalKnowledgeFact(UserOwnedModel):
    """One durable fact or piece of context about the user's life.

    Ownership/soft-delete/timestamps come from `UserOwnedModel` (the WLJ convention),
    which carries `user`, `status` (active/archived/deleted), `deleted_at`,
    `created_at`/`updated_at` and the SoftDeleteManager. `user` is the physical stand-in
    for the user's Personal Space per the ratified Security & Authorization Framework, so
    no re-scoping migration is needed when the PDP lands.
    """

    # ── the payload (ENCRYPTED AT REST) ───────────────────────────────────────
    # Stored via a property pair, mirroring UserPreferences.ai_personal_context, so the
    # column NEVER holds plaintext. There must be no plaintext regression against the
    # legacy encrypted blob this authority replaces.
    _statement = models.TextField(
        db_column="statement",
        blank=True,
        default="",
        help_text="ENCRYPTED. The fact in the user's own words. Data, never an "
                  "instruction, and never a WLJ-authored interpretation.",
    )

    # ── retrieval index ───────────────────────────────────────────────────────
    topic = models.CharField(
        max_length=64,
        default=Topic.OTHER,
        db_index=True,
        help_text="Knowledge area. Topic.* are suggestions, not a constraint — an "
                  "emergent topic must be storable without a deploy.",
    )
    # Canonical entity reference (Contract 5.4). NULLABLE ON PURPOSE: the Person
    # Consolidation programme has backfilled identity rows (0c-A/0c-B shipped) but
    # consumer redirect (0c+) is not finished, so Personal Knowledge must be fully
    # usable BEFORE that completes. PK never creates a Person and never forks the
    # consolidation programme.
    subject_person = models.ForeignKey(
        "people.Person",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="personal_knowledge_facts",
        help_text="Canonical people.Person this fact is about, when one exists.",
    )
    subject_label = models.CharField(
        max_length=200,
        blank=True,
        default="",
        db_index=True,
        help_text="Free-text subject when no canonical entity exists. NOT an identity "
                  "record — it never becomes a person.",
    )
    attributes = models.JSONField(
        default=dict,
        blank=True,
        help_text="Sparse deterministic attributes, ONLY where unambiguous "
                  "(e.g. {'relation': 'spouse', 'since': 1997}). Absent by default; a "
                  "fact needing none stores none.",
    )

    # ── provenance / trust / sensitivity ──────────────────────────────────────
    provenance = models.CharField(
        max_length=32, choices=Provenance.choices, default=Provenance.ABOUT_ME_ENTRY,
        db_index=True, help_text="How this was acquired. Permanent.",
    )
    source_conversation = models.ForeignKey(
        "ai.AssistantConversation",
        null=True, blank=True, on_delete=models.SET_NULL,
        related_name="personal_knowledge_facts",
        help_text="Where it came from — makes 'forget everything from that chat' possible.",
    )
    sensitivity = models.CharField(
        max_length=16, choices=Sensitivity.choices, default=Sensitivity.NORMAL,
        db_index=True,
        help_text="SENSITIVE is excluded from standing context entirely; it is "
                  "retrievable only on-subject.",
    )
    review_state = models.CharField(
        max_length=16, choices=ReviewState.choices, default=ReviewState.USER_AUTHORED,
        db_index=True,
        help_text="Only reviewed/user-authored knowledge may enter standing context.",
    )
    confidence = models.FloatField(
        default=1.0,
        help_text="Extraction confidence. Explicitly taught facts are 1.0.",
    )

    # ── lineage ───────────────────────────────────────────────────────────────
    fact_status = models.CharField(
        max_length=16, choices=FactStatus.choices, default=FactStatus.ACTIVE,
        db_index=True,
        help_text="A correction marks the old row SUPERSEDED and creates a new ACTIVE "
                  "row. History is preserved, never destroyed.",
    )
    superseded_by = models.ForeignKey(
        "self", null=True, blank=True, on_delete=models.SET_NULL,
        related_name="supersedes",
        help_text="The correction that replaced this fact.",
    )

    # ── standing-context eligibility ──────────────────────────────────────────
    pinned = models.BooleanField(
        default=False, db_index=True,
        help_text="User forced this into the always-on standing tier (still subject to "
                  "the hard cap and the absolute sensitivity exclusion).",
    )

    # ── as-of (never more precise than the user supplied) ─────────────────────
    as_of = models.DateField(
        null=True, blank=True,
        help_text="When the fact became true, if the user supplied it. WLJ never infers "
                  "a precision the user did not give.",
    )

    class Meta:
        app_label = "core"
        db_table = "core_personal_knowledge_fact"
        ordering = ["topic", "-created_at"]
        indexes = [
            models.Index(fields=["user", "fact_status", "status"],
                         name="idx_pk_user_factstatus"),
            models.Index(fields=["user", "topic", "fact_status"],
                         name="idx_pk_user_topic"),
            models.Index(fields=["user", "sensitivity", "review_state"],
                         name="idx_pk_user_sens_review"),
            models.Index(fields=["user", "pinned"], name="idx_pk_user_pinned"),
        ]
        verbose_name = "Personal Knowledge Fact"
        verbose_name_plural = "Personal Knowledge Facts"

    # ── encrypted payload accessors ───────────────────────────────────────────
    @property
    def statement(self) -> str:
        if not self._statement:
            return ""
        decrypted, _ok = decrypt_personal_data_safe(self._statement)
        return decrypted

    @statement.setter
    def statement(self, value: str):
        if not value:
            self._statement = ""
            return
        self._statement = encrypt_personal_data(value)

    def __str__(self):
        # NEVER render the decrypted statement here — __str__ reaches logs, admin lists
        # and error reports. Personal Knowledge must not leak through telemetry.
        subject = self.subject_label or (
            self.subject_person.display_name if self.subject_person_id else "")
        return f"[{self.topic}]{(' ' + subject) if subject else ''} ({self.fact_status})"

    @property
    def subject_display(self) -> str:
        """The subject's name — canonical entity first, then the label fallback."""
        if self.subject_person_id:
            try:
                return self.subject_person.display_name
            except Exception:  # pragma: no cover - defensive
                pass
        return self.subject_label or ""
