"""
WLJ Operations — Recovery Policy (Phase II).

The declarative rules the gate consults before any recovery action
(WLJ_OPERATIONS_VISION.md §4 classification · WLJ_OPERATIONS_PHASE2_PLAN.md §3).

Key discipline (resolves the "R1 unlimited retries" wording): vision §4 states R1
retries are *safe to repeat* (idempotent + verified) — that is a safety PROPERTY,
not a licence for an unbounded loop. EVERY production policy here — R1 included —
carries a finite ``max_attempts``, a ``cooldown``, an escalation threshold, and a
recurrence limit. Repeated *successful* recovery of the same class beyond
``recurrence_limit`` raises a permanent-fix escalation ("eliminate the class",
Constitution V.2) instead of silently masking the defect.
"""
from __future__ import annotations

from dataclasses import dataclass

# Safety classifications (vision §4). Only R1/R2 may auto-execute.
R0 = "R0"  # Observe only — no recovery; escalate.
R1 = "R1"  # Safe idempotent — auto, verify, repeatable but still bounded.
R2 = "R2"  # Low-risk service — auto, bounded by retry policy, verify.
R3 = "R3"  # Stateful — never auto; explicit operator approval (Phase III).
R4 = "R4"  # Destructive — never automated; deliberate engineering only.

AUTO_EXECUTABLE = frozenset({R1, R2})


@dataclass(frozen=True)
class RecoveryPolicy:
    """Deterministic policy for one recovery handler."""

    classification: str
    max_attempts: int  # FINITE for every class, R1 included (no unbounded loop).
    cooldown_seconds: int  # Minimum interval between attempts (anti-thrash).
    verification_required: bool = True  # Always True; explicit for clarity.
    # Recurrence / permanent-fix escalation (the "eliminate the class" guard).
    recurrence_window_hours: int = 24
    recurrence_limit: int | None = None  # successful recoveries in-window → escalate

    def __post_init__(self):
        if self.classification not in {R0, R1, R2, R3, R4}:
            raise ValueError(f"Unknown recovery classification: {self.classification!r}")
        if self.max_attempts < 1:
            raise ValueError("max_attempts must be finite and >= 1 (no unbounded loop).")
        if self.cooldown_seconds < 0:
            raise ValueError("cooldown_seconds must be >= 0.")

    @property
    def auto_executable(self) -> bool:
        """Only R1/R2 may run without a human (vision §4)."""
        return self.classification in AUTO_EXECUTABLE
