"""
SUE -- Semantic Logger.

Logs every interpretation decision to SemanticDecisionLog
for audit, debugging, and future model improvement.
Failures in logging must NEVER break the interpretation pipeline.
"""

import logging

logger = logging.getLogger(__name__)


def log_decision(user, raw_text, semantic_result, context=None):
    """
    Log a semantic interpretation decision.

    Args:
        user: Django user instance.
        raw_text: Original user input.
        semantic_result: SemanticResult from semantic_engine.interpret().
        context: Optional page context dict.

    Returns:
        SemanticDecisionLog instance, or None on failure.
    """
    try:
        from apps.core.ai_semantics.semantic_models import SemanticDecisionLog

        log_entry = SemanticDecisionLog.objects.create(
            user=user,
            raw_text=raw_text[:2000],  # Truncate for safety
            page_context=context or {},
            parsed_intent=semantic_result.intent or "",
            parsed_domain=semantic_result.domain or "",
            parsed_entities=semantic_result.entities or {},
            parsed_time_expression=semantic_result.time_expression or "",
            overall_confidence=semantic_result.confidence.overall,
            intent_confidence=semantic_result.confidence.intent_score,
            entity_confidence=semantic_result.confidence.entity_score,
            is_ambiguous=semantic_result.is_ambiguous,
            ambiguity_type=semantic_result.ambiguity_type or "",
            clarification_question=semantic_result.clarification_question or "",
            alternative_intents=semantic_result.alternative_intents or [],
            used_slcme=semantic_result.used_slcme,
            used_sae=semantic_result.used_sae,
            used_context=semantic_result.used_context,
        )
        return log_entry

    except Exception as e:
        logger.error(f"SUE logging failed: {e}", exc_info=True)
        return None


def mark_decision_correct(decision_log_id, was_correct, correction=None):
    """
    Update a decision log with outcome feedback.

    Called after UAIO execution completes, to record whether
    the interpretation was correct.

    Args:
        decision_log_id: ID of the SemanticDecisionLog entry.
        was_correct: bool -- whether the interpretation was correct.
        correction: Optional str -- what the user actually meant.
    """
    try:
        from apps.core.ai_semantics.semantic_models import SemanticDecisionLog

        SemanticDecisionLog.objects.filter(id=decision_log_id).update(
            was_correct=was_correct,
            correction_applied=correction or "",
        )
    except Exception as e:
        logger.error(f"SUE decision update failed: {e}", exc_info=True)
