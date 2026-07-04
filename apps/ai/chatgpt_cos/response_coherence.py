# ==============================================================================
# File: apps/ai/chatgpt_cos/response_coherence.py
# Capability: RESPONSE COHERENCE VALIDATION.
#
# A Chief of Staff composes a finished response from fragments — a greeting, an
# overnight fact, a check-in prompt, an agenda. Each fragment can be individually
# valid while the COMPLETED response is internally impossible. Production case: at
# 8:16 PM Beth said "Good evening…" (a time-aware greeting) immediately followed by
# "…how are you feeling this morning?" (a hardcoded fragment). Both correct alone;
# together, incoherent — two different "current" parts of day in one message.
#
# This is the deterministic pass that guarantees every FINISHED response reads as if
# written by one coherent person. It runs AFTER composition and BEFORE presentation,
# over EVERY composed response (greeting, check-in, executive summary, mission
# update), at the single choke point they all pass through (lanes.route_message). It
# does not patch any one composer — it validates and re-grounds the completed text.
#
# Scope is deliberately SURGICAL: it re-grounds only phrase families that frame the
# PRESENT moment — a salutation ("Good evening"), a present-wellbeing frame ("feeling
# this morning", "enjoy your evening"), or an agenda opener ("This evening you've
# still got…"). Legitimate historical / scheduled references ("you slept 6 hours last
# night", "your 8am workout this morning is done", "I'll call you this evening") are
# NOT present-moment frames and are never rewritten.
# ==============================================================================
import logging
import re

logger = logging.getLogger(__name__)

MORNING, AFTERNOON, EVENING = "morning", "afternoon", "evening"
_PARTS = (MORNING, AFTERNOON, EVENING)


def part_of_day(user, now=None):
    """The single source of truth for the user's CURRENT part of day. Buckets match
    the greeting composer (4–12 morning, 12–17 afternoon, else evening) so a greeting
    and a check-in can never disagree by construction."""
    if now is None:
        from apps.core.utils import get_user_now
        now = get_user_now(user)
    h = now.hour
    if 4 <= h < 12:
        return MORNING
    if 12 <= h < 17:
        return AFTERNOON
    return EVENING


def greeting_word(user, now=None):
    """"Good morning|afternoon|evening" for the current clock — the greeting authority."""
    return "Good " + part_of_day(user, now)


def this_part_phrase(user, now=None):
    """"this morning|afternoon|evening" for the current clock — the check-in authority."""
    return "this " + part_of_day(user, now)


# ── Present-moment phrase families (the ONLY things re-grounded) ─────────────
_POD = r"(morning|afternoon|evening)"
# 1) Salutations always frame the present.
_GREETING_RE = re.compile(r"\b([Gg]ood)\s+" + _POD + r"\b")
# 2) Present-wellbeing frames without "this": "enjoy your evening", "hope your
#    morning", "how's your afternoon", "rest of your evening", "have a good evening".
_YOUR_POD_RE = re.compile(
    r"\b(hope your|enjoy your|how'?s your|hows your|rest of your|"
    r"have a (?:good|great))\s+" + _POD + r"\b", re.IGNORECASE)
# 3) "this <pod>" — present ONLY in a present-frame context (below); historical /
#    scheduled "this <pod>" is deliberately excluded.
_THIS_POD_RE = re.compile(r"\bthis\s+" + _POD + r"\b", re.IGNORECASE)
# A present/near subject immediately following "this <pod>" (agenda opener):
#   "This evening you've still got…", "this morning we'll…", "this afternoon there's…"
# A present/near subject as a WHOLE word (a boundary or contraction apostrophe after
# it), so "this morning went long" is NOT misread ("we" must not match "went").
_PRESENT_AFTER = re.compile(r"\s+(?:you|we|i|there|it)(?=['’\s.,!?]|$)", re.IGNORECASE)
_WELLBEING_BEFORE = ("feeling", "feel", "doing")
_SENTENCE_END = ".!?;:—-"


def _this_is_present_frame(text, m):
    """True when a "this <pod>" occurrence frames the PRESENT moment — sentence-
    initial (an agenda opener), directly following a wellbeing cue ("feeling this
    morning"), or immediately followed by a present subject ("this evening you've").
    False for historical/scheduled references ("meeting this morning went long")."""
    pre = text[:m.start()].rstrip()
    if not pre or pre[-1] in _SENTENCE_END:
        return True
    last = re.split(r"\s+", pre)[-1].strip(",.;:!?").lower()
    if last in _WELLBEING_BEFORE:
        return True
    return bool(_PRESENT_AFTER.match(text[m.end():]))


def coherence_issues(text, part):
    """List the present-moment part-of-day references in `text` that CONFLICT with
    `part` (the actual clock). Empty list ⇒ the finished response is coherent."""
    text = text or ""
    issues = []
    for m in _GREETING_RE.finditer(text):
        if m.group(2).lower() != part:
            issues.append({"kind": "greeting", "found": m.group(2).lower(),
                           "expected": part})
    for m in _YOUR_POD_RE.finditer(text):
        if m.group(2).lower() != part:
            issues.append({"kind": "wellbeing", "found": m.group(2).lower(),
                           "expected": part})
    for m in _THIS_POD_RE.finditer(text):
        if m.group(1).lower() != part and _this_is_present_frame(text, m):
            issues.append({"kind": "present_frame", "found": m.group(1).lower(),
                           "expected": part})
    return issues


def repair(text, user=None, part=None, now=None):
    """Re-ground every present-moment part-of-day reference in `text` to `part` (or
    the user's current clock). Returns ``(repaired_text, issues)``. Surgical: touches
    only salutations, present-wellbeing frames, and agenda openers — never
    historical/scheduled references."""
    if not text:
        return text, []
    if part not in _PARTS:
        try:
            part = part_of_day(user, now)
        except Exception:
            logger.warning("response_coherence: part_of_day failed", exc_info=True)
            return text, []
    issues = coherence_issues(text, part)
    if not issues:
        return text, []

    def _fix_greeting(m):
        return f"{m.group(1)} {part}" if m.group(2).lower() != part else m.group(0)

    def _fix_your(m):
        if m.group(2).lower() == part:
            return m.group(0)
        return m.group(0)[:m.start(2) - m.start(0)] + part

    def _fix_this(m):
        if m.group(1).lower() == part or not _this_is_present_frame(m.string, m):
            return m.group(0)
        return m.group(0)[:m.start(1) - m.start(0)] + part

    text = _GREETING_RE.sub(_fix_greeting, text)
    text = _YOUR_POD_RE.sub(_fix_your, text)
    text = _THIS_POD_RE.sub(_fix_this, text)
    return text, issues


def harmonize(text, user, now=None):
    """The choke-point pass: return `text` re-grounded to the user's current part of
    day, so no composed response is ever presented with an internally-contradictory
    sense of time. Never raises — coherence must never break a response."""
    try:
        return repair(text, user=user, now=now)[0]
    except Exception:
        logger.warning("response_coherence: harmonize failed", exc_info=True)
        return text


def is_coherent(text, part):
    """True when `text` has no present-moment part-of-day reference conflicting with
    `part`. Used by the coherence regression + Executive Certification."""
    return not coherence_issues(text, part)
