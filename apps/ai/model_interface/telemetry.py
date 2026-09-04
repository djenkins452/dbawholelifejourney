# ==============================================================================
# File: apps/ai/model_interface/telemetry.py
# Project: Whole Life Journey - Django 5.x Personal Wellness/Journaling App
# Description: Privacy-safe structural measurement of a Chief-of-Staff turn
# Owner: Danny Jenkins (admin@wholelifejourney.com)
# Created: 2026-09-03
# ==============================================================================
"""How big is the prompt, what did it contain, and did any of it earn its place?

Stage 0 of the Cognitive Simplification migration. Three confident hypotheses about this
runtime have already been overturned by measurement, so the migration starts by making the
prompt measurable rather than by shortening it. Nothing here changes a turn; it only
records the shape of one.

WHAT IS RECORDED — sizes, counts, names, booleans and ratios:

  * prompt characters BY SECTION (constitution / current situation / structured context /
    grounding / completion reminder), and the constitution's own invariant-vs-guidance
    split from ``constitution_map``;
  * how many tools were EXPOSED, their combined schema size, the largest few by name, and
    which were actually CALLED — the gap between those two is the tool-pruning evidence;
  * tool-loop rounds and whether the loop hit its cap;
  * Phase-2 eligibility, whether Phase 2 ran, and whether its answer MATERIALLY differed
    from Phase 1 — measured as a length delta and a word-set overlap ratio;
  * context coverage and truncation counts.

WHAT IS NEVER RECORDED: conversation text, the user's message, the answer, Personal
Knowledge statements, health or finance values, raw prompts, evidence payloads, or any
free text derived from them. The word-overlap ratio is computed in memory and discarded —
only the number survives. Nothing in this module returns a string that came from the user.

The whole record is a small flat dict stored on the turn's existing ``response`` audit row,
so measurement costs one dictionary per turn and no extra query.
"""

import re

# --- what counts as a duplicated instruction ---------------------------------
# Six themes that the architecture review found restated across the constitution and the
# per-turn leads (142 mentions when first measured). These patterns are deliberately
# coarse: the number is a TREND to drive down, not a precise linguistic claim.
_THEMES = {
    "confirmation": re.compile(
        r"confirm|confirmation_id|resolve_pending_action", re.I),
    "persona_voice": re.compile(
        r"persona|voice|tone|chief of staff|relationship style", re.I),
    "active_subject": re.compile(
        r"active subject|what the conversation is about|follow-up|short reply", re.I),
    "retrieve_never_invent": re.compile(
        r"never invent|retrieve|call a truth tool|fabricat", re.I),
    "grounding": re.compile(
        r"grounded|grounding|deterministic evidence|WLJ-grounded", re.I),
    "current_truth": re.compile(
        r"current truth|outranks history|mutable state", re.I),
}

_MAX_NAMED_TOOLS = 6
_MATERIAL_CHANGE_OVERLAP = 0.80   # below this, Phase 2 rewrote rather than polished


def duplicate_instruction_counts(text):
    """How many times each recurring instruction theme appears in one section."""
    if not text:
        return {}
    return {name: len(pattern.findall(text))
            for name, pattern in _THEMES.items()
            if pattern.search(text)}


def measure_sections(sections):
    """Characters per prompt section, plus the total. `sections` is name -> text."""
    sizes = {name: len(text or "") for name, text in sections.items()}
    sizes["total"] = sum(sizes.values())
    return sizes


def measure_tools(tools):
    """Exposed tool count, combined schema size, and the largest few BY NAME.

    Names are WLJ's own tool identifiers — configuration, not user content.
    """
    import json
    exposed, largest, total = 0, [], 0
    for tool in tools or []:
        try:
            name = ((tool.get("function") or {}).get("name")
                    or tool.get("name") or "?")
            size = len(json.dumps(tool, ensure_ascii=False))
        except Exception:      # a malformed schema must not break measurement
            continue
        exposed += 1
        total += size
        largest.append((name, size))
    largest.sort(key=lambda pair: -pair[1])
    return {
        "tools_exposed": exposed,
        "tool_schema_chars": total,
        "largest_tools": [{"name": n, "chars": c}
                          for n, c in largest[:_MAX_NAMED_TOOLS]],
    }


def _words(text):
    return set(re.findall(r"[a-z0-9]+", (text or "").lower()))


def answer_delta(before, after):
    """Did Phase 2 MATERIALLY change the answer, or merely re-word it?

    Word-set overlap (Jaccard) over the two answers. The sets are local and discarded;
    only the ratio and the lengths are returned. This is the measurement that decides
    whether Phase 2 is earning a second billable request per executive turn.
    """
    a, b = _words(before), _words(after)
    union = a | b
    overlap = round(len(a & b) / len(union), 3) if union else 1.0
    return {
        "phase1_chars": len(before or ""),
        "phase2_chars": len(after or ""),
        "word_overlap": overlap,
        "materially_changed": overlap < _MATERIAL_CHANGE_OVERLAP,
    }


def constitution_composition():
    """The Stage-1 invariant/guidance split, as numbers."""
    try:
        from apps.ai.model_interface import constitution_map as cmap
        return cmap.composition()
    except Exception:          # pragma: no cover - measurement is never load-bearing
        return {}


