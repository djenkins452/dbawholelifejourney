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
    current_metrics = ("days_since_entry", "last_entry", "themes")
    history_metrics = ("mood",)
    # Record-level truth: journal entries (title, body, MOOD, emotions, tags). Additive —
    # `describe()` delegates to the canonical JournalQueries authority (no new store).
    # This makes "what was my journal about yesterday?" / "what was my mood yesterday?"
    # answerable from JOURNAL truth, instead of a cross-domain search that surfaces
    # unrelated health metrics (defect 2026-07-17).
    entity_types = ("entry",)
    # ANALYSIS participation — PURE COMPOSITION of the two inputs ALREADY exposed above:
    # history('mood') (the deterministic mood series) + describe('entry') (dated entries
    # carrying text/mood/emotions/tags). The generic get_analysis composer reuses those;
    # it adds NO retrieval, NO new store, NO reasoning. WLJ supplies the evidence bundle;
    # the model summarizes / interprets / reflects / advises and identifies conversational
    # themes from the supplied entries. WLJ declares NO verdict — it never deterministically
    # calls anything healthy / concerning / positive / a commitment (that is the model's
    # reasoning). Every subject maps to the SAME (mood, entry) inputs; the varied keys are
    # only the natural phrasings the model reaches for (so it never invents an undeclared
    # subject → unsupported). Structured themes reach the model as the tags/emotions carried
    # ON each entry record — not as free-text extraction.
    analysis_subjects = {
        "journal":          {"history_metric": "mood", "entity_type": "entry"},
        "entries":          {"history_metric": "mood", "entity_type": "entry"},
        "journal_entries":  {"history_metric": "mood", "entity_type": "entry"},
        "summary":          {"history_metric": "mood", "entity_type": "entry"},
        "recent_journal":   {"history_metric": "mood", "entity_type": "entry"},
        "mood":             {"history_metric": "mood", "entity_type": "entry"},
        "trends":           {"history_metric": "mood", "entity_type": "entry"},
        "patterns":         {"history_metric": "mood", "entity_type": "entry"},
        "reflection":       {"history_metric": "mood", "entity_type": "entry"},
        "advice":           {"history_metric": "mood", "entity_type": "entry"},
        "gratitude":        {"history_metric": "mood", "entity_type": "entry"},
        "themes":           {"history_metric": "mood", "entity_type": "entry"},
        "positive_changes": {"history_metric": "mood", "entity_type": "entry"},
        "concerns":         {"history_metric": "mood", "entity_type": "entry"},
    }

    def current(self, metric):
        if metric == "themes":
            from apps.journal.services.journal_queries import JournalQueries
            tc = JournalQueries.theme_counts(self.user)
            if not (tc["tags"] or tc["emotions"]):
                return _absent(self.domain, metric, "no journal themes yet")
            return CurrentTruth.found(self.domain, metric, tc["repeated"], F.CURRENT,
                                      source="journal", detail=tc)
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

    def describe(self, entity_type="entry", filters=None):
        """Journal entries as CompleteEntity objects — "what did I write about", "what
        was my mood/emotions/tags". A `filters={period|start,end}` scopes to a window
        ('what have I written this week'). entity_type ∈ entry. JOURNAL truth only."""
        if entity_type not in (None, "entry"):
            raise KeyError(f"journal domain cannot describe {entity_type!r} "
                           f"(have {self.entity_types})")
        from apps.journal.services.journal_queries import JournalQueries
        f = filters or {}
        return JournalQueries.describe(self.user, period=f.get("period"),
                                       start=f.get("start"), end=f.get("end"))

    def describe_one(self, name):
        """The journal entry matching `name` (a date or title), or None."""
        from apps.journal.services.journal_queries import JournalQueries
        return JournalQueries.describe_one(self.user, name)

    def history(self, metric, period="last_7_days", **kwargs):
        """Per-day mood series — 'how has my mood changed recently'. Journal-only truth."""
        if metric != "mood":
            raise KeyError(f"journal history unsupported: {metric!r} "
                           f"(have {self.history_metrics})")
        from apps.journal.services.journal_queries import JournalQueries
        return JournalQueries.mood_series(self.user, period, **kwargs)


