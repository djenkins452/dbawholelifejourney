"""Telemetry writer — Phase 0 STUB.

This is the interface the live-path probe will eventually call. In the inert
Phase 0 build there is NO database model (no migration), so `record_mode_observation`
does NOT persist anything. It:

  - builds a privacy-safe observation payload (de-identified by default),
  - logs it at DEBUG (invisible in production),
  - returns the payload dict for tests / offline analysis,
  - NEVER raises, NEVER touches the response path.

When the migration lands (requires approval), the single TODO below becomes a
`CognitiveModeObservation.objects.create(**payload)` — and nothing else changes.
"""

from __future__ import annotations

import hashlib
import logging
import re
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)

# Per-deploy salt so message hashes are not externally correlatable. In Phase 0
# this is a module constant; production would source it from settings/secret.
_DEFAULT_SALT = "phase0-inert-salt"


@dataclass
class ModeObservation:
    """Privacy-safe observation payload. Mirrors the future DB model fields."""

    request_id: str = ""
    user_id: object = None

    # prediction
    predicted_mode: str = "unknown"
    predicted_domain: object = None
    mode_confidence: float = 0.0
    mode_reason: str = ""
    coach_tail: bool = False

    # actual routing (filled by the probe from the already-decided route)
    actual_route_taken: str = ""
    actual_handler: object = None
    was_terminal: bool = False
    deterministic_router_match: object = None
    cos_shortcut_match: bool = False
    llm_intent_selected: object = None
    legacy_analysis_branch_fired: bool = False

    # derived flags
    route_mismatch: bool = False
    greedy_route_flag: bool = False

    # package gap
    package_needed: list = field(default_factory=list)
    package_available: list = field(default_factory=list)

    # privacy-safe message features
    message_hash: str = ""
    message_len: int = 0
    message_features: dict = field(default_factory=dict)
    message_text: object = None  # only set when raw logging explicitly enabled

    def as_dict(self) -> dict:
        return {
            "request_id": self.request_id,
            "user_id": self.user_id,
            "predicted_mode": self.predicted_mode,
            "predicted_domain": self.predicted_domain,
            "mode_confidence": self.mode_confidence,
            "mode_reason": self.mode_reason,
            "coach_tail": self.coach_tail,
            "actual_route_taken": self.actual_route_taken,
            "actual_handler": self.actual_handler,
            "was_terminal": self.was_terminal,
            "deterministic_router_match": self.deterministic_router_match,
            "cos_shortcut_match": self.cos_shortcut_match,
            "llm_intent_selected": self.llm_intent_selected,
            "legacy_analysis_branch_fired": self.legacy_analysis_branch_fired,
            "route_mismatch": self.route_mismatch,
            "greedy_route_flag": self.greedy_route_flag,
            "package_needed": list(self.package_needed),
            "package_available": list(self.package_available),
            "message_hash": self.message_hash,
            "message_len": self.message_len,
            "message_features": dict(self.message_features),
            "message_text": self.message_text,
        }


def hash_message(message: str, salt: str = _DEFAULT_SALT) -> str:
    norm = re.sub(r"\s+", " ", (message or "").lower().strip())
    return hashlib.sha256((salt + "|" + norm).encode("utf-8")).hexdigest()


def extract_safe_features(message: str) -> dict:
    """Non-PII signal features. No names, numbers, or free text retained."""
    m = re.sub(r"\s+", " ", (message or "").lower().strip())
    return {
        "len_bucket": _len_bucket(len(m)),
        "has_question_mark": "?" in (message or ""),
        "starts_what": m.startswith("what"),
        "starts_how": m.startswith("how"),
        "starts_should": m.startswith("should"),
        "has_today": "today" in m,
        "has_history": "history" in m,
        "has_compare": "compare" in m,
        "word_count": len(m.split()),
    }


def _len_bucket(n: int) -> str:
    if n <= 20:
        return "xs"
    if n <= 60:
        return "s"
    if n <= 140:
        return "m"
    return "l"


def record_mode_observation(observation: "ModeObservation", *, persist: bool = False) -> dict:
    """Record one observation. INERT in Phase 0.

    `persist` is accepted for forward-compatibility but ignored until the DB
    model exists. This function is guaranteed never to raise.
    """
    try:
        payload = observation.as_dict()
        # ---- TODO (post-migration, requires approval): persist ----
        # if persist and _model_available():
        #     from apps.ai.models import CognitiveModeObservation
        #     CognitiveModeObservation.objects.create(**_db_fields(payload))
        logger.debug("cognitive_mode.observation %s", payload)
        return payload
    except Exception:  # never break the (future) caller
        logger.debug("record_mode_observation failed (non-fatal)", exc_info=True)
        return {}
