# ==============================================================================
# File: apps/journal/services/journal_conversation.py
# Project: Whole Life Journey — Journal experience redesign (Milestone 2)
# ==============================================================================
"""
Write Together / Talk It Through — the dedicated Journal conversation.

One focused conversation whose sole purpose is to create today's journal. It runs
under the Journal Conversation Playbook and the Conversational Memory Model, and
at the end it generates the entry in the user's own voice for review → approve.

This is NOT a reasoning engine, classifier, question engine, or emotion engine.
It composes the existing Model Interface seam (``AIService._call_api``) with a
Playbook-grounded system prompt and the running conversation as history. It lives
in the service layer (not a request module), so the model call never sits inline
on a view — preserving the request-path-safety contract. Text and voice share
this one system; only the input/output modality differs (voice is a later
milestone that plugs into these same functions).

Governing design:
    docs/WLJ_JOURNAL_CONVERSATION_PLAYBOOK.md
    docs/WLJ_JOURNAL_CONVERSATIONAL_MEMORY_MODEL.md
    docs/WLJ_JOURNAL_EXPERIENCE.md  (§5 Write Together, §12 generation)
"""

import logging

from apps.ai.services import AIService

logger = logging.getLogger(__name__)

# Provenance value for entries created from a Journal conversation. Stored on the
# entry's created_via (max_length 20; choices are validation-only). Structural
# provenance is also captured by JournalConversation.resulting_entry.
CREATED_VIA_VOICE_TOGETHER = "voice_together"

_SIMPLE_OPENER = "What would you like to remember about today?"
_FALLBACK_REPLY = "Tell me more — what happened next?"

# ── The conversation posture (Playbook) ───────────────────────────────────────
_CONVO_SYSTEM = (
    "You are the user's Chief of Staff, sitting down with them at the end of the day for a "
    "warm, unhurried journaling conversation. You are NOT a therapist, coach, counselor, or "
    "analyst, and this is NOT the general assistant chat.\n\n"
    "Your ONE purpose is to help them preserve the story of their day, so it can become today's "
    "journal. You are helping them tell the story — not interviewing them for facts.\n\n"
    "How you talk:\n"
    "- Ask ONE short, genuinely curious question at a time. Follow whatever they seem most alive in.\n"
    "- Ask about events, people, actions, specifics, and what a moment was like — never about their psychology.\n"
    "- Reflect a fragment of what they said before asking, so they feel heard — but never summarize or recap.\n"
    "- Let them do most of the talking. Keep your replies to a sentence or two.\n"
    "- Never diagnose, never label a feeling, never give advice, never tell them what to do.\n"
    "- Do NOT ask 'how did that make you feel'. Let feeling emerge through concrete detail.\n"
    "- Never analyze, never moralize, never manufacture depth. An ordinary day is a complete day.\n"
    "- Remember what matters within this conversation and gently return to an unfinished thread the "
    "user clearly cared about — but never repeat details just to prove you remember.\n\n"
    "Ending: when you sense you have enough to write a meaningful entry (usually a few exchanges), "
    "warmly let them know — e.g. 'I think I have what I need for today's journal whenever you're ready.' "
    "Do not keep fishing for more once the story has landed."
)

# ── The generation posture (fidelity — UX §12) ────────────────────────────────
_GEN_SYSTEM = (
    "You are writing today's journal entry FOR the user, in THEIR own voice, from the conversation "
    "you just had with them. You are a scribe preserving their day — not an author.\n\n"
    "Rules:\n"
    "- First person, past tense, as if the user wrote it themselves.\n"
    "- Include ONLY what the user actually said or clearly meant. Never invent an event, a feeling, "
    "a lesson, or a conclusion they did not express. No embellishment.\n"
    "- Preserve the specifics: names, places, and the small details that make it real.\n"
    "- Natural, flowing prose — NOT a transcript, NOT a summary, NOT bullet points, NOT an essay.\n"
    "- Match how this person actually writes (see their recent entries below for voice — cadence and "
    "length, not content).\n"
    "- Return ONLY the entry text (plain prose, paragraphs separated by a blank line). No title, no preamble."
)


def get_or_create_active(user):
    """Resume the user's active conversation, or start a new one for today.

    Durability: there is at most one active conversation; returning to Write
    Together always resumes it, so nothing is ever lost.
    """
    from apps.journal.models import JournalConversation
    from apps.core.utils import get_user_today
    today = get_user_today(user)
    convo = (
        JournalConversation.objects
        .filter(user=user, state=JournalConversation.STATE_ACTIVE, entry_date=today)
        .order_by("-updated_at")
        .first()
    )
    if convo is None:
        convo = JournalConversation.objects.create(user=user, entry_date=today)
    return convo


def ensure_opening(user, convo):
    """If the conversation hasn't started, produce and persist the CoS opening."""
    if convo.transcript:
        return None
    opening = _generate_opening(user)
    convo.add_turn(convo.ROLE_ASSISTANT, opening)
    convo.save(update_fields=["transcript", "updated_at"])
    return opening