@register_domain_truth
class CalendarDomainTruth(DomainTruth):
    domain = "calendar"
    current_metrics = ("today_event_count", "next_event",
                       "tomorrow_event_count", "upcoming_count")
    history_metrics = ("events",)
    entity_types = ("event",)

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
        if metric == "tomorrow_event_count":
            from datetime import timedelta
            from apps.core.utils import get_user_today
            from apps.calendar_engine.services.calendar_queries import CalendarQueries
            tomorrow = get_user_today(self.user) + timedelta(days=1)
            return _found(self.domain, metric,
                          CalendarQueries.events_on_date(self.user, tomorrow).count())
        if metric == "upcoming_count":
            from apps.calendar_engine.services.calendar_queries import CalendarQueries
            return _found(self.domain, metric,
                          CalendarQueries.upcoming(self.user).count())
        return _absent(self.domain, metric, "unsupported metric")

    def history(self, metric, period="last_7_days", **kwargs):
        """Per-day scheduled/completed event COUNT — 'how many meetings last week'."""
        from django.db.models import Count
        from django.db.models.functions import TruncDate
        from apps.core.truth.history import series_from_rows
        from apps.core.truth.periods import resolve_period
        from apps.core.utils import get_user_today
        from apps.calendar_engine.services.calendar_queries import CalendarQueries
        if metric != "events":
            raise KeyError(f"calendar history unsupported: {metric!r}")
        p = resolve_period(period, get_user_today(self.user),
                           start=kwargs.get("start"), end=kwargs.get("end"))
        rows = (CalendarQueries.events_in_range(self.user, p.start, p.end)
                .annotate(d=TruncDate("start_dt")).values("d")
                .annotate(v=Count("id")).order_by("d"))
        return series_from_rows("calendar", metric, p,
            [{"date": r["d"], "value": r["v"]} for r in rows], unit="events")

    def describe(self, entity_type="event", filters=None):
        """Events as CompleteEntity objects. Deterministic scoping via filters:
          * on_date (ISO) — events that day ('what did I have last Tuesday').
          * period / start+end — events in a window.
        Unscoped: recent past + upcoming ('meetings coming up', 'recently completed')."""
        if entity_type not in (None, "event"):
            raise KeyError(f"calendar domain cannot describe {entity_type!r}")
        from datetime import date as _date
        from apps.calendar_engine.services.calendar_queries import CalendarQueries
        f = filters or {}
        if f.get("on_date"):
            d = f["on_date"]
            if isinstance(d, str):
                d = _date.fromisoformat(d[:10])
            return [self._event_entity(ev)
                    for ev in CalendarQueries.events_on_date(self.user, d)]
        if f.get("start") or f.get("end") or f.get("period"):
            from apps.core.truth.periods import resolve_period
            from apps.core.utils import get_user_today
            p = resolve_period(f.get("period") or "custom", get_user_today(self.user),
                               start=f.get("start"), end=f.get("end"))
            return [self._event_entity(ev)
                    for ev in CalendarQueries.events_in_range(self.user, p.start, p.end)]
        seen, out = set(), []
        for ev in (list(CalendarQueries.past(self.user, lookback_days=7))
                   + list(CalendarQueries.upcoming(self.user, horizon_days=14))):
            if ev.id in seen:
                continue
            seen.add(ev.id)
            out.append(self._event_entity(ev))
        return out

    def describe_one(self, name):
        from apps.calendar_engine.services.calendar_queries import CalendarQueries
        q = (name or "").strip()
        if not q:
            return None
        ev = (CalendarQueries._base(self.user)
              .filter(title__icontains=q).order_by("-start_dt").first())
        return self._event_entity(ev) if ev else None

    def _event_entity(self, ev):
        from apps.core.truth import freshness as F
        from apps.core.truth.entity import CompleteEntity
        rrule = getattr(ev, "recurrence", None)   # RecurrenceRule OneToOne or None
        recurrence = None
        if rrule is not None:
            recurrence = {"frequency": rrule.frequency, "interval": rrule.interval,
                          "byweekday": getattr(rrule, "byweekday", None),
                          "until": (rrule.until_dt.isoformat()
                                    if getattr(rrule, "until_dt", None) else None),
                          "count": getattr(rrule, "count", None),
                          "timezone": getattr(rrule, "timezone", None)}
        return CompleteEntity(
            kind="event",
            identity=ev.title,
            definition={
                "start": ev.start_dt.isoformat(),
                "end": ev.end_dt.isoformat(),
                "all_day": ev.is_all_day,
                "domain": ev.domain.name if ev.domain else "",
                "kind": ev.event_kind,
                "commitment_level": ev.commitment_level,
                "duration_minutes": getattr(ev, "duration_minutes", None),
                "source_type": ev.source_type,
                "is_projected": getattr(ev, "is_projected", None),
            },
            status=ev.status,
            standing={"is_protected": ev.is_protected},
            extensions={"description": ev.description or "",
                        "recurrence": recurrence,
                        "source_id": ev.source_id or None},
            freshness=F.CURRENT,
        )


