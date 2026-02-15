"""
Ambiguity Detector — Identify unclear time expressions that need clarification.

The AI must NEVER guess dates. If a time expression is ambiguous,
this module detects it and generates a clarification question.
"""

import re
from datetime import timedelta

from apps.core.time.resolver import DAY_NAMES, _get_next_weekday


class AmbiguityResult:
    """Result of ambiguity detection."""

    __slots__ = ("is_ambiguous", "clarification_question", "candidates", "reason")

    def __init__(
        self, is_ambiguous, clarification_question=None, candidates=None, reason=None
    ):
        self.is_ambiguous = is_ambiguous
        self.clarification_question = clarification_question
        self.candidates = candidates or []
        self.reason = reason

    def to_dict(self):
        result = {"is_ambiguous": self.is_ambiguous}
        if self.is_ambiguous:
            result["clarification_question"] = self.clarification_question
            if self.candidates:
                result["candidates"] = self.candidates
            if self.reason:
                result["reason"] = self.reason
        return result


# Vague expressions that always need clarification
VAGUE_PATTERNS = [
    (r"\brecently\b", "When specifically did this happen? (e.g., '3 days ago', 'last Tuesday')"),
    (r"\ba\s+while\s+ago\b", "How long ago? (e.g., '2 weeks ago', 'last month')"),
    (r"\bthe\s+other\s+day\b", "Which day specifically? (e.g., 'Monday', '3 days ago')"),
    (r"\bsometime\s+last\s+week\b", "Which day last week? (e.g., 'last Monday', 'last Wednesday')"),
    (r"\bsometime\s+next\s+week\b", "Which day next week? (e.g., 'next Monday', 'next Wednesday')"),
    (r"\bsometime\s+last\s+month\b", "What date last month? (e.g., 'last month on the 15th')"),
    (r"\bsometime\s+next\s+month\b", "What date next month? (e.g., 'next month on the 10th')"),
]


def detect_ambiguity(parsed_input, reference_time):
    """
    Check if a parsed time expression is ambiguous.

    Args:
        parsed_input: ParsedTimeInput from parser.py
        reference_time: Timezone-aware datetime representing "now".

    Returns:
        AmbiguityResult indicating whether clarification is needed.
    """
    if not parsed_input.has_time:
        return AmbiguityResult(is_ambiguous=False)

    expr = parsed_input.time_expression.strip().lower()

    # Check vague patterns first
    for pattern, question in VAGUE_PATTERNS:
        if re.search(pattern, expr):
            return AmbiguityResult(
                is_ambiguous=True,
                clarification_question=question,
                reason="vague_expression",
            )

    # "next WEEKDAY" when today IS that weekday — could mean today or +7
    m = re.match(r"next\s+(monday|tuesday|wednesday|thursday|friday|saturday|sunday)", expr)
    if m:
        target_day = DAY_NAMES[m.group(1)]
        if reference_time.weekday() == target_day:
            next_date = reference_time + timedelta(days=7)
            today_str = reference_time.strftime("%B %d")
            next_str = next_date.strftime("%B %d")
            return AmbiguityResult(
                is_ambiguous=True,
                clarification_question=(
                    f"Today is {m.group(1).title()}. "
                    f"Did you mean today ({today_str}) or next week ({next_str})?"
                ),
                candidates=[
                    reference_time.strftime("%Y-%m-%d"),
                    next_date.strftime("%Y-%m-%d"),
                ],
                reason="same_day_ambiguity",
            )

    # "last WEEKDAY" when today IS that weekday — could mean today or -7
    m = re.match(r"last\s+(monday|tuesday|wednesday|thursday|friday|saturday|sunday)", expr)
    if m:
        target_day = DAY_NAMES[m.group(1)]
        if reference_time.weekday() == target_day:
            last_date = reference_time - timedelta(days=7)
            today_str = reference_time.strftime("%B %d")
            last_str = last_date.strftime("%B %d")
            return AmbiguityResult(
                is_ambiguous=True,
                clarification_question=(
                    f"Today is {m.group(1).title()}. "
                    f"Did you mean today ({today_str}) or last week ({last_str})?"
                ),
                candidates=[
                    reference_time.strftime("%Y-%m-%d"),
                    last_date.strftime("%Y-%m-%d"),
                ],
                reason="same_day_ambiguity",
            )

    # "next month on the Nth" — confirm the target month
    m = re.match(r"next\s+month\s+on\s+the\s+(\d{1,2})", expr)
    if m:
        from dateutil.relativedelta import relativedelta

        target_day = int(m.group(1))
        next_month = reference_time + relativedelta(months=1)
        # Check if day is valid for that month
        import calendar

        _, max_day = calendar.monthrange(next_month.year, next_month.month)
        if target_day > max_day:
            return AmbiguityResult(
                is_ambiguous=True,
                clarification_question=(
                    f"{next_month.strftime('%B %Y')} only has {max_day} days. "
                    f"Did you mean the {max_day}th?"
                ),
                reason="invalid_day_for_month",
            )

    # Not ambiguous
    return AmbiguityResult(is_ambiguous=False)
