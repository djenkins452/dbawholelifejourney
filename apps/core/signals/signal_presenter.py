"""
Phase 3 — Signal Presenter: Controlled Exposure Layer

Transforms raw Phase 2 signals into safe, user-facing suggestions.
This is a PRESENTATION layer only — it never writes to the database,
never marks anything complete, and never alters execution truth.

ARCHITECTURAL RULES:
- Execution Truth Engine remains the only source of truth
- Signal Engine remains read-only and passive
- This layer may only format and filter signals
- Output language always preserves uncertainty (suggestions, not facts)
- Maximum 2 surfaced suggestions at a time
- Only same-day signals may be surfaced

Pipeline:
    detect_signals(user) → get_execution_truth(user) → filter → present

Consumers: Beth (conversational AI), optional UI suggestion cards.
"""

import logging
from datetime import date, datetime
from typing import Dict, List, Optional

from django.utils import timezone

from apps.core.signals.signal_engine import (
    EFFORT_SIGNAL,
    INCONSISTENCY_SIGNAL,
    INTENT_SIGNAL,
    POSSIBLE_COMPLETION,
    detect_signals,
)

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

MAX_SUGGESTIONS = 2

# Priority order: lower number = higher priority
SIGNAL_TYPE_PRIORITY = {
    POSSIBLE_COMPLETION: 1,
    INCONSISTENCY_SIGNAL: 2,
    INTENT_SIGNAL: 3,
    EFFORT_SIGNAL: 4,
}

# Friendly labels for items (signal item -> human label)
ITEM_LABELS = {
    "prayer": "prayer",
    "bible_reading": "Bible reading",
    "church": "church attendance",
    "workout": "your workout",
    "running": "your run",
    "walking": "your walk",
    "yoga": "your yoga session",
    "journal_entry": "journaling",
    "goal_work": "your goal work",
}

# Friendly labels for domains (fallback when item is missing)
DOMAIN_LABELS = {
    "faith": "your faith practice",
    "health": "your workout",
    "journal": "journaling",
    "purpose": "your goal work",
}

# ---------------------------------------------------------------------------
# Message templates by signal type
# ---------------------------------------------------------------------------

MESSAGE_TEMPLATES = {
    POSSIBLE_COMPLETION: {
        "message": "We noticed you may have completed {label} today. Want to mark it as done?",
        "question": "Did you complete {label} today?",
    },
    INCONSISTENCY_SIGNAL: {
        "message": "You mentioned something that may conflict with today's plan for {label}. Want to review it?",
        "question": "Do you want to update {label} for today?",
    },
    INTENT_SIGNAL: {
        "message": "It looks like you may be planning to {label} today.",
        "question": "Do you want to keep {label} on your plan for today?",
    },
    EFFORT_SIGNAL: {
        "message": "It sounds like you made an effort on {label} today, even if it may not be complete.",
        "question": "Do you want to update {label} based on what you did?",
    },
}


# ---------------------------------------------------------------------------
# Domain+Item → Truth mapping
# ---------------------------------------------------------------------------

def _is_completed_in_truth(domain: str, item: str, truth: Dict) -> bool:
    """Check if a signal's domain+item is already completed in execution truth.

    Returns True if truth says the item is completed, False otherwise.
    """
    domains = truth.get("domains", {})

    if domain == "faith":
        faith = domains.get("faith", {})
        if item == "prayer":
            return faith.get("prayer_completed", False)
        if item == "bible_reading":
            return faith.get("bible_reading_completed", False)
        if item == "church":
            # No specific church completion tracking — check both faith items
            return (
                faith.get("prayer_completed", False)
                and faith.get("bible_reading_completed", False)
            )
        # Unknown faith item — not completed
        return False

    if domain == "health":
        return domains.get("workout", {}).get("completed", False)

    if domain == "journal":
        return domains.get("journal", {}).get("completed", False)

    # Purpose and other domains: no truth tracking yet
    return False


def _is_expected_in_truth(domain: str, item: str, truth: Dict) -> bool:
    """Check if a signal's domain+item is expected today in execution truth.

    Returns True if the domain/item is expected, False if not.
    If the domain has no expectation tracking, returns True (don't suppress).
    """
    domains = truth.get("domains", {})

    if domain == "faith":
        faith = domains.get("faith", {})
        if item == "prayer":
            return faith.get("prayer_expected", False)
        if item == "bible_reading":
            return faith.get("bible_expected", False)
        if item == "church":
            # Church not specifically tracked — allow if faith is expected
            return faith.get("expected", False)
        return faith.get("expected", False)

    if domain == "health":
        return domains.get("workout", {}).get("expected", False)

    if domain == "journal":
        return domains.get("journal", {}).get("expected", False)

    # Purpose and other domains: no expectation tracking → don't suppress
    return True


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def get_presented_signals(user) -> Dict:
    """Transform raw signals into safe, presentation-ready suggestions.

    This is the single entry point for Beth and UI consumers.

    Pipeline:
        1. Fetch raw signals from Signal Engine
        2. Fetch execution truth
        3. Filter: same-day only, suppress completed/unexpected
        4. Deduplicate by (type, domain, item)
        5. Prioritize and limit to MAX_SUGGESTIONS
        6. Build user-facing messages

    Returns:
        {
            "suggestions": [
                {
                    "type": str,
                    "domain": str,
                    "item": str,
                    "confidence": float,
                    "source": str,
                    "text": str,
                    "timestamp": str (ISO),
                    "message": str,
                    "question": str,
                    "priority": int,
                }
            ]
        }
    """
    raw = _get_raw_signals(user)
    truth = _get_execution_truth(user)

    signals = raw.get("signals", [])

    # Filter pipeline
    signals = _filter_same_day(signals)
    signals = _filter_completed_or_unexpected(signals, truth)
    signals = _deduplicate_suggestions(signals)
    signals = _prioritize_signals(signals)
    signals = signals[:MAX_SUGGESTIONS]

    # Build presentation output
    suggestions = _normalize_presented_output(signals)

    logger.info(
        "[SIGNAL PRESENTER] user=%s raw=%d filtered_to=%d",
        user.id, len(raw.get("signals", [])), len(suggestions),
    )

    return {"suggestions": suggestions}


