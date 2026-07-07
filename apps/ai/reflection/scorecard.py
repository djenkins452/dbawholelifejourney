# ==============================================================================
# File: apps/ai/reflection/scorecard.py
# Project: Whole Life Journey - Django 5.x Personal Wellness/Journaling App
# Description: Executive Scorecard — composed summary of reflection outcomes.
# ==============================================================================
"""
The Executive Scorecard turns individual ReflectionEvents into a performance
TRAJECTORY — Beth's internal professional-development review. Trust is the
headline; every other dimension is a diagnostic sub-score. Two dimensions double
as GUARDRAILS on Phase 4 itself: a rising learning rate warns that learning may
be escaping default-deny; concentrated EIOs show where the platform constrains
trust.

Composition only (Modify Before Adding): it aggregates existing ReflectionEvents.
It is computed in the background and read from a snapshot — never live on the
request path (WLJ F5).
"""

import logging
from datetime import timedelta

from django.utils import timezone

logger = logging.getLogger(__name__)


def summarize(user, days=30):
    """Aggregate a user's ReflectionEvents into the Executive Scorecard dict."""
    from apps.ai.models import ReflectionEvent

    since = timezone.now() - timedelta(days=days)
    events = list(ReflectionEvent.objects.filter(user=user, created_at__gte=since))
    total = len(events)

    def count(pred):
        return sum(1 for e in events if pred(e))

    trust_up = count(lambda e: e.trust_delta == "increased")
    trust_down = count(lambda e: e.trust_delta == "decreased")
    trust_flat = count(lambda e: e.trust_delta == "maintained")

    learn_n = count(lambda e: e.disposition == "learn")
    eio_n = count(lambda e: e.disposition == "eio")
    reinforce_n = count(lambda e: e.disposition == "reinforce")
    insuff_n = count(lambda e: e.disposition == "insufficient_evidence")

    def locus_count(locus):
        return count(lambda e: e.locus == locus)

    return {
        "window_days": days,
        "reflection_count": total,
        # Headline
        "user_trust": {
            "increased": trust_up,
            "maintained": trust_flat,
            "decreased": trust_down,
            "net": trust_up - trust_down,
        },
        # Value signal
        "executive_initiative": {
            "reinforced_successes": reinforce_n,
        },
        # Diagnostic sub-scores
        "truth_accuracy_issues": locus_count("truth_retrieval"),
        "reasoning_issues": locus_count("reasoning"),
        "execution_issues": locus_count("execution"),
        "communication_learnings": locus_count("communication"),
        "preference_learnings": locus_count("preference"),
        "confidence_calibration_issues": locus_count("confidence_calibration"),
        # Dispositions (learning-rate + EIO guardrails on Phase 4 itself)
        "learning_events": learn_n,
        "reinforcements": reinforce_n,
        "executive_improvement_opportunities": eio_n,
        "insufficient_evidence": insuff_n,
        # Health check: learning must stay RARE (P2).
        "learning_rate": round(learn_n / total, 3) if total else 0.0,
    }


def compute_and_store(user, days=30):
    """Compute the scorecard and persist a snapshot (background pattern)."""
    from apps.ai.models import ExecutiveScorecardSnapshot

    data = summarize(user, days)
    try:
        return ExecutiveScorecardSnapshot.objects.create(
            user=user,
            window_days=days,
            reflection_count=data["reflection_count"],
            dimensions=data,
        )
    except Exception:
        logger.warning("scorecard: snapshot write failed", exc_info=True)
        return None
