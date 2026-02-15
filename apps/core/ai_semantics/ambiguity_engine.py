"""
SUE -- Ambiguity Engine.

Detects when user input is ambiguous and generates clarification
questions. Ambiguity types:

- intent_ambiguity: Multiple intents match with similar confidence
- entity_ambiguity: Contextual reference can't be resolved
- domain_ambiguity: Input could belong to multiple domains
- multi_intent: User appears to be asking for multiple things
- insufficient_info: Intent is clear but required entities are missing
"""

import logging

logger = logging.getLogger(__name__)

# Confidence gap threshold -- if top two intents are within this gap,
# the input is considered intent-ambiguous
INTENT_CONFIDENCE_GAP = 0.10

# Minimum confidence to consider an intent valid
MIN_INTENT_CONFIDENCE = 0.50

# Threshold below which overall confidence triggers ambiguity
OVERALL_AMBIGUITY_THRESHOLD = 0.60


class AmbiguityResult:
    """Result of ambiguity detection."""

    __slots__ = (
        "is_ambiguous",
        "ambiguity_type",
        "clarification_question",
        "alternative_intents",
        "missing_entities",
    )

    def __init__(self):
        self.is_ambiguous = False
        self.ambiguity_type = ""         # "intent", "entity", "domain", "multi_intent", "insufficient_info"
        self.clarification_question = ""
        self.alternative_intents = []     # List[dict] with {intent, confidence}
        self.missing_entities = []        # List[str]

    def to_dict(self):
        result = {
            "is_ambiguous": self.is_ambiguous,
        }
        if self.is_ambiguous:
            result["ambiguity_type"] = self.ambiguity_type
            result["clarification_question"] = self.clarification_question
            if self.alternative_intents:
                result["alternative_intents"] = self.alternative_intents
            if self.missing_entities:
                result["missing_entities"] = self.missing_entities
        return result


def detect_ambiguity(parse_result, entity_resolution):
    """
    Analyze parse result and entity resolution for ambiguity.

    Args:
        parse_result: ParseResult from semantic_parser.
        entity_resolution: EntityResolutionResult from entity_resolver.

    Returns:
        AmbiguityResult with ambiguity details.
    """
    result = AmbiguityResult()

    # Check 1: No intent detected at all
    if not parse_result.intent_candidates:
        # Not necessarily ambiguous -- could be conversational
        return result

    # Check 2: Intent ambiguity (top two are too close)
    ambiguity = _check_intent_ambiguity(parse_result)
    if ambiguity:
        return ambiguity

    # Check 3: Multi-intent detection
    ambiguity = _check_multi_intent(parse_result)
    if ambiguity:
        return ambiguity

    # Check 4: Unresolved entity references
    ambiguity = _check_entity_ambiguity(parse_result, entity_resolution)
    if ambiguity:
        return ambiguity

    # Check 5: Missing required entities
    ambiguity = _check_missing_entities(parse_result)
    if ambiguity:
        return ambiguity

    return result


def _check_intent_ambiguity(parse_result):
    """Check if top two intent candidates are too close in confidence."""
    candidates = parse_result.intent_candidates
    if len(candidates) < 2:
        return None

    top = candidates[0]
    second = candidates[1]

    # If different domains and close confidence, it's ambiguous
    if (
        top.domain != second.domain
        and abs(top.confidence - second.confidence) <= INTENT_CONFIDENCE_GAP
    ):
        result = AmbiguityResult()
        result.is_ambiguous = True
        result.ambiguity_type = "intent"
        result.alternative_intents = [
            {"intent": top.intent_type, "domain": top.domain, "confidence": top.confidence},
            {"intent": second.intent_type, "domain": second.domain, "confidence": second.confidence},
        ]
        result.clarification_question = _build_intent_clarification(top, second)
        return result

    return None


