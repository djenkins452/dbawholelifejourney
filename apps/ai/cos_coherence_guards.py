"""CoS Coherence Guards — Phase 1 (OBSERVE-ONLY).

Three trust detectors that quantify, on real traffic, the failure classes that
erode trust when Beth "sounds smart while being wrong":

  G1 — Count coherence.   The stated remaining count must equal the number of
        remaining items actually listed. Catches "19 of 25 complete" rendered
        beside only 5 pending items (the invented-sixth-task bug).

  G2 — Operational entity hallucination.   Beth must only name operational
        entities that exist in canonical state. The first concrete target is
        invented medication GROUP labels ("Nightly Medications") — meds have no
        grouping entity in the data model, so any such label is fabricated.

  G3 — Metric coherence (calories).   One metric → one number. Detects when a
        calorie "N% under/over target" claim in Beth's reply disagrees with the
        single canonical reader (today's live intake vs target).

PHASE 1 CONTRACT: these functions DETECT and LOG only. They never alter Beth's
response, never append violations, never raise. Output is byte-identical to
before. Phase 2 flips the per-guard enforcement flags (default False here) to
make them fail closed.

Conventions mirror apps/ai/cognitive_mode/health_truth.py:
  - flag-gated (defaults below), read live via django settings
  - never raise (every public entry wrapped; failures are non-fatal)
  - log at ERROR when a detector fires (visible in production)

Flags (config/settings.py):
  WLJ_BETH_COHERENCE_DIAG_ENABLED   — master switch for all three detectors
                                       (observe-only logging). Default True.
  WLJ_BETH_COUNT_GUARD_ENABLED      — Phase 2 enforcement of G1. Default False.
  WLJ_BETH_ENTITY_GUARD_ENABLED     — Phase 2 enforcement of G2. Default False.
  WLJ_BETH_NUTRITION_GUARD_ENABLED  — Phase 2 enforcement of G3. Default False.
"""

from __future__ import annotations

import logging
import re

logger = logging.getLogger("apps.ai.cos_coherence")


def _flag(name: str, default: bool) -> bool:
    try:
        from django.conf import settings
        return bool(getattr(settings, name, default))
    except Exception:
        return default


def coherence_diag_enabled() -> bool:
    """Master observe-only switch. When off, all detectors are no-ops."""
    return _flag("WLJ_BETH_COHERENCE_DIAG_ENABLED", True)


# Per-guard enforcement flags — Phase 2 flips these on. Read by future
# enforcement wiring; in Phase 1 they only label log lines as observe-only.
def count_guard_enforced() -> bool:
    return _flag("WLJ_BETH_COUNT_GUARD_ENABLED", False)


def entity_guard_enforced() -> bool:
    return _flag("WLJ_BETH_ENTITY_GUARD_ENABLED", False)


def nutrition_guard_enforced() -> bool:
    return _flag("WLJ_BETH_NUTRITION_GUARD_ENABLED", False)


# ── G1 — Count Coherence ────────────────────────────────────────────────

def check_count_coherence(user, *, routine_total, routine_done, pending_names,
                          meds_expected=0, meds_taken=0, meds_skipped=0):
    """Detect count/list mismatches in the canonical execution state.

    Invariants (both must hold or trust breaks):
      routines:  (total - done) == len(pending_names)
      meds:      (expected - taken - skipped) >= 0   AND  taken <= expected

    Returns a list of mismatch dicts (empty when coherent). OBSERVE-ONLY:
    logs at ERROR and returns the findings; the caller does NOT alter output
    in Phase 1. Never raises.
    """
    if not coherence_diag_enabled():
        return []
    mismatches = []
    try:
        try:
            r_total = int(routine_total or 0)
            r_done = int(routine_done or 0)
        except (TypeError, ValueError):
            r_total = r_done = 0
        listed = len(pending_names or [])
        expected_remaining = r_total - r_done

        if expected_remaining != listed:
            mismatches.append({
                "domain": "routines",
                "type": "count_list_mismatch",
                "stated_remaining": expected_remaining,
                "listed_items": listed,
                "total": r_total,
                "done": r_done,
            })

        try:
            m_exp = int(meds_expected or 0)
            m_taken = int(meds_taken or 0)
            m_skip = int(meds_skipped or 0)
        except (TypeError, ValueError):
            m_exp = m_taken = m_skip = 0
        m_remaining = m_exp - m_taken - m_skip
        if m_exp > 0 and (m_remaining < 0 or m_taken > m_exp):
            mismatches.append({
                "domain": "medications",
                "type": "count_impossible",
                "expected": m_exp,
                "taken": m_taken,
                "skipped": m_skip,
                "computed_remaining": m_remaining,
            })

        if mismatches:
            logger.error(
                "[CoS COUNT GUARD] user=%s OBSERVE-ONLY enforce=%s "
                "mismatches=%s",
                getattr(user, "id", "?"), count_guard_enforced(), mismatches,
            )
    except Exception:
        logger.debug("count coherence check skipped (non-fatal)", exc_info=True)
    return mismatches


