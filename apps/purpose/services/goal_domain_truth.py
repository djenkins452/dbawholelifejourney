"""GoalDomainTruth — canonical interface to Goals/Missions truth.

Thin facade over existing purpose authorities: GoalQueries, select_active_mission_goal
/ _mission_facts, LifeGoal milestone properties, and the nightly GoalMomentumSnapshot.
Owns NO new retrieval logic. Read-only; never recomputes momentum on the request path.
"""
from apps.core.truth.current import CurrentTruth
from apps.core.truth.domain import DomainTruth, register_domain_truth
from apps.core.truth.entity import CompleteEntity
from apps.core.truth.freshness import CURRENT, MISSING
from apps.core.truth.history import series_from_rows
from apps.core.truth.periods import resolve_period

_DOMAIN = "goals"


def _today(user):
    from apps.core.utils import get_user_today
    return get_user_today(user)


def annual_direction_dict(ad):
    """Full AnnualDirection truth (not a 2-field stub). Reused by goals + habits."""
    if ad is None:
        return None
    g = lambda a: getattr(ad, a, None)
    return {"year": g("year"), "word_of_year": g("word_of_year"),
            "word_explanation": (g("word_explanation") or "").strip() or None,
            "theme": g("theme") or None,
            "theme_description": (g("theme_description") or "").strip() or None,
            "anchor_text": (g("anchor_text") or "").strip() or None,
            "anchor_source": g("anchor_source") or None,
            "is_current": g("is_current")}


