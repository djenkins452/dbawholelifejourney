"""HabitDomainTruth — canonical interface to Habits truth.

Thin facade over HabitQueries + HabitGoal model properties + streak_service + the
nightly-composed 'habits' SAE snapshot. Read-only; owns no new retrieval logic.
HabitGoal ("HabitGoal" is the habit model) had a full model and a streak authority but
ZERO truth-layer plumbing — this exposes it.
"""
from apps.core.truth import freshness as F
from apps.core.truth.current import CurrentTruth
from apps.core.truth.domain import DomainTruth, register_domain_truth
from apps.core.truth.entity import CompleteEntity
from apps.core.truth.history import series_from_rows
from apps.core.truth.periods import resolve_period

_DOMAIN = "habits"


def _today(user):
    from apps.core.utils import get_user_today
    return get_user_today(user)


@register_domain_truth
class HabitDomainTruth(DomainTruth):
    domain = "habits"
    current_metrics = ("active_habits",)
    history_metrics = ("consistency",)
    entity_types = ("habit",)
    analysis_subjects = {
        "habits": {"entity_type": "habit", "history_metric": "consistency"},
    }

    def current(self, metric):
        from apps.life.services.habit_queries import HabitQueries
        if metric == "active_habits":
            habits = list(HabitQueries.active(self.user)
                          .order_by("-is_foundational", "-start_date", "name"))
            if not habits:
                return CurrentTruth.absent(_DOMAIN, metric, F.MISSING,
                                           source="habit_queries",
                                           reason="no active habits")
            from apps.purpose.services.streak_service import get_streak_data
            rows = []
            for h in habits:
                sd = get_streak_data(h)
                rows.append({"name": h.name, "measurement_type": h.measurement_type,
                             "frequency_type": h.frequency_type,
                             "is_foundational": h.is_foundational,
                             "current_streak": sd.current, "longest_streak": sd.longest,
                             "at_risk": sd.at_risk,
                             "completion_rate": round(h.completion_rate, 1)})
            return CurrentTruth.found(
                _DOMAIN, metric, len(habits), F.CURRENT, source="habit_queries",
                detail={"names": [h.name for h in habits], "habits": rows})
        raise KeyError(f"habits current unsupported: {metric!r} "
                       f"(have {self.current_metrics})")

    def history(self, metric, period="last_month", **kwargs):
        if metric != "consistency":
            raise KeyError(f"habits history unsupported: {metric!r} "
                           f"(have {self.history_metrics})")
        from django.db.models import Count
        from apps.purpose.models import HabitEntry
        p = resolve_period(period, _today(self.user),
                           start=kwargs.get("start"), end=kwargs.get("end"))
        qs = HabitEntry.objects.filter(completed=True, date__range=(p.start, p.end))
        habit = kwargs.get("habit")
        if habit is not None:
            qs = qs.filter(goal=habit)
        else:
            qs = qs.filter(goal__user=self.user, goal__status="active")
        rows = qs.values("date").annotate(value=Count("id")).order_by("date")
        return series_from_rows(
            _DOMAIN, metric, p,
            [{"date": r["date"], "value": r["value"]} for r in rows], unit="completions")

    def describe(self, entity_type="habit"):
        if entity_type not in (None, "habit"):
            raise KeyError(f"habits domain cannot describe {entity_type!r} "
                           f"(have {self.entity_types})")
        from apps.life.services.habit_queries import HabitQueries
        return [self._habit_entity(h) for h in
                HabitQueries.active(self.user).prefetch_related("goal_links__goal")]

    def describe_one(self, name):
        from apps.purpose.models import HabitGoal
        q = (name or "").strip()
        if not q:
            return None
        h = (HabitGoal.all_objects.filter(user=self.user, name__icontains=q)
             .order_by("status", "-start_date")
             .prefetch_related("goal_links__goal").first())
        return self._habit_entity(h) if h else None

    def _habit_entity(self, h):
        from apps.purpose.services.streak_service import get_streak_data
        sd = get_streak_data(h)
        last_entry = (h.habit_entries.filter(completed=True)
                      .order_by("-date").values_list("date", flat=True).first())
        definition = {
            "purpose": (h.purpose or "").strip(),
            "description": (h.description or "").strip(),
            "success_criteria": (h.success_criteria or "").strip(),
            "category": h.category or None,
            "measurement_type": h.measurement_type,
            "frequency_type": h.frequency_type,
            "target_value": float(h.target_value) if h.target_value is not None else None,
            "target_unit": h.target_unit_display or None,
            "sessions_per_week": h.sessions_per_week,
            "commitment_level": h.commitment_level,
            "is_foundational": h.is_foundational,
            "domain": getattr(h.domain, "name", None),
        }
        performance = {
            "completion_rate_percent": round(h.completion_rate, 1),
            "completed_days": h.completed_days,
            "last_completed": last_entry.isoformat() if last_entry else None,
        }
        return CompleteEntity(
            kind="habit", identity=h.name, status=h.status,
            definition=definition,
            plan={"start_date": h.start_date.isoformat() if h.start_date else None,
                  "end_date": h.end_date.isoformat() if h.end_date else None,
                  "total_days": h.total_days},
            standing={"current_streak": sd.current, "longest_streak": sd.longest,
                      "at_risk": sd.at_risk,
                      "streak_start_date": (sd.streak_start_date.isoformat()
                                            if sd.streak_start_date else None),
                      "elapsed_days": h.elapsed_days},
            performance=performance,
            extensions={"linked_goals": [gl.goal.title for gl in h.goal_links.all()]},
            freshness=F.CURRENT)
