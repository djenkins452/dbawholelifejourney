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
    "get_consistency", "get_change_point", "get_ranked_entity", "get_comparison",
    "get_analysis", "get_entity", "get_user_truth", "get_foundational_health_facts",
    "get_execution_review", "search_history",
})

# Pre-decided PROGRESS/DRIFT verdict fields WLJ must NOT hand OpenAI as executive input
# (Blueprint §4 — the I.3→I.4 line). A momentum SCORE / band / pace label ("momentum 25",
# "behind pace", "slipping") IS the progress-vs-drift judgment OpenAI is being asked to form;
# handed one pre-decided, the model narrates it as its own verdict — and cannot substantiate
# it on challenge, because the collapsed number has no retrievable lineage (proven on the live
# runtime 2026-08-14: the flagship claimed "momentum scores low / drifting" for missions it
# never retrieved — the values came only from this orientation). The FACTS underneath
# (milestone %, target dates, completion counts, last activity) stay: OpenAI reasons from
# those and can re-retrieve them to defend the judgment.
_VERDICT_KEYS = frozenset({
    "momentum_score", "momentum_7d_avg", "momentum", "momentum_summary",
    "momentum_trend", "recommended_action", "strategic_summary",
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


def _sub_item_labels(meta):
    """The identifying sub-item NAMES a ranked entity carries (a workout's exercises, a
    meal's foods) — so Phase 2 grounds "which exercises/what was in it" in the real items."""
    if not isinstance(meta, dict):
        return []
    for key in ("exercises", "items"):
        seq = meta.get(key)
        if isinstance(seq, list) and seq:
            out = [str(x.get("name") or x.get("food_name") or "").strip()
                   for x in seq if isinstance(x, dict)]
            out = [x for x in out if x]
            if out:
                return out
    return []


# --- COMPOSED ENTITY FLATTENING -------------------------------------------------
# The canonical `CompleteEntity` dimensions. A by-name or by-type `get_entity` read
# returns composed entities, and BEFORE 2026-08-25 this renderer had no branch for
# either shape (`entity` / `entities`) — it fell through to the "top-level scalars"
# fallback and handed Phase 2 nothing but the record's NAME. Proven on the live
# runtime: a turn that correctly retrieved a personal medication schedule AND its
# authoritative product labelling rendered as exactly
#     [medicine] name: Mounjaro
#     [medication_reference] name: Mounjaro
# so Phase 2 replaced a grounded Phase-1 answer with generic prose — not because the
# model ignored the evidence, but because the evidence never reached it. Same class as
# the two lineage bugs recorded above (envelope-unwrap, ranked-entity), third shape.
_ENTITY_DIMENSIONS = ("definition", "plan", "standing", "performance", "extensions")
_ENTITY_VALUE_CAP = 4000      # one decisive text survives intact
_LIST_VALUE_CAP = 140         # a LIST of entities stays scannable
_MAX_ENTITY_FACTS = 60
_MAX_LIST_ENTITIES = 12
_TRUNCATION_MARK = "…[truncated]"


def _clip(value, cap, verbatim=False):
    """Bound one leaf value — but NEVER a block the producing surface marked VERBATIM.

    A cap is a guess about where the meaning is. That guess is provably unsafe for
    authoritative text: in the production reproducer the decisive sentence began at
    offset EXACTLY 1600 of a 3,852-character approved-labelling section, so a 1,600
    cap would have destroyed the one fact the answer depended on while appearing to
    fix the bug. A surface that marks content `verbatim` is asserting that the text
    IS the fact, so compaction must not edit it. Truncation is otherwise explicit —
    never silent — so the model can tell that something was cut.
    """
    s = str(value)
    if verbatim or len(s) <= cap:
        return s
    return s[:cap] + _TRUNCATION_MARK


def _leaf_facts(node, prefix, out, cap, limit, verbatim=False):
    """Flatten a composed entity dimension to `path: value` lines, KEEPING TEXT.

    The previous entity handling (`records`) kept only NUMERIC `performance` values,
    so every non-numeric deterministic fact — a schedule, a recorded instruction, an
    authoritative labelling text, a provenance identifier — was silently destroyed on
    the way to Phase 2. Facts are facts whether or not they are numbers.
    """
    if len(out) >= limit:
        return
    if isinstance(node, dict):
        # A dimension may declare its own contents verbatim; that flows to its leaves.
        verbatim = verbatim or bool(node.get("verbatim"))
        for k, v in node.items():
            if k == "verbatim":
                continue
            _leaf_facts(v, f"{prefix}.{k}" if prefix else str(k), out, cap, limit,
                        verbatim)
    elif isinstance(node, list):
        for i, v in enumerate(node[:6]):
            _leaf_facts(v, f"{prefix}[{i}]", out, cap, limit, verbatim)
    elif node not in (None, "", [], {}):
        out.append(f"{prefix}: {_clip(node, cap, verbatim)}")


def _facts_from_entity(ent, *, cap=_ENTITY_VALUE_CAP, limit=_MAX_ENTITY_FACTS):
    """One composed entity -> its deterministic facts, across every dimension.

    Identity and provenance are kept alongside the values so Phase 2 can tell WHOSE
    fact each one is — e.g. a person's own regimen record versus an impersonal
    authoritative product label. Losing that distinction is how a synthesis blurs two
    kinds of truth together.
    """
    out = []
    if not isinstance(ent, dict):
        return out
    ident = ent.get("identity") or ent.get("name")
    if ident:
        out.append(f"identity: {ident}")
    for key in ("kind", "status", "freshness", "confidence"):
        if ent.get(key):
            out.append(f"{key}: {ent[key]}")
    for dim in _ENTITY_DIMENSIONS:
        _leaf_facts(ent.get(dim), dim, out, cap, limit)
    return out[:limit]


def _facts_from_result(result):
    """Flatten ONE truth result to compact 'label: value unit (Δ change)' lines — every
    deterministic fact, none of the scaffolding/nesting. This keeps the Phase-2 prompt small
    (the A/B experiment showed ~9× reduction with grounding preserved), so the synthesis call
    is fast and never times out on payload size."""
    facts = []
    if not isinstance(result, dict):
        return facts
    # UNWRAP the canonical truth envelope: dispatch wraps every tool result via
    # `make_envelope`, which nests the ENTIRE payload under "value" (alongside freshness/
    # confidence/source/status). Without unwrapping, `_facts_from_result` read only the
    # envelope scaffolding and Phase 2 received NO real facts — it then fabricated entities/
    # numbers (proven 2026-08-14: the ranked+PR combo invented "squats/deadlifts"). If the
    # inner value is a scalar, that IS the fact.
    if ("value" in result and isinstance(result.get("source"), str)
            and ("freshness" in result or "status" in result)):
        inner = result.get("value")
        if isinstance(inner, dict):
            result = inner
        elif inner is not None:
            return [str(inner)]
        else:
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
            if (isinstance(v, (int, float, str)) and k not in ("enabled",)
                    and not str(k).endswith("basis") and k not in _VERDICT_KEYS):
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
    # RANKED ENTITY — `results[]` are the ranked ENTITIES (name + value + their own detail).
    # Without this Phase 2 saw only the ranked scalar totals and FABRICATED the entities (the
    # "which workouts/exercises had the most X" → invented "squats/deadlifts" class, 2026-08-14).
    unit = result.get("unit")
    for r in (result.get("results") or [])[:12]:
        if not isinstance(r, dict):
            continue
        line = (f"#{r.get('rank')} {r.get('name') or r.get('ref')}: "
                f"{r.get('value')}{(' ' + unit) if unit else ''}")
        if r.get("occurred_on"):
            line += f" ({r['occurred_on']})"
        sub_labels = _sub_item_labels(r.get("meta"))
        if sub_labels:
            line += " — " + ", ".join(sub_labels[:8])
        facts.append(line)
    # ENTITY RECORDS — analysis/entity `records[]` are the user's ACTUAL entities (a PR, a
    # workout): render each identity + its numeric performance so Phase 2 names REAL entities.
    recs = result.get("records")
    rec_list = (recs.get("records") if isinstance(recs, dict)
                else recs if isinstance(recs, list) else None)
    for e in (rec_list or [])[:15]:
        if not isinstance(e, dict):
            continue
        ident = e.get("identity") or (e.get("definition") or {}).get("name") or e.get("name")
        perf = e.get("performance") if isinstance(e.get("performance"), dict) else {}
        vals = "; ".join(f"{k} {v}" for k, v in perf.items()
                         if isinstance(v, (int, float)) and v is not None)
        if ident:
            facts.append(f"{ident}" + (f": {vals}" if vals else ""))
        # ...and the entity's NON-numeric deterministic facts, which the numeric-only
        # line above silently dropped (same defect class as the `entity` shapes).
        _leaf_facts({d: e.get(d) for d in _ENTITY_DIMENSIONS if e.get(d)},
                    ident or "record", facts, _LIST_VALUE_CAP, len(facts) + 14)
    # COMPOSED ENTITIES — the `get_entity` shapes. `entity` is a by-name retrieval,
    # `entities` a by-type listing. Neither had a branch here, so both collapsed to the
    # scalar fallback and reached Phase 2 as just the record's name.
    ent = result.get("entity")
    if isinstance(ent, dict):
        facts.extend(_facts_from_entity(ent))
    for e in (result.get("entities") or [])[:_MAX_LIST_ENTITIES]:
        if isinstance(e, dict):
            facts.extend(_facts_from_entity(e, cap=_LIST_VALUE_CAP, limit=14))
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


def _strip_verdicts(obj):
    """Recursively drop the pre-decided progress/drift VERDICT fields (`_VERDICT_KEYS`),
    keeping every FACT. A momentum score/band/pace label is the very judgment OpenAI must
    form (I.4); the milestone %, target dates and counts underneath it are the facts it
    reasons from and can substantiate."""
    if isinstance(obj, dict):
        return {k: _strip_verdicts(v) for k, v in obj.items() if k not in _VERDICT_KEYS}
    if isinstance(obj, list):
        return [_strip_verdicts(v) for v in obj]
    return obj


# ── Phase-1 → Phase-2 context continuity ──────────────────────────────────────
# Phase 2 used to RECONSTRUCT a partial prompt from a hand-listed subset of the envelope,
# so every new context type had to remember to opt in — and anything that forgot simply
# vanished at the boundary. Measured before this change: 5 of 8 envelope keys were lost,
# including the user's own persona and any pending confirmation.
#
# It now carries the WHOLE current situation forward, and an omission must be DECLARED
# here with its reason. `test_phase2_context_continuity` fails if a key disappears
# silently, so the default for anything new is "it survives".
INTENTIONALLY_OMITTED = {
    "deterministic_understanding": (
        "WLJ's own heuristic assessment (biggest_risk, primary_challenge, momentum band, "
        "strategic summary). Handed a pre-decided verdict the model narrates it as its own "
        "with no evidence lineage to defend on challenge — the whole judgment is the "
        "model's to form from evidence + facts (Constitution I.3->I.4)."),
    "interview": (
        "Getting to Know You orchestration state. Phase 2 is an executive synthesis of a "
        "question, never an interview turn; the interview never reaches synthesis."),
}

# Per-key budgets keep the synthesis prompt small and fast. A key with no entry gets the
# default; nothing is dropped for lack of a budget.
_ORIENTATION_BUDGETS = {
    "missions": 800,
    "current_action": 400,
    "personal_truth": 900,
    "execution_state": 500,
    "current_context": 400,
    "conversation_state": 500,
    "pending_confirmations": 400,
    "ai_relationship": 400,
}
_ORIENTATION_DEFAULT_BUDGET = 300


def build_orientation(standing_context):
    """The standing ORIENTATION for Phase 2 — FACTS ONLY, and now the WHOLE situation.

    Carries every envelope key except those declared in `INTENTIONALLY_OMITTED`, with
    verdicts stripped: WLJ states what IS, the model decides what it MEANS. Capped per key
    so the synthesis prompt stays small.
    """
    if not isinstance(standing_context, dict):
        return "{}"
    keep = {}
    for key, value in standing_context.items():
        if key in INTENTIONALLY_OMITTED or not value:
            continue
        budget = _ORIENTATION_BUDGETS.get(key, _ORIENTATION_DEFAULT_BUDGET)
        keep[key] = _compact(_strip_verdicts(value), budget)
    return json.dumps(keep, default=str, ensure_ascii=False)


def orientation_coverage(standing_context):
    """What survived the boundary, what was declared away, and what leaked. Used by the
    continuity contract and available for instrumentation. Read-only."""
    present = {k for k, v in (standing_context or {}).items() if v}
    omitted = present & set(INTENTIONALLY_OMITTED)
    try:
        carried = set(json.loads(build_orientation(standing_context)))
    except Exception:
        carried = set()
    return {
        "phase1_keys": sorted(present),
        "carried": sorted(carried),
        "intentionally_omitted": sorted(omitted),
        "silently_lost": sorted(present - carried - omitted),
    }


SYNTHESIS_SYSTEM = (
    "You are Danny's Chief of Staff. This is the SECOND phase of ONE task: you have "
    "ALREADY investigated and gathered the deterministic WLJ evidence below. Do NOT ask "
    "for more, do NOT say you will look something up, do NOT mention tools or retrieval — "
    "just give Danny the executive read.\n\n"
    "ACCOUNT FOR HIS CIRCUMSTANCES BEFORE YOU JUDGE HIS NUMBERS. If he has told you "
    "something this conversation that explains what the evidence shows — a recovery, a "
    "disruption, a deliberate change of plan, anything WLJ holds no record of — that "
    "context is part of the truth of his situation, and a verdict that ignores it is "
    "simply wrong. The measurements stay canonical: do not revise a number because of "
    "something he said. But WHAT THE NUMBERS MEAN depends on what is going on in his "
    "life, and telling someone their activity has dropped when they have just explained "
    "why is not executive judgment — it is not listening.\n\n"
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
    "insufficient to support a claim, say so plainly. The STANDING ORIENTATION gives you only "
    "FACTS about WHO Danny is and WHAT he is working toward — his missions and their milestone "
    "progress, his personal truth, and the deterministic next action. It contains NO assessment "
    "of how he is doing: whether he is progressing or drifting, what his biggest risk is, what "
    "to do first — all of that is YOURS to judge, and ONLY from the gathered EVIDENCE plus those "
    "facts. Distinguish what WLJ measured (a fact/number) from what you conclude it means (your "
    "judgment); never present a bare score or label as if it were the verdict, and if a claim "
    "about how he is doing is not supported by the gathered evidence, say so rather than assert it."
)


# Phase 2 is a SINGLE, hard-bounded call. It deliberately bypasses AIService._call_api's
# retry loop + rate-limit circuit breaker so it can NEVER storm retries or hang a turn: one
# attempt, a strict wall-clock timeout, and on ANY error/timeout return "" so the caller keeps
# the grounded Phase-1 answer. (A retry storm here was making broad turns run >260s.)
SYNTHESIS_TIMEOUT_SECONDS = 35

# What the person told us in THIS conversation, bounded. Phase 2 is deliberately a small,
# self-contained prompt, so this is a slice — enough to carry circumstance, not a transcript.
_CONTEXT_TURNS = 8
_CONTEXT_CHARS_PER_TURN = 400
_CONTEXT_CHARS_TOTAL = 2000


def render_conversation_context(conversation_history):
    """The circumstances the person has stated this conversation, as CONTEXT — never as
    evidence.

    Phase 2 used to receive only the question, the standing orientation and the retrieved
    evidence; `conversation_history` was accepted and then dropped on the floor. Anything
    the user had just explained about their situation — something WLJ holds no record of,
    because it is circumstance rather than a measurement — was invisible at exactly the
    moment a judgment was formed. That is how a person could say they were injured and be
    told minutes later that their declining activity showed poor engagement.

    Bounded and newest-last so the freshest statements survive truncation.
    """
    rows = [r for r in (conversation_history or [])
            if isinstance(r, dict) and (r.get("content") or "").strip()]
    if not rows:
        return ""
    out, used = [], 0
    for row in reversed(rows[-_CONTEXT_TURNS:]):
        who = "Danny" if row.get("role") == "user" else "You"
        text = " ".join((row.get("content") or "").split())[:_CONTEXT_CHARS_PER_TURN]
        line = f"{who}: {text}"
        if used + len(line) > _CONTEXT_CHARS_TOTAL:
            break
        out.append(line)
        used += len(line)
    return "\n".join(reversed(out))


def run_executive_synthesis(ai_service, *, message, evidence, standing_context,
                            conversation_history=None, user=None, temperature=0.5,
                            metrics=None):
    """Run the bounded Phase-2 synthesis: ONE completion, NO tools, NO retries, over the
    already-gathered evidence + standing orientation. The prompt is self-contained (question +
    evidence + orientation), so conversation history is not needed here — cross-turn continuity
    is preserved because the FINAL answer persists as the turn and the NEXT turn re-enters
    Phase 1 with full history. Returns the answer, or "" on any failure/timeout (the caller
    keeps the grounded Phase-1 answer as the justified safe fallback). Never raises.

    `metrics`: an optional caller-owned dict filled with structural counters for Stage-0
    telemetry — how large the rendered evidence was and how many values the renderer had to
    truncate to fit it. Truncation is worth counting because a cap once landed exactly on
    the decisive sentence of a retrieval, and Phase 2 sees ONLY what render_evidence
    emits. Counts only; the evidence itself never leaves this function."""
    import time as _time
    client = getattr(ai_service, "client", None)
    if client is None:
        return ""
    try:
        evidence_block = render_evidence(evidence)
        if metrics is not None:
            metrics["evidence_chars"] = len(evidence_block)
            metrics["truncations"] = evidence_block.count(_TRUNCATION_MARK)
        orientation = build_orientation(standing_context)
        recent = render_conversation_context(conversation_history)
        context_block = (
            f"WHAT DANNY HAS TOLD YOU IN THIS CONVERSATION (his circumstances — CONTEXT, "
            f"not measurements). WLJ may hold no record of any of it, and that does not "
            f"make it untrue. If something here explains what the evidence shows, your "
            f"judgment MUST account for it rather than reading the numbers as if he had "
            f"said nothing:\n{recent}\n\n"
        ) if recent else ""
        user_prompt = (
            f"Danny's question:\n{message}\n\n"
            f"STANDING ORIENTATION (who he is / what he is working toward — NOT current "
            f"evidence):\n{orientation}\n\n"
            f"{context_block}"
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
        # Cost ledger: Phase-2 synthesis is a SEPARATE billable provider request that was
        # previously untracked. Tag source=executive_synthesis; traffic_class inherits the
        # ambient context (a certification/proactive turn's synthesis stays that class).
        try:
            from apps.ai.llm_accounting import (record_llm_event_from_response,
                                                SOURCE_EXECUTIVE_SYNTHESIS)
            record_llm_event_from_response(
                resp, model=getattr(ai_service, "model", None), user=user, success=True,
                latency_ms=int((_time.monotonic() - t0) * 1000),
                endpoint='model_interface_synthesis', source=SOURCE_EXECUTIVE_SYNTHESIS,
            )
        except Exception:
            pass
        answer = (resp.choices[0].message.content or "").strip()
        logger.info("MI_SYNTHESIS_CALL ok=%s dur=%.1fs evidence_chars=%d",
                    bool(answer), _time.monotonic() - t0, len(evidence_block))
        return answer
    except Exception:
        logger.warning("executive synthesis failed/timed out — keeping phase-1 answer",
                       exc_info=True)
        # Record the failed/timed-out synthesis honestly.
        try:
            from apps.ai.llm_accounting import (record_llm_event,
                                                SOURCE_EXECUTIVE_SYNTHESIS)
            record_llm_event(
                model=getattr(ai_service, "model", None), user=user, success=False,
                endpoint='model_interface_synthesis', source=SOURCE_EXECUTIVE_SYNTHESIS,
            )
        except Exception:
            pass
        return ""
