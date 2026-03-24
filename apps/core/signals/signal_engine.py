"""
Phase 2 — Signal Engine: Behavioral Awareness (Read-Only)

Detects possible user behavior or intent from unstructured text inputs.
Answers: "What might the user have done or intended?"
NOT: "What DID the user complete?"

ARCHITECTURAL RULES:
- Read-only: no DB writes, no side effects
- No coupling to Execution Truth Engine
- Conservative detection: high-confidence matches only (>= 0.75)
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

# Phase 2.1: Hardened threshold — 0.75 minimum, target range 0.80–0.95
MIN_CONFIDENCE = 0.75

# ---------------------------------------------------------------------------
# Centralized domain keyword mapping (Phase 2.1 Patch #4)
#
# Each domain has:
#   "phrases" — high-confidence multi-word phrases (checked first)
#   "keywords" — single-word or short patterns (checked second)
#   "items"    — item-level patterns for sub-classification
#
# All matching is case-insensitive via regex \b word boundaries.
# ---------------------------------------------------------------------------
DOMAIN_KEYWORDS = {
    "faith": {
        "phrases": [
            r"\bprayer time\b",
            r"\bquiet time\b",
            r"\bbible reading\b",
            r"\bscripture reading\b",
            r"\bspe(?:nt|nd) time (?:in |with )?(?:god|prayer|scripture|the word)\b",
            r"\bread (?:the |my )?bible\b",
            r"\btime with god\b",
        ],
        "keywords": [
            r"\bpray(?:ed|er|ing)?\b",
            r"\bdevotional?\b",
            r"\bchurch\b",
            r"\bworship(?:ed|ped|ping)?\b",
            r"\bsermon\b",
            r"\bbible\b",
            r"\bscripture\b",
        ],
        "items": {
            "prayer": [r"\bpray(?:ed|er|ing)?\b", r"\bprayer time\b", r"\btime with god\b", r"\bgod\b"],
            "bible_reading": [
                r"\bbible\b", r"\bscripture\b", r"\bdevotional?\b",
                r"\bquiet time\b", r"\bread (?:the |my )?(?:bible|word)\b",
            ],
            "church": [r"\bchurch\b", r"\bworship\b", r"\bsermon\b"],
        },
    },
    "health": {
        "phrases": [
            r"\bwork(?:ed)? out\b",
            r"\bcompleted (?:my |a )?workout\b",
            r"\bfinished (?:my |a )?(?:workout|run|exercise)\b",
            r"\blifted weights\b",
            r"\bwent (?:to (?:the )?)?gym\b",
        ],
        "keywords": [
            r"\bworkout\b",
            r"\bexercis(?:ed?|ing)\b",
            r"\bgym\b",
            r"\blift(?:ed|ing)?\b",
            r"\byoga\b",
            r"\bstretch(?:ed|ing)?\b",
            r"\bran\b",
            r"\bjogg(?:ed|ing)\b",
            r"\bwalk(?:ed|ing)?\b",
            r"\bhik(?:ed|ing)?\b",
            r"\btraining\b",
        ],
        "items": {
            "workout": [
                r"\bwork(?:ed)? out\b", r"\bworkout\b", r"\bgym\b",
                r"\bexercis\w*\b", r"\blift(?:ed|ing)?\b", r"\btraining\b",
            ],
            "running": [r"\b(?:ran|jogg(?:ed|ing)|run(?:ning)?)\b"],
            "walking": [r"\bwalk(?:ed|ing)?\b", r"\bhik(?:ed|ing)?\b"],
            "yoga": [r"\byoga\b", r"\bstretch(?:ed|ing)?\b"],
        },
    },
    "journal": {
        "phrases": [
            r"\bjournal entry\b",
            r"\bwrote (?:in )?(?:my )?journal\b",
            r"\bdiary entry\b",
        ],
        "keywords": [
            r"\bjournal(?:ed|ing)?\b",
            r"\breflection\b",
        ],
        "items": {
            "journal_entry": [r"\bjournal\w*\b", r"\bdiary\b", r"\breflection\b"],
        },
    },
    "purpose": {
        "phrases": [
            r"\bworked on (?:my )?goal\b",
        ],
        "keywords": [
            r"\bgoal\b",
            r"\bmission\b",
            r"\bpurpose\b",
            r"\bvision\b",
        ],
        "items": {
            "goal_work": [r"\bgoal\b", r"\bmission\b", r"\bpurpose\b"],
        },
    },
    "sports": {
        "phrases": [
            r"\bwatch(?:ed|ing)? the game\b",
            r"\bteam (?:won|lost|played)\b",
            r"\bgame (?:tonight|today|tomorrow)\b",
        ],
        "keywords": [
            r"\bgame\b",
            r"\bplayoff\b",
            r"\btournament\b",
            r"\bfootball\b",
            r"\bbasketball\b",
            r"\bbaseball\b",
        ],
        "items": {
            "watching": [r"\bwatch(?:ed|ing)?\b", r"\bgame\b", r"\bplayoff\b"],
            "result": [r"\bwon\b", r"\blost\b", r"\bbeat\b", r"\bscor(?:e|ed|ing)\b"],
        },
    },
}

# ---------------------------------------------------------------------------
# Verb indicator patterns — classify signal type
# ---------------------------------------------------------------------------

# Past-tense / completion indicators
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
        confidence, source, text, timestamp.
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

    Returns list of signal dicts that meet MIN_CONFIDENCE.
    """
    signals = []
    if not text or not text.strip():
        return signals

    text_lower = text.lower()

    for domain, config in DOMAIN_KEYWORDS.items():
        # Phase 2.1: Phrase-first matching — check phrases before keywords
        domain_match = False
        phrase_hit = False

        for pattern in config.get("phrases", []):
            if re.search(pattern, text_lower):
                domain_match = True
                phrase_hit = True
                break

        if not domain_match:
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
        signal = _classify_and_score(
            text, text_lower, domain, best_item, source, phrase_hit
        )
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


