"""
Beth narration contract for HealthBriefing (Phase 1A · C14).

Two layers:

1. `HEALTH_BRIEFING_NARRATION_ADDENDUM_BASE` — the static, universal
   narration contract. It is registered once via
   `register_health_briefing_addendum()` and concatenated into Beth's
   system prompt by the C15 prompt assembler. It carries the rules
   that never change per turn: role, MUST / MAY / MUST NOT.

2. `build_briefing_addendum(briefing)` — produces the dynamic
   per-turn addendum that varies with the specific briefing the
   composer just emitted. It surfaces:
     - briefing identity (for replay traceability)
     - overall status / confidence / risk_level
     - acute alerts (must mention first)
     - insufficient_data_flag (must say so)
     - positive_recognition_required (must name a driver)
     - the pre-ranked driver / watch_item lists (do not re-rank)
     - inputs_missing (do not comment on)
     - insulin gate when insulin_trend_30d is None

Architecture commitments (Phase 0 lock):

* Beth is a narrator, not an analyst. The HealthBriefing is the
  analysis; Beth's job is communication.
* Beth never receives raw GlucoseEntry / LabResult / IntakeLog rows.
* The two channels (alerts feed vs briefing) are independent — Beth's
  briefing addendum does not quote alerts-feed text.
* Wave 5 invariant for C14: this module is NOT yet imported by
  `personal_assistant.py` or `cos_context.py`. C15 wires registration.
  C14 only delivers the contract + dynamic builder + tests.

This module is pure (no DB queries, no Django imports beyond standard
typing). Imports the C1 contract dataclasses for type annotations only.
"""

from __future__ import annotations

import logging
from typing import Dict, List, Optional

from apps.core.health_briefing.contract import HealthBriefing


logger = logging.getLogger(__name__)


# Stable name for the registration map. Bible Journey's faith
# addendum should use a distinct name (e.g., "faith_journey").
ADDENDUM_NAME: str = "health_briefing"


# ── Static base addendum ────────────────────────────────────────────


HEALTH_BRIEFING_NARRATION_ADDENDUM_BASE: str = """\
HEALTH BRIEFING NARRATION CONTRACT

You may receive a HealthBriefing data structure describing the user's
metabolic state. When you do, narrate from it under the contract below.
The HealthBriefing has already done the analysis. Your job is to
communicate it warmly, accurately, and concisely.

ROLE
You are a narrator of deterministic health intelligence, not an analyst.
The composer has already weighed evidence, ranked drivers, classified
risk, and decided what matters. Speak from that, not around it.

YOU MUST
1. Treat overall_status, overall_confidence, and risk_level as
   authoritative. Do not contradict them.
2. When acute_alerts is non-empty, surface the acute in your FIRST
   sentence. Quote the specific value (e.g., "48 mg/dL") if it appears
   in the alert's `why` field. Recommend the concrete corrective
   action when the alert calls for one (fast-acting carb for low,
   hydration / recheck for high).
3. When positive_recognition_required is true, name at least one item
   from top_positive_drivers specifically. Generic encouragement does
   not count.
4. When insufficient_data_flag is true, explicitly say there isn't
   enough data to characterize the situation. Do not fabricate
   trajectory, status, or risk language.
5. Use only data present in inputs_used. Do not invent numbers, do not
   make claims about fields listed in inputs_missing.
6. Use association language ("when sleep is this short, glucose often
   runs higher") — never causal language ("your short sleep caused
   this").
7. If insulin_trend_30d is null in the briefing, you have NO insulin
   observation. Do not mention insulin at all. Absence of data is not
   the same as "insulin is zero."
8. When staleness_flags includes a field, acknowledge that the most
   recent reading for that field is not current — do not narrate from
   a stale value as if it were live.

YOU MAY
- Personalize tone to the user and the situation.
- Order delivery (e.g., open with a positive driver) without re-ranking
  the lists themselves.
- Connect to other CoS context (calendar, goals, life events, travel)
  when relevant — but do not invent context the briefing doesn't
  support.
- Suggest reframings of action items without changing the underlying
  items.
- Adjust verbosity: brief for stable weeks, balanced for mixed states,
  focused and urgent for acute alerts.
- Recognize effort (consistency, adherence, workouts) alongside metric
  outcomes when the briefing supports it.

YOU MUST NOT
- Re-rank top_positive_drivers or watch_items. The composer already
  ranked them; trust the order.
- Compute your own trajectory ("your glucose is probably going to…").
  PRIE will project trajectories deterministically in a future phase.
- Claim causality. "Likely related to" / "often associated with" are
  fine; "caused by" / "because of" are not.
- Invent metabolic, glycemic, or clinical terminology not present in
  the briefing.
- Cite numeric values that do not appear in inputs_used.
- Override risk_level. If the briefing says "low", you may not say
  "concerning."
- Manufacture concerns when the briefing is stable. Do not look for
  something to warn about.
- Quote text from the alerts feed in a briefing-channel response.
  Two channels, two surfaces.

TONE BAR
The briefing aims to feel wise, balanced, encouraging, truthful,
non-alarmist, and high-trust. A response that is structurally correct
but feels alarmist, dismissive, or robotic fails the contract.

CAVEATS
You can always say:
- "I don't have insulin data" (when insulin_trend_30d is null).
- "I haven't seen a recent glucose reading" (when latest_glucose is
  flagged stale).
- "Not enough data to say yet" (when a single fact is insufficient).
- "Worth mentioning to your provider" (when a trend is rising but
  cause is unknown).
"""


