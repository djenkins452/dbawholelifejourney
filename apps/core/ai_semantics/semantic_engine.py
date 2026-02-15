"""
SUE -- Semantic Engine.

Main entry point for the Semantic Understanding Engine.
Coordinates parsing, entity resolution, ambiguity detection,
and confidence scoring into a single interpret() call.

SUE does NOT execute actions. It returns structured semantic
data for the UAIO orchestrator to use.

Pipeline:
    Raw Text
      -> Semantic Parser (intent candidates, entities, time, references)
      -> Entity Resolver (resolve references via context/SLCME/SAE)
      -> Ambiguity Engine (detect ambiguity, generate clarifications)
      -> Confidence Engine (compute composite confidence)
      -> SemanticResult
"""

import logging

from apps.core.ai_semantics.ambiguity_engine import AmbiguityResult, detect_ambiguity
from apps.core.ai_semantics.confidence_engine import (
    ConfidenceScore,
    compute_confidence,
)
from apps.core.ai_semantics.entity_resolver import (
    EntityResolutionResult,
    resolve_entities,
)
from apps.core.ai_semantics.semantic_logger import log_decision
from apps.core.ai_semantics.semantic_parser import parse

logger = logging.getLogger(__name__)


class SemanticResult:
    """
    Complete result of semantic interpretation.

    This is the primary output of interpret() and contains everything
    the UAIO orchestrator needs to decide what to do with user input.
    """

    __slots__ = (
        "intent",
        "domain",
        "entities",
        "time_expression",
        "confidence",
        "is_ambiguous",
        "ambiguity_type",
        "clarification_question",
        "alternative_intents",
        "contextual_references",
        "entity_resolution",
        "used_slcme",
        "used_sae",
        "used_context",
        "raw_text",
        "parse_result",
        "decision_log_id",
    )

    def __init__(self):
        self.intent = ""                    # Primary intent (e.g., "log_weight")
        self.domain = ""                    # Domain (e.g., "health")
        self.entities = {}                  # Extracted entities {name: value}
        self.time_expression = ""           # Detected time (pre-HTIE)
        self.confidence = ConfidenceScore() # Composite confidence
        self.is_ambiguous = False
        self.ambiguity_type = ""
        self.clarification_question = ""
        self.alternative_intents = []       # [{intent, domain, confidence}]
        self.contextual_references = []     # ["that goal", "my weight"]
        self.entity_resolution = None       # EntityResolutionResult
        self.used_slcme = False
        self.used_sae = False
        self.used_context = False
        self.raw_text = ""
        self.parse_result = None            # Full ParseResult for debugging
        self.decision_log_id = None         # ID of logged decision

    def to_dict(self):
        return {
            "intent": self.intent,
            "domain": self.domain,
            "entities": self.entities,
            "time_expression": self.time_expression,
            "confidence": self.confidence.to_dict(),
            "is_ambiguous": self.is_ambiguous,
            "ambiguity_type": self.ambiguity_type,
            "clarification_question": self.clarification_question,
            "alternative_intents": self.alternative_intents,
            "contextual_references": self.contextual_references,
            "used_slcme": self.used_slcme,
            "used_sae": self.used_sae,
            "used_context": self.used_context,
        }


def interpret(user, raw_text, context=None):
    """
    Interpret raw user text into structured semantic data.

    This is the SUE public API. It:
    1. Parses text for intents, entities, time, references
    2. Resolves contextual references (context → SLCME → SAE)
    3. Detects ambiguity
    4. Computes confidence
    5. Logs the decision

    SUE does NOT execute actions. UAIO remains execution authority.

    Args:
        user: Django user instance.
        raw_text: The raw user input string.
        context: Optional dict with page context (url, module, page_title, object_id).

    Returns:
        SemanticResult with complete interpretation data.
    """
    result = SemanticResult()
    result.raw_text = raw_text

    if not raw_text or not raw_text.strip():
        return result

    try:
        # Step 1: Parse raw text
        parse_result = parse(raw_text)
        result.parse_result = parse_result
        result.time_expression = parse_result.time_expression
        result.contextual_references = parse_result.contextual_references
        result.entities = parse_result.entities

        # Set intent and domain from primary candidate
        primary = parse_result.primary_intent
        if primary:
            result.intent = primary.intent_type
            result.domain = primary.domain

        # Step 2: Resolve entity references
        entity_resolution = _safe_resolve_entities(
            user, parse_result, context
        )
        result.entity_resolution = entity_resolution

        # Track which sources were used
        if entity_resolution:
            result.used_slcme = entity_resolution.used_slcme
            result.used_sae = entity_resolution.used_sae
            result.used_context = entity_resolution.used_context

        # Step 3: Detect ambiguity
        ambiguity = detect_ambiguity(parse_result, entity_resolution)
        result.is_ambiguous = ambiguity.is_ambiguous
        result.ambiguity_type = ambiguity.ambiguity_type
        result.clarification_question = ambiguity.clarification_question
        result.alternative_intents = ambiguity.alternative_intents

        # Step 4: Compute confidence
        confidence = compute_confidence(parse_result, entity_resolution, ambiguity)
        result.confidence = confidence

        # Step 5: Log the decision
        _safe_log_decision(user, raw_text, result, context)

    except Exception as e:
        # SUE failures must NEVER break the main pipeline
        logger.error(f"SUE interpretation failed: {e}", exc_info=True)

    return result


def _safe_resolve_entities(user, parse_result, context):
    """Resolve entities with error isolation."""
    try:
        if not parse_result.contextual_references:
            return EntityResolutionResult()

        return resolve_entities(
            user=user,
            contextual_references=parse_result.contextual_references,
            domain_hint=parse_result.domain_hint,
            context=context,
        )
    except Exception as e:
        logger.error(f"Entity resolution failed: {e}", exc_info=True)
        return EntityResolutionResult()


def _safe_log_decision(user, raw_text, semantic_result, context):
    """Log decision with error isolation."""
    try:
        log_entry = log_decision(user, raw_text, semantic_result, context)
        if log_entry:
            semantic_result.decision_log_id = log_entry.id
    except Exception as e:
        logger.debug(f"SUE decision logging skipped: {e}")
