"""BrainTrainingDomainTruth — canonical Layer-1 interface to Brain-Training truth.

Thin facade over GameSession / DailyStats / UserOverallStats, read live. Owns NO new
retrieval logic. Brain Training had a full engagement/analytics model (sessions,
per-day stats, streaks) but ZERO Truth-Layer provider — this exposes it. `score` is a
DERIVED value (not user-entered); Challenge solution data is secret and never surfaced.
"""
from datetime import timedelta

from django.db.models import Max, Sum

from apps.core.truth.current import CurrentTruth
from apps.core.truth.domain import DomainTruth, register_domain_truth
from apps.core.truth.entity import CompleteEntity
from apps.core.truth.freshness import CURRENT, MISSING
from apps.core.truth.history import series_from_rows
from apps.core.truth.periods import resolve_period

_DOMAIN = "brain_training"


def _today(user):
    from apps.core.utils import get_user_today
    return get_user_today(user)


@register_domain_truth
class BrainTrainingDomainTruth(DomainTruth):
    domain = "brain_training"
    current_metrics = ("games_played_7d", "recent_scores", "current_streak")
    history_metrics = ("daily_best_score", "games_played")
    entity_types = ("game_session",)

    def current(self, metric):
        from apps.brain_training.models import DailyStats, GameSession, UserOverallStats

        if metric == "games_played_7d":
            week_ago = _today(self.user) - timedelta(days=6)
            rows = DailyStats.objects.filter(user=self.user, date__gte=week_ago)
            played = sum(d.sessions_completed for d in rows)
            if played == 0:
                return CurrentTruth.absent(_DOMAIN, metric, MISSING, source="daily_stats",
                                           reason="no games completed in last 7 days")
            return CurrentTruth.found(_DOMAIN, metric, played, CURRENT, source="daily_stats")

        if metric == "recent_scores":
            sessions = list(GameSession.objects
                            .filter(user=self.user, status="completed")
                            .select_related("challenge__game")
                            .order_by("-completed_at")[:10])
            if not sessions:
                return CurrentTruth.absent(_DOMAIN, metric, MISSING, source="game_session",
                                           reason="no completed sessions")
            return CurrentTruth.found(
                _DOMAIN, metric, len(sessions), CURRENT, source="game_session",
                detail={"sessions": [
                    {"game": s.game.name, "difficulty": s.difficulty, "score": s.score,
                     "date": (s.completed_at.date().isoformat() if s.completed_at else None)}
                    for s in sessions]})

        if metric == "current_streak":
            overall = UserOverallStats.objects.filter(user=self.user).first()
            streak = overall.current_streak if overall else 0
            return CurrentTruth.found(
                _DOMAIN, metric, streak, CURRENT if streak else MISSING,
                source="user_overall_stats",
                detail={"longest_streak": overall.longest_streak if overall else 0,
                        "last_played_date": (overall.last_played_date.isoformat()
                                             if overall and overall.last_played_date
                                             else None)})

        raise KeyError(f"brain_training current unsupported: {metric!r} "
                       f"(have {self.current_metrics})")

    def history(self, metric, period="last_7_days", **kwargs):
        from apps.brain_training.models import DailyStats
        agg = {"daily_best_score": ("best", Max("best_score")),
               "games_played": ("games", Sum("sessions_completed"))}.get(metric)
        if agg is None:
            raise KeyError(f"brain_training history unsupported: {metric!r} "
                           f"(have {self.history_metrics})")
        key, expr = agg
        p = resolve_period(period, _today(self.user),
                           start=kwargs.get("start"), end=kwargs.get("end"))
        rows = (DailyStats.objects.filter(user=self.user, date__range=(p.start, p.end))
                .values("date").annotate(**{key: expr}).order_by("date"))
        unit = "score" if metric == "daily_best_score" else "sessions"
        return series_from_rows(_DOMAIN, metric, p,
                                [{"date": r["date"], "value": r[key] or 0} for r in rows],
                                unit=unit)

    def describe(self, entity_type="game_session"):
        if entity_type not in (None, "game_session"):
            raise KeyError(f"brain_training cannot describe {entity_type!r} "
                           f"(have {self.entity_types})")
        from apps.brain_training.models import GameSession
        qs = (GameSession.objects.filter(user=self.user)
              .select_related("challenge__game").order_by("-started_at")[:50])
        return [self._session_entity(s) for s in qs]

    def describe_one(self, name):
        from apps.brain_training.models import GameSession
        q = (name or "").strip()
        if not q:
            return None
        s = (GameSession.objects.filter(user=self.user, challenge__game__name__icontains=q)
             .select_related("challenge__game").order_by("-started_at").first())
        return self._session_entity(s) if s else None

    def _session_entity(self, s):
        return CompleteEntity(
            kind="game_session",
            identity=f"{s.game.name} — {s.started_at.date().isoformat()}",
            definition={"game": s.game.name, "game_slug": s.game.slug,
                        "category": s.game.category, "difficulty": s.difficulty},
            status=s.status,
            plan={"started_at": s.started_at.isoformat(),
                  "completed_at": (s.completed_at.isoformat() if s.completed_at else None)},
            standing={"date": s.started_at.date().isoformat(),
                      "time_spent_seconds": s.time_spent_seconds},
            performance={"score": s.score, "mistakes": s.mistakes,
                         "hints_used": s.hints_used},
            freshness=CURRENT,
        )
