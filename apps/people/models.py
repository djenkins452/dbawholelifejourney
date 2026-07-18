"""
Whole Life Journey — Canonical Person domain (Layer 1 truth).

`apps/people` is the ONE always-on identity authority. Every feature module
(Relationships, Legacy, Journal, Health, Calendar, Finance, CoS, …) CONSUMES this
Person; none owns its own Person. Identity never disappears because a feature flag
is off. See docs/WLJ_PERSON_CONSOLIDATION_AND_RECOGNITION.md.

This module owns identity, independent status truths, People membership, recognition
phrases, photos, and meaningful lifecycle provenance. It does NOT own relationships,
genealogy, interaction history, or relationship strength — those live in the feature
modules and reference this Person by FK.

IMPORTANT — dependency direction: this module must NOT import any feature app
(relationships, legacy, journal, health, …). Enforced by
apps/people/tests/test_architecture_boundary.py.
"""

from django.conf import settings
from django.contrib.contenttypes.fields import GenericForeignKey
from django.contrib.contenttypes.models import ContentType
from django.db import models

from apps.core.models import TimeStampedModel, UserOwnedModel
from apps.core.rich_text import RichTextMixin

from .normalization import normalize_name


class PersonOrigin(models.TextChoices):
    """How a canonical Person first entered WLJ — provenance, for audit and
    reprocessing. Independent of every other status truth."""

    MANUAL = "manual", "Created manually"
    CONTACT_IMPORT = "contact_import", "Imported from contacts"
    GEDCOM = "gedcom", "Imported from GEDCOM"
    EXTRACTION = "extraction", "Recognized from text"
    MENTION = "mention", "Created from a mention"
    PROMOTION = "promotion", "Promoted from Legacy"
    API = "api", "Created via API"


class Person(RichTextMixin, UserOwnedModel):
    """The canonical identity record. One per real human in the user's world.

    Status/visibility are modeled as INDEPENDENT truths (no `person_kind` catch-all):
    a person can be deceased AND GEDCOM-imported AND a People member AND still
    referenced historically — all at once.
    """

    first_name = models.CharField(max_length=100, blank=True)
    last_name = models.CharField(max_length=100, blank=True)
    display_name = models.CharField(max_length=200, db_index=True)

    email = models.EmailField(blank=True)
    phone = models.CharField(max_length=40, blank=True)

    # Rich identity notes (canonical HTML + plain shadow) — "basic contact info".
    notes = models.TextField(blank=True, default="")
    notes_plain = models.TextField(blank=True, default="", editable=False)

    # --- Independent status truths (each modeled separately, never overloaded) ---
    is_deceased = models.BooleanField(default=False, db_index=True)
    is_self = models.BooleanField(
        default=False, db_index=True,
        help_text="This Person IS the user (the self-anchor). At most one per user.",
    )
    origin = models.CharField(
        max_length=20, choices=PersonOrigin.choices, default=PersonOrigin.MANUAL,
        db_index=True, help_text="How this identity first entered WLJ.",
    )

    RICH_TEXT_FIELDS = {"notes": "notes_plain"}
    CONTEXT_FIELDS = ("display_name", "notes_plain")

    class Meta:
        ordering = ["display_name"]
        indexes = [
            models.Index(fields=["user", "status"]),
            models.Index(fields=["user", "is_self"]),
        ]

    def __str__(self):
        return self.display_name or f"Person #{self.pk}"

    def save(self, *args, **kwargs):
        if not self.display_name:
            self.display_name = (
                f"{self.first_name} {self.last_name}".strip() or "Unnamed"
            )
        super().save(*args, **kwargs)  # RichTextMixin.save → sanitize notes

    @property
    def full_name(self) -> str:
        return f"{self.first_name} {self.last_name}".strip() or self.display_name

    @property
    def normalized_name(self) -> str:
        return normalize_name(self.display_name)

    @property
    def is_member(self) -> bool:
        """True iff this Person belongs to the everyday People experience
        (has a PersonMembership). Deceased members stay members."""
        return PersonMembership.objects.filter(person=self).exists()

    @property
    def is_genealogy_participant(self) -> bool:
        """DERIVED (never stored): true iff a Legacy extension binds this Person
        into the family graph. Resolved without importing Legacy — the bridge
        link is what proves participation."""
        return PersonSourceLink.objects.filter(
            person=self, source_domain=PersonSourceLink.Source.LEGACY
        ).exists()