# ── Dynamic per-briefing addendum builder ───────────────────────────


def _format_acute_alerts(briefing: HealthBriefing) -> List[str]:
    lines: List[str] = []
    if not briefing.acute_alerts:
        return lines
    lines.append("ACUTE — surface FIRST in your response:")
    for alert in briefing.acute_alerts:
        lines.append(
            f"  [{alert.severity.value}] {alert.label} — {alert.why}"
        )
    return lines


def _format_positive_recognition(briefing: HealthBriefing) -> List[str]:
    if not briefing.positive_recognition_required:
        return []
    if not briefing.top_positive_drivers:
        return []
    names = "; ".join(d.label for d in briefing.top_positive_drivers)
    return [
        f"POSITIVE RECOGNITION REQUIRED — name at least one of: {names}",
    ]


def _format_drivers(briefing: HealthBriefing) -> List[str]:
    lines: List[str] = []
    if briefing.top_positive_drivers:
        lines.append("Pre-ranked positive drivers (do NOT re-rank):")
        for d in briefing.top_positive_drivers:
            score = f"+{int(d.score)}" if d.score > 0 else f"{int(d.score)}"
            lines.append(f"  + {d.label} ({score}) — {d.why}")
    if briefing.watch_items:
        lines.append("Pre-ranked watch items (do NOT re-rank):")
        for d in briefing.watch_items:
            lines.append(f"  - {d.label} ({int(d.score)}) — {d.why}")
    return lines


def _format_inputs_guidance(briefing: HealthBriefing) -> List[str]:
    lines: List[str] = []
    # Insulin gate: explicit silence when no insulin observation.
    if briefing.insulin_trend_30d is None:
        lines.append(
            "No insulin observation in this briefing — do NOT mention "
            "insulin in your response."
        )
    if briefing.inputs_missing:
        skip = ", ".join(sorted(briefing.inputs_missing)[:8])
        lines.append(
            f"No data on: {skip}. Do NOT make claims about these fields."
        )
    if briefing.staleness_flags:
        stale = ", ".join(sorted(briefing.staleness_flags))
        lines.append(
            f"Stale data flagged: {stale}. Acknowledge the gap; do not "
            "narrate from these as current."
        )
    return lines


