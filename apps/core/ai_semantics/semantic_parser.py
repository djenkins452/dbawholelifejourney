"""
SUE -- Semantic Parser.

Parses raw text into structured semantic components:
- Intent candidates (what the user wants to do)
- Entity extraction (values, names, references)
- Domain classification (which module this belongs to)
- Time expression detection (before HTIE resolves it)

This is a rule-based parser that does NOT call OpenAI.
It pre-processes text to give the UAIO richer signal before
OpenAI-based intent recognition runs.
"""

import re
import logging

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Intent pattern definitions
# ---------------------------------------------------------------------------

# Each pattern maps regex → (intent_type, domain, base_confidence)
INTENT_PATTERNS = [
    # Health - Weight
    (r"\b(?:log|record|update|enter|set)\b.*\b(?:weight|weigh)\b", "log_weight", "health", 0.85),
    (r"\b(?:my weight|i weigh|weighed)\b", "log_weight", "health", 0.80),
    (r"\b(\d{2,3}(?:\.\d)?)\s*(?:lbs?|pounds?|kg)\b", "log_weight", "health", 0.70),

    # Health - Heart Rate
    (r"\b(?:log|record)\b.*\b(?:heart rate|pulse|bpm|hr)\b", "log_heart_rate", "health", 0.85),
    (r"\b(?:heart rate|pulse)\b.*\b(?:is|was)\b.*\b(\d{2,3})\b", "log_heart_rate", "health", 0.75),

    # Health - Blood Pressure
    (r"\b(?:log|record)\b.*\b(?:blood pressure|bp)\b", "log_blood_pressure", "health", 0.85),
    (r"\b(\d{2,3})\s*/\s*(\d{2,3})\b", "log_blood_pressure", "health", 0.65),

    # Health - Blood Glucose
    (r"\b(?:log|record)\b.*\b(?:blood sugar|glucose|blood glucose)\b", "log_glucose", "health", 0.85),

    # Health - Blood Oxygen
    (r"\b(?:log|record)\b.*\b(?:blood oxygen|spo2|oxygen)\b", "log_blood_oxygen", "health", 0.85),

    # Health - Food
    (r"\b(?:log|record|track)\b.*\b(?:food|meal|ate|eaten|breakfast|lunch|dinner|snack)\b", "log_food", "health", 0.85),
    (r"\b(?:i (?:ate|had|eaten))\b", "log_food", "health", 0.70),

    # Medicine
    (r"\b(?:take|took|taken)\b.*\b(?:medicine|medication|meds?|pill|vitamin|supplement)\b", "take_medicine", "health", 0.85),
    (r"\b(?:log|record)\b.*\b(?:medicine|medication|meds?)\b", "take_medicine", "health", 0.80),

    # Fasting
    (r"\b(?:start|begin)\b.*\b(?:fast|fasting)\b", "start_fast", "health", 0.85),
    (r"\b(?:end|stop|break)\b.*\b(?:fast|fasting)\b", "end_fast", "health", 0.85),

    # Fitness
    (r"\b(?:log|record)\b.*\b(?:workout|exercise|training)\b", "log_workout", "health", 0.85),
    (r"\b(?:log|record)\b.*\b(?:run|jog|walk|swim|bike|cycle|lift)\b", "log_workout", "health", 0.75),
    (r"\b(?:log|record)\b.*\bsets?\b", "log_exercise_set", "health", 0.75),
    (r"\b(?:log|record)\b.*\bcardio\b", "log_cardio", "health", 0.80),

    # Journal
    (r"\b(?:write|create|start|add)\b.*\b(?:journal|journal entry|diary)\b", "create_journal_entry", "journal", 0.85),
    (r"\b(?:add|write|log)\b.*\bgratitude\b", "add_gratitude", "journal", 0.85),

    # Faith
    (r"\b(?:log|add|record|write)\b.*\bprayer\b", "log_prayer", "faith", 0.85),
    (r"\b(?:mark|set)\b.*\bprayer\b.*\b(?:answered|resolved)\b", "mark_prayer_answered", "faith", 0.85),
    (r"\b(?:save|bookmark)\b.*\b(?:verse|scripture)\b", "save_verse", "faith", 0.85),
    (r"\b(?:add|log)\b.*\bfaith\b.*\bmilestone\b", "add_faith_milestone", "faith", 0.80),

    # Goals
    (r"\b(?:create|set|add|make)\b.*\bgoal\b", "create_goal", "purpose", 0.85),
    (r"\b(?:update|progress)\b.*\bgoal\b", "update_goal_progress", "purpose", 0.80),
    (r"\b(?:set|create)\b.*\bintention\b", "set_intention", "purpose", 0.80),

    # Habits
    (r"\b(?:log|record|track|check|mark)\b.*\bhabit\b", "log_habit", "purpose", 0.85),
    (r"\b(?:completed?|done|did|finished)\b.*\bhabit\b", "log_habit", "purpose", 0.80),

    # Tasks
    (r"\b(?:create|add|make)\b.*\btask\b", "create_task", "life", 0.85),
    (r"\b(?:complete|finish|done)\b.*\btask\b", "complete_task", "life", 0.85),
    (r"\b(?:create|add|make)\b.*\bevent\b", "create_event", "life", 0.85),
    (r"\b(?:add|set|create)\b.*\breminder\b", "add_reminder", "life", 0.80),
]