# Fail-closed wording when checklist counts don't reconcile — never narrate a
# broken count, never invent an item; surface the actual canonical items only.
_COUNT_MISMATCH_FALLBACK = (
    "I'm seeing a mismatch in your checklist counts, so I don't want to guess."
)

# Routine/checklist completion-count claims in a reply: "19 of 25", "6 items
# remaining", "5 left". Medication-dose claims are deliberately excluded so a
# routine mismatch never clobbers a correct "4 of 6 doses" sentence.
_COUNT_OF_RE = re.compile(r"\b\d{1,3}\s+of\s+\d{1,3}\b", re.I)
# Up to 3 filler words between the number and the "remaining" cue so real
# phrasing like "6 routine items remaining" / "5 things still to do" matches.
# Over-matching ("20 minutes left") is gated downstream by _LIST_CONTEXT_RE
# (must mention routine/item/task) and the medication exclusion.
_COUNT_REMAINING_RE = re.compile(
    r"\b\d{1,3}\s+(?:[\w'-]+\s+){0,3}?"
    r"(?:remaining|left|to\s+go|outstanding|still\s+(?:pending|left|to\s+do))\b",
    re.I,
)
_LIST_CONTEXT_RE = re.compile(r"\b(routine|checklist|item|task|to-?do)s?\b", re.I)
_MED_CONTEXT_RE = re.compile(
    r"\b(dose|medication|medicine|supplement|pill|vitamin)s?\b", re.I)


def enforce_count_coherence(response_text, user, *, routine_total,
                            routine_done, pending_names):
    """Fail closed on incoherent routine/checklist counts (G1 enforcement).

    Fires ONLY when canonical state is itself incoherent
    (`routine_total − routine_done != len(pending_names)`). In that case any
    sentence in the reply that states a routine completion count is replaced
    (once) with safe wording that lists the ACTUAL pending items — so Beth
    never narrates the broken count and never invents a missing item. When the
    counts reconcile, the reply is returned untouched (Beth answers naturally).

    When the guard flag is off, falls back to observe-only logging. Returns
    (text, num_flagged). Never raises.
    """
    if not response_text:
        return response_text, 0
    if not count_guard_enforced():
        # observe-only fallback at the response stage
        check_count_coherence(
            user, routine_total=routine_total, routine_done=routine_done,
            pending_names=pending_names,
        )
        return response_text, 0
    try:
        try:
            total = int(routine_total or 0)
            done = int(routine_done or 0)
        except (TypeError, ValueError):
            return response_text, 0
        listed = len(pending_names or [])
        if total <= 0 or (total - done) == listed:
            return response_text, 0  # coherent — leave the reply natural

        sentences = re.split(r"(?<=[.!?])\s+", response_text)
        out = []
        flagged = 0
        emitted = False
        for s in sentences:
            states_count = bool(
                _COUNT_OF_RE.search(s) or _COUNT_REMAINING_RE.search(s))
            is_list_ctx = bool(_LIST_CONTEXT_RE.search(s))
            is_med_ctx = bool(_MED_CONTEXT_RE.search(s))
            if states_count and is_list_ctx and not is_med_ctx:
                flagged += 1
                if not emitted:
                    items = (
                        ", ".join(pending_names[:8]) if pending_names
                        else "none that I can confirm right now"
                    )
                    out.append(
                        f"{_COUNT_MISMATCH_FALLBACK} The remaining items I can "
                        f"see are: {items}."
                    )
                    emitted = True
                continue
            out.append(s)
        if not flagged:
            return response_text, 0
        logger.error(
            "[CoS COUNT GUARD] user=%s FAIL-CLOSED enforce=True corrected=%d "
            "claim(s) (canonical total=%d done=%d listed=%d)",
            getattr(user, "id", "?"), flagged, total, done, listed,
        )
        return " ".join(p for p in out if p).strip(), flagged
    except Exception:
        logger.debug("count coherence enforcement skipped (non-fatal)",
                     exc_info=True)
        return response_text, 0


# ── G2 — Operational Entity Hallucination (medication group labels) ──────

