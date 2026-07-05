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
    # Biological sex from the source (GEDCOM SEX: 'M'/'F', '' unknown). Evidence, not
    # identity — used to type parent relationships (biological father vs mother) so the
    # importer never leaves a generic "Parent" when the source already tells us.
    sex = models.CharField(max_length=1, blank=True, db_index=True)
    birth_year = models.PositiveIntegerField(null=True, blank=True)
    death_year = models.PositiveIntegerField(null=True, blank=True)
    # Full dates when known (e.g. from GEDCOM "29 MAR 1971"). The *_year fields
    # always hold the year for compact views; these hold the exact day when we
    # have it, so Legacy can show "29 Mar 1971" instead of just "1971".
    birth_date = models.DateField(null=True, blank=True)
    death_date = models.DateField(null=True, blank=True)
    bio = models.TextField(blank=True, help_text="A 'who they were' narrative")
    primary_photo = models.ForeignKey(
        Media, on_delete=models.SET_NULL, null=True, blank=True, related_name='primary_for_people',
    )
    # Significance is multi-typed/perspectival in the full model; Phase 1 keeps a
    # single ordinal for ranking prominence. 0 = unset.
    significance = models.PositiveSmallIntegerField(default=0)
    # The keeper's own node in the Family tree — the "home" position the view
    # centers on. Denormalized from LegacyProfile.self_person for fast reads.
    is_self = models.BooleanField(default=False, db_index=True)
    # Genealogy provenance — set when a person is committed from a GEDCOM import.
    # A GEDCOM individual is unique by (source_batch, gedcom_xref); we NEVER merge
    # distinct individuals by name (that is what caused impossible parent counts).
    source_batch = models.ForeignKey(
        'ImportBatch', on_delete=models.SET_NULL, null=True, blank=True,
        related_name='imported_people')
    gedcom_xref = models.CharField(max_length=40, blank=True, db_index=True)

    class Meta:
        ordering = ['display_name']
        verbose_name_plural = 'People'

    def __str__(self):
        return self.display_name

    @property
    def display_birth(self):
        return fmt_life_date(self.birth_date, self.birth_year)

    @property
    def display_death(self):
        return fmt_life_date(self.death_date, self.death_year)

    @property
    def portrait_url(self):
        """The ONE canonical Primary Portrait for this person — reused everywhere in
        Legacy (Family tree, People, Relationships, stories, …). Empty when unset, so
        every surface falls back to the default silhouette. Backed by the existing Media
        model via `primary_photo`; changing it updates every view at once."""
        m = self.primary_photo
        return m.file.url if (m and m.file) else ""


def fmt_life_date(full, year):
    """'29 Mar 1971' when the exact day is known, else '1971', else ''."""
    if full:
        return "%d %s %d" % (full.day, full.strftime("%b"), full.year)
    return str(year) if year else ""


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


# Curated relationship vocabulary (value = the canonical directional phrase the
# Family graph reads; label = what the user sees). Not every parent comes from a
# marriage; not every romantic relationship is a marriage. "Other" allows a
# free-typed phrase; "" is Unknown.
RELATIONSHIP_TYPE_CHOICES = [
    ("Family — partners", (
        ("married to", "Spouse"),
        ("former spouse of", "Former spouse"),
        ("partner of", "Partner"),
        ("fiancé of", "Fiancé(e)"),
        ("boyfriend of", "Boyfriend"),
        ("girlfriend of", "Girlfriend"),
        ("had a relationship with", "Affair / other romantic"),
    )),
    ("Family — parents & children", (
        ("biological mother of", "Biological mother"),
        ("biological father of", "Biological father"),
        ("mother of", "Mother"),
        ("father of", "Father"),
        ("parent of", "Parent"),
        ("stepmother of", "Stepmother"),
        ("stepfather of", "Stepfather"),
        ("step-parent of", "Step-parent"),
        ("adoptive mother of", "Adoptive mother"),
        ("adoptive father of", "Adoptive father"),
        ("adoptive parent of", "Adoptive parent"),
        ("foster parent of", "Foster parent"),
        ("guardian of", "Guardian"),
        ("child of", "Child"),
    )),
    ("Family — siblings", (
        ("sibling of", "Sibling"),
        ("half-sibling of", "Half sibling"),
        ("step-sibling of", "Step sibling"),
    )),
    ("Beyond family", (
        ("friend of", "Friend"),
        ("coworker of", "Coworker"),
        ("manager of", "Manager"),
        ("mentor of", "Mentor"),
        ("pastor of", "Pastor"),
        ("teacher of", "Teacher"),
        ("neighbor of", "Neighbor"),
        ("related to", "Other"),
    )),
]