@register_domain_truth
class TaskDomainTruth(DomainTruth):
    domain = "tasks"
    current_metrics = ("overdue_count", "tasks_due_today")
    history_metrics = ("completed",)
    entity_types = ("task",)

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

    def history(self, metric, period="this_week", **kwargs):
        """Per-day COMPLETED-task count — 'what have I accomplished this week'.
        Grouped on completed_at (momentum), not due_date."""
        from django.db.models import Count
        from django.db.models.functions import TruncDate
        from apps.core.truth.history import series_from_rows
        from apps.core.truth.periods import resolve_period
        from apps.core.utils import get_user_today
        from apps.life.services.task_queries import TaskQueries
        if metric != "completed":
            raise KeyError(f"tasks history unsupported: {metric!r}")
        p = resolve_period(period, get_user_today(self.user),
                           start=kwargs.get("start"), end=kwargs.get("end"))
        rows = (TaskQueries.completed_between(self.user, p.start, p.end)
                .annotate(d=TruncDate("completed_at")).values("d")
                .annotate(v=Count("id")).order_by("d"))
        return series_from_rows("tasks", metric, p,
            [{"date": r["d"], "value": r["v"]} for r in rows], unit="tasks")

    def describe(self, entity_type="task"):
        """Actionable tasks (overdue + due-today + recently completed) as
        CompleteEntity objects. NOTE: 'what should I work on NEXT' is NOT here — that
        is served only by decision_authority.current_action (single decision producer)."""
        if entity_type not in (None, "task"):
            raise KeyError(f"tasks domain cannot describe {entity_type!r}")
        from datetime import timedelta
        from apps.core.utils import get_user_today
        from apps.life.services.task_queries import TaskQueries
        today = get_user_today(self.user)
        seen, out = set(), []
        buckets = (list(TaskQueries.overdue(self.user, today))
                   + list(TaskQueries.due_today(self.user, today))
                   + list(TaskQueries.completed_between(
                       self.user, today - timedelta(days=1), today)))
        for t in buckets:
            if t.id in seen:
                continue
            seen.add(t.id)
            out.append(self._task_entity(t, today))
        return out

    def describe_one(self, name):
        from apps.life.models import Task
        from apps.core.utils import get_user_today
        q = (name or "").strip()
        if not q:
            return None
        t = (Task.objects.filter(user=self.user, title__icontains=q)
             .order_by("completion_status", "-completed_at", "due_date").first())
        return self._task_entity(t, get_user_today(self.user)) if t else None

    def _resolve_dependency(self, t):
        """depends_on_key as deterministic truth: the raw key + the dependent task's
        title/status when it maps to a real task (no second task authority)."""
        key = getattr(t, "depends_on_key", None)
        if not key:
            return None
        out = {"key": key, "hidden_until_ready": getattr(t, "hide_until_ready", None)}
        try:
            from apps.life.models import Task
            dep = None
            for fld in ("depends_on_key", "task_key", "key"):
                if any(f.name == fld for f in Task._meta.concrete_fields):
                    dep = Task.objects.filter(user=t.user, **{fld: key}).exclude(
                        pk=t.pk).first()
                    if dep:
                        break
            if dep is not None:
                out["task"] = dep.title
                out["task_status"] = dep.completion_status
        except Exception:
            pass
        return out

    def _task_entity(self, t, today):
        from apps.core.truth import freshness as F
        from apps.core.truth.entity import CompleteEntity
        overdue = (t.completion_status == "pending"
                   and t.due_date is not None and t.due_date < today)
        recurrence = None
        if getattr(t, "is_recurring", False):
            recurrence = {"pattern": t.recurrence_pattern,
                          "start_date": t.start_date.isoformat() if t.start_date else None,
                          "end_date": t.end_date.isoformat() if t.end_date else None}
        return CompleteEntity(
            kind="task",
            identity=t.title,
            definition={
                "due_date": t.due_date.isoformat() if t.due_date else None,
                "priority": t.priority,
                "commitment_level": t.commitment_level,
                "is_routine": t.is_routine,
                "project": (t.project.title if t.project_id else None),
                "module": t.module or None,
                "effort": getattr(t, "effort", None) or None,
                "is_foundational": t.is_foundational,
            },
            status=t.completion_status,
            standing={
                "overdue": overdue,
                "progress_percentage": t.progress_percentage,
                "completed_at": t.completed_at.isoformat() if t.completed_at else None,
                "skip_streak": getattr(t, "effective_skip_streak", None),
            },
            extensions={k: v for k, v in {
                "notes": t.notes or "",
                "scheduled_time": (t.scheduled_time.isoformat()
                                   if getattr(t, "scheduled_time", None) else None),
                "scheduled_end_time": (t.scheduled_end_time.isoformat()
                                       if getattr(t, "scheduled_end_time", None) else None),
                "estimated_duration_minutes": getattr(t, "estimated_duration_minutes", None),
                "recurrence": recurrence,
                "progress_state": getattr(t, "progress_state", None) or None,
                "depends_on": self._resolve_dependency(t),
            }.items() if v not in (None, "")},
            freshness=F.CURRENT,
        )


