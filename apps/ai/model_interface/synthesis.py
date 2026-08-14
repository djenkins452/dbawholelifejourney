# ==============================================================================
# File: apps/ai/model_interface/synthesis.py
# Project: Whole Life Journey - Django 5.x Personal Wellness/Journaling App
# Description: Bounded Executive Synthesis Phase (Phase 2 of one CoS task)
# Owner: Danny Jenkins (admin@wholelifejourney.com)
# Created: 2026-08-13
# ==============================================================================
"""
Bounded Executive Synthesis — the SAME OpenAI Chief of Staff, second phase.

Phase 1 (the tool loop) INVESTIGATES and gathers deterministic WLJ evidence — the
model decides what the question means, which truth is relevant, and when it has
enough. Phase 2 does NOT retrieve more: it steps back from the gathered evidence
and produces the final executive judgment.

This is not a new authority, engine, or second assistant, and it is NOT
judge-the-judge (Phase 2 never sees Phase 1's prose — only the EVIDENCE Phase 1
gathered). It runs only for turns that genuinely required cross-evidence
executive synthesis (≥2 independent substantive truth surfaces) — a pure runtime
signal, never a phrase-list classifier. Narrow lookups stay single-phase.
"""

import json
import logging

logger = logging.getLogger(__name__)

# Result scaffolding that is instruction/metadata, NOT reasoning evidence — stripped
# from the evidence handed to Phase 2 (the deterministic FACTS are preserved).
_SCAFFOLD_KEYS = frozenset({
    "scope", "note", "schema_version", "generated_at", "granularity",
    "subjects_covered", "subjects_with_data", "has_state", "evidence",
    "status", "subject", "state_the_period",
})

_READ_TOOLS = frozenset({
    "get_domain_state", "get_history", "get_readings", "get_event_frequency",
    "get_comparison", "get_analysis", "get_entity", "get_user_truth",
    "get_foundational_health_facts", "get_execution_review", "search_history",
})


def is_substantive_truth(name, result):
    """A truth read that returned real data (not empty/error/unsupported)."""
    if name not in _READ_TOOLS or not isinstance(result, dict):
        return False
    if result.get("holds_data") is True:
        return True
    status = str(result.get("status") or "").lower()
    return status in ("ready", "ok", "rich")


def synthesis_eligible(evidence):
    """Smallest general eligibility boundary, from RUNTIME behaviour only: the turn
    drew on ≥2 INDEPENDENT substantive truth surfaces (distinct tool+domain+subject),
    so the answer requires cross-evidence executive judgment. No phrase list, no fixed
    domain set — a narrow lookup (0–1 surfaces) stays single-phase."""
    surfaces = set()
    for e in evidence or []:
        a = e.get("args") or {}
        dom = a.get("domain") or a.get("section") or ""
        sub = a.get("subject") or a.get("metric") or a.get("entity_type") or ""
        surfaces.add((e.get("tool"), str(dom), str(sub)))
    return len(surfaces) >= 2


