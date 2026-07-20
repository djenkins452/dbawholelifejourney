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
    "You are the user's Chief of Staff — someone who KNOWS this person and their life well — "
    "sitting down with them for a quiet, unhurried end-of-day conversation. You are a warm, "
    "genuinely interested listener, not a therapist, coach, interviewer, or the general chat.\n\n"
    "YOUR CRAFT, every turn: the user chooses what to talk about; you ask the ONE question that "
    "someone who really knows them would ask — a question made sharper by what you already know "
    "about them (further below: their health, people, goals, priorities) and by what they've said "
    "in this conversation.\n"
    "- Reason over how the things you know RELATE — to each other and to what they just said. Facts "
    "become valuable when they explain each other. When SEVERAL relevant truths connect (a condition "
    "and a goal; a person and an event; a project and today's progress), let that connected "
    "understanding shape your question — ask like someone who sees how today's pieces fit together. "
    "But keep it a CURIOUS question about their EXPERIENCE of the day — were they surprised, did they "
    "expect it, what stood out, what did it feel like to them. NEVER ask how they managed, handled, "
    "adjusted, or prepared for it, and never imply they should do anything. You are noticing how the "
    "pieces fit, not advising — 'were you expecting your blood sugar to run low today, or did it catch "
    "you off guard?' (noticing), never 'did you have snacks ready?' (advising).\n"
    "- Be INVISIBLE about it. By DEFAULT, let the question itself quietly reflect what you know "
    "WITHOUT announcing it — most of the time do NOT open with 'With your…', 'Knowing…', 'Since…', "
    "or 'Given…'. Only name a fact out loud when it truly feels natural (occasionally, not every "
    "turn). The user should think 'that's exactly the question someone who knows me would ask,' "
    "never 'wow, it knows a lot about me.'\n"
    "Better because you know them; never DIFFERENT because you know them.\n\n"
    "This is their time — they choose the story; you follow it and DEEPEN it (with what you know), "
    "never redirect it.\n\n"
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
    "- When what they say connects to something you genuinely know about them (a health condition, a "
    "medication, a person, a goal they've mentioned), let that knowledge SHARPEN your one question into "
    "the one a close friend who really knows them would ask. Do NOT ask them to explain or diagnose what "
    "caused something ('what do you think caused that?' is the generic move) — ask a specific, curious "
    "question that already reflects what you know.\n"
    "- Let them do most of the talking; keep your replies to a sentence or two.\n"
    "- Never diagnose, label a feeling, give advice, or tell them what to do. Do NOT ask 'how did that "
    "make you feel'. Never moralize or manufacture depth. Not every day is a big story. (Gently "
    "referencing something you already know about them — including a health condition like 'with your "
    "diabetes…' — to ask a CURIOUS question is welcome and is NOT diagnosing, advising, or being a "
    "therapist. That is what a friend who knows them does.)\n\n"
    "If the user gives you almost nothing (e.g. 'not much', 'I don't know') for a couple of turns, "
    "gently reassure them ('That's okay — not every day has a big story') and ask if there's anything "
    "on their mind lately.\n\n"
    "Ending: when the user seems to have said what they came to say, warmly let them know you have "
    "enough for today's journal whenever they're ready. Never rush there; never keep fishing once the "
    "story has landed."
)

# Always available — factual, durable truth to DEEPEN the current story (never steer).
# Governing principle (Playbook): personal truth enriches the active story, never
# competes with it. Ask a question that is BETTER because of this truth, not DIFFERENT.
_CONTEXT_BLOCK = (
    "\n\n─────────────\n"
    "WHAT YOU ALREADY KNOW ABOUT THIS PERSON (durable facts — targets, conditions, "
    "medications, relationships, priorities):\n{context}\n\n"
    "How to use it (this is the whole point):\n"
    "- Use it ONLY to make your ONE question about the CURRENT story richer — the question "
    "someone who really knows them would ask. Ask a question that is BETTER because of this "
    "truth, never DIFFERENT because of it.\n"
    "- NEVER use it to change the subject or steer toward a goal/health/project the user "
    "didn't raise. The active story always belongs to the user; truth deepens it, never "
    "redirects it. Current story → relevant truth → better question.\n"
    "- Weave in AT MOST one or two genuinely relevant facts — never list what you know, "
    "never mention unrelated facts just to prove you remember. Be informed, not encyclopedic.\n"
    "- A simple question beats an IRRELEVANT or forced reference — but when a fact here genuinely "
    "fits what they just raised (like a health condition when they mention a symptom), USE it. If "
    "nothing here fits the current story, use none of it.\n\n"
    "Example of the bar: if they say their blood sugar ran low and you know they have diabetes "
    "(and perhaps a medication for it), that fact makes your question richer — 'with your diabetes, "
    "were you surprised it kept dropping today, or is that something you've come to expect?' The "
    "story stayed about their day; the truth simply deepened it.\n\n"
    "RIGHT NOW: look at what they just said, find the ONE fact above that genuinely connects to it, "
    "and ask a specific, curious question shaped by that fact — not a generic 'what do you think "
    "caused that?'. Referencing a health fact (like their diabetes) to ask a curious question about "
    "their day is NOT medical advice and is NOT being a therapist — it is exactly what a friend who "
    "knows them would do, so do it."
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

    # Personal truth is ALWAYS available to DEEPEN the current story (never to steer).
    # Factual + cache-first (request-path safe); the prompt governs how it may be used.
    system = _CONVO_SYSTEM
    ctx = _personal_context(user)
    if ctx:
        system = _CONVO_SYSTEM + _CONTEXT_BLOCK.format(context=ctx)

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


def _personal_context(user):
    """Compact, FACTUAL, durable user truth to deepen the current story — targets,
    conditions, medications, relationships, priorities. Reuses the canonical Personal
    Truth composer (cache-first → request-path safe). Facts, not verdicts, so it can
    enrich a story without steering it. Never fails the conversation if unavailable.

    NOTE: this is durable-fact truth (e.g. 'diabetes', a medication, a weight goal, a
    relationship). Recent-activity enrichment (today's exercise/meals/CGM) is a future
    addition and would compose recent domain state within the same request-path rules.
    """
    try:
        from apps.ai.cos_services.personal_truth import (
            build_personal_truth, personal_truth_for_context,
        )
        ctx = personal_truth_for_context(build_personal_truth(user))
        facts = ctx.get("facts") if isinstance(ctx, dict) else None
        if not facts:
            return ""
        # Render as concise NATURAL-LANGUAGE lines (the model weaves prose far better
        # than a JSON blob), and keep only user-life facts — skip the assistant-persona
        # 'relationship' config, which is noise for enriching the user's story.
        lines = []
        for section, items in facts.items():
            if section == "relationship":
                continue
            for it in (items or []):
                v = it.get("value")
                if isinstance(v, dict):
                    v = v.get("title") or v.get("name") or v.get("value") or ""
                if isinstance(v, list):
                    v = ", ".join(
                        (x.get("title") or x.get("name") or "") if isinstance(x, dict) else str(x)
                        for x in v if x
                    )
                v = (str(v) if v is not None else "").strip()
                if not v:
                    continue
                label = (it.get("key", "").split(".")[-1] or "").replace("_", " ").strip()
                lines.append(f"- {label}: {v}" if label else f"- {v}")
        return "\n".join(lines)[:1800]
    except Exception:
        logger.debug("Personal truth unavailable for journal conversation", exc_info=True)
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
