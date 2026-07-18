"""CaptureDomainTruth — canonical Layer-1 interface to Capture truth.

Thin facade over CaptureQueries + CaptureEntry model fields, read live. Owns NO new
retrieval logic. Capture stored a full model (audio → transcript → summary,
category/subcategory, processing status) with deterministic queries but ZERO
Truth-Layer provider — this exposes it. Content (transcript/summary) exists only once
status='ready'.
"""
from apps.core.truth.current import CurrentTruth
from apps.core.truth.domain import DomainTruth, register_domain_truth
from apps.core.truth.entity import CompleteEntity
from apps.core.truth.freshness import CURRENT, MISSING

_DOMAIN = "capture"


def _today(user):
    from apps.core.utils import get_user_today
    return get_user_today(user)


@register_domain_truth
class CaptureDomainTruth(DomainTruth):
    domain = "capture"
    current_metrics = ("unprocessed_count",)
    history_metrics = ()
    entity_types = ("capture",)

    def current(self, metric):
        from apps.capture.services.capture_queries import CaptureQueries
        if metric == "unprocessed_count":
            pending = CaptureQueries.pending_uploads(self.user).count()
            ready_recent = list(CaptureQueries.ready_recent(self.user, days=7)[:10])
            failed = CaptureQueries.failed_recent(self.user, days=7).count()
            total = pending + len(ready_recent) + failed
            if total == 0:
                return CurrentTruth.absent(_DOMAIN, metric, MISSING,
                                           source="capture_queries",
                                           reason="no unprocessed captures")
            return CurrentTruth.found(
                _DOMAIN, metric, total, CURRENT, source="capture_queries",
                detail={"pending_uploads": pending,
                        "ready_awaiting_review": len(ready_recent),
                        "failed": failed,
                        "recent": [{"title": e.title or "Untitled",
                                    "category": e.category or None,
                                    "subcategory": e.subcategory or None,
                                    "date": e.created_at.date().isoformat()}
                                   for e in ready_recent]})
        raise KeyError(f"capture current unsupported: {metric!r} "
                       f"(have {self.current_metrics})")

    def describe(self, entity_type="capture"):
        if entity_type not in (None, "capture"):
            raise KeyError(f"capture cannot describe {entity_type!r} "
                           f"(have {self.entity_types})")
        from apps.capture.models import CaptureEntry
        qs = (CaptureEntry.objects.filter(user=self.user)
              .prefetch_related("extraction_signals").order_by("-created_at")[:50])
        return [self._capture_entity(e) for e in qs]

    def describe_one(self, name):
        from apps.capture.models import CaptureEntry
        q = (name or "").strip()
        if not q:
            return None
        e = (CaptureEntry.objects.filter(user=self.user, title__icontains=q)
             .prefetch_related("extraction_signals").order_by("-created_at").first())
        return self._capture_entity(e) if e else None

    def _capture_entity(self, e):
        try:
            signals = list(e.extraction_signals.all())
        except Exception:
            signals = []
        return CompleteEntity(
            kind="capture",
            identity=e.title or f"Capture {str(e.id)[:8]}",
            definition={"category": e.category or None,
                        "subcategory": e.subcategory or None,
                        "source": "audio_recording",
                        "duration_seconds": e.duration_seconds},
            status=e.status,
            standing={"date": e.created_at.date().isoformat(),
                      "audio_available": bool(e.audio_file_url),
                      "error_message": e.error_message or None},
            performance={"has_transcript": bool(e.transcript),
                         "transcript": (e.transcript or "").strip() or None,
                         "summary": (e.summary or "").strip() or None},
            extensions={"linked_signals": {
                "count": len(signals),
                "domains": sorted({s.domain for s in signals}),
                "types": sorted({s.signal_type for s in signals})}} if signals else {},
            freshness=CURRENT,
        )