def _facts_from_result(result):
    """Flatten ONE truth result to compact 'label: value unit (Δ change)' lines — every
    deterministic fact, none of the scaffolding/nesting. This keeps the Phase-2 prompt small
    (the A/B experiment showed ~9× reduction with grounding preserved), so the synthesis call
    is fast and never times out on payload size."""
    facts = []
    if not isinstance(result, dict):
        return facts
    for grp in (result.get("concepts") or {}).values():
        if not isinstance(grp, dict):
            continue
        for m in (grp.get("members") or {}).values():
            if isinstance(m, dict) and m.get("value") is not None:
                s = f"{m.get('label')}: {m.get('value')}{(' ' + m['unit']) if m.get('unit') else ''}"
                if m.get("change") not in (None, ""):
                    s += f" (Δ {m['change']})"
                facts.append(s)
    st = result.get("state")
    if isinstance(st, dict):
        for k, v in st.items():
            if isinstance(v, (int, float, str)) and k not in ("enabled",) and not str(k).endswith("basis"):
                facts.append(f"{k}: {v}")
    subs = result.get("subjects")
    if isinstance(subs, dict):
        for name, s in subs.items():
            if not isinstance(s, dict) or not s.get("present"):
                continue
            ch = s.get("change") or {}
            if ch:
                facts.append(f"{name}: {ch.get('first')}→{ch.get('last')} "
                             f"(Δ {ch.get('delta')}, {ch.get('direction')})")
            elif s.get("average") is not None:
                facts.append(f"{name}: avg {s.get('average')} {s.get('unit', '')}")
    # Fallback for non-analysis truth shapes: keep top-level scalar facts.
    if not facts:
        for k, v in result.items():
            if k in _SCAFFOLD_KEYS or k in ("domain", "window"):
                continue
            if isinstance(v, (int, float, str, bool)):
                facts.append(f"{k}: {v}")
    return facts


def render_evidence(evidence):
    """Consolidate the gathered evidence into ONE pooled block of COMPACT flat facts (tagged
    by what was retrieved), scaffolding + nesting removed. Pooled — NOT one section per tool —
    because the controlled experiment showed a per-tool partition invites a per-tool report.
    The Phase-1→Phase-2 handoff of already-gathered truth; small so synthesis stays fast."""
    blocks = []
    for e in evidence or []:
        a = e.get("args") or {}
        dom = a.get("domain") or a.get("section") or e.get("tool", "")
        sub = a.get("subject") or a.get("metric")
        label = f"{dom}" + (f".{sub}" if sub and sub != "overall" else "")
        facts = _facts_from_result(e.get("result") or {})
        if facts:
            blocks.append(f"[{label}] " + "; ".join(str(f) for f in facts))
    return "\n".join(blocks)


def _compact(v, limit=1200):
    s = json.dumps(v, default=str, ensure_ascii=False)
    return s if len(s) <= limit else s[:limit] + "…"


def build_orientation(standing_context):
    """The standing ORIENTATION for Phase 2 — small: who Danny is and what he is working
    toward (missions, current action, a capped personal-truth summary) + a COMPACT read of
    the deterministic understanding (challenge/risk/goal-pace) as ORIENTATION ONLY. Its
    interpretive fields are WLJ's heuristic read, NOT current evidence (the prompt says so).
    Capped so the synthesis prompt stays small and fast."""
    if not isinstance(standing_context, dict):
        return "{}"
    keep = {}
    if standing_context.get("missions"):
        keep["missions"] = _compact(standing_context["missions"], 800)
    if standing_context.get("current_action"):
        keep["current_action"] = _compact(standing_context["current_action"], 400)
    if standing_context.get("personal_truth"):
        keep["personal_truth"] = _compact(standing_context["personal_truth"], 900)
    du = standing_context.get("deterministic_understanding")
    if isinstance(du, dict):
        keep["understanding_read"] = _compact(
            {k: du.get(k) for k in ("executive", "priority", "direction") if du.get(k)}, 900)
    return json.dumps(keep, default=str, ensure_ascii=False)


