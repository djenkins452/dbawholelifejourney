"""
Narration Contract Validator — soft-warn enforcement.

Inspects an LLM response for state-determining claims (done / overdue /
at risk / next action / fix first) and verifies each claim traces to a
canonical_item_truth section. Claims traceable only to rollup_summary,
advisory, or contextual sections are flagged as warnings.

This is SOFT enforcement in v1: the validator logs and returns a
structured violations dict. It does NOT block responses. The caller
(apps/ai/personal_assistant.py post-LLM) is responsible for logging
the result and (optionally) attaching it to a chat snapshot.

PURE module: no DB, no LLM. Stable for unit tests.
"""

import logging
import re
from dataclasses import dataclass
from typing import Iterable, Optional

logger = logging.getLogger(__name__)


# ── Claim families ─────────────────────────────────────────────────
# Tuned to the failure cases observed in production:
#   - "X is already done" / "X is complete"
#   - "X is overdue" / "X is behind"
#   - "X is at risk" / "X is slipping"
#   - "next: X" / "do X now" / "start with X"
#   - "fix X first"

_COMPLETION_PATTERNS = [
    r"\b(is|are|was|were|already|now)\s+(done|completed|complete|finished|taken|logged)\b",
    r"\byou\s+(have|already)\s+(done|completed|finished|taken|logged)\b",
    r"\b(checked|knocked)\s+off\b",
]

_OVERDUE_PATTERNS = [
    r"\bis\s+overdue\b",
    r"\bare\s+overdue\b",
    r"\bbehind\s+on\b",
    r"\bbehind\s+schedule\b",
    r"\bmissed\s+your\b",
]

_AT_RISK_PATTERNS = [
    r"\bat\s+risk\b",
    r"\bat-risk\b",
    r"\bslipping\b",
    r"\bgoing\s+to\s+slip\b",
]

_NEXT_ACTION_PATTERNS = [
    r"\bnext\s+action\b",
    r"\bdo\s+this\s+now\b",
    r"\bstart\s+with\b",
    r"\bnext:\s+",
]

_FIX_PRIORITY_PATTERNS = [
    r"\bfix\s+(this\s+)?first\b",
    r"\bfix\s+this\s+next\b",
    r"\bclean\s+this\s+up\s+first\b",
]


@dataclass
class ClaimMatch:
    family: str          # 'completed' | 'overdue' | 'at_risk' | 'next_action' | 'fix_priority'
    matched_text: str    # the exact span the regex matched
    surrounding: str     # ~80 chars of surrounding response text (entity context)


@dataclass
class Violation:
    family: str
    matched_text: str
    surrounding: str
    canonical_match: bool
    rollup_match: bool
    severity: str        # 'pass' | 'warning' | 'error'
    note: str


# ── Internal helpers ────────────────────────────────────────────────

def _scan(text: str, patterns: Iterable[str], family: str) -> list:
    """Return a list of ClaimMatch for `text` against `patterns`."""
    if not text:
        return []
    matches = []
    for pat in patterns:
        for m in re.finditer(pat, text, flags=re.IGNORECASE):
            start = max(0, m.start() - 40)
            end = min(len(text), m.end() + 40)
            matches.append(ClaimMatch(
                family=family,
                matched_text=text[m.start():m.end()],
                surrounding=text[start:end].replace("\n", " "),
            ))
    return matches


def _entity_in(text: str, blob: Optional[str]) -> bool:
    """Coarse-grained: do any 2+ word phrases from `text` appear in
    `blob`? Used as a soft trace check — not exact entity match.

    Strategy: pull out all tokens of length >= 4 from `text`, lowercase
    both sides, and require at least one such token to appear in blob.
    Avoids false positives from common short words.
    """
    if not blob:
        return False
    blob_lc = blob.lower()
    tokens = re.findall(r"[A-Za-z][A-Za-z'-]{3,}", text or "")
    if not tokens:
        return False
    for tok in tokens:
        if tok.lower() in blob_lc:
            return True
    return False


def _classify_claim(claim: ClaimMatch, canonical_blob: str,
                    rollup_blob: str) -> Violation:
    canonical = _entity_in(claim.surrounding, canonical_blob)
    rollup = _entity_in(claim.surrounding, rollup_blob)
    if canonical:
        sev = "pass"
        note = "claim traces to canonical_item_truth"
    elif rollup:
        sev = "warning"
        note = (
            "claim traces only to rollup_summary — possible "
            "rollup-to-per-item leak"
        )
    else:
        sev = "error"
        note = (
            "claim does not trace to any canonical or rollup section "
            "in the prompt"
        )
    return Violation(
        family=claim.family,
        matched_text=claim.matched_text,
        surrounding=claim.surrounding,
        canonical_match=canonical,
        rollup_match=rollup,
        severity=sev,
        note=note,
    )


# ── Public API ──────────────────────────────────────────────────────

def validate_narration_contract(
    response_text: str,
    canonical_blob: str,
    rollup_blob: str,
    *,
    user_id: Optional[int] = None,
    request_id: Optional[str] = None,
) -> dict:
    """Inspect `response_text` for state-determining claims and grade
    each by traceability.

    Args:
        response_text: the final LLM response.
        canonical_blob: concatenation of all [TIER:canonical_item_truth]
            sections from the system prompt (or their content).
        rollup_blob: concatenation of all [TIER:rollup_summary]
            sections from the system prompt.
        user_id, request_id: optional, attached to telemetry logs.

    Returns:
        dict:
            'passed': list[Violation] (severity='pass')
            'warnings': list[Violation] (severity='warning')
            'errors': list[Violation] (severity='error')
            'summary': dict with counts
    """
    families = [
        ("completed", _COMPLETION_PATTERNS),
        ("overdue", _OVERDUE_PATTERNS),
        ("at_risk", _AT_RISK_PATTERNS),
        ("next_action", _NEXT_ACTION_PATTERNS),
        ("fix_priority", _FIX_PRIORITY_PATTERNS),
    ]

    all_claims = []
    for family, pats in families:
        all_claims.extend(_scan(response_text or "", pats, family))

    passed, warnings, errors = [], [], []
    for c in all_claims:
        v = _classify_claim(c, canonical_blob or "", rollup_blob or "")
        if v.severity == "pass":
            passed.append(v)
        elif v.severity == "warning":
            warnings.append(v)
        else:
            errors.append(v)

    if warnings or errors:
        logger.warning(
            "NARRATION_CONTRACT_VIOLATION user=%s request=%s "
            "warnings=%d errors=%d",
            user_id, request_id, len(warnings), len(errors),
        )
        for v in warnings + errors:
            logger.warning(
                "  [%s] %s — '%s' :: %s",
                v.severity.upper(), v.family,
                v.matched_text, v.note,
            )

    return {
        "passed": [vars(v) for v in passed],
        "warnings": [vars(v) for v in warnings],
        "errors": [vars(v) for v in errors],
        "summary": {
            "passed": len(passed),
            "warnings": len(warnings),
            "errors": len(errors),
        },
    }
