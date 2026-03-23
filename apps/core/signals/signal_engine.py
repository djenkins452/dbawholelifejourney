"""
Phase 2 — Signal Engine: Behavioral Awareness (Read-Only)

Detects possible user behavior or intent from unstructured text inputs.
Answers: "What might the user have done or intended?"
NOT: "What DID the user complete?"

ARCHITECTURAL RULES:
- Read-only: no DB writes, no side effects
- No coupling to Execution Truth Engine
- Conservative detection: high-confidence matches only (>= 0.70)
- Signals NEVER modify execution truth, mark completions, or affect scoring

Input sources: JournalEntry.body, WorkoutSession.notes
"""

import logging
import re
from datetime import timedelta

from django.utils import timezone

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Signal types
# ---------------------------------------------------------------------------
POSSIBLE_COMPLETION = "possible_completion"
EFFORT_SIGNAL = "effort_signal"
INTENT_SIGNAL = "intent_signal"
INCONSISTENCY_SIGNAL = "inconsistency_signal"

CONFIDENCE_FLOOR = 0.70

# ---------------------------------------------------------------------------
# Domain keyword maps — conservative, high-precision patterns
# ---------------------------------------------------------------------------

# Strong action verbs indicating completion (past tense / completed phrasing)
_COMPLETION_PATTERNS = {
    "faith": {
        "keywords": [
            r"\b(?:pray(?:ed|er)?|prayer time|devotion(?:al)?|bible reading|scripture reading|quiet time)\b",
            r"\b(?:read (?:the |my )?bible|spe(?:nt|nd) time (?:in |with )?(?:god|prayer|scripture|the word))\b",
            r"\b(?:church|worship(?:ed|ped)?|sermon)\b",
        ],
        "items": {
            "prayer": [r"\bpray(?:ed|er)\b", r"\bprayer time\b"],
            "bible_reading": [r"\bbible\b", r"\bscripture\b", r"\bdevotional?\b", r"\bquiet time\b", r"\bread (?:the |my )?(?:bible|word)\b"],
            "church": [r"\bchurch\b", r"\bworship\b", r"\bsermon\b"],
        },
    },
    "health": {
        "keywords": [
            r"\b(?:work(?:ed)? out|workout|exercis(?:ed|ing)|ran|jogged|walked|hiked|gym|lifted|yoga|stretch(?:ed)?)\b",
            r"\b(?:completed (?:my |a )?workout|finished (?:my |a )?(?:workout|run|exercise))\b",
        ],
        "items": {
            "workout": [r"\bwork(?:ed)? out\b", r"\bworkout\b", r"\bgym\b", r"\bexercis\w*\b", r"\blift(?:ed|ing)?\b"],
            "running": [r"\b(?:ran|jogg(?:ed|ing)|run(?:ning)?)\b"],
            "walking": [r"\bwalk(?:ed|ing)?\b", r"\bhik(?:ed|ing)?\b"],
            "yoga": [r"\byoga\b", r"\bstretch(?:ed|ing)?\b"],
        },
    },
    "journal": {
        "keywords": [
            r"\b(?:journal(?:ed|ing)?|wrote (?:in )?(?:my )?journal|diary entry)\b",
        ],
        "items": {
            "journal_entry": [r"\bjournal\w*\b", r"\bdiary\b"],
        },
    },
    "purpose": {
        "keywords": [
            r"\b(?:goal|mission|purpose|vision)\b",
        ],
        "items": {
            "goal_work": [r"\bgoal\b", r"\bmission\b", r"\bpurpose\b"],
        },
    },
}

# Past-tense / completion indicators — boost confidence
_COMPLETION_INDICATORS = re.compile(
    r"\b(?:did|done|completed|finished|accomplished|went to|had|spent time|"
    r"made time|got (?:my|a)|checked off|"
    r"prayed|exercised|worked out|journaled|jogged|walked|hiked|"
    r"lifted|stretched|worshiped|worshipped)\b",
    re.IGNORECASE,
)