def _compact_coverage(coverage):
    """Phase-1 → Phase-2 context coverage as COUNTS, plus the one list that is actionable.

    `silently_lost` is named because a key disappearing across the phase boundary is a
    defect to chase (it once ate the persona and an injury). The keys that survived are
    only interesting as a number.
    """
    coverage = coverage or {}
    lost = list(coverage.get("silently_lost") or [])
    return {
        "phase1_keys": len(coverage.get("phase1_keys") or []),
        "carried": len(coverage.get("carried") or []),
        "intentionally_omitted": len(coverage.get("intentionally_omitted") or []),
        "silently_lost": lost[:8],
        "silently_lost_count": len(lost),
    }


# Current Context means WHAT IS TRUE RIGHT NOW. `attachments` is the only key under it
# that may describe a file, and only files sent with THIS message. Any other artifact-
# bearing key there is a prior turn wearing the present tense — the 2026-09-03 defect.
_CURRENT_CONTEXT_FILE_KEYS = ("attachments",)
_ARTIFACT_WORDS = ("artifact", "attachment", "upload", "image", "photo", "file")


def attachment_state(standing_context):
    """Is anything actually attached to this turn — and does the envelope say so honestly?

    The counters that would have caught the production failure in one line: nothing was
    attached, no subject was active, and yet the model was carrying a list of images.
    Counts and key NAMES only; no filename, no preview, no pixel ever reaches this record.
    """
    ctx = standing_context or {}
    current = ctx.get("current_context") or {}
    history = ctx.get("artifact_history") or {}
    subject = ((ctx.get("conversation_state") or {}).get("active_subject") or {})
    stray = sorted(
        key for key in current
        if key not in _CURRENT_CONTEXT_FILE_KEYS
        and any(word in key.lower() for word in _ARTIFACT_WORDS)
    )
    return {
        "attached_this_turn": len(current.get("attachments") or []),
        "historical_files": int(history.get("count") or 0),
        "history_is_marked_historical": history.get("status") == "historical",
        "active_subject_is_artifact": bool(subject.get("artifact")),
        # MUST stay empty. A name here means a past upload is being presented as present.
        "stray_current_context_file_keys": stray,
    }


_EXECUTION_BUCKETS = ("overdue", "due_now", "coming_up", "later", "completed")


def envelope_state(standing_context):
    """What the envelope actually handed the model, structurally.

    Three questions this answers that nothing else could. Which sections were present at
    all — a key name, not its contents. Whether `deterministic_understanding` was populated
    or still warming, which decides whether a whole-life read was even available. And HOW
    MANY items sat in each canonical execution bucket, which decides whether the day's
    outstanding work was in front of the model when it judged the day.

    On 2026-09-03 none of that was recoverable after the fact: "How did I do today?" came
    back as "strong momentum" and the counters could only say the envelope had eight keys.
    Counts and WLJ's own key names — never a title, a time, or a value.

    `verdict_keys_present` MUST stay empty. It reads the same `_VERDICT_KEYS` the strip
    uses, so it cannot drift from it, and it is the direct measurement of the Phase-1
    verdict boundary holding.
    """
    ctx = standing_context or {}
    understanding = ctx.get("deterministic_understanding")
    execution = ctx.get("execution_state") or {}
    try:
        from apps.ai.model_interface.synthesis import verdict_keys_in
        verdicts = verdict_keys_in(ctx)
    except Exception:      # pragma: no cover - measurement is never load-bearing
        verdicts = []
    return {
        "keys": sorted(k for k, v in ctx.items() if v),
        "understanding_status": (understanding.get("status")
                                 if isinstance(understanding, dict) else None),
        "execution_buckets": {
            name: len(execution.get(name) or []) for name in _EXECUTION_BUCKETS
        },
        "verdict_keys_present": verdicts,
    }


def build_turn_telemetry(*, sections, tools, tools_called, loop_metrics=None,
                         synthesis_eligible=False, synthesis_used=False,
                         answer_change=None, coverage=None, truncations=0,
                         evidence_chars=None, standing_context=None):
    """Assemble one turn's record. Bounded, flat, and free of user content."""
    loop_metrics = loop_metrics or {}
    called = [str(t)[:64] for t in (tools_called or [])]
    record = {
        "prompt_chars": measure_sections(sections),
        "constitution": constitution_composition(),
        "duplicate_instructions": {
            name: duplicate_instruction_counts(text)
            for name, text in sections.items() if text
        },
        "tools": measure_tools(tools),
        "tools_called": called[:12],
        "tools_called_count": len(called),
        "tools_called_distinct": len(set(called)),
        "loop": {
            "rounds_used": loop_metrics.get("rounds_used"),
            "max_rounds": loop_metrics.get("max_rounds"),
            "hit_round_cap": bool(loop_metrics.get("rounds_used")
                                  and loop_metrics.get("max_rounds")
                                  and loop_metrics["rounds_used"]
                                  > loop_metrics["max_rounds"]),
            "tool_output_chars": loop_metrics.get("tool_output_chars"),
            "history_trimmed": loop_metrics.get("history_trimmed"),
        },
        "phase2": {
            "eligible": bool(synthesis_eligible),
            "used": bool(synthesis_used),
            "evidence_chars": evidence_chars,
            **(answer_change or {}),
        },
        "coverage": _compact_coverage(coverage),
        "attachments": attachment_state(standing_context),
        "envelope": envelope_state(standing_context),
        "truncations": int(truncations or 0),
    }
    record["tools"]["tools_unused"] = max(
        0, record["tools"]["tools_exposed"] - record["tools_called_distinct"])
    return record