# ---------------------------------------------------------------------------
# Internal pipeline steps
# ---------------------------------------------------------------------------

def _get_raw_signals(user) -> Dict:
    """Fetch signals from Phase 2 Signal Engine."""
    try:
        return detect_signals(user)
    except Exception:
        logger.error(
            "Signal presenter: failed to fetch signals", exc_info=True,
        )
        return {"signals": []}


def _get_execution_truth(user) -> Dict:
    """Fetch execution truth from Phase 1 Execution Truth Engine."""
    try:
        from apps.core.execution.execution_truth_engine import get_execution_truth
        return get_execution_truth(user)
    except ImportError:
        logger.warning("Signal presenter: execution truth engine not available")
        return {}
    except Exception:
        logger.error(
            "Signal presenter: failed to fetch execution truth", exc_info=True,
        )
        return {}


def _filter_same_day(signals: List[Dict]) -> List[Dict]:
    """Only keep signals from today (system timezone).

    Signals without a timestamp are excluded.
    """
    today = timezone.localdate()
    result = []
    for sig in signals:
        ts = sig.get("timestamp")
        if ts is None:
            continue
        if isinstance(ts, datetime):
            sig_date = timezone.localdate(ts)
        elif isinstance(ts, date):
            sig_date = ts
        else:
            continue
        if sig_date == today:
            result.append(sig)
    return result


def _filter_completed_or_unexpected(
    signals: List[Dict], truth: Dict,
) -> List[Dict]:
    """Remove signals for items that are already completed or not expected.

    Rule: If truth says completed=True → suppress.
    Rule: If truth says expected=False → suppress.
    """
    result = []
    for sig in signals:
        domain = sig.get("domain", "")
        item = sig.get("item", "")

        if _is_completed_in_truth(domain, item, truth):
            continue

        if not _is_expected_in_truth(domain, item, truth):
            continue

        result.append(sig)
    return result


def _deduplicate_suggestions(signals: List[Dict]) -> List[Dict]:
    """Deduplicate by (type, domain, item), keeping highest confidence."""
    best = {}
    for sig in signals:
        key = (sig.get("type"), sig.get("domain"), sig.get("item"))
        existing = best.get(key)
        if existing is None or sig.get("confidence", 0) > existing.get("confidence", 0):
            best[key] = sig
    return list(best.values())


def _prioritize_signals(signals: List[Dict]) -> List[Dict]:
    """Sort signals by priority order, then confidence, then recency.

    Priority: possible_completion > inconsistency > intent > effort
    Within same type: higher confidence first, newer timestamp first.
    """
    def sort_key(sig):
        type_priority = SIGNAL_TYPE_PRIORITY.get(sig.get("type"), 99)
        confidence = -(sig.get("confidence", 0))  # negative for descending
        ts = sig.get("timestamp")
        if isinstance(ts, datetime):
            ts_val = -ts.timestamp()  # negative for descending (newer first)
        else:
            ts_val = 0
        return (type_priority, confidence, ts_val)

    return sorted(signals, key=sort_key)


def _get_item_label(signal: Dict) -> str:
    """Get a human-friendly label for a signal's item."""
    item = signal.get("item", "")
    if item and item in ITEM_LABELS:
        return ITEM_LABELS[item]
    domain = signal.get("domain", "")
    return DOMAIN_LABELS.get(domain, "this item")


def _build_message(signal: Dict) -> str:
    """Build the suggestion message for a signal."""
    signal_type = signal.get("type", "")
    template = MESSAGE_TEMPLATES.get(signal_type, {})
    msg_template = template.get("message", "")
    if not msg_template:
        return ""
    label = _get_item_label(signal)
    return msg_template.format(label=label)


def _build_question(signal: Dict) -> str:
    """Build the suggestion question for a signal."""
    signal_type = signal.get("type", "")
    template = MESSAGE_TEMPLATES.get(signal_type, {})
    q_template = template.get("question", "")
    if not q_template:
        return ""
    label = _get_item_label(signal)
    return q_template.format(label=label)


def _normalize_presented_output(signals: List[Dict]) -> List[Dict]:
    """Convert filtered signals into the final presentation format.

    Each suggestion includes the original signal metadata plus
    message, question, and priority fields.
    """
    suggestions = []
    for i, sig in enumerate(signals):
        ts = sig.get("timestamp")
        if isinstance(ts, datetime):
            ts_str = ts.isoformat()
        else:
            ts_str = str(ts) if ts else ""

        suggestion = {
            "type": sig.get("type", ""),
            "domain": sig.get("domain", ""),
            "item": sig.get("item", ""),
            "confidence": sig.get("confidence", 0),
            "source": sig.get("source", ""),
            "text": sig.get("text", ""),
            "timestamp": ts_str,
            "message": _build_message(sig),
            "question": _build_question(sig),
            "priority": i + 1,
        }
        suggestions.append(suggestion)
    return suggestions
