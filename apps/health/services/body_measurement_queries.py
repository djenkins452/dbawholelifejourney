"""Record-level truth for body-composition CHECK-INS. One CompleteEntity per
BodyMeasurementSession; performance carries {metric_name: value} for that session's
entries. Individual BodyCompositionEntry rows remain canonical (per-metric history
lives on HealthDomainTruth) — the session only GROUPS them ("all measurements taken
on date X"), which had no entity surface."""
from apps.core.truth.entity import CompleteEntity
from apps.core.truth.freshness import CURRENT


class BodyMeasurementQueries:

    @staticmethod
    def describe(user):
        from apps.health.models import BodyMeasurementSession
        out = []
        qs = (BodyMeasurementSession.objects.filter(user=user, status="active")
              .prefetch_related("entries").order_by("-checked_in_at"))
        for s in qs:
            entries = [e for e in s.entries.all()
                       if getattr(e, "status", "active") == "active"]
            performance = {e.metric_name: float(e.value) for e in entries}
            when = s.checked_in_at.date().isoformat() if s.checked_in_at else None
            out.append(CompleteEntity(
                kind="body_measurement",
                identity=(s.title or f"Check-in {when or s.pk}"),
                definition={"date": when, "title": s.title or None,
                            "source": s.source or None},
                status="active",
                performance=performance,
                extensions={"notes": s.notes} if s.notes else {},
                freshness=CURRENT,
            ))
        return out
