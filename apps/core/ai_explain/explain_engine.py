"""
E3 — Explain Engine.

Main entry point for Evidence & Explainability.
Creates explain records for intelligence outputs if missing.
"""

import logging

from apps.core.ai_explain.evidence_builder import (
    build_evidence_for_briefing,
    build_evidence_for_guidance,
    build_evidence_for_weekly_report,
)
from apps.core.ai_explain.explain_logger import store_explain_record
from apps.core.ai_explain.explain_templates import (
    explain_briefing,
    explain_guidance,
    explain_weekly_report,
)
from apps.core.ai_explain.models import ExplainRecord

logger = logging.getLogger(__name__)

# Map source object class names to their handler functions
_HANDLERS = {
    "GuidanceItem": {
        "engine": "PGE",
        "explain_fn": explain_guidance,
        "evidence_fn": build_evidence_for_guidance,
    },
    "DailyBriefing": {
        "engine": "DBE",
        "explain_fn": explain_briefing,
        "evidence_fn": build_evidence_for_briefing,
    },
    "WeeklyIntelligenceReport": {
        "engine": "WIRE",
        "explain_fn": explain_weekly_report,
        "evidence_fn": build_evidence_for_weekly_report,
    },
}


def ensure_explain_record(user, source_engine, obj):
    """
    Create an explain record if missing, otherwise return existing.

    This is the main entry point for E3. Safe to call from any
    pipeline — never raises, returns None on failure.

    Args:
        user: Django User instance.
        source_engine: str — PIE, PRIE, PGE, DBE, WIRE.
        obj: Model instance — the intelligence output.

    Returns:
        ExplainRecord instance or None on failure.
    """
    try:
        obj_type = obj.__class__.__name__
        obj_id = obj.pk

        # Check for existing record first (fast path)
        existing = ExplainRecord.objects.filter(
            user=user,
            source_object_type=obj_type,
            source_object_id=obj_id,
        ).first()
        if existing:
            return existing

        # Look up handler
        handler = _HANDLERS.get(obj_type)
        if not handler:
            logger.warning(f"E3: No handler for object type {obj_type}")
            return None

        # Generate explanation
        explanation, confidence_explanation = handler["explain_fn"](obj)

        # Build evidence
        evidence = handler["evidence_fn"](obj)

        # Store
        record = store_explain_record(
            user=user,
            source_engine=source_engine,
            source_object_type=obj_type,
            source_object_id=obj_id,
            title=_get_title(obj),
            explanation=explanation,
            evidence=evidence,
            confidence_explanation=confidence_explanation,
        )

        return record

    except Exception as e:
        logger.error(f"E3: Failed to create explain record: {e}", exc_info=True)
        return None


def get_explain_record(user, source_engine, obj_type, obj_id):
    """
    Look up an existing explain record.

    Args:
        user: Django User instance.
        source_engine: str — PIE, PRIE, PGE, DBE, WIRE.
        obj_type: str — model class name.
        obj_id: int — PK.

    Returns:
        ExplainRecord or None.
    """
    return ExplainRecord.objects.filter(
        user=user,
        source_object_type=obj_type,
        source_object_id=obj_id,
    ).first()


def _get_title(obj):
    """Extract a title from a source object."""
    if hasattr(obj, "title"):
        return obj.title
    if hasattr(obj, "summary"):
        # Truncate summary to 100 chars for title
        return obj.summary[:100]
    return str(obj)
