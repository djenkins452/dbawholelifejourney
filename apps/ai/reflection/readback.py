# ==============================================================================
# File: apps/ai/reflection/readback.py
# Project: Whole Life Journey - Django 5.x Personal Wellness/Journaling App
# Description: Classifier-approved correction read-back for the CoS prompt.
# ==============================================================================
"""
GATED correction read-back (Phase 4).

The ungated read-back (`correction_service.get_correction_context_block`) would
re-inject ANY stored correction — including truth/reasoning/execution corrections
— telling Beth to "use the corrected information". That is precisely learning
around a deterministic defect (P3). This gated variant injects ONLY corrections
the Executive Reflection classifier approved (preference/communication learnings,
`CorrectionRecord.readback_approved=True`).

Default-deny: a correction is NOT read back until the classifier explicitly
approves it. Truth-domain corrections become EIOs and are never approved, so they
are never re-injected — the platform is fixed instead.
"""

import logging

from django.utils import timezone

logger = logging.getLogger(__name__)

_MAX_READBACK = 5


def approved_correction_context_block(user, query=""):
    """System-prompt block of ONLY classifier-approved corrections. Empty when
    there are none. Never raises."""
    try:
        from apps.ai.models import CorrectionRecord
        recs = list(
            CorrectionRecord.objects.filter(user=user, readback_approved=True)
            .order_by("-created_at")[:_MAX_READBACK]
        )
    except Exception:
        logger.debug("gated read-back query failed", exc_info=True)
        return ""

    if not recs:
        return ""

    now = timezone.now()
    lines = []
    for r in recs:
        delta = now - r.created_at
        if delta.days == 0:
            when = "Earlier today"
        elif delta.days == 1:
            when = "Yesterday"
        elif delta.days < 7:
            when = r.created_at.strftime("%A")
        else:
            when = r.created_at.strftime("%B %d")
        truth = (r.corrected_truth or r.user_correction or "")[:200]
        lines.append(f"  [{when}] The user asked you to: {truth}")

    block = "\n".join(lines)
    return (
        "\n## LEARNED PREFERENCES (classifier-approved; style/personalization only "
        "— NOT facts)\n"
        "Honor these delivery/personalization preferences. They never override "
        "deterministic truth.\n"
        f"{block}\n"
    )
