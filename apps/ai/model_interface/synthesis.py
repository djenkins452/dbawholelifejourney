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


def _strip(obj):
    """Recursively drop scaffolding keys; keep every fact-bearing value."""
    if isinstance(obj, dict):
        return {k: _strip(v) for k, v in obj.items() if k not in _SCAFFOLD_KEYS}
    if isinstance(obj, list):
        return [_strip(v) for v in obj]
    return obj


def render_evidence(evidence):
    """Consolidate the gathered evidence into ONE pooled block (facts tagged by what
    was retrieved), scaffolding removed. Pooled — NOT re-partitioned as one section per
    tool — because the controlled experiment showed a per-tool partition invites a
    per-tool report. This is the Phase-1→Phase-2 handoff of already-gathered truth, not
    a new retrieval format."""
    blocks = []
    for e in evidence or []:
        a = e.get("args") or {}
        tag = e.get("tool", "")
        dom = a.get("domain") or a.get("section")
        sub = a.get("subject") or a.get("metric")
        label = tag + (f"[{dom}" + (f".{sub}" if sub else "") + "]" if dom else "")
        facts = _strip(e.get("result") or {})
        blocks.append(f"### {label}\n{json.dumps(facts, default=str, ensure_ascii=False)}")
    return "\n\n".join(blocks)


def build_orientation(standing_context):
    """The standing ORIENTATION for Phase 2: who Danny is and what he is working toward
    (missions, personal truth, current action) + the deterministic understanding as
    ORIENTATION ONLY. Its interpretive/verdict fields are WLJ's heuristic read, NOT
    current evidence — the synthesis prompt says so. Never the substance of the judgment."""
    if not isinstance(standing_context, dict):
        return "{}"
    keep = {}
    for k in ("missions", "personal_truth", "current_action", "deterministic_understanding",
              "current_context"):
        v = standing_context.get(k)
        if v:
            keep[k] = v
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


def run_executive_synthesis(ai_service, *, message, evidence, standing_context,
                            conversation_history=None, user=None, temperature=0.5):
    """Run the bounded Phase-2 synthesis: one completion, NO tools, over the already-gathered
    evidence + standing orientation. Returns the answer string, or "" on failure (the caller
    keeps the grounded Phase-1 answer as the justified safe fallback). Never raises."""
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
        answer = ai_service._call_api(
            SYNTHESIS_SYSTEM, user_prompt, max_tokens=650, temperature=temperature,
            endpoint="model_interface_synthesis", user=user,
            conversation_history=conversation_history,
        )
        return (answer or "").strip()
    except Exception:
        logger.warning("executive synthesis failed", exc_info=True)
        return ""