def _classify_and_score(text, text_lower, domain, item, source, phrase_hit):
    """Classify signal type and compute confidence score.

    Returns signal dict or None if below MIN_CONFIDENCE.
    """
    has_completion = bool(_COMPLETION_INDICATORS.search(text_lower))
    has_intent = bool(_INTENT_INDICATORS.search(text_lower))
    has_effort = bool(_EFFORT_INDICATORS.search(text_lower))
    has_inconsistency = bool(_INCONSISTENCY_INDICATORS.search(text_lower))

    # Priority: inconsistency > effort > completion > intent
    if has_inconsistency and not has_completion:
        signal_type = INCONSISTENCY_SIGNAL
    elif has_effort and not has_completion:
        signal_type = EFFORT_SIGNAL
    elif has_completion:
        signal_type = POSSIBLE_COMPLETION
    elif has_intent:
        signal_type = INTENT_SIGNAL
    else:
        # Domain keyword matched but no verb indicator — too ambiguous, reject
        return None

    confidence = _score_signal(
        text_lower, domain, item, signal_type, source, phrase_hit
    )

    if confidence < MIN_CONFIDENCE:
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
        "timestamp": timezone.now(),
    }


def _score_signal(text_lower, domain, item, signal_type, source, phrase_hit=False):
    """Compute confidence score for a signal.

    Scoring factors:
    - Base score by signal type (tuned so strong matches land >= 0.80)
    - Source weighting (journal > workout_notes)
    - Phrase hit bonus (multi-word matches are higher confidence)
    - Multiple keyword hits boost confidence
    - Text length (very short = less context = lower confidence)
    """
    # Base scores — tuned for 0.80–0.95 target range
    base_scores = {
        POSSIBLE_COMPLETION: 0.82,
        EFFORT_SIGNAL: 0.78,
        INTENT_SIGNAL: 0.78,
        INCONSISTENCY_SIGNAL: 0.80,
    }
    score = base_scores.get(signal_type, 0.75)

    # Source weighting
    source_bonus = {
        "journal": 0.04,
        "workout_notes": 0.02,
        "task_comments": 0.0,
        "routine_notes": 0.0,
    }
    score += source_bonus.get(source, 0.0)

    # Phrase-hit bonus: multi-word matches are inherently higher confidence
    if phrase_hit:
        score += 0.03

    # Multiple item keyword hits — boost slightly
    if domain in DOMAIN_KEYWORDS:
        items_map = DOMAIN_KEYWORDS[domain]["items"]
        if item in items_map:
            hit_count = sum(
                1 for p in items_map[item] if re.search(p, text_lower)
            )
            if hit_count >= 2:
                score += 0.04
            if hit_count >= 3:
                score += 0.02

    # Very short text penalty (< 15 chars = less context)
    if len(text_lower) < 15:
        score -= 0.12

    # Cap at 0.95
    return min(score, 0.95)


# ---------------------------------------------------------------------------
# Output helpers
# ---------------------------------------------------------------------------

def _deduplicate(signals):
    """Keep highest-confidence signal per (type, domain, item) tuple.

    Phase 2.1: This is the single deduplication point. Called in
    detect_signals() after collecting from all sources.
    """
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
