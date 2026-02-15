"""
E3 — Explain Logger.

Stores ExplainRecords with deduplication (one per source object).
"""

import logging

from django.db import IntegrityError

from apps.core.ai_explain.models import ExplainRecord

logger = logging.getLogger(__name__)


def store_explain_record(
    user,
    source_engine,
    source_object_type,
    source_object_id,
    title,
    explanation,
    evidence,
    confidence_explanation=None,
):
    """
    Store an explain record with deduplication.

    If a record already exists for this user + source object, returns existing.

    Args:
        user: Django User instance.
        source_engine: str — PIE, PRIE, PGE, DBE, WIRE.
        source_object_type: str — model name.
        source_object_id: int — PK of source object.
        title: str — short title.
        explanation: str — human-readable explanation.
        evidence: list — evidence objects.
        confidence_explanation: str or None.

    Returns:
        ExplainRecord instance.
    """
    # Check for existing record
    existing = ExplainRecord.objects.filter(
        user=user,
        source_object_type=source_object_type,
        source_object_id=source_object_id,
    ).first()

    if existing:
        logger.debug(
            f"E3: Record already exists for {source_object_type}"
            f"#{source_object_id}"
        )
        return existing

    try:
        record = ExplainRecord.objects.create(
            user=user,
            source_engine=source_engine,
            source_object_type=source_object_type,
            source_object_id=source_object_id,
            title=title,
            explanation=explanation,
            confidence_explanation=confidence_explanation,
            evidence=evidence,
        )
        logger.info(
            f"E3: Created explain record for {source_engine}/"
            f"{source_object_type}#{source_object_id}"
        )
        return record
    except IntegrityError:
        logger.debug(
            f"E3: Race condition for {source_object_type}"
            f"#{source_object_id}"
        )
        return ExplainRecord.objects.filter(
            user=user,
            source_object_type=source_object_type,
            source_object_id=source_object_id,
        ).first()