SYNTHESIS_SYSTEM = (
    "You are Danny's Chief of Staff. This is the SECOND phase of ONE task: you have "
    "ALREADY investigated and gathered the deterministic WLJ evidence below. Do NOT ask "
    "for more, do NOT say you will look something up, do NOT mention tools or retrieval — "
    "just give Danny the executive read.\n\n"
    "YOUR JOB: step back from the evidence and answer his question with a judgment. Lead "
    "with the ONE thing that most matters, stated as a verdict in your first sentence. "
    "Then, in flowing PROSE (usually three to six sentences), tell the through-line: how "
    "the pieces that matter relate, whether he is genuinely progressing or drifting toward "
    "what he says matters, and the single highest-leverage thing to do next — weaving in "
    "only the few numbers that make the point land. Prioritise. Explain WHY. Challenge him "
    "when the evidence warrants it. If only two things truly matter, say only those.\n\n"
    "STRUCTURE (critical): ONE synthesized judgment, NOT a report. Do NOT mirror the "
    "structure of the evidence — no section per domain, no 'Health: … Nutrition: … "
    "Finances: …' tour, no header named after a source you retrieved, and never open with "
    "'here's how you're doing across key areas'. The evidence SUPPORTS your judgment; it is "
    "not the structure of your answer. Reserve bullets for genuinely list-like requests, "
    "never for a broad assessment.\n\n"
    "GROUNDING (truth rule): every important claim MUST be supported by the DETERMINISTIC "
    "EVIDENCE provided (or valid WLJ-grounded evidence already in the conversation, the "
    "standing personal truth, or general world knowledge where relevant). NEVER invent a "
    "Danny-specific fact and never silently fill a gap — if the evidence is genuinely "
    "insufficient to support a claim, say so plainly. The STANDING ORIENTATION tells you "
    "WHO Danny is and WHAT he is working toward (goals, missions, priorities); its "
    "interpretive fields (biggest risk, primary challenge, patterns-as-meaning) are WLJ's "
    "HEURISTIC read — orientation, NOT current evidence and NOT your judgment. The gathered "
    "EVIDENCE tells you HOW he is actually doing right now; base the current judgment on it."
)


# Phase 2 is a SINGLE, hard-bounded call. It deliberately bypasses AIService._call_api's
# retry loop + rate-limit circuit breaker so it can NEVER storm retries or hang a turn: one
# attempt, a strict wall-clock timeout, and on ANY error/timeout return "" so the caller keeps
# the grounded Phase-1 answer. (A retry storm here was making broad turns run >260s.)
SYNTHESIS_TIMEOUT_SECONDS = 35


def run_executive_synthesis(ai_service, *, message, evidence, standing_context,
                            conversation_history=None, user=None, temperature=0.5):
    """Run the bounded Phase-2 synthesis: ONE completion, NO tools, NO retries, over the
    already-gathered evidence + standing orientation. The prompt is self-contained (question +
    evidence + orientation), so conversation history is not needed here — cross-turn continuity
    is preserved because the FINAL answer persists as the turn and the NEXT turn re-enters
    Phase 1 with full history. Returns the answer, or "" on any failure/timeout (the caller
    keeps the grounded Phase-1 answer as the justified safe fallback). Never raises."""
    import time as _time
    client = getattr(ai_service, "client", None)
    if client is None:
        return ""
    try:
        evidence_block = render_evidence(evidence)
        orientation = build_orientation(standing_context)
        user_prompt = (
            f"Danny's question:\n{message}\n\n"
            f"STANDING ORIENTATION (who he is / what he is working toward — NOT current "
            f"evidence):\n{orientation}\n\n"
            f"DETERMINISTIC WLJ EVIDENCE you gathered this turn (ground every important claim "
            f"in THIS; do not invent; if it is insufficient for a claim, say so):\n"
            f"{evidence_block}"
        )
        t0 = _time.monotonic()
        resp = client.chat.completions.create(
            model=getattr(ai_service, "model", None),
            messages=[{"role": "system", "content": SYNTHESIS_SYSTEM},
                      {"role": "user", "content": user_prompt}],
            temperature=temperature, max_tokens=650,
            timeout=SYNTHESIS_TIMEOUT_SECONDS,
        )
        answer = (resp.choices[0].message.content or "").strip()
        logger.info("MI_SYNTHESIS_CALL ok=%s dur=%.1fs evidence_chars=%d",
                    bool(answer), _time.monotonic() - t0, len(evidence_block))
        return answer
    except Exception:
        logger.warning("executive synthesis failed/timed out — keeping phase-1 answer",
                       exc_info=True)
        return ""
