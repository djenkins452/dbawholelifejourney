"""
DETERMINISTIC MEASUREMENT-WRITE VALIDATION (M2).

WHY THIS EXISTS (production 2026-08-27). `log_weight(value=534, unit='lb')` became
canonical truth for a user whose preceding series was ~268–278 lb — a ~+263 lb
single-day change. Two deterministic gaps let it through:

  1. The only plausibility check was an ABSOLUTE range (`multimodal._WEIGHT_RANGE`,
     40–1000 lb). 534 lb is a plausible weight for *somebody*; it is not plausible for
     THIS series. WLJ already held the history and never consulted it.
  2. `execute_action` short-circuits at its generic confirmation gate BEFORE the
     handler runs, so the handler's validation lived DOWNSTREAM of the confirmation.
     The user authorised the value before WLJ had ever looked at it.

WHAT THIS MODULE IS ALLOWED TO DECIDE. Narrow, and deliberately not clinical:

    WLJ may determine that a proposed measurement is inconsistent enough with
    canonical measurement truth that it requires stronger verification before
    persistence.

It never decides that a measurement is medically impossible, never diagnoses, and
never emits a clinical judgment. Three outcomes only:

    NORMAL       passes deterministic validation → the ordinary flow continues
    INVALID      malformed / unsupported unit / outside a HARD domain constraint →
                 fail closed, and never mint a confirmation that could persist it
    EXCEPTIONAL  structurally valid, but materially inconsistent with recent canonical
                 history → still writable, but only behind an EXPLICIT exceptional
                 authorization that makes the unusual value unmistakable

NO UNIVERSAL THRESHOLD. A 20% change means something different for weight, glucose,
temperature, blood pressure or waist circumference. Each measurement plugs its own
deterministic thresholds into this ONE shared mechanism; the mechanism owns the
comparison, the domain owns the numbers.

REUSE, NOT DUPLICATION: hard bounds come from the existing `multimodal` validators and
history from the canonical `DailyHealthQueries` accessor. Normalization uses the
model's own canonical conversion property. This module adds no new truth authority.
"""
import logging
from dataclasses import dataclass
from datetime import timedelta
from typing import Callable, Optional

logger = logging.getLogger(__name__)

NORMAL = "normal"
INVALID = "invalid"
EXCEPTIONAL = "exceptional"


@dataclass(frozen=True)
class MeasurementSpec:
    """One measurement write's deterministic validation configuration.

    `min_abs_delta` AND `rel_delta` must BOTH be exceeded for a value to be exceptional.
    Requiring both is deliberate: a relative test alone flags trivial swings on a small
    base, and an absolute test alone flags normal variation on a large one.
    """
    intent: str
    value_param: str
    unit_param: str
    default_unit: str
    canonical_unit: str
    units: tuple
    normalize: Callable            # (value, unit) -> canonical float
    in_hard_bounds: Callable       # (value, unit) -> bool
    recent: Callable               # (user, lookback_days) -> (canonical_value, when) | None
    label: str
    lookback_days: int
    min_abs_delta: float           # in canonical units
    rel_delta: float               # fraction of the comparison value


@dataclass(frozen=True)
class ValidationOutcome:
    status: str
    spec: Optional[MeasurementSpec] = None
    reason: str = ""
    detail: dict = None
    message: str = ""

    @property
    def is_invalid(self):
        return self.status == INVALID

    @property
    def is_exceptional(self):
        return self.status == EXCEPTIONAL


# ── weight: normalization + hard bounds + canonical history (all reused) ─────────
def _weight_normalize(value, unit):
    v = float(value)
    return v if (unit or "lb") == "lb" else v * 2.20462   # WeightEntry.value_in_lb


def _weight_in_hard_bounds(value, unit):
    from apps.ai.multimodal import validate_weight      # the EXISTING absolute gate
    return bool(validate_weight(value, unit))


def _weight_recent(user, lookback_days):
    """The most recent canonical weight within the window, normalized, with its date.
    Reads the canonical series directly — never model prose, never conversation state."""
    from django.utils import timezone

    from apps.health.models import WeightEntry
    cutoff = timezone.now() - timedelta(days=lookback_days)
    e = (WeightEntry.objects.filter(user=user, recorded_at__gte=cutoff)
         .order_by("-recorded_at").first())
    if e is None:
        return None
    return (float(e.value_in_lb), e.recorded_at)