class PersonMembership(TimeStampedModel):
    """The deterministic People-vs-Legacy boundary as a first-class truth.

    A Person is a member of the everyday People experience when they became part
    of the user's life (manually created, imported as a contact, a resolved
    mention, referenced/interacted-with, added by a feature, or explicitly
    promoted from Legacy). Membership is GRANTED, never auto-revoked — a deceased
    member stays; a GEDCOM-only ancestor never referenced outside genealogy never
    earns it (no membership row) and stays only in Legacy.
    """

    class Grant(models.TextChoices):
        MANUAL = "manual", "Manually created"
        CONTACT_IMPORT = "contact_import", "Imported as a contact"
        MENTION = "mention", "Resolved mention"
        REFERENCE = "reference", "Referenced by the user"
        INTERACTION = "interaction", "Interacted with"
        FEATURE = "feature", "Added by a WLJ feature"
        PROMOTION = "promotion", "Promoted from Legacy"

    person = models.OneToOneField(
        Person, on_delete=models.CASCADE, related_name="membership"
    )
    granted_via = models.CharField(max_length=20, choices=Grant.choices)
    granted_at = models.DateTimeField(auto_now_add=True)
    note = models.CharField(max_length=200, blank=True)

    def __str__(self):
        return f"Member: {self.person_id} via {self.granted_via}"


class RecognitionPhrase(TimeStampedModel):
    """A durable phrase that resolves to a canonical Person.

    Only TWO durable sources are stored here: `custom` (user-managed, e.g. "Honey")
    and `learned` (created ONLY after explicit user confirmation during Save/Review).
    `derived` phrases (first name, full name, unique relationship roles like "wife")
    are COMPUTED at resolve-time from deterministic truth and are never stored — so
    they update automatically when relationship truth changes.

    Authority chain: AI proposes → WLJ validates → user confirms → WLJ stores. No
    code path lets a model write a durable phrase.
    """

    class Source(models.TextChoices):
        CUSTOM = "custom", "User-defined"
        LEARNED = "learned", "User-confirmed (learned)"

    person = models.ForeignKey(
        Person, on_delete=models.CASCADE, related_name="recognition_phrases"
    )
    phrase = models.CharField(max_length=120, help_text="As entered by the user.")
    normalized = models.CharField(max_length=120, db_index=True, editable=False)
    source = models.CharField(max_length=10, choices=Source.choices)
    # Provenance for a learned phrase (which entry taught it) — kept small.
    learned_from = models.CharField(
        max_length=120, blank=True,
        help_text="e.g. 'journal:1234' — the entry where the user confirmed this.",
    )

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["person", "normalized"], name="unique_phrase_per_person"
            )
        ]
        indexes = [models.Index(fields=["normalized"])]

    def save(self, *args, **kwargs):
        self.normalized = normalize_name(self.phrase)
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.phrase} → {self.person_id} ({self.source})"


def person_photo_upload_to(instance, filename):
    return f"people/photos/{instance.person_id}/{filename}"


class PersonPhoto(TimeStampedModel):
    """A photo of a canonical Person. Stored on default storage (Cloudinary in
    prod, local FS in dev), like the rich-text image pipeline."""

    person = models.ForeignKey(
        Person, on_delete=models.CASCADE, related_name="photos"
    )
    image = models.ImageField(upload_to=person_photo_upload_to)
    caption = models.CharField(max_length=200, blank=True)
    is_primary = models.BooleanField(default=False)

    class Meta:
        ordering = ["-is_primary", "created_at"]

    def __str__(self):
        return f"Photo of {self.person_id}"


