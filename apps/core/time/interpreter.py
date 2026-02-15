"""
HTIE Interpreter Orchestrator — Main entry point for human time interpretation.

Coordinates parsing, ambiguity detection, and resolution into a single call.
This is the public API that the AI assistant integration (prompt #3) will use.
"""

from apps.core.time.ambiguity_detector import detect_ambiguity
from apps.core.time.parser import parse_time_expression
from apps.core.time.resolver import resolve_time_expression
from apps.core.time.system_clock import get_current_time


class InterpretationResult:
    """Full result of interpreting a human time expression."""

    __slots__ = (
        "success",
        "resolved_time",
        "is_ambiguous",
        "clarification_question",
        "original_input",
        "time_expression",
        "remaining_text",
        "error",
    )

    def __init__(self, **kwargs):
        self.success = kwargs.get("success", False)
        self.resolved_time = kwargs.get("resolved_time")
        self.is_ambiguous = kwargs.get("is_ambiguous", False)
        self.clarification_question = kwargs.get("clarification_question")
        self.original_input = kwargs.get("original_input")
        self.time_expression = kwargs.get("time_expression")
        self.remaining_text = kwargs.get("remaining_text")
        self.error = kwargs.get("error")

    def to_dict(self):
        result = {
            "success": self.success,
            "original_input": self.original_input,
            "time_expression": self.time_expression,
            "remaining_text": self.remaining_text,
        }
        if self.success and self.resolved_time:
            result["resolved_datetime"] = self.resolved_time.datetime_aware.isoformat()
            result["confidence"] = self.resolved_time.confidence
        if self.is_ambiguous:
            result["is_ambiguous"] = True
            result["clarification_question"] = self.clarification_question
        if self.error:
            result["error"] = self.error
        return result


def interpret_human_time(user_input, user_timezone=None):
    """
    Main entry point: interpret a natural language time expression.

    Args:
        user_input: Raw string from user (e.g. "update my weight to 250 lbs 3 days ago")
        user_timezone: Optional IANA timezone string (e.g. 'America/New_York').
                       Falls back to Django settings.TIME_ZONE.

    Returns:
        InterpretationResult with either:
        - success=True + resolved_time (precise datetime)
        - is_ambiguous=True + clarification_question (needs user input)
        - success=False + error (could not parse)
    """
    if not user_input or not user_input.strip():
        return InterpretationResult(
            success=False,
            original_input=user_input,
            error="Empty input",
        )

    reference_time = get_current_time(user_timezone)

    # Step 1: Parse — extract time expression from input
    parsed = parse_time_expression(user_input)

    if not parsed.has_time:
        return InterpretationResult(
            success=False,
            original_input=user_input,
            remaining_text=parsed.remaining_text,
            error="No time expression found in input",
        )

    # Step 2: Check for ambiguity — ask rather than guess
    ambiguity = detect_ambiguity(parsed, reference_time)

    if ambiguity.is_ambiguous:
        return InterpretationResult(
            success=False,
            is_ambiguous=True,
            clarification_question=ambiguity.clarification_question,
            original_input=user_input,
            time_expression=parsed.time_expression,
            remaining_text=parsed.remaining_text,
        )

    # Step 3: Resolve — convert to precise timestamp
    resolved = resolve_time_expression(parsed.time_expression, reference_time)

    if resolved is None:
        return InterpretationResult(
            success=False,
            original_input=user_input,
            time_expression=parsed.time_expression,
            remaining_text=parsed.remaining_text,
            error=f"Could not resolve time expression: '{parsed.time_expression}'",
        )

    return InterpretationResult(
        success=True,
        resolved_time=resolved,
        original_input=user_input,
        time_expression=parsed.time_expression,
        remaining_text=parsed.remaining_text,
    )
