"""
Legacy domain models — canonical shape (Phase 1).

These models implement the *shape* of the Legacy Canonical Truth model
(Attestation → Assertion → Projection; see docs/WLJ_LEGACY_DOMAIN_ARCHITECTURE.md)
faithfully enough that no redesign is needed when the full truth machinery
(assertion composition, conflict sets, promotion gate) and the assistant arrive
in later phases.

Phase-1 mapping to the architecture:
  * Memory      → the capture container / testimonial unit. Carries its own
                  provenance (source_kind / contributor / attributed_to /
                  created_via) — i.e. it *is* an attestation container. Full
                  append-only assertion composition layers on top later.
  * Person/Place→ canonical graph nodes.
  * Media       → evidence carriers (a photo with no linked Memory is
                  "unpreserved" — surfaced later as a gap).
  * Relationship→ first-class typed edge between people.
  * Contributor → a family co-author (attribution is permanent).
  * Output      → a projection; never canonical, always regenerable.

All models are user-owned and soft-deletable. Nothing is ever hard-deleted by
normal flows — "Set aside" (archive) is the primary destructive action, in line
with the preservation mandate.
"""

from django.conf import settings
from django.db import models

from apps.core.models import UserOwnedModel


class LegacyOwnedModel(UserOwnedModel):
    """
    User-owned + soft-delete base for all Legacy models.

    Overrides the inherited ``user`` reverse accessor to a Legacy-namespaced one
    (``user.legacy_<model>s``) so Legacy model names (e.g. Relationship) never
    clash with identically-named models in other apps.
    """

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="legacy_%(class)ss",
    )

    class Meta:
        abstract = True


# ──────────────────────────────────────────────────────────────────────────
# Media — evidence carriers
# ──────────────────────────────────────────────────────────────────────────
class Media(LegacyOwnedModel):
    """A photo, video, audio clip, document, or letter — a doorway to memory."""

    class MediaType(models.TextChoices):
        PHOTO = 'photo', 'Photo'
        VIDEO = 'video', 'Video'
        AUDIO = 'audio', 'Audio'
        DOCUMENT = 'document', 'Document'
        LETTER = 'letter', 'Letter'
        OTHER = 'other', 'Other'

    media_type = models.CharField(
        max_length=12, choices=MediaType.choices, default=MediaType.PHOTO, db_index=True,
    )
    file = models.FileField(upload_to='legacy/media/%Y/%m/', blank=True, null=True)
    original_filename = models.CharField(max_length=255, blank=True)
    caption = models.CharField(max_length=500, blank=True)
    taken_on = models.DateField(null=True, blank=True, help_text="When the media was captured")
    source_note = models.CharField(
        max_length=255, blank=True,
        help_text="Provenance: where/whom this came from (e.g. 'Mom's box')",
    )

    class Meta:
        ordering = ['-taken_on', '-created_at']
        verbose_name_plural = 'Media'

    def __str__(self):
        return self.caption or self.original_filename or f"{self.get_media_type_display()} #{self.pk}"


# ──────────────────────────────────────────────────────────────────────────
# Person — canonical node (the primary index of a life)
# ──────────────────────────────────────────────────────────────────────────
class Person(LegacyOwnedModel):
    """A person whose life is preserved, who contributes, or who is referenced."""

    display_name = models.CharField(max_length=200, db_index=True)
    also_known_as = models.CharField(
        max_length=200, blank=True, help_text="Nicknames / other names (comma-separated)",
    )
    relationship_label = models.CharField(
        max_length=120, blank=True, help_text="Relationship to the keeper (e.g. 'your father')",
    )
    birth_year = models.PositiveIntegerField(null=True, blank=True)
    death_year = models.PositiveIntegerField(null=True, blank=True)
    bio = models.TextField(blank=True, help_text="A 'who they were' narrative")
    primary_photo = models.ForeignKey(
        Media, on_delete=models.SET_NULL, null=True, blank=True, related_name='primary_for_people',
    )
    # Significance is multi-typed/perspectival in the full model; Phase 1 keeps a
    # single ordinal for ranking prominence. 0 = unset.
    significance = models.PositiveSmallIntegerField(default=0)

    class Meta:
        ordering = ['display_name']
        verbose_name_plural = 'People'

    def __str__(self):
        return self.display_name