def respond(user, convo, user_message):
    """Persist the user's turn, get the CoS reply (Playbook), persist and return it."""
    text = (user_message or "").strip()
    if not text:
        return None
    convo.add_turn(convo.ROLE_USER, text)
    convo.save(update_fields=["transcript", "updated_at"])

    history = _history_for_api(convo, exclude_last=True)
    reply = _call(user, _CONVO_SYSTEM, text, conversation_history=history,
                  max_tokens=260, temperature=0.6, endpoint="journal_write_together_convo")
    if not reply:
        reply = _FALLBACK_REPLY
    convo.add_turn(convo.ROLE_ASSISTANT, reply)
    convo.save(update_fields=["transcript", "updated_at"])
    return reply


def generate_entry(user, convo):
    """Generate today's journal from the conversation, in the user's voice.

    Stores the draft on the conversation and moves it to REVIEWING. Returns the
    draft text (plain prose) for the review step. Never raises to the caller.
    """
    system = _GEN_SYSTEM + _voice_samples_block(user)
    transcript = _transcript_as_text(convo)
    user_prompt = (
        "Here is the conversation with the user about their day:\n\n"
        f"{transcript}\n\n"
        "Write today's journal entry in their voice, following the rules exactly."
    )
    draft = _call(user, system, user_prompt, max_tokens=700, temperature=0.5,
                  endpoint="journal_write_together_generate")
    draft = (draft or "").strip()
    convo.generated_draft = draft
    convo.state = convo.STATE_REVIEWING
    convo.save(update_fields=["generated_draft", "state", "updated_at"])
    return draft


# ── internals ─────────────────────────────────────────────────────────────────

def _call(user, system, user_prompt, conversation_history=None, max_tokens=260,
          temperature=0.6, endpoint="journal_write_together"):
    try:
        return AIService()._call_api(
            system,
            user_prompt,
            max_tokens=max_tokens,
            temperature=temperature,
            endpoint=endpoint,
            user=user,
            conversation_history=conversation_history,
        )
    except Exception:
        logger.exception("Journal conversation model call failed (endpoint=%s)", endpoint)
        return None


def _generate_opening(user):
    """A warm opening — personal when WLJ has a genuinely relevant hook, else a
    simple natural invitation (never forced personalization)."""
    context = _personal_context(user)
    system = (
        "You are the user's Chief of Staff, opening an end-of-day journaling conversation. "
        "Say ONE warm sentence to invite them to begin. If the context below contains a genuinely "
        "relevant, specific thing about today (a person they were with, an event, a milestone), open "
        "with THAT — like a friend who knows them. If nothing stands out, use a simple natural "
        "invitation. Never force a personal reference just to prove you remember. Return only the "
        "one-sentence opening.\n\n"
        f"Context about the user (may be empty):\n{context}"
    )
    opening = _call(user, system, "Open the journaling conversation.",
                    max_tokens=80, temperature=0.6, endpoint="journal_write_together_open")
    opening = (opening or "").strip().strip('"').strip()
    return opening or _SIMPLE_OPENER


def _personal_context(user):
    """A compact, safe-to-embed standing read for grounding the opener. Reuses the
    existing composer; never fails the conversation if unavailable."""
    try:
        from apps.ai.cos_intelligence import build_cos_intelligence
        data = build_cos_intelligence(user)
        if isinstance(data, dict):
            import json
            return json.dumps(data, default=str)[:1500]
        return str(data)[:1500]
    except Exception:
        logger.debug("Personal context unavailable for journal opener", exc_info=True)
        return ""


def _voice_samples_block(user):
    """A few of the user's recent entries so generation matches how THEY write."""
    try:
        from apps.journal.services.journal_queries import JournalQueries
        entries = list(JournalQueries.recent(user, days=180)[:3])
        samples = [(e.body_plain or "").strip()[:600] for e in entries if (e.body_plain or "").strip()]
        if not samples:
            return ""
        joined = "\n---\n".join(samples)
        return f"\n\nThe user's recent journal entries (for VOICE only — cadence and length, not content):\n{joined}"
    except Exception:
        logger.debug("Voice samples unavailable for journal generation", exc_info=True)
        return ""


def _history_for_api(convo, exclude_last=False):
    turns = list(convo.transcript or [])
    if exclude_last and turns:
        turns = turns[:-1]
    out = []
    for t in turns:
        role = t.get("role")
        content = (t.get("text") or "").strip()
        if role in ("user", "assistant") and content:
            out.append({"role": role, "content": content})
    return out


def _transcript_as_text(convo):
    lines = []
    for t in (convo.transcript or []):
        content = (t.get("text") or "").strip()
        if not content:
            continue
        who = "Me" if t.get("role") == "user" else "Chief of Staff"
        lines.append(f"{who}: {content}")
    return "\n".join(lines)