# Compile patterns for performance
COMPILED_PATTERNS = [
    (re.compile(pattern, re.IGNORECASE), intent, domain, conf)
    for pattern, intent, domain, conf in INTENT_PATTERNS
]


# ---------------------------------------------------------------------------
# Entity extraction patterns
# ---------------------------------------------------------------------------

ENTITY_PATTERNS = {
    # Specific typed patterns FIRST (before generic numeric_value)
    "weight_with_unit": re.compile(
        r"\b(\d{2,3}(?:\.\d)?)\s*(lbs?|pounds?|kg|kilograms?)\b", re.IGNORECASE
    ),
    "bp_reading": re.compile(
        r"\b(\d{2,3})\s*/\s*(\d{2,3})\b"
    ),
    "percentage": re.compile(
        r"\b(\d{1,3}(?:\.\d)?)\s*%"
    ),
    "duration_minutes": re.compile(
        r"\b(\d{1,3})\s*(?:min(?:ute)?s?|mins?)\b", re.IGNORECASE
    ),
    "duration_hours": re.compile(
        r"\b(\d{1,2}(?:\.\d)?)\s*(?:hours?|hrs?)\b", re.IGNORECASE
    ),
    # Generic numeric fallback LAST
    "numeric_value": re.compile(
        r"\b(\d{1,4}(?:\.\d{1,2})?)\b"
    ),
}

# Time-related expressions (detected but NOT resolved -- HTIE does that)
TIME_EXPRESSION_PATTERN = re.compile(
    r"\b("
    r"yesterday|today|tonight|this morning|this afternoon|this evening|"
    r"last (?:night|monday|tuesday|wednesday|thursday|friday|saturday|sunday|week|month)|"
    r"(?:on )?(?:monday|tuesday|wednesday|thursday|friday|saturday|sunday)|"
    r"\d{1,2}[/-]\d{1,2}(?:[/-]\d{2,4})?|"
    r"\d{4}[/-]\d{1,2}[/-]\d{1,2}|"
    r"(?:\d{1,2}\s+)?(?:jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)\w*"
    r"(?:\s+\d{1,2})?(?:\s*,?\s*\d{4})?|"
    r"\d{1,2}\s*(?:am|pm)|"
    r"(?:at|around)\s+\d{1,2}(?::\d{2})?\s*(?:am|pm)?|"
    r"(?:\d+\s+)?(?:days?|weeks?|months?)\s+ago|"
    r"this (?:week|month|year)|"
    r"earlier (?:today|this week)"
    r")\b",
    re.IGNORECASE,
)

# Contextual reference patterns ("it", "that one", "my prayer")
CONTEXTUAL_REF_PATTERN = re.compile(
    r"\b(that (?:one|goal|task|prayer|habit|entry|verse|scripture|weight|reading)|"
    r"(?:my|the) (?:latest|last|recent|current) (?:entry|weight|goal|task|prayer|habit|reading)|"
    r"\bit\b)\b",
    re.IGNORECASE,
)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

class IntentCandidate:
    """A candidate intent detected from text analysis."""

    __slots__ = ("intent_type", "domain", "confidence", "matched_text")

    def __init__(self, intent_type, domain, confidence, matched_text=""):
        self.intent_type = intent_type
        self.domain = domain
        self.confidence = confidence
        self.matched_text = matched_text

    def to_dict(self):
        return {
            "intent_type": self.intent_type,
            "domain": self.domain,
            "confidence": self.confidence,
            "matched_text": self.matched_text,
        }


