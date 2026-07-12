"""
WLJ Operations — Recovery Handler contract + registry (Phase II).

A ``RecoveryHandler`` lives HERE, in ``operations/`` — never on an observability
monitor class (that would put action code inside the truth package, violating the
frozen §11 seam). A handler *consumes* Operations Truth (the detector predicate) from
``ai_observability/`` and performs the deterministic action.

The lifecycle (WLJ_OPERATIONS_VISION.md §5): diagnose → recover → verify, driven by
``RecoveryEngine``. Verification reuses the EXACT detector predicate that raised the
incident, so "recovered" is provably the negation of "detected".
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

from apps.core.operations.recovery.policy import RecoveryPolicy


@dataclass
class RecoveryDiagnosis:
    """Structured, side-effect-free cause + target for one incident."""

    target: str  # the specific thing to act on (e.g. a Beat task name)
    reason: str  # human-readable deterministic cause
    evidence: dict = field(default_factory=dict)
    recoverable: bool = True  # False → observe-only (R0) even if a handler exists


@dataclass
class RecoveryOutcome:
    """What ``recover()`` deterministically did."""

    action_taken: str
    # If the effect is asynchronous (e.g. a re-enqueued task runs later),
    # verification must defer to a later cycle rather than close optimistically.
    verification_deferred: bool = False
    evidence: dict = field(default_factory=dict)


@dataclass
class VerificationResult:
    """Deterministic proof (from the detector predicate) that health returned."""

    healthy: bool
    evidence: dict = field(default_factory=dict)


class RecoveryHandler:
    """Base class for a deterministic recovery. Subclass in ``operations/``.

    A handler is associated with incidents by ``monitor_key`` and the set of
    ``anomaly_type`` values it handles. An incident with no registered handler is
    R0 by default (observe-only) — the safe default.
    """

    monitor_key: str = ""
    handled_anomaly_types: frozenset[str] = frozenset()
    policy: RecoveryPolicy
    # Human-readable name of the deterministic predicate ``verify()`` reuses (the
    # exact detector that raised the incident). Used by Shadow Mode to record the
    # verification STRATEGY without executing it. Overridden per handler.
    verification_predicate: str = ""

    def diagnose(self, anomaly) -> RecoveryDiagnosis:  # pragma: no cover - interface
        raise NotImplementedError

    def recover(self, diagnosis: RecoveryDiagnosis) -> RecoveryOutcome:  # pragma: no cover
        raise NotImplementedError

    def verify(self, diagnosis: RecoveryDiagnosis) -> VerificationResult:  # pragma: no cover
        raise NotImplementedError

    def describe_action(self, diagnosis: RecoveryDiagnosis) -> str:
        """Side-effect-free description of the action ``recover()`` WOULD take.

        Shadow Mode uses this to record "what recovery would have done" WITHOUT
        calling ``recover()``. Must never mutate state. Default is generic; each
        handler overrides it with its concrete deterministic action.
        """
        return f"execute recovery for '{diagnosis.target}'"

    def is_enabled(self) -> bool:
        """Is this handler's operator flag on? (read-only settings fact).

        SINGLE source for "is handler X enabled" — ``diagnose()`` reuses this so the
        Ops Wall telemetry snapshot can never drift from the gating the engine
        actually applies. Default False (ship-dark); each handler overrides.
        """
        return False

    def allowlist_size(self) -> Optional[int]:
        """Count of allowlisted targets for this handler, or ``None`` if it has no
        allowlist (a read-only config fact for Ops Wall display, never a verdict)."""
        return None


class RecoveryRegistry:
    """Maps an incident's ``anomaly_type`` to the handler that recovers it."""

    def __init__(self):
        self._by_type: dict[str, RecoveryHandler] = {}

    def register(self, handler: RecoveryHandler) -> None:
        for atype in handler.handled_anomaly_types:
            self._by_type[atype] = handler

    def handler_for(self, anomaly_type: str) -> Optional[RecoveryHandler]:
        return self._by_type.get(anomaly_type)

    def handlers(self) -> list[RecoveryHandler]:
        """Distinct registered handler instances (a handler may claim >1 type)."""
        return list(dict.fromkeys(self._by_type.values()))

    def __len__(self) -> int:
        return len(self._by_type)


# Process-wide registry, populated by ``handlers.register_default_handlers()``.
registry = RecoveryRegistry()