# Future / intent indicators
_INTENT_INDICATORS = re.compile(
    r"\b(?:plan(?:ning)? to|going to|want to|need to|will|gonna|hope to|"
    r"intend(?:ing)? to|about to|looking forward to|tomorrow|later)\b",
    re.IGNORECASE,
)

# Effort without completion
_EFFORT_INDICATORS = re.compile(
    r"\b(?:tried|attempted|started|began|almost|couldn'?t finish|"
    r"ran out of time|didn'?t (?:quite |fully )?finish|partially|half)\b",
    re.IGNORECASE,
)

# Inconsistency / skip indicators
_INCONSISTENCY_INDICATORS = re.compile(
    r"\b(?:skipped|missed|didn'?t|forgot|neglected|blew off|"
    r"failed to|dropped|couldn'?t make it)\b",
    re.IGNORECASE,
)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def detect_signals(user, lookback_hours=24):
    """Detect behavioral signals from a user's recent unstructured text inputs.

    Args:
        user: Django User instance.
        lookback_hours: How far back to scan (default 24h).

    Returns:
        dict with "signals" list. Each signal has: type, domain, item,
        confidence, source, text.
    """
    cutoff = timezone.now() - timedelta(hours=lookback_hours)
    signals = []

    signals.extend(_extract_journal_signals(user, cutoff))
    signals.extend(_extract_workout_signals(user, cutoff))

    # Deduplicate: keep highest-confidence signal per (type, domain, item)
    signals = _deduplicate(signals)

    return _normalize_output(signals)


# ---------------------------------------------------------------------------
# Source extractors
# ---------------------------------------------------------------------------

def _extract_journal_signals(user, cutoff):
    """Extract signals from JournalEntry.body text."""
    signals = []
    try:
        from apps.journal.models import JournalEntry
    except ImportError:
        return signals

    try:
        entries = JournalEntry.objects.filter(
            user=user,
            created_at__gte=cutoff,
        ).values_list("body", flat=True)
    except Exception:
        logger.warning("Signal engine: failed to query journal entries", exc_info=True)
        return signals

    for text in entries:
        if not text or not text.strip():
            continue
        detected = _detect_from_text(text, source="journal")
        signals.extend(detected)

    return signals


def _extract_workout_signals(user, cutoff):
    """Extract signals from WorkoutSession.notes."""
    signals = []
    try:
        from apps.health.models import WorkoutSession
    except ImportError:
        return signals

    try:
        sessions = WorkoutSession.objects.filter(
            user=user,
            created_at__gte=cutoff,
        ).values_list("notes", flat=True)
    except Exception:
        logger.warning("Signal engine: failed to query workout sessions", exc_info=True)
        return signals

    for text in sessions:
        if not text or not text.strip():
            continue
        detected = _detect_from_text(text, source="workout_notes")
        signals.extend(detected)

    return signals


# ---------------------------------------------------------------------------
# Core detection
# ---------------------------------------------------------------------------

def _detect_from_text(text, source):
    """Run all detection rules against a single text block.

    Returns list of signal dicts that meet the confidence floor.
    """
    signals = []
    text_lower = text.lower()

    for domain, config in _COMPLETION_PATTERNS.items():
        # Check if any domain keyword matches
        domain_match = False
        for pattern in config["keywords"]:
            if re.search(pattern, text_lower):
                domain_match = True
                break

        if not domain_match:
            continue

        # Determine best matching item
        best_item = _match_item(text_lower, config["items"])
        if not best_item:
            continue

        # Classify signal type and score
        signal = _classify_and_score(text, text_lower, domain, best_item, source)
        if signal:
            signals.append(signal)

    return signals