@register_domain_truth
class FaithDomainTruth(DomainTruth):
    domain = "faith"
    current_metrics = ("reading_streak", "days_since_reading", "unanswered_prayers",
                       "studying")
    history_metrics = ("reading",)
    # Record-level truth. prayer + reading_plan are the composed authorities; milestone /
    # saved_verse / study_note / highlight / bookmark expose the remaining user-owned faith
    # records (salvation/baptism moments, memory verses, study notes, highlights, bookmarks)
    # that had records but no `get_entity` surface — additive exposure, delegating to the
    # canonical FaithQueries composers (no new store, no reasoning).
    entity_types = ("prayer", "reading_plan", "milestone", "saved_verse",
                    "study_note", "highlight", "bookmark")
    # ANALYSIS participation — PURE COMPOSITION of inputs ALREADY exposed above: the
    # deterministic reading-completion series (history('reading')) + the prayer / reading_plan
    # entity records. The generic get_analysis composer reuses those; it adds NO retrieval,
    # NO new store, NO reasoning. WLJ supplies the evidence bundle; the model summarizes /
    # interprets / advises — WLJ declares NO verdict (it never calls a faith practice
    # consistent / faithful / lacking; that is the model's reasoning). Study-oriented subjects
    # carry the reading_plan record; prayer-oriented subjects carry the prayer record. Every
    # subject maps to the SAME reading series (the domain's only history metric — mirrors how
    # journal maps every subject to 'mood'); the varied keys are just the natural phrasings the
    # model reaches for, so it never invents an undeclared subject → unsupported.
    analysis_subjects = {
        "faith":                {"history_metric": "reading", "entity_type": "reading_plan"},
        "bible_reading":        {"history_metric": "reading", "entity_type": "reading_plan"},
        "scripture":            {"history_metric": "reading", "entity_type": "reading_plan"},
        "reading":              {"history_metric": "reading", "entity_type": "reading_plan"},
        "reading_consistency":  {"history_metric": "reading", "entity_type": "reading_plan"},
        "study":                {"history_metric": "reading", "entity_type": "reading_plan"},
        "devotion":             {"history_metric": "reading", "entity_type": "reading_plan"},
        "habits":               {"history_metric": "reading", "entity_type": "reading_plan"},
        "spiritual_life":       {"history_metric": "reading", "entity_type": "prayer"},
        "prayer":               {"history_metric": "reading", "entity_type": "prayer"},
        "prayers":              {"history_metric": "reading", "entity_type": "prayer"},
        "prayer_life":          {"history_metric": "reading", "entity_type": "prayer"},
        "faith_journey":        {"history_metric": "reading", "entity_type": "prayer"},
    }

    def current(self, metric):
        if metric == "studying":
            from apps.faith.services.faith_queries import FaithQueries
            plans = list(FaithQueries.active_reading_plans(self.user))
            if not plans:
                return _absent(self.domain, metric, "no active reading plan")
            # Name plans by their TEMPLATE TITLE (the field is `title`, not `name`) — never
            # str(pl), whose UserReadingPlan.__str__ is "user@email: Title" and leaked the
            # email while mis-naming the plan (Faith cert Step 1, Finding B).
            names = [(getattr(getattr(pl, "template", None), "title", None) or "Reading plan")
                     for pl in plans]
            return CurrentTruth.found(self.domain, metric, names[0], F.CURRENT,
                                      source="faith", detail={"plans": names})
        st = self.state()
        v = st.get(metric)
        if v is None:
            return _absent(self.domain, metric)
        return _found(self.domain, metric, v, st.get("last_scripture_read"))

    def describe(self, entity_type="prayer"):
        """Faith record-level truth. entity_type ∈ prayer | reading_plan | milestone |
        saved_verse | study_note | highlight | bookmark. Prayers → 'what have I been
        praying about'; reading plans → 'what am I studying' with progress/current-reading;
        milestones → 'my baptism / salvation'; saved_verse → 'my memory verses'; study_note
        → 'my notes on Romans 8'; highlight / bookmark → passages I marked. Faith truth
        only — every branch delegates to the canonical FaithQueries composer."""
        from apps.faith.services.faith_queries import FaithQueries
        dispatch = {
            "reading_plan": FaithQueries.describe_plans,
            "milestone": FaithQueries.describe_milestones,
            "saved_verse": FaithQueries.describe_saved_verses,
            "study_note": FaithQueries.describe_study_notes,
            "highlight": FaithQueries.describe_highlights,
            "bookmark": FaithQueries.describe_bookmarks,
        }
        if entity_type in dispatch:
            return dispatch[entity_type](self.user)
        if entity_type not in (None, "prayer"):
            raise KeyError(f"faith domain cannot describe {entity_type!r} "
                           f"(have {self.entity_types})")
        return FaithQueries.describe(self.user)

    def describe_one(self, name):
        """Resolve a NAMED faith record. Reading plan first (by template title, across ALL
        plans), then prayer (dedicated title search), then the remaining entity types via the
        shared identity resolver — which reuses each type's own describe() so a by-name hit
        returns the SAME complete object as the list path, for every type (no parallel
        retrieval logic)."""
        from apps.faith.services.faith_queries import FaithQueries
        plan = FaithQueries.describe_plan_one(self.user, name)
        if plan is not None:
            return plan
        prayer = FaithQueries.describe_one(self.user, name)
        if prayer is not None:
            return prayer
        return self._entity_by_identity(
            name, ("milestone", "saved_verse", "study_note", "highlight", "bookmark"))

    def history(self, metric, period="last_7_days", **kwargs):
        """Per-day Bible-reading completion — 'how consistent has my reading been'."""
        if metric != "reading":
            raise KeyError(f"faith history unsupported: {metric!r} "
                           f"(have {self.history_metrics})")
        from apps.faith.services.faith_queries import FaithQueries
        return FaithQueries.reading_series(self.user, period, **kwargs)


