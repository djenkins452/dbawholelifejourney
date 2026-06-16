"""
Phase 3 — Right Now Focus Resolver.

Deterministic single-item answer to "what should the user focus on right now?".
Reads SAE state across all critical domains, looks at each domain's Trust
Report (priority_level + confidence + sufficiency), and picks ONE focus.

Selection rules (deterministic, no ML, no randomness):

    1. Eligibility filter:
       - Must have a Trust Report
       - Sufficiency must NOT be "low" UNLESS priority_level is "high"
         (a high-priority gap deserves attention even with thin data)
       - Confidence must be ≥ 50 (we won't push the user on a coin flip)

    2. Priority ranking:
       high > medium > low

    3. Tie-breaker within a priority bucket:
       higher confidence wins

    4. Final tie-break:
       deterministic domain order (workouts → medication → fasting →
       nutrition → sleep → body_composition → journal → faith)

    5. If no eligible domain has priority "high" or "medium", returns
       a low-pressure recovery focus (e.g. "Stay consistent — nothing
       urgent today.").

CoS reads ``right_now_focus`` from state. CoS must NEVER recompute it.
"""

from __future__ import annotations

import logging
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)


# Deterministic tie-break order. Earlier = higher precedence.
_DOMAIN_ORDER = [
    "workouts",
    "medication",
    "fasting",
    "nutrition",
    "sleep",
    "body_composition",
    "journal",
    "faith",
]

_PRIORITY_RANK = {"high": 3, "medium": 2, "low": 1}


def _eligible(report: Dict[str, Any]) -> bool:
    """Phase 3 eligibility gate for right_now selection."""
    if not isinstance(report, dict):
        return False
    confidence = report.get("confidence", 0) or 0
    priority = report.get("priority_level", "low")
    sufficiency = report.get("sufficiency", "low")

    if confidence < 50:
        return False
    if sufficiency == "low" and priority != "high":
        return False
    return True


# Map execution-truth completion → right_now domain keys. Only domains with a
# canonical "done today" signal are gated; others are unaffected.
def _execution_completed_domains(user) -> set:
    """Right-now domains whose canonical completion is satisfied TODAY (Tier-1
    execution truth). Used to gate recommendations so a completed domain is
    never silently surfaced as a gap/focus (trust bug 2026-06-16). Never raises."""
    done: set = set()
    try:
        from apps.core.execution.execution_truth_engine import get_execution_truth
        truth = get_execution_truth(user)
        faith = truth.get('domains', {}).get('faith', {})
        if faith.get('bible_reading_completed') or faith.get('prayer_completed'):
            done.add('faith')
        if truth.get('domains', {}).get('workout', {}).get('completed'):
            done.add('workouts')
        if truth.get('domains', {}).get('journal', {}).get('completed'):
            done.add('journal')
        meds = truth.get('medications', {})
        if (meds.get('expected', 0) or 0) > 0 and meds.get('all_taken'):
            done.add('medication')
    except Exception:
        logger.debug("right_now: completed-domains read failed", exc_info=True)
    return done


def compute_right_now_focus(
    trust_reports: Dict[str, Optional[Dict[str, Any]]],
    completed_today: Optional[set] = None,
) -> Dict[str, Any]:
    """
    Pick the single most important focus from a dict of trust reports.

    Args:
        trust_reports: ``{domain_name: trust_report_dict_or_None}``

    Returns:
        Dict with: ``domain``, ``priority``, ``confidence``, ``reason``,
        plus a ``status`` key indicating whether a focus was found
        (``"focused"``) or no urgent items exist (``"steady"``).
    """
    completed_today = completed_today or set()
    eligible = []
    for domain, report in trust_reports.items():
        if report is None:
            continue
        if not _eligible(report):
            continue
        # Grounding gate: a domain completed today is NOT a gap/focus, unless
        # the report carries explicit grounded evidence to override completion
        # (e.g. a declining trend / journal sentiment). Silent overrides are
        # prohibited — see the reason-citing below (trust bug 2026-06-16).
        if domain in completed_today and not report.get("grounded_override_reason"):
            continue
        eligible.append((domain, report))

    if not eligible:
        return {
            "status": "steady",
            "domain": None,
            "priority": "low",
            "confidence": None,
            "reason": "Nothing urgent right now — stay consistent.",
        }

    def sort_key(item):
        domain, report = item
        priority_rank = _PRIORITY_RANK.get(report.get("priority_level", "low"), 1)
        confidence = report.get("confidence", 0) or 0
        # Domain order is a stable secondary tie-break — earlier domains
        # in _DOMAIN_ORDER win when everything else is equal.
        try:
            order_index = _DOMAIN_ORDER.index(domain)
        except ValueError:
            order_index = len(_DOMAIN_ORDER)
        # Sort: priority desc, confidence desc, domain order asc
        return (-priority_rank, -confidence, order_index)

    eligible.sort(key=sort_key)
    chosen_domain, chosen_report = eligible[0]

    reason = chosen_report.get("priority_reason", f"Focus on {chosen_domain}")
    overridden = chosen_domain in completed_today
    if overridden:
        # Surfacing a completed domain — MUST cite the grounded override reason.
        override_reason = chosen_report.get("grounded_override_reason") or reason
        reason = (
            f"{chosen_domain.replace('_', ' ').title()} is completed today, but "
            f"I'm surfacing it because {override_reason}"
        )

    return {
        "status": "focused",
        "domain": chosen_domain,
        "priority": chosen_report.get("priority_level", "medium"),
        "confidence": chosen_report.get("confidence"),
        "reason": reason,
        "completed_override": overridden,
    }
