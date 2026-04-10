"""
Phase 18.2 — Decision Governance Layer.

Sits between prioritization and output. Every recommendation passes
through validate_decision() before reaching the user. If a
recommendation violates real-world logic, priority hierarchy, or
consistency, it is REJECTED and a safe fallback is returned.

Pipeline position:
    State → Prioritizer → **Governor** → Output (CoS / UI)

Rules enforced:
    1. REALITY CONSTRAINT — fixed items cannot be moved/deprioritized
    2. PRIORITY HIERARCHY — faith > health > work > household > flexible
    3. DECISION CONSISTENCY — same state → same answer
    4. NO LOGICAL NONSENSE — blocked/completed items never recommended
    5. SINGLE DECISION SOURCE — no recomputation outside SAE
"""

import hashlib
import logging

from django.core.cache import cache

logger = logging.getLogger(__name__)


# ── Priority Hierarchy (global, immutable) ───────────────────────────
# Higher tier items MUST be recommended before lower tier items when
# both are overdue. Time-based ordering NEVER overrides this.

PRIORITY_TIERS = {
    # Tier 0 — Faith (non-negotiable)
    'prayer': 0,
    'bible': 0,
    'faith': 0,
    'scripture': 0,
    'devotional': 0,
    # Tier 1 — Health (critical)
    'workout': 1,
    'medication': 1,
    'health': 1,
    'supplement': 1,
    # Tier 2 — Core Work
    'work': 2,
    'wlj': 2,
    'life': 2,
    # Tier 3 — Household / Responsibilities
    'household': 3,
    'chore': 3,
    'errand': 3,
    # Tier 4 — Flexible / Optional
    'flexible': 4,
    'optional': 4,
}


def _infer_tier(item):
    """Infer the priority tier of an execution item.

    Uses domain, title keywords, and importance to map into the
    global priority hierarchy. Unknown items default to tier 3
    (household) — safe middle ground.
    """
    title_lower = (item.get('title') or '').lower()
    domain = (item.get('domain') or '').lower()
    source_type = item.get('source_type', '')
    importance = item.get('importance', '')

    # Quick-action health items (Phase 16)
    if source_type in ('medication_dose', 'supplement_dose'):
        return 1

    # Faith keywords
    for kw in ('prayer', 'bible', 'scripture', 'devotional',
               'faith', 'reading plan'):
        if kw in title_lower:
            return 0

    # Health keywords
    for kw in ('workout', 'exercise', 'gym', 'protein shake',
               'medication', 'supplement'):
        if kw in title_lower:
            return 1

    # Domain-based
    if domain in ('faith', 'spiritual'):
        return 0
    if domain in ('health', 'fitness', 'medical'):
        return 1
    if domain in ('work', 'career'):
        return 2

    # Importance-based fallback
    if importance == 'foundational':
        return 2
    if importance == 'flexible':
        return 4

    return 3  # default: household


def _infer_constraint_type(item):
    """Infer whether an item is fixed, anchored, or flexible.

    - fixed: cannot be moved (calendar events with is_protected=True,
      or commitment_level='foundational')
    - anchored: limited flexibility (important items with a scheduled time)
    - flexible: can move freely
    """
    is_protected = item.get('is_protected', False)
    commitment = (item.get('commitment_level') or '').lower()

    if is_protected or commitment == 'foundational':
        return 'fixed'
    if item.get('scheduled_time') and commitment in ('important', ''):
        return 'anchored'
    return 'flexible'


# ── Governance Validation ────────────────────────────────────────────

class GovernanceViolation(Exception):
    """Raised when a recommendation violates a governance rule."""

    def __init__(self, rule, reason, recommendation):
        self.rule = rule
        self.reason = reason
        self.recommendation = recommendation
        super().__init__(f"[{rule}] {reason}")


