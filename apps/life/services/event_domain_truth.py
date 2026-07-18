"""EventDomainTruth — canonical interface to SignificantEvent truth (Layer 1).

The ONLY SignificantEvent authority. Previously these records were surfaced only for
`event_type="birthday"` via the relationships provider — anniversaries, memorials,
milestones, holidays, and 'other' events, plus each event's description / original_year
/ linked person / custom_message, were invisible. This exposes every type and field.
Read-only; owns no new retrieval logic.
"""
from apps.core.truth.current import CurrentTruth
from apps.core.truth.domain import DomainTruth, register_domain_truth
from apps.core.truth.entity import CompleteEntity
from apps.core.truth.freshness import CURRENT, MISSING

_DOMAIN = "events"


@register_domain_truth
class EventDomainTruth(DomainTruth):
    domain = "events"
    current_metrics = ("upcoming_events",)
    history_metrics = ()
    entity_types = ("event",)

    def _all(self):
        from apps.life.models import SignificantEvent
        return SignificantEvent.objects.filter(user=self.user)

    def current(self, metric):
        if metric == "upcoming_events":
            rows = []
            for ev in self._all():
                days = ev.days_until_next()
                if days is not None and 0 <= days <= 30:
                    rows.append({"title": ev.title, "type": ev.event_type,
                                 "person": ev.person_name or None,
                                 "date": ev.get_next_occurrence().isoformat(),
                                 "days_until": days})
            rows.sort(key=lambda r: r["days_until"])
            if not rows:
                return CurrentTruth.absent(_DOMAIN, metric, MISSING, source="events",
                                           reason="no events in the next 30 days")
            return CurrentTruth.found(_DOMAIN, metric, len(rows), CURRENT,
                                      source="events", detail={"events": rows})
        raise KeyError(f"events current unsupported: {metric!r} "
                       f"(have {self.current_metrics})")

    def describe(self, entity_type="event"):
        if entity_type not in (None, "event"):
            raise KeyError(f"events cannot describe {entity_type!r} "
                           f"(have {self.entity_types})")
        return [self._event_entity(ev) for ev in self._all().order_by("event_date")]

    def describe_one(self, name):
        q = (name or "").strip().lower()
        if not q:
            return None
        for ev in self._all():
            if q in (ev.title or "").lower() or q in (ev.person_name or "").lower():
                return self._event_entity(ev)
        return None

    def _event_entity(self, ev):
        try:
            nxt = ev.get_next_occurrence()
            days = ev.days_until_next()
        except Exception:
            nxt, days = None, None
        person = None
        if ev.person_id:
            person = getattr(ev.person, "display_name", None) or str(ev.person)
        return CompleteEntity(
            kind="event",
            identity=ev.title,
            definition={"event_type": ev.event_type,
                        "event_type_label": ev.get_event_type_display(),
                        "event_date": ev.event_date.isoformat() if ev.event_date else None,
                        "original_year": ev.original_year,
                        "person": person or (ev.person_name or None)},
            status=("recurring" if getattr(ev, "reminder_days", None) is not None
                    else "recorded"),
            plan={"next_occurrence": nxt.isoformat() if nxt else None,
                  "days_until": days},
            extensions={k: v for k, v in {
                "description": (ev.description or "").strip() or None,
                "custom_message": (ev.custom_message or "").strip() or None,
            }.items() if v},
            freshness=CURRENT)