# ── THE canonical relationship classifier — the ONE place a relationship_type is
#    mapped to a category. Everything (Family View, Relationships hub, future
#    social graphs / Beth) reads the STORED category; nothing else keyword-matches.
#    Order matters: the first group whose keyword is present wins.
_CATEGORY_KEYWORDS = [
    ("romantic", ("married", "spouse", "husband", "wife", "wed", "partner",
                  "fianc", "boyfriend", "girlfriend", "relationship with", "affair")),
    ("family", ("parent", "father", "mother", "mom", "dad", "mum", "child", "son",
                "daughter", "sibling", "brother", "sister", "half", "grand", "aunt",
                "uncle", "cousin", "niece", "nephew", "in-law", "step", "adoptive",
                "guardian")),
    ("professional", ("coworker", "colleague", "manager", "boss", "mentor",
                      "employer", "employee", "client")),
    ("faith", ("pastor", "priest", "minister", "rabbi", "imam", "church",
               "congregation", "chaplain")),
    ("education", ("teacher", "professor", "tutor", "classmate", "student", "coach",
                   "instructor", "principal")),
    ("military", ("military", "commander", "platoon", "regiment", "squad", "served with")),
    ("medical", ("doctor", "nurse", "physician", "therapist", "caregiver", "surgeon")),
    ("community", ("neighbor", "neighbour")),
    ("social", ("friend",)),
]


def classify_category(relationship_type):
    """Map a relationship_type to its canonical category. The single source of
    truth; consumers read the stored `relationship_category`, never call this."""
    t = (relationship_type or "").lower().strip()
    if not t:
        return "unknown"
    for cat, kws in _CATEGORY_KEYWORDS:
        if any(k in t for k in kws):
            return cat
    return "other"