def _match_item(text_lower, items_map):
    """Find the best matching item from a domain's item patterns.

    Returns item name or None.
    """
    best_item = None
    best_count = 0

    for item_name, patterns in items_map.items():
        match_count = sum(
            1 for p in patterns if re.search(p, text_lower)
        )
        if match_count > best_count:
            best_count = match_count
            best_item = item_name

    return best_item


def _classify_and_score(text, text_lower, domain, item, source):
    """Classify signal type and compute confidence score.

    Returns signal dict or None if below confidence floor.
    """
    has_completion = bool(_COMPLETION_INDICATORS.search(text_lower))
    has_intent = bool(_INTENT_INDICATORS.search(text_lower))
    has_effort = bool(_EFFORT_INDICATORS.search(text_lower))
    has_inconsistency = bool(_INCONSISTENCY_INDICATORS.search(text_lower))

    # Priority: inconsistency > effort > completion > intent
    # (inconsistency and effort are more specific signals)
    if has_inconsistency and not has_completion:
        signal_type = INCONSISTENCY_SIGNAL
        confidence = _score_signal(text_lower, domain, item, signal_type, source)
    elif has_effort and not has_completion:
        signal_type = EFFORT_SIGNAL
        confidence = _score_signal(text_lower, domain, item, signal_type, source)
    elif has_completion:
        signal_type = POSSIBLE_COMPLETION
        confidence = _score_signal(text_lower, domain, item, signal_type, source)
    elif has_intent:
        signal_type = INTENT_SIGNAL
        confidence = _score_signal(text_lower, domain, item, signal_type, source)
    else:
        # Domain keyword matched but no verb indicator — too ambiguous
        return None

    if confidence < CONFIDENCE_FLOOR:
        return None

    # Truncate text for output (keep first 200 chars)
    snippet = text[:200].strip()
    if len(text) > 200:
        snippet += "..."

    return {
        "type": signal_type,
        "domain": domain,
        "item": item,
        "confidence": round(confidence, 2),
        "source": source,
        "text": snippet,
    }


def _score_signal(text_lower, domain, item, signal_type, source):
    """Compute confidence score for a signal.

    Scoring factors:
    - Base score by signal type
    - Source weighting (journal > workout_notes)
    - Multiple keyword hits boost confidence
    - Text length (very short = less context = lower confidence)
    """
    # Base scores by type — conservative
    base_scores = {
        POSSIBLE_COMPLETION: 0.80,
        EFFORT_SIGNAL: 0.75,
        INTENT_SIGNAL: 0.75,
        INCONSISTENCY_SIGNAL: 0.78,
    }
    score = base_scores.get(signal_type, 0.70)

    # Source weighting
    source_bonus = {
        "journal": 0.05,
        "workout_notes": 0.02,
        "task_comments": 0.0,
        "routine_notes": 0.0,
    }
    score += source_bonus.get(source, 0.0)

    # Multiple item keyword hits — boost slightly
    if domain in _COMPLETION_PATTERNS:
        items_map = _COMPLETION_PATTERNS[domain]["items"]
        if item in items_map:
            hit_count = sum(
                1 for p in items_map[item] if re.search(p, text_lower)
            )
            if hit_count >= 2:
                score += 0.05
            if hit_count >= 3:
                score += 0.03

    # Very short text penalty (< 15 chars = less context)
    if len(text_lower) < 15:
        score -= 0.10

    # Cap at 0.95
    return min(score, 0.95)


# ---------------------------------------------------------------------------
# Output helpers
# ---------------------------------------------------------------------------

def _deduplicate(signals):
    """Keep highest-confidence signal per (type, domain, item) tuple."""
    best = {}
    for sig in signals:
        key = (sig["type"], sig["domain"], sig["item"])
        if key not in best or sig["confidence"] > best[key]["confidence"]:
            best[key] = sig
    return list(best.values())


def _normalize_output(signals):
    """Wrap signals in the standard output envelope.

    Sorts by confidence descending.
    """
    signals.sort(key=lambda s: s["confidence"], reverse=True)
    return {"signals": signals}