# ──────────────────────────────────────────────────────────────────────────
# Place — canonical node (spatial anchor of memory)
# ──────────────────────────────────────────────────────────────────────────
class Place(LegacyOwnedModel):
    """A location with meaning — a home, a town, a favorite table."""

    name = models.CharField(max_length=200, db_index=True)
    location_text = models.CharField(max_length=255, blank=True)
    description = models.TextField(blank=True, help_text="A 'what it was' narrative")
    primary_photo = models.ForeignKey(
        Media, on_delete=models.SET_NULL, null=True, blank=True, related_name='primary_for_places',
    )
    significance = models.PositiveSmallIntegerField(default=0)

    class Meta:
        ordering = ['name']

    def __str__(self):
        return self.name


# ──────────────────────────────────────────────────────────────────────────
# Contributor — a family co-author
# ──────────────────────────────────────────────────────────────────────────
class Contributor(LegacyOwnedModel):
    """Someone invited to help remember. Attribution to them is permanent."""

    class Permission(models.TextChoices):
        VIEW = 'view', 'Can see'
        ADD = 'add', 'Can add'
        MANAGE = 'manage', 'Can help manage'

    class InviteStatus(models.TextChoices):
        INVITED = 'invited', 'Invited'
        ACTIVE = 'active', 'Active'
        DECLINED = 'declined', 'Declined'
        EXPIRED = 'expired', 'Expired'

    name = models.CharField(max_length=200)
    email = models.EmailField(blank=True)
    relationship_label = models.CharField(max_length=120, blank=True)
    permission_level = models.CharField(
        max_length=10, choices=Permission.choices, default=Permission.ADD,
    )
    invite_status = models.CharField(
        max_length=10, choices=InviteStatus.choices, default=InviteStatus.INVITED, db_index=True,
    )
    invite_token = models.CharField(max_length=64, blank=True, db_index=True)
    invited_at = models.DateTimeField(null=True, blank=True)
    # If the contributor also has a WLJ account, link it (optional).
    linked_user = models.ForeignKey(
        'users.User', on_delete=models.SET_NULL, null=True, blank=True,
        related_name='legacy_contributions',
    )
    # If the contributor corresponds to a Person node in the graph.
    person = models.ForeignKey(
        Person, on_delete=models.SET_NULL, null=True, blank=True, related_name='as_contributor',
    )

    class Meta:
        ordering = ['name']

    def __str__(self):
        return self.name


