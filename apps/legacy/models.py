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
    # Set when a public place is verified via lookup (name + location only —
    # no deep research). Blank for personal places like "Grandma's house".
    latitude = models.DecimalField(max_digits=9, decimal_places=6, null=True, blank=True)
    longitude = models.DecimalField(max_digits=9, decimal_places=6, null=True, blank=True)
    primary_photo = models.ForeignKey(
        Media, on_delete=models.SET_NULL, null=True, blank=True, related_name='primary_for_places',
    )
    significance = models.PositiveSmallIntegerField(default=0)

    class Meta:
        ordering = ['name']

    def __str__(self):
        return self.name


# ──────────────────────────────────────────────────────────────────────────
# Life Milestone — a major chapter of a life (an organizing layer, not an owner)
# ──────────────────────────────────────────────────────────────────────────
class LifeMilestone(LegacyOwnedModel):
    """
    A major chapter of a person's life — Marriage, Bought First House, Birth of
    a Child, Moved to Tennessee, Met Eric and Carrie, Retirement…

    A Milestone is a purely ASSOCIATIVE organizing layer. It does NOT own Stories
    or Media — Stories keep owning their own media and context. Many Stories (and
    through them People, Places, Media, Quotes, Themes) simply share one or more
    Milestones, which lets a whole life be organized by its chapters (e.g. "1997")
    and later powers the Timeline and milestone-scoped Outputs — without any
    manual organizing and without moving or duplicating anything.
    """

    class Kind(models.TextChoices):
        MARRIAGE = 'marriage', 'Marriage'
        HOME = 'home', 'Home'
        EDUCATION = 'education', 'Education'
        MILITARY = 'military', 'Military'
        CAREER = 'career', 'Career'
        BIRTH = 'birth', 'Birth'
        DEATH = 'death', 'Loss'
        FAITH = 'faith', 'Faith'
        HEALTH = 'health', 'Health'
        RELOCATION = 'relocation', 'Move'
        TRAVEL = 'travel', 'Travel'
        BUSINESS = 'business', 'Business'
        RELATIONSHIP = 'relationship', 'Relationship'
        OTHER = 'other', 'Milestone'

    title = models.CharField(max_length=200, db_index=True)
    kind = models.CharField(max_length=14, choices=Kind.choices, default=Kind.OTHER)
    year = models.PositiveIntegerField(null=True, blank=True, db_index=True)
    description = models.TextField(blank=True)
    significance = models.PositiveSmallIntegerField(default=0)

    class Meta:
        ordering = ['-year', 'title']
        verbose_name = 'Life milestone'
        verbose_name_plural = 'Life milestones'

    def __str__(self):
        return self.title


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
    # Associative only — a story shares milestones; milestones never own the story.
    milestones = models.ManyToManyField('LifeMilestone', related_name='memories', blank=True)
    primary_media = models.ForeignKey(
        Media, on_delete=models.SET_NULL, null=True, blank=True, related_name='cover_for_memories',
    )

    significance = models.PositiveSmallIntegerField(default=0)

    # Optional, story-aware preservation prompts from the Discovery Engine
    # ("You mentioned your grandfather but never described what he was like").
    # Suggestions only — never interview questions, never required.
    discovery_prompts = models.JSONField(default=list, blank=True)

    # Cleanup phase (before Discovery): the user's ORIGINAL wording, preserved so
    # the gentle copy-edit can always be undone. Set only when cleanup changed
    # something. The user's voice is never lost.
    cleanup_original_body = models.TextField(blank=True, default="")

    # Import provenance — set when a memory was created by the Import Engine from
    # an existing document. Always visible on the memory. (created_via='import'.)
    import_batch = models.ForeignKey(
        'ImportBatch', on_delete=models.SET_NULL, null=True, blank=True, related_name='memories')
    import_chunk = models.PositiveIntegerField(null=True, blank=True)

    class Meta:
        ordering = ['-created_at']
        verbose_name_plural = 'Memories'
        indexes = [
            models.Index(fields=['user', 'entry_state', 'status']),
        ]

    def __str__(self):
        return self.title or f"Memory #{self.pk}"

    def cover_media(self):
        """The image used as this story's thumbnail — the chosen primary photo if
        set, otherwise the first attached photo. Guarantees a consistent tile
        whenever the story has any photo, even if the primary was removed."""
        pm = self.primary_media
        if pm and pm.media_type == Media.MediaType.PHOTO and pm.file:
            return pm
        return self.media.filter(
            media_type=Media.MediaType.PHOTO).exclude(file="").order_by("pk").first()

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
class MemoryDiscovery(models.Model):
    """
    A single proposal from the Story Discovery Engine (Phase 2).

    The engine reads a memory's text and proposes everything it understood —
    people, relationships, places, human/calendar/relative time, life stage,
    events, quotes, artifacts, media references, themes, values, traditions,
    emotions. **Nothing here is canonical.** A discovery is `proposed` until the
    user reviews it. Accepting a person/place discovery is the promotion gate:
    it creates/links a real Person/Place graph node and connects it to the
    memory. All other accepted discoveries are preserved as user-confirmed,
    confidence-scored attested enrichment on the memory (extensible to
    first-class nodes in a later slice). Rejected/undecided rows remain as an
    audit of what was proposed — provenance is never bypassed.
    """

    class Kind(models.TextChoices):
        PERSON = 'person', 'Person'
        RELATIONSHIP = 'relationship', 'Relationship'
        PLACE = 'place', 'Place'
        MILESTONE = 'milestone', 'Life milestone'
        HUMAN_TIME = 'human_time', 'Human time'
        CALENDAR_TIME = 'calendar_time', 'Calendar time'
        LIFE_STAGE = 'life_stage', 'Life stage'
        RELATIVE_TIME = 'relative_time', 'Relative time'
        EVENT = 'event', 'Event'
        QUOTE = 'quote', 'Quote'
        ARTIFACT = 'artifact', 'Artifact'
        MEDIA_REF = 'media_ref', 'Media reference'
        EXISTING_MEDIA = 'existing_media', 'Media you already have'
        THEME = 'theme', 'Theme'
        VALUE = 'value', 'Value'
        TRADITION = 'tradition', 'Tradition'
        EMOTION = 'emotion', 'Emotion'

    class Confidence(models.TextChoices):
        HIGH = 'high', 'High'
        MEDIUM = 'medium', 'Medium'
        LOW = 'low', 'Low'

    class Status(models.TextChoices):
        PROPOSED = 'proposed', 'Proposed'
        ACCEPTED = 'accepted', 'Accepted'
        REJECTED = 'rejected', 'Rejected'

    memory = models.ForeignKey(Memory, on_delete=models.CASCADE, related_name='discoveries')
    kind = models.CharField(max_length=16, choices=Kind.choices, db_index=True)
    label = models.CharField(max_length=500)
    detail = models.JSONField(default=dict, blank=True)
    confidence = models.CharField(max_length=6, choices=Confidence.choices, default=Confidence.MEDIUM)
    status = models.CharField(max_length=10, choices=Status.choices, default=Status.PROPOSED, db_index=True)

    # Set when a person/place discovery is promoted into a real graph node.
    linked_person = models.ForeignKey(
        'Person', on_delete=models.SET_NULL, null=True, blank=True, related_name='discoveries')
    linked_place = models.ForeignKey(
        'Place', on_delete=models.SET_NULL, null=True, blank=True, related_name='discoveries')
    linked_milestone = models.ForeignKey(
        'LifeMilestone', on_delete=models.SET_NULL, null=True, blank=True, related_name='discoveries')

    created_at = models.DateTimeField(auto_now_add=True)
    decided_at = models.DateTimeField(null=True, blank=True)

    # Display order for the Kind groups in the review panel.
    _ORDER = {
        'person': 0, 'relationship': 1, 'place': 2, 'milestone': 3, 'human_time': 4,
        'calendar_time': 5, 'life_stage': 6, 'relative_time': 7, 'event': 8, 'quote': 9,
        'artifact': 10, 'media_ref': 11, 'theme': 12, 'value': 13, 'tradition': 14, 'emotion': 15,
        'existing_media': 16,
    }

    class Meta:
        ordering = ['status', 'kind', 'id']

    def __str__(self):
        return f"{self.get_kind_display()}: {self.label}"


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


