"""
Deterministic Narration Boundary (Sprint 7).

The final rendering layer. Narration is a RENDERING of deterministic observations,
not an intelligence layer: it never creates facts, ranks, infers, diagnoses, or
recommends. Beth consumes narration objects only — she does not inspect raw
observations, evidence, or timelines (those stay below this boundary).

Fact preservation (Sprint 7D) is structural: a narration's ``summary`` is built
ONLY from the observation's own deterministic ``title``/``detail`` plus a fixed,
pre-vetted framing suffix that contains no facts, no causal claims, and no
recommendations. Tone is METADATA (how to say it), never injected words — so the
summary can never introduce new content. ``assert_safe`` verifies this at runtime.
"""

from dataclasses import dataclass

from apps.health.observations.core import SafetyClass


# ── Tone policy (Sprint 7C) — tone is determined by safety class ──────────────
TONE_BY_SAFETY = {
    SafetyClass.INFORMATIONAL: "matter_of_fact",
    SafetyClass.OBSERVATION: "supportive",
    SafetyClass.EDUCATIONAL: "contextual",
    SafetyClass.PHYSICIAN_DISCUSSION: "calm_encouraging",
}

# ── Narration type per observation type (Sprint 7B — different render rules) ──
NARRATION_TYPE = {
    "medication_stable": "calm_reassurance",
    "long_term_stability": "calm_reassurance",
    "treatment_recently_changed": "informational_summary",
    "multiple_dose_increases": "informational_summary",
    "multiple_dose_reductions": "informational_summary",
    "recent_provider_change": "informational_summary",
    "recent_refill_pattern": "informational_summary",
    "adherence_improving": "supportive_observation",
    "adherence_declining": "supportive_observation",
    "weight_after_treatment_change": "educational_observation",
    "glucose_after_treatment_change": "educational_observation",
    "exercise_during_treatment": "educational_observation",
}

# Fixed, pre-vetted framing. Contains NO facts, NO causal claims, NO treatment
# recommendation. The physician suffix is a discussion suggestion only (which the
# safety layer explicitly authorizes) — never advice to change medication.
PHYSICIAN_SUFFIX = "This may be worth bringing up at your next visit."

# Phrases that must never be INTRODUCED by narration (only allowed if they were
# already in the deterministic source text). Used by assert_safe + tests.
CAUSAL_PHRASES = ("caused", "because", "therefore", "due to", "led to",
                  "results in", "thanks to", "is working")
RECOMMENDATION_PHRASES = ("you should", "i recommend", "adjust your medication",
                          "change your dose", "increase your", "decrease your",
                          "stop taking", "start taking")


@dataclass(frozen=True)
class Narration:
    """Deterministic narration object (Sprint 7A). No LLM-generated facts."""

    observation_type: str
    narration_type: str
    tone: str
    title: str
    summary: str
    supporting_facts: tuple
    physician_discussion: bool
    educational: bool
    evidence: tuple
    confidence: float
    safety_class: str
    priority_score: int = 0

    def to_dict(self):
        return {
            "observation_type": self.observation_type,
            "narration_type": self.narration_type,
            "tone": self.tone,
            "title": self.title,
            "summary": self.summary,
            "supporting_facts": list(self.supporting_facts),
            "physician_discussion": self.physician_discussion,
            "educational": self.educational,
            "evidence": list(self.evidence),
            "confidence": self.confidence,
            "safety_class": self.safety_class,
            "priority_score": self.priority_score,
        }


def assert_safe(narration, source_text):
    """Runtime guardrail (Sprint 7D): a narration summary may not INTRODUCE causal
    or recommendation phrasing absent from the deterministic source text. Raises
    ValueError if it does (structural construction should make this impossible)."""
    s = narration.summary.lower()
    src = source_text.lower()
    for phrase in CAUSAL_PHRASES + RECOMMENDATION_PHRASES:
        if phrase in s and phrase not in src:
            raise ValueError(
                f"Narration introduced disallowed phrasing '{phrase}': {narration.summary!r}"
            )
    return True


def render_narration(obs_dict):
    """Render one prioritized observation dict into a deterministic Narration.

    The summary is the observation's own title (+ detail) plus, only when the
    safety layer flagged physician discussion, the fixed discussion suffix.
    Confidence and safety class are carried through UNCHANGED (never upgraded /
    weakened). Tone is set from the safety class, not invented.
    """
    otype = obs_dict["type"]
    safety_class = obs_dict.get("safety_class", SafetyClass.OBSERVATION)
    physician = bool(obs_dict.get("physician_discussion"))

    title = obs_dict["title"]
    detail = obs_dict.get("detail", "")
    source_text = f"{title} {detail}".strip()

    summary = title
    if detail:
        summary = f"{summary} {detail}".strip()
    if physician:
        summary = f"{summary} {PHYSICIAN_SUFFIX}".strip()

    narration_type = NARRATION_TYPE.get(otype, "informational_summary")
    supporting_facts = tuple(
        e.get("summary") for e in (obs_dict.get("evidence") or [])
        if isinstance(e, dict) and e.get("summary")
    )

    n = Narration(
        observation_type=otype,
        narration_type=narration_type,
        tone=TONE_BY_SAFETY.get(safety_class, "supportive"),
        title=title,
        summary=summary,
        supporting_facts=supporting_facts,
        physician_discussion=physician,
        educational=(narration_type == "educational_observation") or physician,
        evidence=tuple(obs_dict.get("evidence") or ()),
        confidence=obs_dict.get("confidence", 0.0),   # carried through, never changed
        safety_class=safety_class,                    # preserved, never weakened
        priority_score=obs_dict.get("priority_score", 0),
    )
    assert_safe(n, source_text)   # structural guarantee; raises if violated
    return n


def build_narrations(user, *, prioritized=None):
    """Approved → prioritized → narration. Returns ordered narration dicts (the
    only medication-observation surface Beth consumes)."""
    if prioritized is None:
        from apps.health.observations.prioritization import build_prioritized
        prioritized, _groups = build_prioritized(user)
    return [render_narration(d).to_dict() for d in prioritized]


def build_narration_view(user):
    """Narrations + their deterministic groups (for the 'What We've Noticed'
    surface and Beth). Groups reuse the prioritization grouping; no new logic."""
    from apps.health.observations.prioritization import (
        GROUP_TITLES,
        build_prioritized,
    )

    prioritized, groups = build_prioritized(user)
    narration_by_obstype = {}
    narrations = []
    for d in prioritized:
        n = render_narration(d).to_dict()
        narrations.append(n)
        narration_by_obstype[(d["type"], ":".join(sorted(d["domains"])))] = n

    narration_groups = []
    for g in groups:
        items = []
        for d in g["observations"]:
            key = (d["type"], ":".join(sorted(d["domains"])))
            if key in narration_by_obstype:
                items.append(narration_by_obstype[key])
        narration_groups.append({
            "key": g["key"],
            "title": g["title"],
            "physician_discussion": g["physician_discussion"],
            "narrations": items,
        })
    return {"narrations": narrations, "groups": narration_groups}