class PersonEvent(TimeStampedModel):
    """Meaningful Person lifecycle provenance — NOT a generic CRUD audit log.

    Records only events that explain how the canonical Person and its identity
    truth evolved, for debugging, explainability, merge confidence, preservation,
    and user trust. Bounded by design: do not record every database mutation.
    """

    class Type(models.TextChoices):
        CREATED_MANUAL = "created_manual", "Created manually"
        IMPORTED_CONTACTS = "imported_contacts", "Imported from contacts"
        IMPORTED_GEDCOM = "imported_gedcom", "Imported from GEDCOM"
        PROMOTED_TO_PEOPLE = "promoted_to_people", "Promoted into People"
        FIRST_MENTION = "first_mention", "First resolved mention"
        PHRASE_CONFIRMED = "phrase_confirmed", "Recognition phrase confirmed"
        PHRASE_REMOVED = "phrase_removed", "Recognition phrase removed"
        DUPLICATE_DETECTED = "duplicate_detected", "Duplicate detected"
        MERGE_COMPLETED = "merge_completed", "Merge completed"
        RELATIONSHIP_ADDED = "relationship_added", "Relationship added"
        RELATIONSHIP_REMOVED = "relationship_removed", "Relationship removed"
        ARCHIVED = "archived", "Archived"
        RESTORED = "restored", "Restored"
        SOURCE_ADDED = "source_added", "Source or provenance added"

    person = models.ForeignKey(
        Person, on_delete=models.CASCADE, related_name="events"
    )
    event_type = models.CharField(max_length=24, choices=Type.choices, db_index=True)
    at = models.DateTimeField(auto_now_add=True, db_index=True)
    # Small structured detail — deterministic facts only (ids, labels, counts).
    detail = models.JSONField(default=dict, blank=True)
    actor = models.CharField(
        max_length=20, default="system",
        help_text="system | user | import — who caused the event.",
    )

    class Meta:
        ordering = ["-at"]
        indexes = [models.Index(fields=["person", "at"])]

    def __str__(self):
        return f"{self.event_type} @ {self.person_id}"


class PersonSourceLink(models.Model):
    """Compatibility bridge / migration mapping: binds a canonical Person to the
    legacy source row(s) it was reconciled from, WITHOUT redirecting consumers.

    One canonical Person may map to several source rows (the same human existed in
    relationships, legacy, AND ai_relationships). Stored as (domain, pk) integers —
    NOT ForeignKeys — so the Core Person domain never imports a feature app. These
    links are temporary: they exist to migrate consumers safely and MUST be retired
    once every consumer reads the canonical Person (explicit retirement gate).
    """

    class Source(models.TextChoices):
        RELATIONSHIPS = "relationships", "relationships.Person"
        LEGACY = "legacy", "legacy.Person"
        AI_RELATIONSHIPS = "ai_relationships", "ai_relationships.Person"

    person = models.ForeignKey(
        Person, on_delete=models.CASCADE, related_name="source_links"
    )
    source_domain = models.CharField(max_length=20, choices=Source.choices, db_index=True)
    source_pk = models.PositiveIntegerField(db_index=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["source_domain", "source_pk"],
                name="unique_source_row_binding",
            )
        ]
        indexes = [models.Index(fields=["source_domain", "source_pk"])]

    def __str__(self):
        return f"{self.source_domain}#{self.source_pk} → person {self.person_id}"


class PersonMention(TimeStampedModel):
    """The canonical, structured link between a Person and a source object that
    references them (a journal entry, task, prayer, …).

    THE deterministic authority for "who is linked to this object." The rich-text
    editor's mention token is the interaction artifact; this row is the truth. One
    canonical mention store, many consumers — never a per-module mention table, and
    never a consumer of a legacy Person. GenericForeignKey keeps the Core Person domain
    free of any feature import (dependency direction: features → Core Person).
    """

    class Source(models.TextChoices):
        EXPLICIT_AT_MENTION = "explicit_at_mention", "Explicit @mention"
        EXACT_NAME = "exact_name", "Recognized by name"
        RELATIONSHIP_ROLE = "relationship_role", "Recognized by role"
        CONFIRMED_ALIAS = "confirmed_alias", "Recognized by phrase"
        REVIEWED_RESOLUTION = "reviewed_resolution", "Confirmed in review"

    person = models.ForeignKey(
        "people.Person", on_delete=models.CASCADE, related_name="content_mentions"
    )
    content_type = models.ForeignKey(ContentType, on_delete=models.CASCADE)
    object_id = models.PositiveIntegerField()
    content_object = GenericForeignKey("content_type", "object_id")

    source_type = models.CharField(
        max_length=24, choices=Source.choices, default=Source.EXPLICIT_AT_MENTION
    )
    # The text as written in the source ("Heather", "my wife") — provenance, never an ID.
    surface_text = models.CharField(max_length=120, blank=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["person", "content_type", "object_id"],
                name="unique_person_mention_per_object",
            )
        ]
        indexes = [
            models.Index(fields=["content_type", "object_id"]),
            models.Index(fields=["person"]),
        ]

    def __str__(self):
        return f"@{self.person_id} in {self.content_type.model}#{self.object_id}"