@register_domain_truth
class RelationshipDomainTruth(DomainTruth):
    domain = "relationships"
    current_metrics = ("neglected_count", "birthdays_today", "upcoming_birthdays",
                       "most_connected")
    # Record-level truth over the REAL relationships.Person (interaction analytics live
    # there). Answers "tell me about Heather", "when did I last spend time with Heather",
    # "most important people" (by interaction volume), "who have I not connected with".
    entity_types = ("person",)

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
        if metric == "upcoming_birthdays":
            return self._upcoming_birthdays()
        if metric == "most_connected":
            from apps.relationships.services import RelationshipAnalyticsService as R
            people = list(R.top_interacted(self.user, limit=5))
            if not people:
                return _absent(self.domain, metric, "no people yet")
            return CurrentTruth.found(
                self.domain, metric, [p.get_display_name() for p in people],
                F.CURRENT, source="relationships",
                detail={"people": [
                    {"name": p.get_display_name(),
                     "interaction_count": p.interaction_count,
                     "last_contact": p.last_interaction_date.isoformat()
                     if p.last_interaction_date else None} for p in people]})
        return _absent(self.domain, metric, "unsupported metric")

    def _upcoming_birthdays(self, within_days=14):
        # Reads life.SignificantEvent directly — the _contract birthday path reads a
        # nonexistent attribute and is always empty (state_builder defect); this uses
        # the real days_until_next()/get_next_occurrence() methods.
        from apps.life.models import SignificantEvent
        upcoming = []
        for ev in SignificantEvent.objects.filter(user=self.user, event_type="birthday"):
            days = ev.days_until_next()
            if days is not None and 0 <= days <= within_days:
                upcoming.append({"name": ev.person_name or ev.title,
                                 "date": ev.get_next_occurrence().isoformat(),
                                 "days_until": days})
        upcoming.sort(key=lambda e: e["days_until"])
        if not upcoming:
            return _absent(self.domain, "upcoming_birthdays",
                           f"no birthdays in the next {within_days} days")
        return _found(self.domain, "upcoming_birthdays", upcoming)

    def describe(self, entity_type="person"):
        if entity_type not in (None, "person"):
            raise KeyError(f"relationships domain cannot describe {entity_type!r} "
                           f"(have {self.entity_types})")
        from apps.relationships.models import Person
        people = (Person.objects.filter(owner=self.user)
                  .order_by("-interaction_count", "-last_interaction_date"))
        return [self._person_entity(p) for p in people]

    def describe_one(self, name):
        from apps.relationships.models import Person
        norm = (name or "").strip().lower()
        if not norm:
            return None
        matches = [p for p in Person.objects.filter(owner=self.user)
                   if norm in (p.get_display_name().lower(),
                               (p.first_name or "").lower())]
        if len(matches) != 1:        # 0 = unresolved, >1 = ambiguous → never guess
            return None
        # Single-person lookup → the FULL cross-WLJ composition ("everything about X").
        return self._person_entity(matches[0], full=True)

    def _person_entity(self, p, full=False):
        from apps.core.truth.entity import CompleteEntity
        from apps.relationships.models import RelationshipInteraction
        from apps.relationships.services import RelationshipAnalyticsService as R
        last = p.last_interaction_date
        days_since = R.days_since_last_interaction(p)
        rtype = (p.relationship_type or "").strip()
        recent = list(RelationshipInteraction.objects.filter(person=p)
                      .order_by("-interaction_date")[:10])
        interactions = [{"date": i.interaction_date.isoformat(),
                         "context": i.context_type_label,
                         "title": (getattr(i.source_object, "title", None)
                                   or getattr(i.source_object, "name", None))}
                        for i in recent]
        definition = {
            "name": p.get_display_name(),
            "relationship_type": p.get_relationship_type_display() if rtype else None,
            "email": p.email or None,
            "phone": p.phone or None,
            "household": (p.household.name if p.household_id else None),
            "groups": [{"name": g.name,
                        "description": (getattr(g, "description_plain", None)
                                        or getattr(g, "description", None) or None)}
                       for g in p.groups.all()],
            "last_contact": last.isoformat() if last else None,
            "days_since_contact": days_since,
            "interaction_count": p.interaction_count,
            "notes": p.notes_plain or None,
        }
        standing = {"recent_interactions": interactions}
        extensions = {}
        if full:
            # Compose the person's footprint ACROSS WLJ from deterministic truth:
            # interactions grouped by domain-context (journal/task/meal/event →
            # "journal entries mentioning X", "what we're working on", "events with X"),
            # legacy memories they appear in, and their upcoming birthday.
            extensions = self._compose_person_footprint(p)
        return CompleteEntity(
            kind="person",
            identity=p.get_display_name(),
            definition={k: v for k, v in definition.items() if v is not None},
            status=("neglected" if days_since is not None and days_since > 30
                    else ("never_contacted" if last is None else "active")),
            standing=standing,
            performance={"interaction_count": p.interaction_count,
                         "days_since_contact": days_since},
            extensions=extensions,
            freshness=F.CURRENT,
        )

    def _compose_person_footprint(self, p):
        """Deterministic cross-WLJ truth about ONE person (bounded queries)."""
        from collections import defaultdict
        from apps.relationships.models import RelationshipInteraction
        name = p.get_display_name()
        # Interactions grouped by context, with the source record's title.
        by_ctx = defaultdict(list)
        for i in (RelationshipInteraction.objects.filter(person=p)
                  .select_related("content_type").order_by("-interaction_date")[:50]):
            obj = None
            try:
                obj = i.source_object
            except Exception:
                obj = None
            title = (getattr(obj, "title", None) or getattr(obj, "name", None)
                     or (str(obj) if obj is not None else None))
            by_ctx[i.context_type_label].append(
                {"date": i.interaction_date.isoformat(), "title": title})
        footprint = {"interactions_by_context": dict(by_ctx)}
        footprint["journal_entries"] = by_ctx.get("journal", [])
        footprint["events"] = by_ctx.get("event", [])
        # Legacy memories the person appears in (matched by display name) + the PLACES
        # those shared memories happened at ("trips / places you've been together").
        first = name.split()[0]
        try:
            from apps.legacy.models import Memory
            mems = list(Memory.objects.filter(user=self.user,
                                              people__display_name__icontains=first)
                        .prefetch_related("places").distinct().order_by("-created_at")[:25])
            footprint["memories"] = [m.title or "(untitled)" for m in mems]
            places = []
            for m in mems:
                for pl in m.places.all():
                    if pl.name not in places:
                        places.append(pl.name)
            footprint["shared_places"] = places
        except Exception:
            footprint["memories"] = []
            footprint["shared_places"] = []
        # The user's GOALS that mention this person (text-match across goal fields —
        # no goal↔person FK exists; this is the deterministic 'goals involving X').
        try:
            from apps.purpose.models import LifeGoal
            from django.db.models import Q
            first = name.split()[0]
            goals = (LifeGoal.all_objects.filter(user=self.user).filter(
                Q(title__icontains=first) | Q(why_it_matters_plain__icontains=first)
                | Q(success_looks_like_plain__icontains=first)
                | Q(motivation_note_plain__icontains=first)
                | Q(description_plain__icontains=first))[:15])
            footprint["goals"] = [g.title for g in goals]
        except Exception:
            footprint["goals"] = []
        # Their upcoming birthday, if recorded.
        try:
            from apps.life.models import SignificantEvent
            ev = SignificantEvent.objects.filter(
                user=self.user, event_type="birthday",
                person_name__icontains=name.split()[0]).first()
            if ev is not None:
                footprint["birthday"] = {"date": ev.get_next_occurrence().isoformat(),
                                         "days_until": ev.days_until_next()}
        except Exception:
            pass
        return footprint