class Relationship(LegacyOwnedModel):
    """A typed, directional, time-bounded relationship between two people. This
    model is the canonical truth for ALL relationships — family, romantic,
    professional, social, faith, and beyond. Specialized views (the Family tree,
    a future professional network, etc.) are just filtered visualizations of it."""

    class Category(models.TextChoices):
        FAMILY = 'family', 'Family'
        ROMANTIC = 'romantic', 'Romantic'
        PROFESSIONAL = 'professional', 'Professional'
        SOCIAL = 'social', 'Social'
        FAITH = 'faith', 'Faith'
        EDUCATION = 'education', 'Education'
        MILITARY = 'military', 'Military'
        COMMUNITY = 'community', 'Community'
        MEDICAL = 'medical', 'Medical'
        OTHER = 'other', 'Other'
        UNKNOWN = 'unknown', 'Unknown'

    # The categories the Family View visualizes: blood/legal kin AND the couple
    # bonds (marriage/partnership) that form a family tree.
    FAMILY_TREE_CATEGORIES = frozenset({Category.FAMILY, Category.ROMANTIC})

    class RelStatus(models.TextChoices):
        CURRENT = 'current', 'Current'
        FORMER = 'former', 'Former'
        ESTRANGED = 'estranged', 'Estranged'
        UNKNOWN = 'unknown', 'Unknown'

    from_person = models.ForeignKey(
        Person, on_delete=models.CASCADE, related_name='relationships_from',
    )
    to_person = models.ForeignKey(
        Person, on_delete=models.CASCADE, related_name='relationships_to',
    )
    relationship_type = models.CharField(
        max_length=120, blank=True, help_text="e.g. 'father of', 'mentored by', 'married to'",
    )
    # STORED category, derived from the type by `classify_category` on save. Every
    # consumer reads this column; none re-classifies. Backfilled for existing rows.
    relationship_category = models.CharField(
        max_length=14, choices=Category.choices, default=Category.UNKNOWN, db_index=True)
    # Whether the relationship is ongoing, ended, estranged, or unknown — separate
    # from what KIND of relationship it is.
    rel_status = models.CharField(max_length=10, choices=RelStatus.choices, blank=True)
    # Set when the user edits this relationship by hand. A Smart Refresh NEVER
    # overwrites a user-edited relationship — Canonical Truth wins over a poorer source.
    user_edited = models.BooleanField(default=False)
    notes = models.TextField(blank=True)
    started_year = models.PositiveIntegerField(null=True, blank=True)
    ended_year = models.PositiveIntegerField(null=True, blank=True)
    # Full dates when known (e.g. GEDCOM marriage/divorce day).
    started_date = models.DateField(null=True, blank=True)
    ended_date = models.DateField(null=True, blank=True)

    class Meta:
        ordering = ['from_person__display_name']

    def save(self, *args, **kwargs):
        # The category is a denormalization of the type via the ONE classifier.
        self.relationship_category = classify_category(self.relationship_type)
        if "update_fields" in kwargs and kwargs["update_fields"] is not None:
            kwargs["update_fields"] = set(kwargs["update_fields"]) | {"relationship_category"}
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.from_person} — {self.relationship_type or 'unknown'} — {self.to_person}"

    @property
    def type_label(self):
        for _group, opts in RELATIONSHIP_TYPE_CHOICES:
            for value, label in opts:
                if value == self.relationship_type:
                    return label
        return self.relationship_type or "Unknown"

    @property
    def display_started(self):
        return fmt_life_date(self.started_date, self.started_year)

    @property
    def display_ended(self):
        return fmt_life_date(self.ended_date, self.ended_year)


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
        GEDCOM = 'gedcom', 'Genealogy (GEDCOM)'
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
    # Completeness/preservation report: what was imported into Canonical Truth,
    # what was preserved but has no canonical home yet (with a recommendation),
    # and what wasn't recognized. Proof that nothing was silently discarded.
    coverage = models.JSONField(default=dict, blank=True)
    # Smart Refresh: when this upload is recognized as a newer export of a source
    # already imported, it SYNCHRONIZES that lineage instead of duplicating it.
    # `refresh_of` points at the original batch (the lineage); `is_refresh` flags a
    # pending refresh awaiting the user's choice; `refresh_summary` is the permanent
    # audit of what a refresh changed (added/updated/preserved/prevented duplicates).
    refresh_of = models.ForeignKey(
        'self', on_delete=models.SET_NULL, null=True, blank=True, related_name='refreshes')
    is_refresh = models.BooleanField(default=False)
    refresh_summary = models.JSONField(default=dict, blank=True)

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
        GEDCOM_PERSON = 'gedcom_person', 'Genealogy person'
        GEDCOM_FAMILY = 'gedcom_family', 'Genealogy family'
        UNKNOWN = 'unknown', 'Not sure yet'

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
    # Structured payload for deterministic kinds (e.g. GEDCOM person/family:
    # xref, sex, birth/death year, spouse & child links) so a queue can be
    # committed into canonical People + Relationships without re-parsing.
    data = models.JSONField(default=dict, blank=True)
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


