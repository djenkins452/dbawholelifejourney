"""
System Gap Awareness — Detect known limitations for proactive CoS transparency.

Project: Whole Life Journey
Path: apps/core/blueprint/system_gap_awareness.py
Purpose: Phase 1 gap awareness using existing ImprovementTaskModel

Description:
    Reads known system gaps (from the assistant gap detection pipeline)
    and surfaces them in the CoS governance prompt so the AI can:
    - Proactively mention what it can't do yet
    - Avoid promising actions it has no pathway for
    - Let the user know when an improvement is in progress

    This is a read-only observational feature — no data modifications.
    Output is capped to avoid prompt bloat.

Public API:
    - get_gap_awareness_injection(user) -> str

Copyright:
    (c) Whole Life Journey. All rights reserved.
"""

import logging

logger = logging.getLogger(__name__)

# Maximum gaps to include in prompt injection (token budget)
MAX_GAPS_IN_PROMPT = 3


def get_gap_awareness_injection(user):
    """
    Build a system prompt injection block listing known system gaps.

    Queries ImprovementTaskModel for recent, unresolved gaps that
    this user has triggered. Capped at MAX_GAPS_IN_PROMPT to limit
    token consumption.

    Args:
        user: Django user instance.

    Returns:
        str — Prompt injection block, or empty string if no gaps.
    """
    try:
        from assistant.models import ImprovementTaskModel

        # Find unresolved gaps triggered by this user (or all recent gaps)
        unresolved_statuses = [
            ImprovementTaskModel.STATUS_NEW,
            ImprovementTaskModel.STATUS_PENDING_APPROVAL,
            ImprovementTaskModel.STATUS_APPROVED,
            ImprovementTaskModel.STATUS_IN_PROGRESS,
        ]

        # User-triggered gaps first, then system-wide recent gaps
        user_gaps = list(
            ImprovementTaskModel.objects.filter(
                triggered_by_user=user,
                status__in=unresolved_statuses,
            ).order_by('-created_at')[:MAX_GAPS_IN_PROMPT]
        )

        # If user has fewer than MAX, fill with recent system-wide gaps
        remaining = MAX_GAPS_IN_PROMPT - len(user_gaps)
        if remaining > 0:
            seen_ids = {g.pk for g in user_gaps}
            system_gaps = (
                ImprovementTaskModel.objects.filter(
                    status__in=unresolved_statuses,
                )
                .exclude(pk__in=seen_ids)
                .order_by('-created_at')[:remaining]
            )
            user_gaps.extend(system_gaps)

        if not user_gaps:
            return ''

        lines = [
            "## KNOWN SYSTEM LIMITATIONS",
            "",
            "The following capabilities are known to be limited or in development.",
            "If the user asks about these, be transparent rather than guessing:",
            "",
        ]

        for gap in user_gaps:
            status_label = _status_display(gap.status)
            gap_label = gap.title or str(gap.gap_type).replace('_', ' ').title()
            lines.append(f"  - {gap_label} [{status_label}]")
            if gap.suggested_fix:
                # Truncate long suggestions
                fix_summary = gap.suggested_fix[:120]
                if len(gap.suggested_fix) > 120:
                    fix_summary += '...'
                lines.append(f"    Workaround: {fix_summary}")

        lines.append("")
        lines.append(
            "RULE: If asked about a known limitation, acknowledge it honestly. "
            "Do not fabricate capabilities. If a workaround exists, offer it."
        )

        return '\n'.join(lines)

    except Exception as e:
        logger.debug("System gap awareness unavailable: %s", e)
        return ''


def _status_display(status):
    """Convert status code to user-friendly label."""
    return {
        'new': 'Identified',
        'pending_approval': 'Under Review',
        'approved': 'Approved for Fix',
        'in_progress': 'Being Fixed',
    }.get(status, status.replace('_', ' ').title())
