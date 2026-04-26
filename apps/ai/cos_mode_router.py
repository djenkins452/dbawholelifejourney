"""
CoS Decision Mode Router — deterministic keyword resolver.

Maps a raw user message to one of three deterministic CoS decision modes:

    "execution"  — "what should I do right now?"
    "risk"       — "what is my biggest risk right now?"
    "fix"        — "what should I fix first?"

NO LLM is involved. Routing is keyword-based and case-insensitive. The
resolver returns either a mode string ("execution" | "risk" | "fix") or
None when the message does not match — in which case the normal intent
pipeline handles it.

This module is the SINGLE source of truth for "is this a deterministic
mode query?" — both the chat shortcut in personal_assistant.send_message
and the JSON API at /assistant/api/cos/decision/?mode=... consult it.
"""

import re

# Case-insensitive substring patterns. We use word-boundary matching for
# short tokens (e.g. "fix") to avoid false positives ("affix", "prefix").

# RISK MODE — phrases asking what is most at-risk right now.
_RISK_PATTERNS = [
    r"\bbiggest risk\b",
    r"\bbiggest concern\b",
    r"\bbiggest problem\b",
    r"\bwhat'?s? wrong\b",
    r"\bwhat is wrong\b",
    r"\bwhat should i worry\b",
    r"\bwhat am i at risk\b",
    r"\bat risk\b",
    r"\bgreatest risk\b",
    r"\bmost at risk\b",
    r"\btop risk\b",
    r"\brisk right now\b",
]

# FIX MODE — phrases asking what to clean up first / what's behind.
_FIX_PATTERNS = [
    r"\bwhat should i fix\b",
    r"\bwhat to fix\b",
    r"\bclean up\b",
    r"\bcleanup\b",
    r"\bfix first\b",
    r"\bcatch up\b",
    r"\bbehind on\b",
    r"\bfalling behind\b",
    r"\bfix the most\b",
    r"\bfix backlog\b",
    r"\breduce backlog\b",
]

# EXECUTION MODE — explicit "what should I do" phrasing AND broad
# status-style queries. CoS Strict Mode Isolation: any status query
# defaults to Execution so the LLM never gets to compose a blended
# multi-mode briefing.
_EXECUTION_PATTERNS = [
    # Direct execution prompts
    r"\bwhat should i do\b",
    r"\bwhat'?s? next\b",
    r"\bwhat is next\b",
    r"\bnext action\b",
    r"\bdo right now\b",
    r"\bwhat now\b",
    r"\bnext step\b",
    r"\bwhat'?s the next\b",
    # Generic status queries (per user spec — must default to Execution)
    r"\bhow am i doing\b",
    r"\bhow are we doing\b",
    r"\bhow'?s? my day\b",
    r"\bhow is my day\b",
    r"\bwhere am i at\b",
    r"\bwhere am i\b",
    r"\bstatus\b",
    r"\bwhat'?s going on\b",
    r"\bwhat is going on\b",
    r"\bgive me an update\b",
    r"\bgive me a status\b",
    r"\bgive me a brief\b",
    r"\bbrief me\b",
    r"\bupdate me\b",
    r"\bwalk me through\b",
    r"\bmy situation\b",
    r"\bcurrent situation\b",
    r"\bstate of (the )?day\b",
    r"\bwhere do i stand\b",
]

VALID_MODES = ("execution", "risk", "fix")


def _matches_any(text: str, patterns) -> bool:
    return any(re.search(p, text) for p in patterns)


def resolve_cos_mode(user_input: str):
    """
    Resolve a user message to a CoS decision mode, or None.

    Args:
        user_input: raw message text. May be None or empty.

    Returns:
        "execution" | "risk" | "fix" — when the message clearly maps to
        a mode.
        None — when the message does not match any deterministic mode
        keyword. The caller should fall through to the normal intent
        pipeline.

    Precedence (per CoS Strict Mode Isolation contract):
        FIX > RISK > EXECUTION

    Fix-mode phrasings ("what to fix", "catch up", "behind on") are
    the most specific and the most user-actionable, so they win when
    a message overlaps multiple categories. Risk wins over Execution
    for the same reason. Generic status queries map to Execution.
    """
    if not user_input:
        return None
    text = str(user_input).strip().lower()
    if not text:
        return None

    if _matches_any(text, _FIX_PATTERNS):
        return "fix"
    if _matches_any(text, _RISK_PATTERNS):
        return "risk"
    if _matches_any(text, _EXECUTION_PATTERNS):
        return "execution"
    return None


def normalize_mode(mode: str) -> str:
    """Normalize an explicit mode string from the API endpoint.

    Accepts only the three canonical mode names. Unknown / missing
    input returns "execution" (the default mode per spec).
    """
    if not mode:
        return "execution"
    m = str(mode).strip().lower()
    return m if m in VALID_MODES else "execution"
