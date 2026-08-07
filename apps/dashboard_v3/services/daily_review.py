# =============================================================================
# File: apps/dashboard_v3/services/daily_review.py
# Purpose: DAILY REVIEW — the DATE-SCOPED reconstruction of one calendar day for
#   Dashboard(date). It answers "what did this day look like?" for any past day,
#   composing ONLY existing date-aware truth authorities. It owns no truth, stores
#   nothing, and never recomputes a metric — like a dashboard, it assembles.
#
#   Spine   ← apps.core.execution.execution_review.build_execution_review(user, D)
#             (the single day-scoped projection of get_execution_truth + Tasks,
#              already faith-deduped) → completion score + outstanding + completed.
#   Metrics ← per-domain date-aware queries (nutrition / water / sleep / weight).
#
#   Request-path safe: build_execution_review reads the execution-truth engine for
#   ONE day (bounded, the same engine v2's live "today" path already calls) and the
#   metric queries are single-day aggregates. No SAE rebuild, no heavy intelligence.
# =============================================================================
"""Deterministic Daily Review for a single past calendar day (facts only)."""

from __future__ import annotations

import logging

logger = logging.getLogger(__name__)


def build_daily_review(user, target_date) -> dict:
    """Reconstruct the DATE-SCOPED truth for ``target_date`` (facts only, never raises).

    Returns::

        {
          "date": date, "date_iso": "YYYY-MM-DD",
          "status": "ready" | "empty",
          "score": int | None,          # completion % (None when nothing intended)
          "intended": int, "completed_count": int, "remaining": int,
          "outstanding": [item, ...],   # execution-review items not completed
          "completed":   [item, ...],   # execution-review items completed
          "fully_reconciled": bool,
          "metrics": { "nutrition"|"water"|"sleep"|"weight": {...} },
        }

    ``item`` is the execution-review shape: ``{kind, title, completed, status,
    detail, source}``. WLJ renders facts only — never a verdict.
    """
    try:
        from apps.core.execution.execution_review import build_execution_review
        review = build_execution_review(user, target_date) or {}
    except Exception:
        logger.warning("daily_review: execution review failed user=%s date=%s",
                       getattr(user, "id", None), target_date, exc_info=True)
        review = {}

    items = review.get("items") or []
    completed = [i for i in items if i.get("completed")]
    outstanding = [i for i in items if not i.get("completed")]
    intended = len(items)
    done = len(completed)
    score = round((done / intended) * 100) if intended else None

    return {
        "date": target_date,
        "date_iso": (target_date.isoformat() if hasattr(target_date, "isoformat")
                     else str(target_date)),
        "status": review.get("status", "empty"),
        "score": score,
        "intended": intended,
        "completed_count": done,
        "remaining": intended - done,
        "outstanding": outstanding,
        "completed": completed,
        "fully_reconciled": intended > 0 and done == intended,
        "metrics": _build_daily_metrics(user, target_date),
    }


def _build_daily_metrics(user, target_date) -> dict:
    """Date-scoped daily metrics from existing per-domain authorities (facts only).

    Every metric is guarded independently: a domain with no record for the day is
    simply absent (honest "nothing logged"), never a fabricated zero-as-verdict.
    """
    metrics: dict = {}

    # ── Nutrition — canonical daily macro totals. Present only if anything logged.
    try:
        from apps.health.services.nutrition_queries import NutritionQueries
        totals = NutritionQueries.get_daily_totals(user, target_date) or {}
        calories = totals.get("calories") or 0
        if calories:
            metrics["nutrition"] = {
                "calories": int(calories),
                "protein_g": int(totals.get("protein_g") or 0),
                "carbs_g": int(totals.get("carbs_g") or 0),
                "fat_g": int(totals.get("fat_g") or 0),
            }
    except Exception:
        logger.debug("daily_review: nutrition metric skipped", exc_info=True)

    # ── Water — hydration progress for the day.
    try:
        from apps.health.models import WaterEntry
        w = WaterEntry.get_daily_goal_progress(user, target_date) or {}
        if (w.get("total_oz") or 0) > 0:
            metrics["water"] = {
                "total_oz": w.get("total_oz"),
                "goal_oz": w.get("goal_oz"),
                "percentage": w.get("percentage"),
                "goal_met": w.get("goal_met"),
            }
    except Exception:
        logger.debug("daily_review: water metric skipped", exc_info=True)

    # ── Sleep — the night whose wake date is target_date (canonical accessor).
    try:
        from apps.health.services import sleep_queries
        s = sleep_queries.on_date(user, target_date)
        if s and s.get("hours"):
            metrics["sleep"] = {"hours": s.get("hours"), "quality": s.get("quality")}
    except Exception:
        logger.debug("daily_review: sleep metric skipped", exc_info=True)

    # ── Weight — the last measurement recorded on that calendar day, if any.
    try:
        from apps.health.models import WeightEntry
        we = (WeightEntry.objects
              .filter(user=user, recorded_at__date=target_date)
              .order_by("-recorded_at").first())
        if we is not None:
            metrics["weight"] = {"value": float(we.value), "unit": we.unit}
    except Exception:
        logger.debug("daily_review: weight metric skipped", exc_info=True)

    return metrics