@register_domain_truth
class NutritionDomainTruth(DomainTruth):
    """Record-level nutrition truth: the actual FOODS the user logged. Additive entity
    surface (delegates to the canonical NutritionQueries authority). Nutrition
    AGGREGATES (calorie/protein targets, daily totals) already reach the model via
    get_foundational_health_facts / get_domain_state; this exposes the food ITEMS so
    "what have I eaten?" and personalized menus reason from real foods, not generic
    knowledge (personalization defect, 2026-07-17). Distinct registry from
    get_domain_state('nutrition') — this cannot change that path."""
    domain = "nutrition"
    # `food` = individual logged items; `meal` = the deterministic grouping of a day's
    # foods by meal_type (breakfast/lunch/dinner/snack); `frequent_food` = foods ranked
    # by how often they were logged. All REUSE the canonical NutritionQueries producers
    # (no new store, no duplicate aggregation) so the CoS answers the unit people speak
    # in — "my last meal", "everything I ate last Tuesday", "what do I eat most".
    entity_types = ("food", "meal", "frequent_food")
    # Per-day macro totals over a period → the generic get_history tool now answers
    # date-scoped totals ("calories yesterday") and windowed averages ("average
    # protein this week"). Delegates to the canonical NutritionQueries authority; no
    # new store. (No current() — there is no generic current-fact tool for nutrition;
    # today's running totals reach the model via get_domain_state('nutrition').)
    history_metrics = ("calories", "protein", "carbs", "fat", "fiber", "sugar")
    # ANALYSIS participation — PURE COMPOSITION of the History (macro series) + Entity
    # (meal) surfaces above; the Analysis surface adds NO retrieval. Each subject maps
    # to an existing history_metric + the meal entity for record detail, so the model
    # receives the complete deterministic evidence bundle to summarize / spot trends /
    # advise / judge "healthiest" — WLJ never interprets. (No new truth; every input
    # is already exposed. Food FREQUENCY is deliberately NOT here — it is a distinct
    # aggregate, exposed as the `frequent_food` entity.)
    # Subject keys include the natural phrasings the model reaches for ("intake",
    # "eating_habits", "diet"…) — all mapping to the SAME existing composition
    # (calorie history + meal records). Aliases are free (declaration-only); they cost
    # nothing and stop the model from inventing an undeclared subject → unsupported.
    analysis_subjects = {
        "nutrition":       {"history_metric": "calories", "entity_type": "meal"},
        "intake":          {"history_metric": "calories", "entity_type": "meal"},
        "recent_nutrition": {"history_metric": "calories", "entity_type": "meal"},
        "eating_habits":   {"history_metric": "calories", "entity_type": "meal"},
        "diet":            {"history_metric": "calories", "entity_type": "meal"},
        "macros":          {"history_metric": "calories", "entity_type": "meal"},
        "calories":        {"history_metric": "calories", "entity_type": "meal"},
        "protein":         {"history_metric": "protein",  "entity_type": "meal"},
        "carbs":           {"history_metric": "carbs",     "entity_type": "meal"},
        "fat":             {"history_metric": "fat",       "entity_type": "meal"},
        "meals":           {"history_metric": "calories",  "entity_type": "meal"},
    }

    def history(self, metric, period="last_7_days", **kwargs):
        from apps.health.services.nutrition_queries import NutritionQueries
        return NutritionQueries.macro_series(self.user, metric, period, **kwargs)

    def describe(self, entity_type="food", filters=None):
        from apps.health.services.nutrition_queries import NutritionQueries
        f = filters or {}
        if entity_type == "meal":
            return NutritionQueries.describe_meals(
                self.user, meal=f.get("meal"), on_date=f.get("on_date"),
                period=f.get("period"), start=f.get("start"), end=f.get("end"))
        if entity_type == "frequent_food":
            return NutritionQueries.top_foods(
                self.user, period=f.get("period"),
                start=f.get("start"), end=f.get("end"))
        if entity_type in (None, "food"):
            return NutritionQueries.describe(
                self.user, meal=f.get("meal"), period=f.get("period"),
                start=f.get("start"), end=f.get("end"), contains=f.get("contains"))
        raise KeyError(f"nutrition domain cannot describe {entity_type!r} "
                       f"(have {self.entity_types})")

    def describe_one(self, name):
        """By-name meal/food lookup. Meal-type names ('breakfast'…) and 'last meal'
        resolve to the most recent matching MEAL (reusing describe_meals); anything
        else is a food-name lookup — so 'what did I have for dinner' and 'what was my
        last meal' both return the SAME complete object the list path returns."""
        from apps.health.services.nutrition_queries import NutritionQueries
        n = (name or "").strip().lower()
        if n in ("breakfast", "lunch", "dinner", "snack"):
            meals = NutritionQueries.describe_meals(self.user, meal=n)
            return meals[0] if meals else None
        if n in ("last meal", "latest meal", "most recent meal", "my last meal"):
            meals = NutritionQueries.describe_meals(self.user)
            return meals[0] if meals else None
        return NutritionQueries.describe_one(self.user, name)
