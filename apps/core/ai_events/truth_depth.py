# ==============================================================================
# File: apps/core/ai_events/truth_depth.py
# Project: Whole Life Journey — Django 5.x Personal Wellness/Journaling App
# Description: Truth Depth classifier — determines data access depth for queries
# Owner: Danny Jenkins (admin@wholelifejourney.com)
# Created: 2026-03-28
# ==============================================================================
"""
Truth Depth Classifier.

Classifies user queries into one of three truth depth levels:

    SUMMARY — Aggregate state (SAE/reporting). "How am I doing?"
    SIGNAL  — Intelligence signals (PIE/PRIE). "Why am I slipping?"
    EVENT   — Raw execution data. "What did I miss and when?"

This classifier is purely lexical — no LLM, no ML. It uses narrow,
high-confidence keyword matching. False negatives are safe (fall through
to existing pipeline). False positives would cause wrong data access.

The router uses this to decide whether to invoke the Event Access Layer
(EVENT depth) instead of the default state-based response.
"""

import re

# =============================================================================
# Truth Depth Constants
# =============================================================================

DEPTH_SUMMARY = 'summary'
DEPTH_SIGNAL = 'signal'
DEPTH_EVENT = 'event'


# =============================================================================
# EVENT Depth Patterns — "What happened? What did I miss?"
# =============================================================================

# Direct miss/skip queries
_MISSED_PATTERNS = (
    'what did i miss',
    'what have i missed',
    'anything i missed',
    'did i miss anything',
    'did i miss any',
    'missed dose',
    'missed doses',
    'missed medication',
    'missed medications',
    'missed med',
    'missed meds',
    'which dose did i miss',
    'which medication did i miss',
    'what dose did i miss',
    'what medication did i miss',
    'what did i skip',
    'what have i skipped',
    'what routine did i miss',
    'which routine did i miss',
    'missed routine',
    'missed routines',
)

# Timeline/history queries
_TIMELINE_PATTERNS = (
    'what happened yesterday',
    'what happened today',
    'what happened this week',
    'what happened last week',
    'show me yesterday',
    'show me today',
    'what did i do yesterday',
    'what did i do today',
    'what was my day like yesterday',
    'give me a breakdown of yesterday',
    'timeline for yesterday',
    'timeline for today',
)

# Slippage/trend queries (EVENT depth because they need event-level detail)
_SLIPPAGE_PATTERNS = (
    'when did my routine start slipping',
    'when did i start slipping',
    'when did things start slipping',
    'when did i start missing',
    'when did my routine drop',
    'when did my adherence drop',
    'when did i stop following my routine',
    'when did i fall off',
)

# Date-specific event queries
_DATE_EVENT_RE = re.compile(
    r'what (?:did i (?:miss|do|take|skip|complete)|happened) '
    r'(?:on |last |this )?\w+day',
    re.IGNORECASE,
)


# =============================================================================
# SIGNAL Depth Patterns — "Why is X happening?"
# =============================================================================

_SIGNAL_PATTERNS = (
    'why am i slipping',
    'why is my score',
    'what caused',
    'what led to',
    'what pattern',
    'what patterns',
    'what correlat',
    'why did my',
)


# =============================================================================
# Public API
# =============================================================================

def classify_truth_depth(msg_lower):
    """
    Classify a message's required truth depth.

    Args:
        msg_lower: User message, already lowercased

    Returns:
        str — one of DEPTH_SUMMARY, DEPTH_SIGNAL, DEPTH_EVENT
        Returns DEPTH_SUMMARY as default (safest — existing pipeline)
    """
    # Check EVENT patterns first (highest specificity)
    if any(p in msg_lower for p in _MISSED_PATTERNS):
        return DEPTH_EVENT

    if any(p in msg_lower for p in _TIMELINE_PATTERNS):
        return DEPTH_EVENT

    if any(p in msg_lower for p in _SLIPPAGE_PATTERNS):
        return DEPTH_EVENT

    if _DATE_EVENT_RE.search(msg_lower):
        return DEPTH_EVENT

    # Check SIGNAL patterns
    if any(p in msg_lower for p in _SIGNAL_PATTERNS):
        return DEPTH_SIGNAL

    # Default: SUMMARY (existing pipeline handles it)
    return DEPTH_SUMMARY


def needs_event_access(msg_lower):
    """
    Quick check: does this message need event-level data access?

    Returns True only for EVENT depth. Used by router to decide
    whether to invoke the Event Access Layer.
    """
    return classify_truth_depth(msg_lower) == DEPTH_EVENT


def classify_event_query_type(msg_lower):
    """
    For EVENT-depth queries, determine the specific query type.

    Returns:
        str — 'missed', 'timeline', 'slippage', or None
    """
    if any(p in msg_lower for p in _MISSED_PATTERNS):
        return 'missed'

    if any(p in msg_lower for p in _TIMELINE_PATTERNS):
        return 'timeline'

    if any(p in msg_lower for p in _SLIPPAGE_PATTERNS):
        return 'slippage'

    if _DATE_EVENT_RE.search(msg_lower):
        return 'timeline'

    return None


def detect_domain_hint(msg_lower):
    """
    Detect if the query is scoped to a specific domain.

    Returns:
        str — domain name or None for cross-domain queries
    """
    _MEDICATION_HINTS = (
        'dose', 'doses', 'medication', 'medications', 'medicine',
        'medicines', 'med ', 'meds', 'pill', 'pills', 'drug',
    )
    _ROUTINE_HINTS = (
        'routine', 'routines', 'morning routine', 'evening routine',
        'habit', 'habits',
    )
    _WORKOUT_HINTS = (
        'workout', 'workouts', 'exercise', 'gym', 'training',
    )

    if any(h in msg_lower for h in _MEDICATION_HINTS):
        return 'medication'
    if any(h in msg_lower for h in _ROUTINE_HINTS):
        return 'routine'
    if any(h in msg_lower for h in _WORKOUT_HINTS):
        return 'workout'

    return None