# ──────────────────────────────────────────────────────────────────────────
# Import Engine — convert existing documents into Legacy Canonical Truth
# ──────────────────────────────────────────────────────────────────────────
class ImportBatch(LegacyOwnedModel):
    """
    A document being imported into Legacy (an autobiography, a ChatGPT/Claude
    conversation, a journal, a memoir, a Word/PDF, plain text…). The document is
    parsed into ImportChunks; importing a chunk creates a draft Memory that runs
    through the SAME Story Discovery Engine as a hand-written story. Nothing
    bypasses Canonical Truth, Discovery, or provenance.
    """

    class SourceType(models.TextChoices):
        CHATGPT = 'chatgpt', 'ChatGPT conversation'
        CLAUDE = 'claude', 'Claude conversation'
        WORD = 'word', 'Word document'
        PDF = 'pdf', 'PDF'
        JOURNAL = 'journal', 'Journal'
        MEMOIR = 'memoir', 'Existing memoir'
        PLAIN_TEXT = 'plain_text', 'Plain text'
        OTHER = 'other', 'Other'

    class Status(models.TextChoices):
        PARSED = 'parsed', 'Parsed'
        IMPORTING = 'importing', 'Importing'
        COMPLETE = 'complete', 'Complete'
        FAILED = 'failed', 'Failed'

    source_name = models.CharField(max_length=255)
    source_type = models.CharField(max_length=12, choices=SourceType.choices, default=SourceType.OTHER)
    # NB: distinct from the inherited soft-delete `status` (active/archived/deleted).
    import_status = models.CharField(max_length=12, choices=Status.choices, default=Status.PARSED)
    total_chunks = models.PositiveIntegerField(default=0)
    imported_count = models.PositiveIntegerField(default=0)
    notes = models.CharField(max_length=500, blank=True)

    class Meta:
        ordering = ['-created_at']
        verbose_name_plural = 'Import batches'

    def __str__(self):
        return self.source_name

    def refresh_counts(self):
        self.imported_count = self.chunks.filter(status=ImportChunk.Status.IMPORTED).count()
        if self.imported_count >= self.total_chunks and self.total_chunks:
            self.import_status = self.Status.COMPLETE
        self.save(update_fields=["imported_count", "import_status", "updated_at"])


