"""NotesDomainTruth — canonical interface to Notes truth.

Thin facade over the Note model. Read-only; owns no new retrieval logic. Notes had a
full model (title/body, tags, color, pinned, attachments) but ZERO truth-layer
plumbing — this exposes each note as a CompleteEntity. Placed at the app top level
(not services/) to avoid shadowing the existing `apps/notes/services.py` module.
"""
from apps.core.truth import freshness as F
from apps.core.truth.current import CurrentTruth
from apps.core.truth.domain import DomainTruth, register_domain_truth
from apps.core.truth.entity import CompleteEntity

_DOMAIN = "notes"


@register_domain_truth
class NotesDomainTruth(DomainTruth):
    domain = "notes"
    current_metrics = ("note_count",)
    history_metrics = ()
    entity_types = ("note",)

    def current(self, metric):
        from apps.notes.models import Note
        if metric == "note_count":
            qs = Note.objects.filter(user=self.user)
            total = qs.count()
            if total == 0:
                return CurrentTruth.absent(_DOMAIN, metric, F.MISSING,
                                           source="notes", reason="no notes")
            pinned = qs.filter(is_pinned=True).count()
            return CurrentTruth.found(_DOMAIN, metric, total, F.CURRENT,
                                      source="notes", detail={"pinned": pinned})
        raise KeyError(f"notes current unsupported: {metric!r} "
                       f"(have {self.current_metrics})")

    def describe(self, entity_type="note"):
        if entity_type not in (None, "note"):
            raise KeyError(f"notes domain cannot describe {entity_type!r} "
                           f"(have {self.entity_types})")
        from django.db.models import Prefetch
        from apps.notes.models import Note, NoteAttachment
        qs = (Note.objects.filter(user=self.user)
              .prefetch_related("tags",
                                Prefetch("attachments",
                                         queryset=NoteAttachment.objects
                                         .select_related("content_type"))))
        return [self._note_entity(n) for n in qs]

    def describe_one(self, name):
        from django.db.models import Prefetch
        from apps.notes.models import Note, NoteAttachment
        q = (name or "").strip()
        if not q:
            return None
        n = (Note.all_objects.filter(user=self.user, title__icontains=q)
             .prefetch_related("tags",
                               Prefetch("attachments",
                                        queryset=NoteAttachment.objects
                                        .select_related("content_type")))
             .order_by("status", "-is_pinned", "-updated_at").first())
        return self._note_entity(n) if n else None

    def _note_entity(self, n):
        try:
            attachments = [a.attachment_display() for a in n.attachments.all()]
            attachments = [a for a in attachments if a]
        except Exception:
            attachments = []
        return CompleteEntity(
            kind="note", identity=n.display_title, status=n.status,
            definition={"title": n.title or None,
                        "content": (n.body_plain or "").strip(),
                        "tags": list(n.tags.values_list("name", flat=True)),
                        "color": n.color},
            standing={"is_pinned": n.is_pinned, "word_count": n.word_count,
                      "attachment_count": n.attachment_count,
                      "attached_to": attachments},
            performance={"created": n.created_at.isoformat() if n.created_at else None,
                         "updated": n.updated_at.isoformat() if n.updated_at else None},
            freshness=F.CURRENT)
