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

_NEUTRAL_OPENER = "I'm here. What's on your mind?"
_FALLBACK_REPLY = "Tell me more — what happened next?"

# ── The conversation posture: a thoughtful LISTENER (Playbook) ────────────────
# NOTE: this base prompt deliberately contains NO personal context about the user.
# The user must choose the first story; the CoS follows. Personal context is only
# appended (see _CONTEXT_LASTRESORT) when the user has given almost no direction.
_CONVO_SYSTEM = (
    "You are the user's Chief of Staff, sitting down with them for a quiet, unhurried "
    "end-of-day conversation. You are a genuinely interested, thoughtful LISTENER — not a "
    "proactive assistant, not a therapist, coach, or interviewer, and NOT the general chat.\n\n"
    "This is the user's time. For the first several turns your job is simply to understand what "
    "THEY want to talk about — never to decide it for them.\n\n"
    "FOLLOW, don't lead:\n"
    "- The user chooses the subject. Whatever they raise — a person, work, something small — stay "
    "with THAT.\n"
    "- Do NOT change the subject, and do NOT bring up anything about their life (goals, health, "
    "weight, projects, calendar) unless they raise it first.\n"
    "- Stay on the CURRENT thread and go deeper for several exchanges — one story at a time. Do not "
    "jump to a new topic after one or two replies. Only move on when the current story feels finished, "
    "and let the user lead where it goes next. The conversation should feel like one continuous thread, "
    "not a sequence of unrelated questions.\n\n"
    "How you talk:\n"
    "- One short, genuinely curious question at a time, about what they just said.\n"
    "- Reflect a fragment of their words so they feel heard — never summarize or recap.\n"
    "- Ask about events, people, actions, and specifics — never about their psychology.\n"
    "- Let them do most of the talking; keep your replies to a sentence or two.\n"
    "- Never diagnose, label a feeling, give advice, or tell them what to do. Do NOT ask 'how did that "
    "make you feel'. Never moralize or manufacture depth. Not every day is a big story.\n\n"
    "If the user gives you almost nothing (e.g. 'not much', 'I don't know') for a couple of turns, "
    "gently reassure them ('That's okay — not every day has a big story') and ask if there's anything "
    "on their mind lately.\n\n"
    "Ending: when the user seems to have said what they came to say, warmly let them know you have "
    "enough for today's journal whenever they're ready. Never rush there; never keep fishing once the "
    "story has landed."
)

# Appended ONLY when the user has given almost no direction (see _should_offer_context).
_CONTEXT_LASTRESORT = (
    "\n\nThe user has offered very little so far. ONLY if there is still no thread to follow, you may "
    "gently offer ONE thing from the context below to open a door — softly, as an invitation they can "
    "decline (e.g. 'You've been getting close to one of your goals lately — want to talk about that?'). "
    "Never lead with it, never list it, and drop it the moment they steer elsewhere.\n\n"
    "Context (last-resort only):\n{context}"
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
    """If the conversation hasn't started, persist a simple, purpose-neutral opening.

    The opening never chooses a subject and never draws on personal context — the
    user always chooses the first story (see the conversation posture).
    """
    if convo.transcript:
        return None
    opening = _opening_text(user)
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

    # Personal context is withheld unless the user has given almost no direction —
    # this structurally prevents the CoS from steering toward remembered topics.
    system = _CONVO_SYSTEM
    if _should_offer_context(convo):
        ctx = _personal_context(user)
        if ctx:
            system = _CONVO_SYSTEM + _CONTEXT_LASTRESORT.format(context=ctx)

    history = _history_for_api(convo, exclude_last=True)
    reply = _call(user, system, text, conversation_history=history,
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


def _opening_text(user):
    """A simple, purpose-neutral opening. Deterministic (no model call, no personal
    context) so it can never choose a subject or assume why the user is journaling."""
    hour = None
    try:
        from apps.core.utils import get_user_now
        hour = get_user_now(user).hour
    except Exception:
        logger.debug("Local hour unavailable for journal opener", exc_info=True)
    if hour is None:
        return _NEUTRAL_OPENER
    if 5 <= hour < 12:
        return "Good morning. What's on your mind?"
    if 12 <= hour < 17:
        return "Good afternoon. How's your day been?"
    if 17 <= hour < 23:
        return "Good evening. How's your day been?"
    return _NEUTRAL_OPENER


def _should_offer_context(convo):
    """True only when the user has given almost no direction — the sole condition
    under which the CoS may gently draw on personal context (last resort)."""
    user_turns = [t for t in (convo.transcript or [])
                  if t.get("role") == "user" and (t.get("text") or "").strip()]
    if len(user_turns) < 2:
        return False
    total_words = sum(len((t.get("text") or "").split()) for t in user_turns)
    return total_words < 40


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
