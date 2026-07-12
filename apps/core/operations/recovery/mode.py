"""
WLJ Operations — Recovery Mode resolver (Phase II-A validation: Shadow Mode).

ONE deterministic source of truth for "what is recovery allowed to do right now":

  * ``DISABLED`` — the whole recovery cycle is a true no-op. No diagnosis, no
    action, no verification, no incident mutation, no audit volume. Production
    default; behaviour identical to pre-recovery.
  * ``SHADOW``   — the engine runs the ENTIRE deterministic lifecycle exactly as it
    would live (detect → diagnose → classify → policy → kill-switch → cooldown →
    retry → verification strategy → determine action → determine escalation path),
    then STOPS immediately before executing the recovery action. It writes a single
    distinct ``SHADOW`` audit row per incident occurrence recording *what recovery
    would have done*, and performs NO action, NO verification, NO state mutation,
    NO incident closure, NO side effect. This is the final validation stage before
    the first automatic production recovery.
  * ``ACTIVE``   — real deterministic recovery (still ships dark; enabled per-pilot
    by the operator, one allowlisted handler at a time).

Config precedence (deliberately fail-safe):
  1. An explicit ``OPS_RECOVERY_MODE`` (DISABLED/SHADOW/ACTIVE) always wins.
  2. Legacy bridge — if ``OPS_RECOVERY_MODE`` is left at its DISABLED default but the
     original master switch ``OPS_RECOVERY_ENABLED=True`` is set, that resolves to
     ``ACTIVE`` (preserves the original kill-switch + every existing test/allowlist).
  3. Anything unrecognised → ``DISABLED`` (fail safe; never silently "on").

An explicit stricter mode can NEVER be upgraded by a stray legacy flag: ``MODE=SHADOW``
with ``OPS_RECOVERY_ENABLED=True`` stays ``SHADOW`` — the bridge only fires when the
mode is the DISABLED default. So the safe direction is the only automatic direction.
"""
from __future__ import annotations

import logging

from django.conf import settings

logger = logging.getLogger(__name__)

DISABLED = "DISABLED"
SHADOW = "SHADOW"
ACTIVE = "ACTIVE"

VALID_MODES = frozenset({DISABLED, SHADOW, ACTIVE})


def get_recovery_mode() -> str:
    """Resolve the effective recovery mode (see module docstring for precedence)."""
    raw = str(getattr(settings, "OPS_RECOVERY_MODE", "") or "").strip().upper()

    if raw in VALID_MODES:
        mode = raw
    else:
        if raw:  # a value was set but is not one of the three → fail safe
            logger.warning("Unknown OPS_RECOVERY_MODE=%r → treating as DISABLED.", raw)
        mode = DISABLED

    # Legacy bridge: only upgrades the DISABLED default → ACTIVE, never overrides an
    # explicit SHADOW/ACTIVE (an explicit stricter mode always wins).
    if mode == DISABLED and bool(getattr(settings, "OPS_RECOVERY_ENABLED", False)):
        mode = ACTIVE

    return mode


def describe_mode_source() -> str:
    """Deterministic label for WHERE the effective mode came from (read-only fact).

    Mirrors the precedence in ``get_recovery_mode()`` so the Ops Wall can tell an
    operator whether the mode is driven by ``OPS_RECOVERY_MODE`` or the legacy
    ``OPS_RECOVERY_ENABLED`` bridge. This is a fact for display — never a verdict.
    """
    raw = str(getattr(settings, "OPS_RECOVERY_MODE", "") or "").strip().upper()
    if raw in VALID_MODES:
        return "OPS_RECOVERY_MODE"
    if bool(getattr(settings, "OPS_RECOVERY_ENABLED", False)):
        return "OPS_RECOVERY_ENABLED (legacy bridge)"
    return "default (DISABLED)"


def recovery_is_enabled() -> bool:
    """True when recovery should run at all (SHADOW or ACTIVE) — the enqueue gate."""
    return get_recovery_mode() != DISABLED


def is_shadow() -> bool:
    return get_recovery_mode() == SHADOW
