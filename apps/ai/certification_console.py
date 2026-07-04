# ==============================================================================
# File: apps/ai/certification_console.py
# The Executive Certification Console — the SINGLE shared implementation that both the
# `trigger_proactive_checkin` management command AND the in-app developer console call.
# Every action invokes a REAL production generation path (the same code the scheduler /
# a greeting / an event would run). There is no duplicated business logic here — each
# action is a thin adapter that calls the production function and summarizes the result
# for display. Developer-only; never exposed to normal users.
#
# This is the manual counterpart to the automated Acceptance Center: Engineering
# Certification validates the implementation; Executive Certification validates the
# Chief of Staff. Add actions by registering another production entry point below.
# ==============================================================================
import logging

logger = logging.getLogger(__name__)

_GUIDANCE_CORRELATION = "sleep_mood"


def _proactive_guidance(user, force=False):
    """REAL path: ProactiveCheckInService.generate_cdce_correlation_check_in — the
    cross-domain guidance card with the Tell me more / How to use this / Got it
    buttons. --force bypasses the cadence throttle and clears any prior dismissal."""
    from apps.ai.proactive_checkins import ProactiveCheckInService

    svc = ProactiveCheckInService(user)
    if force:
        svc.throttler.can_send = lambda *a, **k: True
        try:
            from django.core.cache import cache
            cache.delete(f"wlj:guidance_dismissed:{user.id}:{_GUIDANCE_CORRELATION}")
        except Exception:
            pass
    msg = svc.generate_cdce_correlation_check_in(
        correlation_type=_GUIDANCE_CORRELATION,
        narrative="on days you sleep 7+ hours, your journal entries are noticeably more positive",
        strength="strong", domains=["sleep", "journal"])
    if not msg:
        return {"ok": False,
                "summary": "No card produced (throttled or already dismissed). Re-run with Force."}
    return {"ok": True, "message_id": msg.id,
            "summary": f"Proactive guidance card created in your chat (id {msg.id}).",
            "buttons": [q.get("label") for q in (msg.quick_replies or [])],
            "preview": msg.content}


def _morning_checkin(user, force=False):
    """REAL path: the greeting check-in composer (lanes._morning_checkin)."""
    from apps.ai.chatgpt_cos.lanes import _morning_checkin as _gen
    result = _gen(user, "Good morning") or {}
    return {"ok": bool(result.get("answer")),
            "summary": "Morning check-in generated.", "preview": result.get("answer", "")}


def _executive_brief(user, force=False):
    """REAL path: the orientation-first executive brief composer."""
    from apps.ai.chatgpt_cos.executive_brief import compose_executive_brief
    text = compose_executive_brief(user)
    return {"ok": bool(text), "summary": "Executive brief generated.", "preview": text}


def _daily_wrapup(user, force=False):
    """REAL path: the deterministic daily agenda / wrap-up (build_daily_agenda)."""
    from apps.core.cos_briefing.daily_agenda import build_daily_agenda
    text = build_daily_agenda(user)
    return {"ok": bool(text), "summary": "Daily wrap-up / agenda generated.", "preview": text}


def _rebuild_executive_interpretation(user, force=False):
    """REAL path: the executive interpretation engine (interpret → ExecutiveSignals).
    Read-only; shows the raw executive read the brief narrates."""
    from apps.ai.chatgpt_cos.executive_interpretation import interpret
    sig = interpret(user)
    preview = (
        f"Headline: {sig.headline}\n"
        f"Workload: {sig.workload} — {sig.workload_summary}\n"
        f"Primary challenge: {sig.primary_challenge}\n"
        f"Disposition: {sig.disposition or '—'}\n"
        f"Highest leverage: {sig.highest_leverage or '—'}\n"
        f"Reconciliation: {sig.reconciliation or '—'}")
    return {"ok": True, "summary": "Executive interpretation rebuilt.", "preview": preview}


def _refresh_standing_context(user, force=False):
    """REAL path: the post-save intelligence chain (fire_intelligence) — SAE state
    update → PIE insights → PRIE predictions. Idempotent; no outward-facing effect."""
    from apps.core.ai_orchestrator.intelligence_hook import fire_intelligence
    fire_intelligence(user, "health")
    return {"ok": True,
            "summary": "Standing context refreshed (SAE state + insights re-run)."}


# Ordered registry. Each entry's `run(user, force)` calls a production path and returns
# {ok, summary, preview?, message_id?, buttons?}. UI + command both iterate this.
ACTIONS = {
    "proactive_guidance": {
        "label": "Generate Proactive Guidance",
        "desc": "The cross-domain guidance card with Tell me more / How to use this / Got it. "
                "Appears in your chat so you can click the buttons.",
        "run": _proactive_guidance, "creates_message": True,
    },
    "morning_checkin": {
        "label": "Generate Morning Check-in",
        "desc": "Beth's morning greeting, overnight facts, and check-in prompt.",
        "run": _morning_checkin, "creates_message": False,
    },
    "executive_brief": {
        "label": "Generate Executive Brief",
        "desc": "The orientation-first executive briefing (interpretation → priorities → agenda).",
        "run": _executive_brief, "creates_message": False,
    },
    "daily_wrapup": {
        "label": "Generate Daily Wrap-up",
        "desc": "The deterministic end-of-day agenda / wrap-up.",
        "run": _daily_wrapup, "creates_message": False,
    },
    "rebuild_executive_interpretation": {
        "label": "Rebuild Executive Interpretation",
        "desc": "Re-run the executive interpretation engine and show the raw read "
                "(headline, workload, challenge, disposition) the brief narrates.",
        "run": _rebuild_executive_interpretation, "creates_message": False,
    },
    "refresh_standing_context": {
        "label": "Refresh Standing Context",
        "desc": "Re-run the intelligence chain (SAE state → insights → predictions) so "
                "Beth reads fresh context. No outward-facing effect.",
        "run": _refresh_standing_context, "creates_message": False,
    },
    # DEFERRED (need a safe/dry-run mode before they become one-click buttons):
    #   • Evening Wrap-up — time-window routing + daily dedup internals.
    #   • Significant Event Review — react_to_significant_event NOTIFIES (push) and
    #     persists a MAJOR_WIN into the real strategic layer (outward-facing; would
    #     pollute real data). Keep it out of a one-click surface until it has a dry run.
}


def action_list():
    """[(key, label, desc, creates_message)] for rendering the console."""
    return [(k, a["label"], a["desc"], a.get("creates_message", False))
            for k, a in ACTIONS.items()]


def run_action(user, key, force=False):
    """Run one certification action against the REAL production path. Never raises —
    returns a display dict {ok, summary, ...}."""
    action = ACTIONS.get(key)
    if not action:
        return {"ok": False, "summary": f"Unknown action: {key}"}
    try:
        return action["run"](user, force=force)
    except Exception as e:
        logger.warning("certification_console: action %s failed", key, exc_info=True)
        return {"ok": False, "summary": f"Error running {key}: {type(e).__name__}: {e}"}