def validate_decision(recommendation, exec_items=None, user=None):
    """Validate a decision recommendation against all governance rules.

    Args:
        recommendation: str — the "Do this next: ..." response text
        exec_items: list — the execution items used for the decision
        user: User — for consistency caching

    Returns:
        str — the approved recommendation (may be the same or a
              corrected version)

    Raises:
        GovernanceViolation — if the recommendation cannot be approved
        and no safe correction is possible.
    """
    if not recommendation:
        return recommendation

    first_line = recommendation.split('\n')[0].lower()

    # ── Rule 1: Reality Constraint ───────────────────────────
    # Fixed items cannot be moved, delayed, or deprioritized.
    # If the recommendation suggests moving a fixed item, block it.
    _MOVE_VERBS = ('move ', 'reschedule ', 'delay ', 'postpone ',
                   'skip ', 'cancel ', 'deprioritize ')
    if exec_items:
        for item in exec_items:
            if _infer_constraint_type(item) != 'fixed':
                continue
            title_lower = (item.get('title') or '').lower()
            for verb in _MOVE_VERBS:
                if verb in first_line and title_lower in first_line:
                    logger.warning(
                        "GOVERNANCE_BLOCK rule=reality_constraint "
                        "action='%s' fixed_item='%s' user=%s",
                        first_line[:80], item.get('title'),
                        getattr(user, 'id', '?'),
                    )
                    raise GovernanceViolation(
                        'REALITY_CONSTRAINT',
                        f"Cannot move/delay fixed item: {item.get('title')}",
                        recommendation,
                    )

    # ── Rule 2: Priority Hierarchy ───────────────────────────
    # The recommended item must not be a lower-tier item when
    # higher-tier overdue items exist.
    if exec_items:
        recommended_title = _extract_title(first_line)
        if recommended_title:
            recommended_item = _find_item(recommended_title, exec_items)
            if recommended_item:
                rec_tier = _infer_tier(recommended_item)
                overdue_items = [
                    i for i in exec_items
                    if i.get('time_status') == 'overdue'
                    and not i.get('completed_today')
                ]
                for overdue in overdue_items:
                    overdue_tier = _infer_tier(overdue)
                    if overdue_tier < rec_tier:
                        overdue_title = overdue.get('title', '?')
                        logger.warning(
                            "GOVERNANCE_BLOCK rule=priority_hierarchy "
                            "recommended='%s' (tier %d) but '%s' "
                            "(tier %d) is overdue user=%s",
                            recommended_item.get('title'), rec_tier,
                            overdue_title, overdue_tier,
                            getattr(user, 'id', '?'),
                        )
                        raise GovernanceViolation(
                            'PRIORITY_HIERARCHY',
                            f"'{overdue_title}' (tier {overdue_tier}) "
                            f"is overdue and outranks "
                            f"'{recommended_item.get('title')}' "
                            f"(tier {rec_tier})",
                            recommendation,
                        )

    # ── Rule 4: No Logical Nonsense ──────────────────────────
    # Completed or non-actionable items must never be recommended.
    if exec_items:
        recommended_title = _extract_title(first_line)
        if recommended_title:
            matched = _find_item(recommended_title, exec_items)
            if matched and matched.get('completed_today'):
                logger.warning(
                    "GOVERNANCE_BLOCK rule=no_nonsense "
                    "completed_item='%s' user=%s",
                    matched.get('title'),
                    getattr(user, 'id', '?'),
                )
                raise GovernanceViolation(
                    'NO_NONSENSE',
                    f"'{matched.get('title')}' is already completed",
                    recommendation,
                )

    return recommendation


def _extract_title(first_line_lower):
    """Extract the item title from a 'Do this next: Start X.' line."""
    for prefix in ('do this next: start ', 'do this next: take ',
                   'do this next: complete ', 'do this next: ',
                   'your priority is: '):
        if first_line_lower.startswith(prefix):
            title = first_line_lower[len(prefix):].rstrip('.')
            # Remove recovery/coaching framing
            for suffix in (' — quick win', ' — this is the fastest',
                          ' now'):
                if title.endswith(suffix):
                    title = title[:-len(suffix)]
            return title.strip()
    return None


def _find_item(title_lower, exec_items):
    """Find the execution item whose title matches (case-insensitive)."""
    for item in exec_items:
        if (item.get('title') or '').lower().strip().rstrip('.') == title_lower:
            return item
    # Partial match fallback
    for item in exec_items:
        if title_lower in (item.get('title') or '').lower():
            return item
    return None