# ──────────────────────────────────────────────────────────────────────────
# Memory — the capture container / testimonial unit (attestation container)
# ──────────────────────────────────────────────────────────────────────────
class Memory(LegacyOwnedModel):
    """A preserved memory/story. The heart of Legacy."""

    class EntryType(models.TextChoices):
        MEMORY = 'memory', 'Memory'
        STORY = 'story', 'Story'
        PERSON = 'person', 'Someone important'
        PLACE = 'place', 'A place'
        EVENT = 'event', 'An event'
        OBJECT = 'object', 'An object'
        TRADITION = 'tradition', 'A tradition'
        LESSON = 'lesson', 'A lesson'
        SAYING = 'saying', 'A saying'
        BRAIN_DUMP = 'brain_dump', 'Brain dump'
        RECORD_TOGETHER = 'record_together', 'Recorded together'

    class EntryState(models.TextChoices):
        # User-facing wording per the UX docs: "Just for me" / "Kept (Legacy)" / "Shared".
        DRAFT = 'draft', 'Just for me'
        LEGACY = 'legacy', 'In your Legacy'
        SHARED = 'shared', 'Shared'

    class Precision(models.TextChoices):
        EXACT = 'exact', 'Exact date'
        MONTH = 'month', 'Month'
        YEAR = 'year', 'Year'
        APPROX = 'approx', 'Approximate'
        UNKNOWN = 'unknown', 'Unknown'

    class SourceKind(models.TextChoices):
        OWNER = 'owner', 'The keeper'
        CONTRIBUTOR = 'contributor', 'A family contributor'

    # Content — capture is never gated, so title/body may be blank.
    title = models.CharField(max_length=255, blank=True)
    body = models.TextField(blank=True, help_text="The story text or voice transcript")
    entry_type = models.CharField(
        max_length=20, choices=EntryType.choices, default=EntryType.MEMORY, db_index=True,
    )
    entry_state = models.CharField(
        max_length=10, choices=EntryState.choices, default=EntryState.DRAFT, db_index=True,
    )

    # When the memory happened (not when it was recorded). Fuzzy by design.
    occurred_on = models.DateField(null=True, blank=True)
    occurred_precision = models.CharField(
        max_length=10, choices=Precision.choices, default=Precision.UNKNOWN,
    )

    # Provenance (attestation shape). Full append-only composition arrives later.
    source_kind = models.CharField(
        max_length=12, choices=SourceKind.choices, default=SourceKind.OWNER,
    )
    attributed_to = models.ForeignKey(
        Person, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='attributed_memories', help_text="Whose memory/voice this is",
    )
    contributor = models.ForeignKey(
        Contributor, on_delete=models.SET_NULL, null=True, blank=True, related_name='memories',
    )
    provenance_note = models.CharField(max_length=255, blank=True)
    # Who last edited this memory (multi-contributor attribution). The owner
    # (user) is the creator; updated_by tracks the most recent editor.
    updated_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='legacy_edited_memories',
    )

    # Graph connections.
    people = models.ManyToManyField(Person, through='MemoryPerson', related_name='memories', blank=True)
    places = models.ManyToManyField(Place, through='MemoryPlace', related_name='memories', blank=True)
    media = models.ManyToManyField(Media, related_name='memories', blank=True)
    primary_media = models.ForeignKey(
        Media, on_delete=models.SET_NULL, null=True, blank=True, related_name='cover_for_memories',
    )

    significance = models.PositiveSmallIntegerField(default=0)

    class Meta:
        ordering = ['-created_at']
        verbose_name_plural = 'Memories'
        indexes = [
            models.Index(fields=['user', 'entry_state', 'status']),
        ]

    def __str__(self):
        return self.title or f"Memory #{self.pk}"

    @property
    def has_audio(self):
        return self.media.filter(media_type=Media.MediaType.AUDIO).exists()


class MemoryPerson(models.Model):
    """Edge: a person appears in a memory (optionally with a role)."""

    memory = models.ForeignKey(Memory, on_delete=models.CASCADE)
    person = models.ForeignKey(Person, on_delete=models.CASCADE)
    role = models.CharField(max_length=120, blank=True)

    class Meta:
        unique_together = ['memory', 'person']


class MemoryPlace(models.Model):
    """Edge: a memory took place at a place."""

    memory = models.ForeignKey(Memory, on_delete=models.CASCADE)
    place = models.ForeignKey(Place, on_delete=models.CASCADE)

    class Meta:
        unique_together = ['memory', 'place']


class MemoryRevision(models.Model):
    """
    Append-only snapshot of a Memory's prior content.

    Preservation truth is not destroyed by editing: when a Memory that is
    already IN a person's Legacy (canonical) is edited, its previous telling is
    snapshotted here first. Revisions are never edited or deleted — editing
    *deepens*, it does not overwrite (see docs/WLJ_LEGACY_DOMAIN_UX_ARCHITECTURE
    §8.2 and the Attestation→Assertion model). This is the Phase-1, minimal
    expression of the append/supersede pattern.
    """

    memory = models.ForeignKey(Memory, on_delete=models.CASCADE, related_name='revisions')
    title = models.CharField(max_length=255, blank=True)
    body = models.TextField(blank=True)
    entry_state = models.CharField(max_length=10, blank=True)
    edited_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='legacy_memory_revisions',
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f"Revision of {self.memory_id} @ {self.created_at:%Y-%m-%d %H:%M}"


