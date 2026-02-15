"""
SUE -- Confidence Engine.

Computes an overall confidence score for the semantic interpretation.
Combines signal from:

- Intent detection confidence
- Entity extraction confidence
- Entity resolution confidence
- Ambiguity absence

Threshold: >= 0.80 safe to execute, < 0.80 ask for clarification.
"""

import logging

logger = logging.getLogger(__name__)

# Confidence threshold for safe execution
SAFE_EXECUTION_THRESHOLD = 0.80

# Weights for combining confidence signals
INTENT_WEIGHT = 0.50
ENTITY_WEIGHT = 0.25
RESOLUTION_WEIGHT = 0.15
AMBIGUITY_WEIGHT = 0.10


class ConfidenceScore:
    """Composite confidence score with breakdown."""

    __slots__ = (
        "overall",
        "intent_score",
        "entity_score",
        "resolution_score",
        "ambiguity_penalty",
        "is_safe_to_execute",
    )

    def __init__(self):
        self.overall = 0.0
        self.intent_score = 0.0
        self.entity_score = 0.0
        self.resolution_score = 0.0
        self.ambiguity_penalty = 0.0
        self.is_safe_to_execute = False

    def to_dict(self):
        return {
            "overall": round(self.overall, 3),
            "intent_score": round(self.intent_score, 3),
            "entity_score": round(self.entity_score, 3),
            "resolution_score": round(self.resolution_score, 3),
            "ambiguity_penalty": round(self.ambiguity_penalty, 3),
            "is_safe_to_execute": self.is_safe_to_execute,
        }


def compute_confidence(parse_result, entity_resolution, ambiguity_result):
    """
    Compute composite confidence score for a semantic interpretation.

    Args:
        parse_result: ParseResult from semantic_parser.
        entity_resolution: EntityResolutionResult from entity_resolver.
        ambiguity_result: AmbiguityResult from ambiguity_engine.

    Returns:
        ConfidenceScore with overall and component scores.
    """
    score = ConfidenceScore()

    # Component 1: Intent confidence
    score.intent_score = _compute_intent_confidence(parse_result)

    # Component 2: Entity extraction confidence
    score.entity_score = _compute_entity_confidence(parse_result)

    # Component 3: Entity resolution confidence
    score.resolution_score = _compute_resolution_confidence(
        parse_result, entity_resolution
    )

    # Component 4: Ambiguity penalty
    score.ambiguity_penalty = _compute_ambiguity_penalty(ambiguity_result)

    # Weighted combination
    raw_score = (
        score.intent_score * INTENT_WEIGHT
        + score.entity_score * ENTITY_WEIGHT
        + score.resolution_score * RESOLUTION_WEIGHT
        + (1.0 - score.ambiguity_penalty) * AMBIGUITY_WEIGHT
    )

    # Clamp to [0, 1]
    score.overall = max(0.0, min(1.0, raw_score))

    # Determine if safe to execute
    score.is_safe_to_execute = (
        score.overall >= SAFE_EXECUTION_THRESHOLD
        and not ambiguity_result.is_ambiguous
    )

    return score


def _compute_intent_confidence(parse_result):
    """Compute intent detection confidence."""
    primary = parse_result.primary_intent
    if not primary:
        return 0.0

    candidates = parse_result.intent_candidates
    base = primary.confidence

    # Boost if only one strong candidate
    if len(candidates) == 1:
        return min(1.0, base + 0.05)

    # Reduce if multiple candidates are close
    if len(candidates) >= 2:
        gap = primary.confidence - candidates[1].confidence
        if gap < 0.10:
            return max(0.0, base - 0.10)
        elif gap < 0.20:
            return max(0.0, base - 0.05)

    return base


def _compute_entity_confidence(parse_result):
    """Compute entity extraction confidence."""
    if not parse_result.entities:
        # No entities needed or found -- neutral score
        primary = parse_result.primary_intent
        if not primary:
            return 0.5

        # Check if this intent typically needs entities
        entity_intents = {
            "log_weight", "log_heart_rate", "log_blood_pressure",
            "log_glucose", "log_blood_oxygen",
        }
        if primary.intent_type in entity_intents:
            return 0.3  # Expected entities but didn't find them
        return 0.8  # No entities expected

    # Found entities -- score based on richness
    entity_count = len(parse_result.entities)
    if entity_count >= 2:
        return 0.95
    return 0.80


def _compute_resolution_confidence(parse_result, entity_resolution):
    """Compute entity resolution confidence."""
    if not parse_result.has_contextual_reference:
        return 1.0  # No references to resolve -- perfect score

    if not entity_resolution:
        return 0.3  # Had references but no resolution attempted

    total_refs = (
        len(entity_resolution.resolved_entities)
        + len(entity_resolution.unresolved_references)
    )
    if total_refs == 0:
        return 1.0

    resolved_ratio = len(entity_resolution.resolved_entities) / total_refs

    # Weight by source quality
    if entity_resolution.resolved_entities:
        avg_confidence = sum(
            e.confidence for e in entity_resolution.resolved_entities
        ) / len(entity_resolution.resolved_entities)
        return resolved_ratio * avg_confidence

    return 0.0


def _compute_ambiguity_penalty(ambiguity_result):
    """Compute penalty from detected ambiguity."""
    if not ambiguity_result.is_ambiguous:
        return 0.0

    penalties = {
        "intent": 0.40,
        "entity": 0.30,
        "domain": 0.35,
        "multi_intent": 0.25,
        "insufficient_info": 0.20,
    }
    return penalties.get(ambiguity_result.ambiguity_type, 0.30)
