"""
Deterministic Observation layer — canonical object + safety classifier (Sprint 5).

Observations are deterministic, evidence-backed statements of chronology and
association — NEVER recommendations, diagnoses, predictions, or causal claims.
They are computed (not LLM output, not stored): a recomputable derived state that
sits between the timeline and Beth.

Pipeline:  rules → Observation → SafetyClassifier → (approved) → Beth narration.

Guardrails (Medication Intelligence Canon):
  - No observation without evidence (insufficient evidence → no observation).
  - No observation reaches Beth without passing the deterministic safety classifier.
  - Low-confidence / incomplete / contradictory / duplicate / pending-confirmation
    observations are SUPPRESSED.
  - The classifier decides what may be said; it does NOT generate language.
"""

from dataclasses import dataclass, field, replace


class ObsType:
    # Medication-only (5C)
    ADHERENCE_IMPROVING = "adherence_improving"
    ADHERENCE_DECLINING = "adherence_declining"
    TREATMENT_RECENTLY_CHANGED = "treatment_recently_changed"
    MULTIPLE_DOSE_REDUCTIONS = "multiple_dose_reductions"
    MULTIPLE_DOSE_INCREASES = "multiple_dose_increases"
    MEDICATION_STABLE = "medication_stable"
    LONG_TERM_STABILITY = "long_term_stability"
    RECENT_PROVIDER_CHANGE = "recent_provider_change"
    RECENT_REFILL_PATTERN = "recent_refill_pattern"
    # Cross-domain (5D)
    WEIGHT_AFTER_TREATMENT_CHANGE = "weight_after_treatment_change"
    GLUCOSE_AFTER_TREATMENT_CHANGE = "glucose_after_treatment_change"
    EXERCISE_DURING_TREATMENT = "exercise_during_treatment"
    SLEEP_AFTER_MED_CHANGE = "sleep_after_med_change"


class SafetyClass:
    INFORMATIONAL = "informational"
    EDUCATIONAL = "educational"
    OBSERVATION = "observation"
    PHYSICIAN_DISCUSSION = "physician_discussion_suggested"
    SUPPRESSED = "suppressed"


# Domains whose association with a treatment change is clinically meaningful and
# should be routed to "discuss with your physician".
BIOMARKER_DOMAINS = {"weight", "glucose", "lab", "blood_pressure"}

# Minimum confidence below which an observation is suppressed (5G).
MIN_CONFIDENCE = 0.40


@dataclass(frozen=True)
class Observation:
    """Canonical observation object (Sprint 5A). Deterministic — not LLM output."""

    type: str
    title: str                      # factual chronology/association — never causal
    detail: str = ""
    confidence: float = 0.0         # 0..1, deterministic
    domains: tuple = ()             # contributing domains
    window_days: int = 0            # time window the observation spans
    evidence: tuple = ()            # evidence references (dicts) — required
    safety_class: str = ""          # set by the classifier
    physician_discussion: bool = False  # set by the classifier
    contradictory: bool = False     # rule may flag a contradictory timeline (→ suppress)

    @property
    def dedupe_key(self):
        return f"{self.type}:{':'.join(sorted(self.domains))}"

    def to_dict(self):
        return {
            "type": self.type,
            "title": self.title,
            "detail": self.detail,
            "confidence": round(self.confidence, 2),
            "domains": list(self.domains),
            "window_days": self.window_days,
            "evidence": list(self.evidence),
            "safety_class": self.safety_class,
            "physician_discussion": self.physician_discussion,
        }


def classify(obs):
    """Deterministic safety classifier (Sprint 5B + 5G).

    Returns the observation with a safety_class assigned, or SUPPRESSED. Decides
    what Beth MAY say; never generates language.
    """
    # 5E / 5G — suppress when evidence is missing, confidence is low, or the
    # timeline is contradictory.
    if not obs.evidence:
        return replace(obs, safety_class=SafetyClass.SUPPRESSED)
    if obs.confidence < MIN_CONFIDENCE:
        return replace(obs, safety_class=SafetyClass.SUPPRESSED)
    if obs.contradictory:
        return replace(obs, safety_class=SafetyClass.SUPPRESSED)

    # Cross-domain association between a treatment change and a biomarker →
    # physician-discussion (still association-only, never advice).
    domains = set(obs.domains)
    if "medication" in domains and (domains & BIOMARKER_DOMAINS):
        return replace(
            obs,
            safety_class=SafetyClass.PHYSICIAN_DISCUSSION,
            physician_discussion=True,
        )

    # Everything else that survived suppression is a plain observation.
    return replace(obs, safety_class=SafetyClass.OBSERVATION)


def approve(observations):
    """Run the full safety gate over raw observations (Sprint 5G):

    1. drop observations with no evidence (5E),
    2. classify each (5B),
    3. drop SUPPRESSED,
    4. collapse duplicates by dedupe_key (keep highest confidence),
    5. order by confidence (desc).
    Returns the list of APPROVED Observation objects — the only ones Beth sees.
    """
    classified = [classify(o) for o in observations if o.evidence]
    approved = [o for o in classified if o.safety_class != SafetyClass.SUPPRESSED]

    best = {}
    for o in approved:
        k = o.dedupe_key
        if k not in best or o.confidence > best[k].confidence:
            best[k] = o
    return sorted(best.values(), key=lambda o: o.confidence, reverse=True)