WEIGHT_SPEC = MeasurementSpec(
    intent="log_weight",
    value_param="value", unit_param="unit",
    default_unit="lb", canonical_unit="lb", units=("lb", "kg"),
    normalize=_weight_normalize,
    in_hard_bounds=_weight_in_hard_bounds,
    recent=_weight_recent,
    label="weight",
    lookback_days=60,
    # Domain-owned thresholds. A >15% AND >15 lb change from the most recent reading
    # inside 60 days is not "unusual", it is almost always a different subject, a unit
    # mix-up, or a value that came from somewhere else entirely.
    min_abs_delta=15.0,
    rel_delta=0.15,
)

# One shared mechanism, per-measurement configuration. `log_body_measurements` is the
# next natural consumer (same shape, per-metric bounds already exist in `multimodal`);
# it is intentionally NOT registered in M2 so this milestone stays a bounded validation
# layer rather than a health-truth redesign.
_REGISTRY = {WEIGHT_SPEC.intent: WEIGHT_SPEC}


def spec_for(intent):
    return _REGISTRY.get((intent or "").strip().lower())


def validate(user, intent, params):
    """Deterministically classify a proposed measurement write.

    Returns a `ValidationOutcome`. Never raises, and never writes anything — a value
    that has not been authorized must not exist anywhere in canonical truth.
    """
    spec = spec_for(intent)
    if spec is None or not isinstance(params, dict):
        return ValidationOutcome(NORMAL)
    if spec.value_param not in params:
        return ValidationOutcome(NORMAL)      # not a value-bearing call

    raw_value = params.get(spec.value_param)
    raw_unit = (params.get(spec.unit_param) or spec.default_unit)
    unit = str(raw_unit).strip().lower()

    # ── INVALID: malformed, unsupported unit, or outside a hard domain constraint ──
    if unit not in spec.units:
        return ValidationOutcome(
            INVALID, spec, reason="unsupported_unit",
            detail={"proposed_value": raw_value, "proposed_unit": raw_unit,
                    "supported_units": list(spec.units)},
            message=(f"I can't record a {spec.label} in '{raw_unit}' — "
                     f"I keep {spec.label} in {' or '.join(spec.units)}."))
    try:
        value = float(raw_value)
    except (TypeError, ValueError):
        return ValidationOutcome(
            INVALID, spec, reason="malformed_value",
            detail={"proposed_value": raw_value, "proposed_unit": unit},
            message=f"That {spec.label} value isn't a number I can record.")
    if not spec.in_hard_bounds(value, unit):
        return ValidationOutcome(
            INVALID, spec, reason="out_of_hard_bounds",
            detail={"proposed_value": value, "proposed_unit": unit},
            message=(f"{value} {unit} is outside the range I can record as a "
                     f"{spec.label}."))

    # ── EXCEPTIONAL: valid, but materially inconsistent with canonical history ──
    try:
        recent = spec.recent(user, spec.lookback_days)
    except Exception:      # history unavailable → never block a valid write
        logger.warning("measurement_validation: history read failed intent=%s",
                       intent, exc_info=True)
        recent = None
    if not recent:
        return ValidationOutcome(NORMAL, spec)

    prior, prior_at = recent
    # NORMALIZE BEFORE COMPARING — a kg value must never be diffed against lb.
    proposed = spec.normalize(value, unit)
    abs_delta = abs(proposed - prior)
    rel_delta = (abs_delta / abs(prior)) if prior else 0.0
    if abs_delta < spec.min_abs_delta or rel_delta < spec.rel_delta:
        return ValidationOutcome(NORMAL, spec)

    detail = {
        "proposed_value": value, "proposed_unit": unit,
        "proposed_canonical": round(proposed, 2),
        "canonical_unit": spec.canonical_unit,
        "compared_with": round(prior, 2),
        "compared_recorded_at": prior_at.isoformat() if prior_at else None,
        "absolute_delta": round(abs_delta, 2),
        "relative_delta": round(rel_delta, 4),
        "lookback_days": spec.lookback_days,
        "thresholds": {"min_abs_delta": spec.min_abs_delta,
                       "rel_delta": spec.rel_delta},
    }
    return ValidationOutcome(
        EXCEPTIONAL, spec, reason="inconsistent_with_history", detail=detail,
        message=exception_note(spec, detail))


def exception_note(spec, detail):
    """The deterministic discrepancy sentence — facts only, no interpretation.

    It states what was proposed, what the canonical record holds, and how far apart
    they are. It does NOT say the value is wrong, impossible, or unhealthy: whether an
    unusual reading is meaningful is not WLJ's judgment to make.
    """
    return (f"{detail['proposed_value']} {detail['proposed_unit']} is a "
            f"{detail['absolute_delta']} {spec.canonical_unit} change from the most "
            f"recent recorded {spec.label} of {detail['compared_with']} "
            f"{spec.canonical_unit}. Confirm this is the {spec.label} to record.")
