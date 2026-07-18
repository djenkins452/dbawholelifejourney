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
            },
            status=ev.status,
            standing={"is_protected": ev.is_protected},
            extensions={"description": ev.description or ""},
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

    def _task_entity(self, t, today):
        from apps.core.truth import freshness as F
        from apps.core.truth.entity import CompleteEntity
        overdue = (t.completion_status == "pending"
                   and t.due_date is not None and t.due_date < today)
        return CompleteEntity(
            kind="task",
            identity=t.title,
            definition={
                "due_date": t.due_date.isoformat() if t.due_date else None,
                "priority": t.priority,
                "commitment_level": t.commitment_level,
                "is_routine": t.is_routine,
            },
            status=t.completion_status,
            standing={
                "overdue": overdue,
                "progress_percentage": t.progress_percentage,
                "completed_at": t.completed_at.isoformat() if t.completed_at else None,
            },
            extensions={"notes": t.notes or ""},
            freshness=F.CURRENT,
        )


@register_domain_truth
class FaithDomainTruth(DomainTruth):
    domain = "faith"
    current_metrics = ("reading_streak", "days_since_reading", "unanswered_prayers",
                       "studying")
    history_metrics = ("reading",)
    entity_types = ("prayer",)

    def current(self, metric):
        if metric == "studying":
            from apps.faith.services.faith_queries import FaithQueries
            plans = list(FaithQueries.active_reading_plans(self.user))
            if not plans:
                return _absent(self.domain, metric, "no active reading plan")
            names = [getattr(getattr(pl, "template", None), "name", None) or str(pl)
                     for pl in plans]
            return CurrentTruth.found(self.domain, metric, names[0], F.CURRENT,
                                      source="faith", detail={"plans": names})
        st = self.state()
        v = st.get(metric)
        if v is None:
            return _absent(self.domain, metric)
        return _found(self.domain, metric, v, st.get("last_scripture_read"))

    def describe(self, entity_type="prayer"):
        """Recent prayer requests as CompleteEntity objects — 'what have I been
        praying about'. Faith truth only."""
        if entity_type not in (None, "prayer"):
            raise KeyError(f"faith domain cannot describe {entity_type!r} "
                           f"(have {self.entity_types})")
        from apps.faith.services.faith_queries import FaithQueries
        return FaithQueries.describe(self.user)

    def describe_one(self, name):
        from apps.faith.services.faith_queries import FaithQueries
        return FaithQueries.describe_one(self.user, name)

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
                         "context": i.context_type_label} for i in recent]
        definition = {
            "name": p.get_display_name(),
            "relationship_type": p.get_relationship_type_display() if rtype else None,
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
    entity_types = ("food",)
    # Per-day macro totals over a period → the generic get_history tool now answers
    # date-scoped totals ("calories yesterday") and windowed averages ("average
    # protein this week"). Delegates to the canonical NutritionQueries authority; no
    # new store. (No current() — there is no generic current-fact tool for nutrition;
    # today's running totals reach the model via get_domain_state('nutrition').)
    history_metrics = ("calories", "protein", "carbs", "fat", "fiber", "sugar")

    def history(self, metric, period="last_7_days", **kwargs):
        from apps.health.services.nutrition_queries import NutritionQueries
        return NutritionQueries.macro_series(self.user, metric, period, **kwargs)

    def describe(self, entity_type="food", filters=None):
        if entity_type not in (None, "food"):
            raise KeyError(f"nutrition domain cannot describe {entity_type!r} "
                           f"(have {self.entity_types})")
        from apps.health.services.nutrition_queries import NutritionQueries
        f = filters or {}
        return NutritionQueries.describe(
            self.user, meal=f.get("meal"), period=f.get("period"),
            start=f.get("start"), end=f.get("end"), contains=f.get("contains"))

    def describe_one(self, name):
        from apps.health.services.nutrition_queries import NutritionQueries
        return NutritionQueries.describe_one(self.user, name)