# Invented grouping labels: a time-of-day word glued to a medication noun.
# Meds have NO grouping entity in the data model (Intake groups only by
# per-schedule time_of_day), so ANY such phrase is a synthesized abstraction.
_MED_GROUP_RE = re.compile(
    r"\b(morning|nightly|night|evening|bedtime|afternoon|midday|noon|daily|"
    r"a\.?m\.?|p\.?m\.?|weekly|lunch(?:time)?|dinner(?:time)?|breakfast)\s+"
    r"(medications?|medicines?|meds|pills?|doses?|supplements?|vitamins?)\b",
    re.I,
)


def build_canonical_entity_set(user) -> set:
    """Lowercased set of REAL operational entity names for this user.

    Active medication/supplement names, today's routine item names, today's
    task titles, and routine names. Used so the entity detector can report
    what the real entities were (and, in Phase 2, constrain narration).
    Never raises; returns whatever it could collect.
    """
    names: set[str] = set()
    try:
        from apps.health.models import Intake
        for n in (
            Intake.objects.filter(user=user, status=Intake.STATUS_ACTIVE)
            .values_list("name", flat=True)
        ):
            if n:
                names.add(n.strip().lower())
    except Exception:
        logger.debug("entity set: intake read failed", exc_info=True)
    try:
        from apps.core.execution.execution_truth_engine import get_execution_truth
        truth = get_execution_truth(user)
        for r_name in (truth.get("routines", {}).get("items", {}) or {}):
            if r_name:
                names.add(str(r_name).strip().lower())
        for _window, items in (
            truth.get("routines", {}).get("_raw_items", {}) or {}
        ).items():
            for item in items:
                nm = (item.get("item_name") or "").strip().lower()
                if nm:
                    names.add(nm)
    except Exception:
        logger.debug("entity set: routine read failed", exc_info=True)
    return names


def detect_operational_entity_hallucination(user, response_text,
                                            entity_set=None):
    """Detect invented medication GROUP labels in Beth's reply.

    A phrase like "Nightly Medications" is flagged unless that exact phrase is
    a real entity name (it never is, given the data model). OBSERVE-ONLY: logs
    and returns findings; the caller does not alter output in Phase 1.

    Lazy: only builds the canonical entity set if a candidate phrase is found,
    so the common (clean) case costs one regex scan. Never raises.
    """
    if not response_text or not coherence_diag_enabled():
        return []
    findings = []
    try:
        candidates = {m.group(0).strip() for m in _MED_GROUP_RE.finditer(response_text)}
        if not candidates:
            return []
        if entity_set is None:
            entity_set = build_canonical_entity_set(user)
        for phrase in candidates:
            if phrase.strip().lower() in entity_set:
                continue  # a real entity happens to carry this label — allow
            findings.append({
                "domain": "medications",
                "type": "invented_group_label",
                "phrase": phrase,
            })
        if findings:
            logger.error(
                "[CoS ENTITY GUARD] user=%s OBSERVE-ONLY enforce=%s "
                "invented_med_group_labels=%s (canonical med/routine "
                "entities=%d)",
                getattr(user, "id", "?"), entity_guard_enforced(),
                [f["phrase"] for f in findings], len(entity_set or []),
            )
    except Exception:
        logger.debug("entity hallucination check skipped (non-fatal)",
                     exc_info=True)
    return findings


def enforce_entity_hallucination(response_text, user, entity_set=None):
    """Strip invented medication GROUP labels from the reply (G2 enforcement).

    A phrase like "Nightly Medications" is a fabricated abstraction (meds have
    no grouping entity). When enforcement is on, the time-of-day prefix is
    removed so the fabricated grouping becomes a plain, source-true noun
    ("your Nightly Medications" → "your medications"); the invented entity
    never reaches the user. A phrase that IS a real entity name (e.g. a routine
    literally called "Morning Vitamins") is left intact.

    When the guard flag is off, falls back to observe-only logging. Returns
    (text, num_flagged). Never raises.
    """
    if not response_text:
        return response_text, 0
    if not entity_guard_enforced():
        detect_operational_entity_hallucination(user, response_text, entity_set)
        return response_text, 0
    try:
        if not _MED_GROUP_RE.search(response_text):
            return response_text, 0
        if entity_set is None:
            entity_set = build_canonical_entity_set(user)
        flagged_phrases = []

        def _repl(m):
            phrase = m.group(0)
            if phrase.strip().lower() in entity_set:
                return phrase  # a real entity carries this label — keep it
            flagged_phrases.append(phrase)
            return m.group(2).lower()  # drop the fabricated time-of-day prefix

        corrected = _MED_GROUP_RE.sub(_repl, response_text)
        if not flagged_phrases:
            return response_text, 0
        logger.error(
            "[CoS ENTITY GUARD] user=%s FAIL-CLOSED enforce=True stripped "
            "invented med-group label(s)=%s (canonical entities=%d)",
            getattr(user, "id", "?"), flagged_phrases, len(entity_set or []),
        )
        return corrected, len(flagged_phrases)
    except Exception:
        logger.debug("entity hallucination enforcement skipped (non-fatal)",
                     exc_info=True)
        return response_text, 0