class ImportChunk(models.Model):
    """One unit of a document. The importer first CLASSIFIES what each unit IS
    (`chunk_kind`) — a story, a fact, a person, a place, a milestone, a quote, a
    relationship alias… — then routes it to the right review queue. Narrative
    units become draft Memories through Discovery; facts and entities are held
    for review and never silently become stories."""

    class Status(models.TextChoices):
        PENDING = 'pending', 'Pending'
        IMPORTED = 'imported', 'Imported'
        SKIPPED = 'skipped', 'Skipped'

    class Kind(models.TextChoices):
        STORY = 'story', 'Story'
        JOURNAL = 'journal_entry', 'Journal entry'
        LETTER = 'letter', 'Letter'
        FACT = 'fact', 'Fact'
        PERSON = 'person', 'Person'
        RELATIONSHIP_ALIAS = 'relationship_alias', 'Relationship alias'
        PLACE = 'place', 'Place'
        MILESTONE = 'milestone', 'Life milestone'
        TIMELINE_EVENT = 'timeline_event', 'Timeline event'
        QUOTE = 'quote', 'Quote'
        ARTIFACT = 'artifact', 'Artifact'
        MEDIA_REF = 'media_ref', 'Media reference'
        BIOGRAPHY = 'biography', 'Biography'
        DESCRIPTION = 'description', 'Description'
        UNKNOWN = 'unknown', 'Unknown'

    # Kinds that legitimately become a narrative Memory (run through Discovery).
    # Everything else is an entity/fact held in its review queue — never auto-storied.
    NARRATIVE_KINDS = frozenset({Kind.STORY, Kind.JOURNAL, Kind.LETTER})

    batch = models.ForeignKey(ImportBatch, on_delete=models.CASCADE, related_name='chunks')
    index = models.PositiveIntegerField()
    title = models.CharField(max_length=255, blank=True)
    body = models.TextField()
    source_ref = models.CharField(max_length=120, blank=True, help_text="e.g. 'message 7'")
    status = models.CharField(max_length=10, choices=Status.choices, default=Status.PENDING)
    # What the orchestrator understood this unit to be (classification precedes extraction).
    chunk_kind = models.CharField(
        max_length=20, choices=Kind.choices, default=Kind.STORY, db_index=True)
    kind_confidence = models.CharField(max_length=6, blank=True)  # high / medium / low
    memory = models.ForeignKey(
        Memory, on_delete=models.SET_NULL, null=True, blank=True, related_name='import_chunks')
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['index']
        unique_together = ['batch', 'index']

    def __str__(self):
        return f"{self.batch_id}#{self.index}: {self.title or self.source_ref}"

    @property
    def is_narrative(self):
        return self.chunk_kind in ImportChunk.NARRATIVE_KINDS


class RelationshipAlias(LegacyOwnedModel):
    """A relational term the keeper uses — "Dad", "Mom", "Coach", "Pastor" — mapped
    to the actual Person it refers to. Learned once (on review) and reused on every
    future import, so Legacy resolves "Dad → Marvin Jenkins" without asking again.
    An alias with no person yet is an open question awaiting the user's answer."""

    alias = models.CharField(max_length=80, db_index=True, help_text="normalized, lowercased")
    label = models.CharField(max_length=80, help_text="as written, e.g. 'Dad'")
    person = models.ForeignKey(
        Person, on_delete=models.CASCADE, null=True, blank=True, related_name='aliases')

    class Meta:
        unique_together = ['user', 'alias']
        verbose_name_plural = 'Relationship aliases'

    def __str__(self):
        return f"{self.label} → {self.person.display_name if self.person else '?'}"