@register_domain_truth
class GoalDomainTruth(DomainTruth):
    domain = "goals"
    current_metrics = ("active_goals", "primary_mission", "completion_rate",
                       "milestones_overdue", "milestones_completed")
    history_metrics = ("progress", "momentum")
    entity_types = ("goal", "milestone", "annual_direction")
    analysis_subjects = {
        "goals":   {"entity_type": "goal", "history_metric": "progress"},
        "mission": {"entity_type": "goal", "history_metric": "momentum"},
    }

    # ── CURRENT ──────────────────────────────────────────────────────────
    def current(self, metric):
        from apps.purpose.services.goal_queries import GoalQueries

        if metric == "active_goals":
            goals = list(GoalQueries.active(self.user).order_by(
                "-is_primary_mission", "-is_foundational", "sort_order"))
            if not goals:
                return CurrentTruth.absent(_DOMAIN, metric, MISSING,
                                           source="goal_queries", reason="no active goals")
            return CurrentTruth.found(
                _DOMAIN, metric, len(goals), CURRENT, source="goal_queries",
                detail={"titles": [g.title for g in goals],
                        "goals": [{"title": g.title,
                                   "is_primary_mission": g.is_primary_mission,
                                   "target_date": g.target_date.isoformat()
                                   if g.target_date else None,
                                   "progress_percent": g.milestone_progress_percent}
                                  for g in goals]})

        if metric == "primary_mission":
            from apps.purpose.mission_selection import select_active_mission_goal
            from apps.purpose.mission_link import _mission_facts
            goal = select_active_mission_goal(self.user)
            if goal is None:
                return CurrentTruth.absent(_DOMAIN, metric, MISSING,
                                           source="mission_selection",
                                           reason="no primary mission selected")
            facts = _mission_facts(goal, _today(self.user))
            return CurrentTruth.found(_DOMAIN, metric, facts["title"], CURRENT,
                                      source="mission_selection", detail=facts)

        if metric == "completion_rate":
            from apps.purpose.models import GoalMilestone
            ms = GoalMilestone.objects.filter(goal__in=GoalQueries.active(self.user))
            total = ms.count()
            if total == 0:
                return CurrentTruth.absent(_DOMAIN, metric, MISSING,
                                           source="goal_queries",
                                           reason="no milestones on active goals")
            done = ms.filter(completed=True).count()
            return CurrentTruth.found(
                _DOMAIN, metric, round(done / total, 2), CURRENT, unit="fraction",
                source="goal_queries",
                detail={"completed_milestones": done, "total_milestones": total,
                        "percent": round(done / total * 100)})

        if metric == "milestones_overdue":
            overdue = list(GoalQueries.overdue_milestones(self.user))
            return CurrentTruth.found(
                _DOMAIN, metric, len(overdue),
                CURRENT if overdue else MISSING, source="goal_queries",
                detail={"milestones": [{"goal": m.goal.title, "title": m.title,
                                        "target_date": m.target_date.isoformat(),
                                        "days_overdue": -(m.days_until_due or 0)}
                                       for m in overdue]})

        if metric == "milestones_completed":
            done = list(GoalQueries.completed_milestones(self.user)
                        .select_related("goal").order_by("-completed_date"))
            return CurrentTruth.found(
                _DOMAIN, metric, len(done),
                CURRENT if done else MISSING, source="goal_queries",
                detail={"milestones": [
                    {"goal": m.goal.title, "title": m.title,
                     "completed_date": m.completed_date.isoformat()
                     if m.completed_date else None} for m in done]})

        raise KeyError(f"goals current unsupported: {metric!r} "
                       f"(have {self.current_metrics})")

    # ── HISTORY (nightly GoalMomentumSnapshot; read-only) ────────────────
    def history(self, metric, period="last_month", **kwargs):
        from apps.dashboard_v2.models import GoalMomentumSnapshot
        goal = kwargs.get("goal")
        if goal is None:
            from apps.purpose.mission_selection import select_active_mission_goal
            goal = select_active_mission_goal(self.user)
        field = {"progress": "progress_score", "momentum": "momentum_score"}.get(metric)
        if field is None:
            raise KeyError(f"goals history unsupported: {metric!r} "
                           f"(have {self.history_metrics})")
        p = resolve_period(period, _today(self.user),
                           start=kwargs.get("start"), end=kwargs.get("end"))
        if goal is None:
            return series_from_rows(_DOMAIN, metric, p, [], unit="score")
        rows = (GoalMomentumSnapshot.objects
                .filter(user=self.user, goal=goal,
                        snapshot_date__range=(p.start, p.end))
                .values("snapshot_date", field).order_by("snapshot_date"))
        return series_from_rows(
            _DOMAIN, metric, p,
            [{"date": r["snapshot_date"], "value": r[field]} for r in rows],
            unit="score")

    # ── ENTITY COMPLETENESS ──────────────────────────────────────────────
    def describe(self, entity_type="goal"):
        from apps.purpose.services.goal_queries import GoalQueries
        if entity_type in (None, "goal"):
            return [self._goal_entity(g) for g in
                    GoalQueries.active(self.user).prefetch_related("milestones")]
        if entity_type == "milestone":
            from apps.purpose.models import GoalMilestone
            ms = GoalMilestone.objects.filter(
                goal__in=GoalQueries.active(self.user)).select_related("goal")
            return [self._milestone_entity(m) for m in ms]
        if entity_type == "annual_direction":
            from apps.purpose.models import AnnualDirection
            return [CompleteEntity(kind="annual_direction",
                                   identity=f"{ad.year}: {ad.word_of_year}",
                                   status=("current" if getattr(ad, "is_current", False)
                                           else "past"),
                                   definition=annual_direction_dict(ad))
                    for ad in AnnualDirection.objects.filter(user=self.user)
                    .order_by("-year")]
        raise KeyError(f"goals cannot describe {entity_type!r} "
                       f"(have {self.entity_types})")

    def describe_one(self, name):
        """Resolve a goal/mission by title (so 'France 2027 mission' matches).
        Includes completed goals via all_objects (default manager hides them)."""
        from apps.purpose.models import LifeGoal
        q = (name or "").strip().lower().replace(" mission", "").strip()
        if not q:
            return None
        goals = list(LifeGoal.all_objects.filter(user=self.user)
                     .prefetch_related("milestones"))
        exact = [g for g in goals if g.title.lower() == q]
        partial = [g for g in goals if q in g.title.lower()]
        pool = exact or partial
        pool.sort(key=lambda g: (not g.is_primary_mission, g.status != "active"))
        if pool:
            return self._goal_entity(pool[0])
        # Not a goal title — a milestone or the annual direction by name/identity, so those
        # entity types are reachable by name too (previously only goals were).
        return self._entity_by_identity(name, ("milestone", "annual_direction"))

    # ── mappers ──────────────────────────────────────────────────────────
    def _goal_entity(self, g):
        ms = list(g.milestones.all())
        done = [m for m in ms if m.completed]
        nxt = g.next_milestone
        # Latest momentum snapshot → what has improved / still needs work (deterministic
        # facts the model reasons over; no verdict invented here).
        snap = g.momentum_snapshots.first() if hasattr(g, "momentum_snapshots") else None
        perf = {"progress_percent": g.milestone_progress_percent,
                "completed_date": g.completed_date.isoformat()
                if g.completed_date else None}
        if snap is not None:
            drivers = snap.drivers if isinstance(snap.drivers, dict) else {}
            perf.update({
                "momentum_score": snap.momentum_score,
                "momentum_trend": snap.momentum_trend,
                "improved": drivers.get("success_drivers") or drivers.get("improved"),
                "needs_work": drivers.get("risk_drivers") or drivers.get("needs_work"),
                "as_of": snap.snapshot_date.isoformat()})
        # Additive truth previously stranded on the model.
        ad = g.annual_direction
        victories = (list(g.victory_milestones.all())
                     if hasattr(g, "victory_milestones") else [])
        extensions = {
            "description": (g.description_plain or "").strip(),
            "reflection": (g.reflection_plain or "").strip(),
            "motivation_note": (g.motivation_note_plain or "").strip(),
            "commitment_level": g.commitment_level,
            "timeframe": g.timeframe,
            "mission_icon": g.mission_icon or "",
            "hero_image_url": (g.hero_image.url if getattr(g, "hero_image", None) else None),
            "annual_direction": annual_direction_dict(ad),
            "victory_milestones": {
                "total": len(victories),
                "completed": sum(1 for v in victories if v.completed),
                "titles": [v.title for v in victories]},
            "motivation_links": [{"title": ln.title, "url": ln.url}
                                 for ln in g.motivation_links.all()],
            "linked_habits": [hl.habit.name
                              for hl in g.habit_links.select_related("habit").all()],
            "signal_sources": [{"signal_type": s.signal_type, "weight": s.weight}
                               for s in g.signal_sources.all()],
        }
        return CompleteEntity(
            kind="goal", identity=g.title, status=g.status,
            definition={"why_it_matters": (g.why_it_matters_plain or "").strip(),
                        "success_looks_like": (g.success_looks_like_plain or "").strip(),
                        "is_primary_mission": g.is_primary_mission,
                        "is_foundational": g.is_foundational,
                        "domain": getattr(g.domain, "name", None)},
            plan={"target_date": g.target_date.isoformat() if g.target_date else None,
                  "days_until_due": g.days_until_due,
                  "next_milestone": nxt.title if nxt else None},
            standing={"is_overdue": g.is_overdue,
                      "milestone_count": len(ms),
                      "completed_milestones": len(done),
                      "overdue_milestones": [m.title for m in g.overdue_milestones]},
            performance=perf,
            extensions=extensions)

    def _milestone_entity(self, m):
        objective = None
        if m.objective_metric:
            objective = {"metric": m.objective_metric, "operator": m.objective_operator,
                         "target_value": (float(m.objective_target_value)
                                          if m.objective_target_value is not None else None)}
        return CompleteEntity(
            kind="milestone", identity=m.title,
            status="completed" if m.completed else "open",
            definition={"goal": m.goal.title, "description": m.description},
            plan={"target_date": m.target_date.isoformat() if m.target_date else None,
                  "days_until_due": m.days_until_due},
            standing={"is_overdue": m.is_overdue},
            performance={"completed_date": m.completed_date.isoformat()
                         if m.completed_date else None},
            extensions=({"objective": objective} if objective else {}))