class ParseResult:
    """Result of semantic parsing."""

    __slots__ = (
        "intent_candidates",
        "entities",
        "time_expression",
        "contextual_references",
        "domain_hint",
        "raw_text",
    )

    def __init__(self):
        self.intent_candidates = []  # List[IntentCandidate]
        self.entities = {}           # Dict[str, Any]
        self.time_expression = ""    # Detected time phrase
        self.contextual_references = []  # List[str]
        self.domain_hint = ""        # Best guess at domain
        self.raw_text = ""

    @property
    def primary_intent(self):
        """Return highest-confidence intent candidate, or None."""
        if not self.intent_candidates:
            return None
        return max(self.intent_candidates, key=lambda c: c.confidence)

    @property
    def has_time(self):
        return bool(self.time_expression)

    @property
    def has_contextual_reference(self):
        return bool(self.contextual_references)

    def to_dict(self):
        primary = self.primary_intent
        return {
            "primary_intent": primary.to_dict() if primary else None,
            "all_candidates": [c.to_dict() for c in self.intent_candidates],
            "entities": self.entities,
            "time_expression": self.time_expression,
            "contextual_references": self.contextual_references,
            "domain_hint": self.domain_hint,
        }


def parse(raw_text):
    """
    Parse raw text into structured semantic components.

    This is a pure function with NO side effects and NO database calls.

    Args:
        raw_text: The user's raw input string.

    Returns:
        ParseResult with intent candidates, entities, time expressions,
        and contextual references.
    """
    result = ParseResult()
    result.raw_text = raw_text

    if not raw_text or not raw_text.strip():
        return result

    text = raw_text.strip()

    # Step 1: Detect intent candidates
    result.intent_candidates = _detect_intents(text)

    # Step 2: Extract entities
    result.entities = _extract_entities(text)

    # Step 3: Detect time expressions
    result.time_expression = _detect_time_expression(text)

    # Step 4: Detect contextual references
    result.contextual_references = _detect_contextual_references(text)

    # Step 5: Determine domain hint
    if result.intent_candidates:
        result.domain_hint = result.primary_intent.domain

    return result


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _detect_intents(text):
    """Match text against intent patterns. Returns ranked list."""
    candidates = []
    seen_intents = set()

    for compiled_re, intent_type, domain, base_confidence in COMPILED_PATTERNS:
        match = compiled_re.search(text)
        if match and intent_type not in seen_intents:
            candidates.append(IntentCandidate(
                intent_type=intent_type,
                domain=domain,
                confidence=base_confidence,
                matched_text=match.group(0),
            ))
            seen_intents.add(intent_type)

    # Sort by confidence descending
    candidates.sort(key=lambda c: c.confidence, reverse=True)
    return candidates


def _extract_entities(text):
    """Extract structured entities from text."""
    entities = {}

    for entity_name, pattern in ENTITY_PATTERNS.items():
        match = pattern.search(text)
        if match:
            if entity_name == "weight_with_unit":
                entities["value"] = float(match.group(1))
                entities["unit"] = _normalize_unit(match.group(2))
            elif entity_name == "bp_reading":
                entities["systolic"] = int(match.group(1))
                entities["diastolic"] = int(match.group(2))
            elif entity_name == "percentage":
                entities["percentage"] = float(match.group(1))
            elif entity_name == "duration_minutes":
                entities["duration_minutes"] = int(match.group(1))
            elif entity_name == "duration_hours":
                entities["duration_hours"] = float(match.group(1))
            elif entity_name == "numeric_value" and "value" not in entities:
                # Only use raw numeric if no typed value found
                entities["numeric_value"] = float(match.group(1))

    return entities


def _detect_time_expression(text):
    """Detect time expressions in text. Does NOT resolve them."""
    match = TIME_EXPRESSION_PATTERN.search(text)
    if match:
        return match.group(0).strip()
    return ""


def _detect_contextual_references(text):
    """Detect phrases that reference existing records/context."""
    refs = []
    for match in CONTEXTUAL_REF_PATTERN.finditer(text):
        refs.append(match.group(0).strip())
    return refs


def _normalize_unit(unit_str):
    """Normalize weight unit strings."""
    unit_lower = unit_str.lower()
    if unit_lower in ("lb", "lbs", "pound", "pounds"):
        return "lb"
    if unit_lower in ("kg", "kilogram", "kilograms"):
        return "kg"
    return unit_lower
