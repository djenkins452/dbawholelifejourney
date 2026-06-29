"""
Domain rollout — thin DomainTruth providers for the remaining life domains so the
Executive Briefing is limited only by available TRUTH, not by missing registrations.

Each provider is a thin facade over the pre-computed SAE module state (read via
`DomainTruth.state()` → get_module_state) wrapped in `CurrentTruth`. No new queries,
no reasoning — pure retrieval, exactly like HealthDomainTruth/FinanceDomainTruth.
"""
from apps.core.truth import freshness as F
from apps.core.truth.current import CurrentTruth
from apps.core.truth.domain import DomainTruth, register_domain_truth


def _found(domain, metric, value, as_of=None):
    return CurrentTruth.found(domain, metric, value, F.CURRENT, as_of=as_of, source="sae")


def _absent(domain, metric, reason="no recent data"):
    return CurrentTruth.absent(domain, metric, reason=reason)


@register_domain_truth
class JournalDomainTruth(DomainTruth):
    domain = "journal"
    current_metrics = ("days_since_entry", "last_entry")

    def current(self, metric):
        st = self.state()
        if metric == "days_since_entry":
            v = st.get("days_since_entry")
            return _found(self.domain, metric, v, st.get("last_entry")) if v is not None \
                else _absent(self.domain, metric, "no journal entries")
        if metric == "last_entry":
            v = st.get("last_entry")
            return _found(self.domain, metric, v, v) if v else \
                _absent(self.domain, metric, "no journal entries")
        return _absent(self.domain, metric, "unsupported metric")


@register_domain_truth
class CalendarDomainTruth(DomainTruth):
    domain = "calendar"
    current_metrics = ("today_event_count", "next_event")

    def current(self, metric):
        st = self.state()
        if metric == "today_event_count":
            v = st.get("today_event_count")
            return _found(self.domain, metric, v) if v is not None \
                else _absent(self.domain, metric)
        if metric == "next_event":
            ne = st.get("next_event")
            if not ne:
                return _absent(self.domain, metric, "nothing upcoming today")
            label = (f"{ne.get('title')} at {ne.get('start')}"
                     if isinstance(ne, dict) else str(ne))
            return _found(self.domain, metric, label)
        return _absent(self.domain, metric, "unsupported metric")


@register_domain_truth
class TaskDomainTruth(DomainTruth):
    domain = "tasks"
    current_metrics = ("overdue_count", "tasks_due_today")

    def current(self, metric):
        st = self.state()
        if metric == "overdue_count":
            v = st.get("overdue_count")
            return _found(self.domain, metric, v) if v is not None \
                else _absent(self.domain, metric)
        if metric == "tasks_due_today":
            due = st.get("tasks_due_today")
            n = len(due) if isinstance(due, (list, tuple)) else (due or 0)
            return _found(self.domain, metric, n)
        return _absent(self.domain, metric, "unsupported metric")


@register_domain_truth
class FaithDomainTruth(DomainTruth):
    domain = "faith"
    current_metrics = ("reading_streak", "days_since_reading", "unanswered_prayers")

    def current(self, metric):
        st = self.state()
        v = st.get(metric)
        if v is None:
            return _absent(self.domain, metric)
        return _found(self.domain, metric, v, st.get("last_scripture_read"))


@register_domain_truth
class RelationshipDomainTruth(DomainTruth):
    domain = "relationships"
    current_metrics = ("neglected_count", "birthdays_today")

    def current(self, metric):
        contract = self.state().get("_contract") or {}
        summary = contract.get("summary") or {}
        today = contract.get("today") or {}
        if metric == "neglected_count":
            v = summary.get("neglected_count")
            return _found(self.domain, metric, v) if v is not None \
                else _absent(self.domain, metric)
        if metric == "birthdays_today":
            b = today.get("birthdays")
            n = len(b) if isinstance(b, (list, tuple)) else (b or 0)
            return _found(self.domain, metric, n)
        return _absent(self.domain, metric, "unsupported metric")