def _check_multi_intent(parse_result):
    """Check if user appears to be requesting multiple actions."""
    candidates = parse_result.intent_candidates
    if len(candidates) < 2:
        return None

    # Multiple strong intents from different domains
    strong = [c for c in candidates if c.confidence >= 0.70]
    unique_domains = set(c.domain for c in strong)

    if len(strong) >= 2 and len(unique_domains) >= 2:
        # Check if text contains conjunctions suggesting multiple requests
        text_lower = parse_result.raw_text.lower()
        multi_signals = [" and ", " also ", " then ", " plus "]
        if any(signal in text_lower for signal in multi_signals):
            result = AmbiguityResult()
            result.is_ambiguous = True
            result.ambiguity_type = "multi_intent"
            result.alternative_intents = [
                {"intent": c.intent_type, "domain": c.domain, "confidence": c.confidence}
                for c in strong[:3]
            ]
            result.clarification_question = (
                "It sounds like you want to do multiple things. "
                "Which would you like to start with?"
            )
            return result

    return None


def _check_entity_ambiguity(parse_result, entity_resolution):
    """Check for unresolved contextual references."""
    if not entity_resolution:
        return None

    unresolved = entity_resolution.unresolved_references
    if not unresolved:
        return None

    # Only flag as ambiguous if we have an intent that needs the entity
    primary = parse_result.primary_intent
    if not primary:
        return None

    # Context-aware intents need entity resolution
    from apps.core.ai_orchestrator.intent_engine import CONTEXT_AWARE_INTENTS
    if primary.intent_type not in CONTEXT_AWARE_INTENTS:
        return None

    result = AmbiguityResult()
    result.is_ambiguous = True
    result.ambiguity_type = "entity"
    result.clarification_question = _build_entity_clarification(unresolved, primary)
    return result


def _check_missing_entities(parse_result):
    """Check if required entities for the detected intent are missing."""
    primary = parse_result.primary_intent
    if not primary:
        return None

    entities = parse_result.entities
    missing = []

    # Define required entities per intent
    required = {
        "log_weight": ["value"],
        "log_heart_rate": ["numeric_value"],
        "log_blood_pressure": ["systolic", "diastolic"],
    }

    required_fields = required.get(primary.intent_type, [])
    for field in required_fields:
        if field not in entities:
            missing.append(field)

    if not missing:
        return None

    # Only flag if confidence is high enough that we're fairly sure of intent
    if primary.confidence < 0.70:
        return None

    result = AmbiguityResult()
    result.is_ambiguous = True
    result.ambiguity_type = "insufficient_info"
    result.missing_entities = missing
    result.clarification_question = _build_missing_entity_clarification(
        primary.intent_type, missing
    )
    return result


# ---------------------------------------------------------------------------
# Clarification question builders
# ---------------------------------------------------------------------------

def _build_intent_clarification(top, second):
    """Build a clarification question for ambiguous intents."""
    intent_labels = {
        "log_weight": "log your weight",
        "log_heart_rate": "log your heart rate",
        "log_blood_pressure": "log blood pressure",
        "log_food": "log a meal",
        "log_prayer": "log a prayer",
        "create_goal": "create a goal",
        "log_habit": "log a habit",
        "create_task": "create a task",
        "create_journal_entry": "write a journal entry",
    }
    top_label = intent_labels.get(top.intent_type, top.intent_type)
    second_label = intent_labels.get(second.intent_type, second.intent_type)
    return f"Did you want to {top_label} or {second_label}?"


def _build_entity_clarification(unresolved, primary_intent):
    """Build a clarification question for unresolved entities."""
    ref_text = ", ".join(f'"{r}"' for r in unresolved[:2])
    return f"I'm not sure which {_intent_to_noun(primary_intent.intent_type)} you mean by {ref_text}. Can you be more specific?"


def _build_missing_entity_clarification(intent_type, missing):
    """Build a clarification question for missing required entities."""
    entity_labels = {
        "value": "the value",
        "numeric_value": "the value",
        "systolic": "the systolic reading",
        "diastolic": "the diastolic reading",
    }
    missing_labels = [entity_labels.get(m, m) for m in missing]
    missing_str = " and ".join(missing_labels)
    return f"I understood what you want to do, but I need {missing_str}."


def _intent_to_noun(intent_type):
    """Convert intent type to a noun for clarification questions."""
    mapping = {
        "mark_prayer_answered": "prayer",
        "save_verse": "verse",
        "update_goal_progress": "goal",
        "complete_task": "task",
        "log_habit": "habit",
    }
    return mapping.get(intent_type, "item")