# ──────────────────────────────────────────────────────────────────────────
# Relationship — first-class typed edge between people
# ──────────────────────────────────────────────────────────────────────────
class Relationship(LegacyOwnedModel):
    """A typed, directional, time-bounded relationship between two people."""

    from_person = models.ForeignKey(
        Person, on_delete=models.CASCADE, related_name='relationships_from',
    )
    to_person = models.ForeignKey(
        Person, on_delete=models.CASCADE, related_name='relationships_to',
    )
    relationship_type = models.CharField(
        max_length=120, help_text="e.g. 'father of', 'mentored by', 'married to'",
    )
    notes = models.TextField(blank=True)
    started_year = models.PositiveIntegerField(null=True, blank=True)
    ended_year = models.PositiveIntegerField(null=True, blank=True)

    class Meta:
        ordering = ['from_person__display_name']

    def __str__(self):
        return f"{self.from_person} — {self.relationship_type} — {self.to_person}"


# ──────────────────────────────────────────────────────────────────────────
# Output — a projection (never canonical, always regenerable)
# ──────────────────────────────────────────────────────────────────────────
class Output(LegacyOwnedModel):
    """A generated gift derived from the life: memoir, album, timeline, etc."""

    class OutputType(models.TextChoices):
        MEMOIR = 'memoir', 'Memoir'
        AUTOBIOGRAPHY = 'autobiography', 'Autobiography'
        CHILDRENS_BOOK = 'childrens_book', "Children's book"
        PICTURE_BOOK = 'picture_book', 'Picture book'
        FAMILY_HISTORY = 'family_history', 'Family history'
        TIMELINE = 'timeline', 'Timeline'
        ENCYCLOPEDIA = 'encyclopedia', 'Character encyclopedia'
        MUSEUM = 'museum', 'Digital museum'
        PHOTO_ALBUM = 'photo_album', 'Photo album'
        PODCAST = 'podcast', 'Podcast script'
        DOCUMENTARY = 'documentary', 'Documentary outline'

    class ScopeKind(models.TextChoices):
        WHOLE_LIFE = 'whole_life', 'Your whole life'
        PERSON = 'person', 'A person'
        PLACE = 'place', 'A place'
        PERIOD = 'period', 'A time period'
        COLLECTION = 'collection', 'A collection'

    class Audience(models.TextChoices):
        ME = 'me', 'Me'
        FAMILY = 'family', 'Family'
        CHILDREN = 'children', 'Children'
        GRANDCHILDREN = 'grandchildren', 'Grandchildren'
        PUBLIC = 'public', 'Public'

    class GenerationStatus(models.TextChoices):
        DRAFT = 'draft', 'Draft'
        GENERATING = 'generating', 'Generating'
        READY = 'ready', 'Ready'
        FAILED = 'failed', 'Failed'

    title = models.CharField(max_length=255, blank=True)
    output_type = models.CharField(max_length=20, choices=OutputType.choices)
    scope_kind = models.CharField(
        max_length=12, choices=ScopeKind.choices, default=ScopeKind.WHOLE_LIFE,
    )
    scope_person = models.ForeignKey(
        Person, on_delete=models.SET_NULL, null=True, blank=True, related_name='outputs',
    )
    scope_place = models.ForeignKey(
        Place, on_delete=models.SET_NULL, null=True, blank=True, related_name='outputs',
    )
    audience = models.CharField(
        max_length=14, choices=Audience.choices, default=Audience.FAMILY,
    )
    generation_status = models.CharField(
        max_length=12, choices=GenerationStatus.choices, default=GenerationStatus.DRAFT,
    )
    summary = models.TextField(blank=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return self.title or f"{self.get_output_type_display()} #{self.pk}"
