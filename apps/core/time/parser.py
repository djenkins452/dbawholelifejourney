"""
Natural Language Time Parser — Extract time expressions from user input.

Identifies and extracts temporal phrases from mixed user input,
separating the time component from the action/content component.
"""

import re

# Ordered longest-first so greedy patterns match before shorter ones
TIME_PATTERNS = [
    # Anchored relative with time: "next Friday at 2pm", "next month on the 15th at 10am"
    r"(?:next|this|last)\s+(?:monday|tuesday|wednesday|thursday|friday|saturday|sunday)"
    r"(?:\s+at\s+\d{1,2}(?::\d{2})?\s*(?:am|pm|AM|PM)?)?",
    r"(?:next|last)\s+month\s+on\s+the\s+\d{1,2}(?:st|nd|rd|th)?"
    r"(?:\s+at\s+\d{1,2}(?::\d{2})?\s*(?:am|pm|AM|PM)?)?",
    r"(?:next|last)\s+(?:week|month|year)"
    r"(?:\s+on\s+(?:monday|tuesday|wednesday|thursday|friday|saturday|sunday))?"
    r"(?:\s+at\s+\d{1,2}(?::\d{2})?\s*(?:am|pm|AM|PM)?)?",
    # Relative with time: "tomorrow at 2pm", "yesterday at noon"
    r"(?:tomorrow|yesterday)\s+(?:morning|afternoon|evening|night)"
    r"(?:\s+at\s+\d{1,2}(?::\d{2})?\s*(?:am|pm|AM|PM)?)?",
    r"(?:tomorrow|yesterday)\s+at\s+\d{1,2}(?::\d{2})?\s*(?:am|pm|AM|PM)?",
    # Duration from now with time: "a week from today at 2pm"
    r"(?:a|an|\d+)\s+(?:minute|hour|day|week|month|year)s?\s+from\s+(?:now|today)"
    r"(?:\s+at\s+\d{1,2}(?::\d{2})?\s*(?:am|pm|AM|PM)?)?",
    # Relative durations: "3 days ago", "in 90 minutes", "in 4 weeks"
    r"in\s+(?:a|an|\d+)\s+(?:minute|hour|day|week|month|year)s?",
    r"(?:a|an|\d+)\s+(?:minute|hour|day|week|month|year)s?\s+ago",
    # Simple relative: "tomorrow", "yesterday", "today"
    r"(?:tomorrow|yesterday|today)",
    # Named periods: "this morning", "tonight", "last night"
    r"(?:this|last|next)\s+(?:morning|afternoon|evening|night)",
    r"tonight",
    # Vague/ambiguous: "recently", "sometime last week", "a while ago"
    r"recently",
    r"sometime\s+(?:last|next)\s+(?:week|month|year)",
    r"a\s+while\s+ago",
    r"the\s+other\s+day",
]

# Compile all patterns into one alternation, case-insensitive
_COMBINED_PATTERN = re.compile(
    r"\b(" + "|".join(TIME_PATTERNS) + r")\b",
    re.IGNORECASE,
)


class ParsedTimeInput:
    """Result of parsing a user input for time expressions."""

    __slots__ = ("original_input", "time_expression", "remaining_text", "has_time")

    def __init__(self, original_input, time_expression, remaining_text):
        self.original_input = original_input
        self.time_expression = time_expression
        self.remaining_text = remaining_text
        self.has_time = bool(time_expression)

    def to_dict(self):
        return {
            "original_input": self.original_input,
            "time_expression": self.time_expression,
            "remaining_text": self.remaining_text,
            "has_time": self.has_time,
        }


def parse_time_expression(user_input):
    """
    Extract a time expression from user input.

    Args:
        user_input: Raw string from the user.

    Returns:
        ParsedTimeInput with extracted time expression and remaining text.
    """
    if not user_input or not user_input.strip():
        return ParsedTimeInput(user_input, None, user_input)

    text = user_input.strip()
    match = _COMBINED_PATTERN.search(text)

    if not match:
        return ParsedTimeInput(user_input, None, text)

    time_expr = match.group(0).strip()
    # Remove the time expression from the text to get remaining content
    remaining = (text[: match.start()] + text[match.end() :]).strip()
    # Clean up extra whitespace and trailing/leading punctuation
    remaining = re.sub(r"\s+", " ", remaining).strip(" ,.")

    return ParsedTimeInput(user_input, time_expr, remaining)