class PreservedFact(LegacyOwnedModel):
    """Legacy's PERMANENT preservation layer — the promise that nothing is ever
    lost. Every imported fact that Canonical Truth cannot yet model lands here as a
    durable row (not trapped inside one import session), tied to the Person it
    describes and tagged with the CONCEPT it belongs to (Career, Faith Journey,
    Military, Life Events…). When a canonical domain is later built, it backfills
    straight from these rows — no user ever re-imports a file. This is how Canonical
    Truth grows: from what people actually entrusted to Legacy, not developer guesses.
    The Canonical Truth Roadmap is simply an aggregation of these rows by concept."""

    class FactStatus(models.TextChoices):
        AWAITING = 'awaiting', 'Awaiting canonical model'
        UNKNOWN = 'unknown', 'Preserved — not yet recognized'
        MODELED = 'modeled', 'Migrated into Canonical Truth'

    # Provenance — where this fact came from, and who it's about.
    source_batch = models.ForeignKey(
        ImportBatch, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='preserved_facts')
    person = models.ForeignKey(
        Person, on_delete=models.CASCADE, null=True, blank=True,
        related_name='preserved_facts')
    subject_label = models.CharField(
        max_length=200, blank=True, help_text="Who/what this is about when no Person is linked")
    source_format = models.CharField(max_length=20, default='gedcom', db_index=True)

    # Concept over structure: the roadmap groups by `concept`; `label` is the granular
    # fact-type; `original_tag` keeps the exact source tag so migration is lossless.
    concept = models.CharField(
        max_length=60, db_index=True, help_text="Canonical concept: Career, Faith Journey, Military…")
    label = models.CharField(max_length=80, help_text="Granular fact type: Occupation, Baptism…")
    original_tag = models.CharField(max_length=40, help_text="Exact source tag, e.g. OCCU, _MILT")

    # The preserved content — kept verbatim so a future model can read it back.
    value = models.CharField(max_length=2000, blank=True)
    fact_date = models.CharField(max_length=80, blank=True, help_text="Raw source date string")
    fact_place = models.CharField(max_length=255, blank=True)
    original_data = models.JSONField(default=dict, blank=True)

    fact_status = models.CharField(
        max_length=12, choices=FactStatus.choices, default=FactStatus.AWAITING, db_index=True)
    # Fingerprint for idempotent re-commit (never duplicate the same preserved fact).
    dedupe_key = models.CharField(max_length=64, db_index=True, blank=True)

    class Meta:
        ordering = ['concept', '-created_at']
        indexes = [models.Index(fields=['user', 'concept'])]

    def __str__(self):
        who = self.person.display_name if self.person_id else (self.subject_label or "?")
        return f"{who} · {self.label}: {self.value[:40]}"

    @property
    def summary(self):
        """One-line human example for the roadmap ('Railroad conductor · 1965')."""
        bits = [self.value] if self.value else []
        if self.fact_place and self.fact_place not in self.value:
            bits.append(self.fact_place)
        if self.fact_date:
            bits.append(self.fact_date)
        return " · ".join(b for b in bits if b) or self.label


class ClarificationDecision(LegacyOwnedModel):
    """A resolved clarification — the user's answer, remembered so the SAME question is
    never asked again (teach-once). Generic across clarification types; `ref` is the
    opaque id the handler uses (e.g. 'spousePk:parentPk' for a step-parent question)."""

    kind = models.CharField(max_length=40, db_index=True)
    ref = models.CharField(max_length=120, db_index=True)
    answer = models.CharField(max_length=60, blank=True)
    detail = models.CharField(max_length=120, blank=True)

    class Meta:
        unique_together = ['user', 'kind', 'ref']

    def __str__(self):
        return f"{self.kind}:{self.ref} → {self.answer}"


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


class LegacyProfile(models.Model):
    """Binds an authenticated WLJ user to the canonical Person that IS them — the
    permanent focal point of the Family View. Set once; never depends on searching
    a 1,500-person tree. Supersedes the transient Person.is_self flag (which is
    kept denormalized for fast reads)."""

    user = models.OneToOneField(
        'users.User', on_delete=models.CASCADE, related_name='legacy_profile')
    self_person = models.ForeignKey(
        Person, on_delete=models.SET_NULL, null=True, blank=True, related_name='+')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"{self.user_id} → {self.self_person_id}"