def build_briefing_addendum_from_payload(payload: Dict) -> str:
    """Dict-payload variant of `build_briefing_addendum`.

    The C15 wiring reads HealthBriefing data from a
    `HealthBriefingSnapshot.payload` JSON dict (serialized by
    `apps.core.health_briefing.composer._serialize_briefing`), not
    from a reconstructed HealthBriefing dataclass. This helper walks
    the dict directly so we never round-trip through the dataclass's
    `__post_init__` validators (which could reject older snapshots
    after a contract change).

    Produces the same shape of output as `build_briefing_addendum`.
    Kept side-by-side with the dataclass variant so the two never
    drift — every change here must mirror the dataclass version.
    """
    parts: List[str] = []

    briefing_id = str(payload.get("briefing_id") or "")
    overall_status = str(payload.get("overall_status") or "stable")
    overall_confidence = payload.get("overall_confidence", 0.0)
    risk_level = str(payload.get("risk_level") or "none")

    parts.append(f"[briefing_id={briefing_id[:12]}…]")
    parts.append(f"Headline: {overall_status} (confidence {overall_confidence})")
    parts.append(f"Risk: {risk_level}")

    if payload.get("insufficient_data_flag"):
        parts.append(
            "INSUFFICIENT DATA — explicitly say so. Do not fabricate "
            "trajectory, status, or risk."
        )

    acute_alerts = payload.get("acute_alerts") or []
    if acute_alerts:
        parts.append("ACUTE — surface FIRST in your response:")
        for alert in acute_alerts:
            sev = str(alert.get("severity") or "high")
            label = str(alert.get("label") or "Acute event")
            why = str(alert.get("why") or "")
            parts.append(f"  [{sev}] {label} — {why}")

    top_drivers = payload.get("top_positive_drivers") or []
    watch_items = payload.get("watch_items") or []
    if payload.get("positive_recognition_required") and top_drivers:
        names = "; ".join(str(d.get("label") or "") for d in top_drivers)
        parts.append(
            f"POSITIVE RECOGNITION REQUIRED — name at least one of: {names}"
        )

    if top_drivers:
        parts.append("Pre-ranked positive drivers (do NOT re-rank):")
        for d in top_drivers:
            score = d.get("score") or 0
            try:
                score_int = int(score)
            except (TypeError, ValueError):
                score_int = 0
            score_str = f"+{score_int}" if score_int > 0 else f"{score_int}"
            parts.append(
                f"  + {d.get('label')} ({score_str}) — {d.get('why', '')}"
            )
    if watch_items:
        parts.append("Pre-ranked watch items (do NOT re-rank):")
        for d in watch_items:
            score = d.get("score") or 0
            try:
                score_int = int(score)
            except (TypeError, ValueError):
                score_int = 0
            parts.append(
                f"  - {d.get('label')} ({score_int}) — {d.get('why', '')}"
            )

    if payload.get("insulin_trend_30d") is None:
        parts.append(
            "No insulin observation in this briefing — do NOT mention "
            "insulin in your response."
        )

    inputs_missing = payload.get("inputs_missing") or []
    if inputs_missing:
        skip = ", ".join(sorted(inputs_missing)[:8])
        parts.append(
            f"No data on: {skip}. Do NOT make claims about these fields."
        )

    staleness_flags = payload.get("staleness_flags") or []
    if staleness_flags:
        stale = ", ".join(sorted(staleness_flags))
        parts.append(
            f"Stale data flagged: {stale}. Acknowledge the gap; do not "
            "narrate from these as current."
        )

    return "\n".join(parts)


def build_briefing_addendum(briefing: HealthBriefing) -> str:
    """Produce the per-turn dynamic addendum for a specific briefing.

    Returned text is appended to the static base addendum at CoS turn
    assembly time (C15 will do that). The format is deterministic so
    replay reproduces identical prompts given identical briefings.

    Layout:
        [briefing_id=…]
        Headline: <status> (confidence <c>)
        Risk: <risk_level>
        (acute block, if any)
        (insufficient-data flag, if set)
        (positive-recognition requirement, if set)
        (driver lists, pre-ranked)
        (inputs guidance: insulin gate, missing, stale)
    """
    parts: List[str] = []

    parts.append(f"[briefing_id={briefing.briefing_id[:12]}…]")
    parts.append(
        f"Headline: {briefing.overall_status.value} "
        f"(confidence {briefing.overall_confidence})"
    )
    parts.append(f"Risk: {briefing.risk_level.value}")

    if briefing.insufficient_data_flag:
        parts.append(
            "INSUFFICIENT DATA — explicitly say so. Do not fabricate "
            "trajectory, status, or risk."
        )

    parts.extend(_format_acute_alerts(briefing))
    parts.extend(_format_positive_recognition(briefing))
    parts.extend(_format_drivers(briefing))
    parts.extend(_format_inputs_guidance(briefing))

    return "\n".join(parts)


# ── Registration helper (for the future C15 prompt assembler) ──────


_REGISTERED_ADDENDA: Dict[str, str] = {}


def register_health_briefing_addendum() -> None:
    """Register the static base addendum under the canonical name.

    The C15 prompt assembler will iterate registered addenda from all
    workstreams (health_briefing here, faith_journey from the Bible
    Journey workstream, etc.) and concatenate them into Beth's system
    prompt. C14 only registers the contract; no assembly happens yet.
    """
    _REGISTERED_ADDENDA[ADDENDUM_NAME] = HEALTH_BRIEFING_NARRATION_ADDENDUM_BASE
    logger.info(
        "[HEALTH_BRIEFING] registered narration addendum name=%s len=%d",
        ADDENDUM_NAME, len(HEALTH_BRIEFING_NARRATION_ADDENDUM_BASE),
    )


def get_registered_addenda() -> Dict[str, str]:
    """Snapshot of registered base addenda (name → text). Used by the
    C15 prompt assembler. Read-only; returns a copy."""
    return dict(_REGISTERED_ADDENDA)


def unregister_health_briefing_addendum() -> None:
    """Test-only helper to undo registration between test cases."""
    _REGISTERED_ADDENDA.pop(ADDENDUM_NAME, None)


def is_addendum_registered() -> bool:
    return ADDENDUM_NAME in _REGISTERED_ADDENDA