# ── G3 — Metric Coherence (calories) ────────────────────────────────────

# Tolerance (percentage points) before two calorie figures are "divergent".
# Tight by design: the same metric computed two ways should agree within
# rounding. The 22%-vs-26% incident was a 4pp gap — anything beyond ~2pp is a
# genuine two-truths divergence, not rounding noise.
_CALORIE_PCT_TOL = 2.0

# "N% under/over/below/above (the) target/goal" — the user-facing calorie chip
# phrasing. We only treat it as a calorie claim when a calorie word is nearby.
_CALORIE_CLAIM_RE = re.compile(
    r"(\d{1,3}(?:\.\d+)?)\s*%\s*(under|over|below|above)\s+(?:the\s+|your\s+)?"
    r"(?:calorie\s+)?(?:target|goal)",
    re.I,
)
_CALORIE_WORD_RE = re.compile(r"\bcalorie", re.I)


def get_canonical_nutrition(user) -> dict:
    """THE single authoritative 'today calories vs target' reader.

    Sources today's intake and active goal from the live SAE nutrition state
    (FoodEntry-backed), so Beth and the dashboard can converge on one number.

    Returns:
        {
          'available': bool,
          'daily_calories': float | None,
          'calorie_target': float | None,
          'compliance_pct': float | None,   # daily / target * 100
          'pct_under_target': float | None, # 0 when at/over target
          'pct_over_target': float | None,  # 0 when at/under target
        }
    Never raises.
    """
    out = {
        "available": False,
        "daily_calories": None,
        "calorie_target": None,
        "compliance_pct": None,
        "pct_under_target": None,
        "pct_over_target": None,
    }
    try:
        from apps.core.ai_state.state_builder import build_nutrition_state
        ns = build_nutrition_state(user) or {}
        if not ns.get("enabled", False):
            return out
        compliance = ns.get("calorie_compliance_pct")
        out["daily_calories"] = ns.get("daily_calories")
        out["calorie_target"] = ns.get("calorie_target")
        if compliance is not None:
            compliance = float(compliance)
            out["compliance_pct"] = compliance
            out["pct_under_target"] = round(max(0.0, 100.0 - compliance), 1)
            out["pct_over_target"] = round(max(0.0, compliance - 100.0), 1)
            out["available"] = True
    except Exception:
        logger.debug("get_canonical_nutrition failed (non-fatal)",
                     exc_info=True)
    return out


def detect_calorie_divergence(user, response_text, canonical=None):
    """Detect calorie 'N% under/over target' claims that disagree with the
    canonical reader.

    OBSERVE-ONLY: logs and returns findings; the caller does not alter output
    in Phase 1. Lazy — only reads canonical nutrition if the response makes a
    calorie-percentage claim. Never raises.
    """
    if not response_text or not coherence_diag_enabled():
        return []
    findings = []
    try:
        if not _CALORIE_WORD_RE.search(response_text):
            return []
        claims = list(_CALORIE_CLAIM_RE.finditer(response_text))
        if not claims:
            return []
        if canonical is None:
            canonical = get_canonical_nutrition(user)
        if not canonical.get("available"):
            return []
        canon_under = canonical.get("pct_under_target") or 0.0
        canon_over = canonical.get("pct_over_target") or 0.0
        for m in claims:
            try:
                stated = float(m.group(1))
            except (TypeError, ValueError):
                continue
            direction = m.group(2).lower()
            if direction in ("under", "below"):
                canon = canon_under
            else:
                canon = canon_over
            if abs(stated - canon) > _CALORIE_PCT_TOL:
                findings.append({
                    "domain": "nutrition",
                    "type": "calorie_pct_divergence",
                    "stated_pct": stated,
                    "direction": direction,
                    "canonical_pct": round(canon, 1),
                    "canonical_compliance_pct": canonical.get("compliance_pct"),
                })
        if findings:
            logger.error(
                "[CoS CALORIE GUARD] user=%s OBSERVE-ONLY enforce=%s "
                "divergences=%s",
                getattr(user, "id", "?"), nutrition_guard_enforced(), findings,
            )
    except Exception:
        logger.debug("calorie divergence check skipped (non-fatal)",
                     exc_info=True)
    return findings
