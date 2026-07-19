# ==============================================================================
# File: apps/journal/services/write_together.py
# Project: Whole Life Journey — Journal experience redesign (Milestone 1)
# ==============================================================================
"""
Write Together — the Chief of Staff as a curious writing companion.

Milestone 1 of the Journal experience redesign (text-only). From the Journal
entry page a user may invite the Chief of Staff to read their in-progress draft
and ask ONE genuinely curious question that helps them tell more of their own
story. The answer is the user's own words, typed into their entry.

This is NOT a reasoning engine, classifier, question engine, or therapy surface.
It composes the existing Model Interface seam (``AIService._call_api``) with a
Playbook-grounded system prompt. It lives in the service layer (not a request
module) so the single model call never sits inline on a view — preserving the
request-path-safety contract (``apps/core/tests/test_request_path_safety_contract.py``).

Governing design:
    docs/WLJ_JOURNAL_EXPERIENCE.md              (§5 Write Together, Definition of Success)
    docs/WLJ_JOURNAL_CONVERSATION_PLAYBOOK.md   (posture, generic-vs-personal, never-therapy)
"""

import logging

from apps.ai.services import AIService

logger = logging.getLogger(__name__)

# Bounds: keep the model call small and predictable.
_MAX_DRAFT_CHARS = 4000
# Below this there isn't enough on the page to ask about — offer a simple opener.
_MIN_DRAFT_CHARS = 15

# A warm, simple, natural invitation for a blank/barely-started page. Honest —
# never dressed up as "personal" when there is no real hook (Playbook §5, §7).
_SIMPLE_OPENER = "What's on your mind — start anywhere, and I'll follow along."

# A safe, non-clinical fallback used only when the companion is unavailable, so
# the Journal never breaks because the model could not be reached.
_FALLBACK_QUESTION = "What's one part of this you'd most want to remember?"

# Playbook-grounded posture. One curious, non-directive question about the
# user's own story — never diagnosis, advice, analysis, or the "how did that
# make you feel" tic.
_SYSTEM_PROMPT = (
    "You are the user's Chief of Staff, invited into their personal journal entry as a "
    "warm, genuinely curious writing companion — never a therapist, coach, counselor, or analyst.\n\n"
    "Read what they have written so far and ask EXACTLY ONE short, curious question that helps "
    "them tell more of their own story. Follow whatever they seem most alive in.\n\n"
    "Rules:\n"
    "- Ask about events, people, actions, specifics, or what a moment was like — never about their psychology.\n"
    "- Never diagnose, never label a feeling, never give advice, never tell them what they should do.\n"
    "- Do not ask 'how did that make you feel'.\n"
    "- Do not analyze, summarize, interpret, or praise. Just ask one real, human question.\n"
    "- One sentence. Warm, plain, and specific to what they actually wrote.\n"
    "Return only the question itself — no preamble, no quotation marks, no explanation."
)


def ask_writing_question(user, draft_text):
    """Return one curious question about the user's in-progress journal draft.

    Args:
        user: the authenticated user (for usage logging / model availability).
        draft_text: the plain text of the draft so far.

    Returns:
        dict: ``{"ok": bool, "question": str, "degraded": bool}``.
        - ``degraded=True`` means the model was unavailable and a safe fallback
          question is returned. This function never raises to the caller — the
          Journal must never break because the companion is unavailable.
    """
    text = (draft_text or "").strip()

    # Blank / barely-started page: a simple natural invitation, deterministically
    # (no model call). Prefer a personal question ONLY when there is a real hook.
    if len(text) < _MIN_DRAFT_CHARS:
        return {"ok": True, "question": _SIMPLE_OPENER, "degraded": False}

    user_prompt = (
        'Here is my journal entry so far:\n\n"""\n'
        f"{text[:_MAX_DRAFT_CHARS]}\n"
        '"""\n\n'
        "Ask me one question."
    )

    try:
        response = AIService()._call_api(
            _SYSTEM_PROMPT,
            user_prompt,
            max_tokens=80,
            temperature=0.6,
            endpoint="journal_write_together",
            user=user,
        )
    except Exception:
        logger.exception("Write Together question generation failed")
        response = None

    if not response:
        # Unavailable / rate-limited / error — never break the page.
        return {"ok": True, "question": _FALLBACK_QUESTION, "degraded": True}

    question = _clean_question(response)
    if not question:
        return {"ok": True, "question": _FALLBACK_QUESTION, "degraded": True}
    return {"ok": True, "question": question, "degraded": False}


def _clean_question(raw):
    """Normalize model output to a single, quote-stripped question line."""
    q = (raw or "").strip()
    # Take the first non-empty line only (defend against multi-question output).
    for line in q.splitlines():
        line = line.strip()
        if line:
            q = line
            break
    # Strip wrapping quotes the model sometimes adds, then hard-cap for UI safety.
    q = q.strip().strip('"').strip("'").strip()
    return q[:300]
