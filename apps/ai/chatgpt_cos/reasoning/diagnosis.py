# ==============================================================================
# File: apps/ai/chatgpt_cos/reasoning/diagnosis.py
# Capability: DIAGNOSTIC REASONING — the "help me understand what changed" mode of the
# conversational-intent-evolution ladder (Status → DIAGNOSIS → Planning → Decision). When
# the user introduces a problem to understand ("I'm having a hard time breaking 289, it's
# not falling off like the beginning"), Beth must stop replaying a status summary and
# reason like a diagnostician over the subject's DETERMINISTIC trajectory.
#
# This REUSES the reasoning lane's deterministic retrieval (synthesize_plan → retrieve_truth
# → build_working_memory) so diagnosis is grounded in real data, NOT LLM speculation — but
# it runs its OWN diagnostic prompt instead of an intent's status/survey profile, so the
# shared reasoning engine (REASONING_PROFILES / run_reasoning) is untouched. Domain-agnostic:
# the same path serves goals and health today, and any future domain that exposes a truth
# scope. No new OpenAI planner intent is introduced — existing intents are used only for
# their RETRIEVAL scope.
# ==============================================================================
import json
import logging

logger = logging.getLogger(__name__)

# Domain → the existing intent whose deterministic RETRIEVAL scope we borrow (goals_state /
# health_state working memory). We do NOT use these intents' status/survey profiles.
_DOMAIN_RETRIEVAL_INTENT = {
    "goals": "goal_concerns",
    "health": "health_concerns",
}

_DIAGNOSTIC_SYSTEM = (
    "You are the user's Chief of Staff, and the conversation has just shifted: the user "
    "moved from checking STATUS to wanting to UNDERSTAND WHY something changed. Do NOT give "
    "a status summary, a progress report, or a list of other areas of their life. Using "
    "ONLY the deterministic working memory provided (their real data and its trajectory), "
    "reason like a diagnostician:\n"
    "1) Briefly acknowledge the shift and reflect back the SPECIFIC thing they raised.\n"
    "2) Reason about WHAT HAS CHANGED over time — the trajectory, the rate of change, and "
    "the most likely contributing factors that are visible IN THE DATA. Where it applies, "
    "note that early rapid change often behaves differently than later (e.g. water weight "
    "and a larger deficit early vs. a smaller gap later) — but only if the data supports it.\n"
    "3) Say what you'd want to look at next to confirm, and ask ONE focused question OR "
    "propose ONE concrete next check.\n"
    "Stay strictly on the ONE subject they raised — do NOT drift to other goals, prayer, "
    "sleep, or unrelated domains unless the data directly ties them to this subject. Be "
    "grounded: if the data doesn't support a cause, say what you'd need to see rather than "
    "guessing. Warm, concise, investigative. Max ~160 words."
)


def _diagnostic_fallback(subject_label):
    """Deterministic fallback when the LLM is unavailable — still investigative and on-
    subject, never a status summary and never a guess."""
    subj = subject_label or "this"
    return (
        f"Let's dig into {subj} rather than just restate where you are. Two things usually "
        "drive a slowdown like this: the early phase tends to move faster (a bigger gap and "
        "some water weight), and small changes in routine — intake, training load, sleep, "
        "stress — show up later than you'd expect. I'd want to look at what's actually "
        "changed in the data around when it slowed before drawing a conclusion. What have "
        "you noticed shifting around that time?")


def answer_diagnostic(user, message, domain, focal_goal=None, subject_label=None):
    """Grounded DIAGNOSIS. Retrieve the subject's deterministic truth, then reason about
    WHAT CHANGED (trajectory + likely factors) — one investigative read, not a status
    summary or a concern survey. Returns a result dict, or None to fall through."""
    intent = _DOMAIN_RETRIEVAL_INTENT.get(domain)
    if intent is None:
        return None
    try:
        from apps.ai.chatgpt_cos.reasoning.plan import synthesize_plan
        from apps.ai.chatgpt_cos.reasoning.stages import (
            retrieve_truth, build_working_memory)
        plan = synthesize_plan(intent, focal_goal=focal_goal)
        truth = retrieve_truth(user, plan)
        working_memory = build_working_memory(plan, truth, user)
    except Exception:
        logger.warning("diagnosis: retrieval failed user=%s domain=%s",
                       getattr(user, "id", None), domain, exc_info=True)
        return None

    user_prompt = (
        f"Question (the user has shifted into diagnosis): {message}\n\n"
        f"Working memory (the ONLY facts you may use):\n"
        f"{json.dumps(working_memory, default=str)}")
    answer = None
    try:
        from apps.ai.services import ai_service
        answer = ai_service._call_api(
            _DIAGNOSTIC_SYSTEM, user_prompt, max_tokens=280, temperature=0.4,
            endpoint="cos_chat", user=user, skip_current_context=True)
    except Exception:
        logger.warning("diagnosis: LLM failed user=%s domain=%s",
                       getattr(user, "id", None), domain, exc_info=True)
        answer = None
    answer = (answer or "").strip()
    used_fallback = not answer
    if used_fallback:
        answer = _diagnostic_fallback(subject_label)

    logger.info("COS_DIAGNOSIS user=%s domain=%s intent=%s focal=%r fallback=%s",
                getattr(user, "id", None), domain, intent, focal_goal, used_fallback)
    return {
        "answer": answer,
        "tools_called": ["reasoning_diagnosis"],
        "tools_advertised": [],
        "lane": "diagnostic",
        "reasoning": {"mode": "diagnosis", "domain": domain,
                      "retrieval_intent": intent, "used_fallback": used_fallback},
    }
