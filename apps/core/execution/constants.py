"""
Execution-layer constants for the WLJ recovery contract.

Single home for every threshold used by the classifier, recoverability
function, recovery-state machine, prioritizer recovery-mode bucket
selection, and risk horizons.

Importing from here is mandatory. Do NOT inline these values at call
sites — the recovery contract depends on a single source of truth.
"""

# ── Recovery-mode triggers ──────────────────────────────────────────
# Hour-of-day after which RECOVERY can be considered (user-local time).
RECOVERY_TRIGGER_HOUR = 12
# Number of recoverable overdue items needed to enter RECOVERY.
RECOVERY_OVERDUE_THRESHOLD = 2

# Hour-of-day after which the system flips to SHUTDOWN if the day is
# still off-track. Above this hour we stop trying to catch up and
# preserve tomorrow.
SHUTDOWN_TRIGGER_HOUR = 20
SHUTDOWN_OVERDUE_THRESHOLD = 3


# ── Risk horizons ───────────────────────────────────────────────────
# Default future-risk window. Items further out than this do not appear
# in Risk mode unless they participate in a dependency chain.
AT_RISK_HORIZON_MINUTES = 90
# Extended horizon when a dependency chain ties a future item to an
# overdue prerequisite.
DEPENDENCY_RISK_HORIZON_MINUTES = 240


# ── Recovery grace defaults ─────────────────────────────────────────
# Per-class default grace minutes. The classifier registry may override
# per-row.
GRACE_HARD_EXPIRED_MIN = 0
GRACE_WINDOWED_DEFAULT_MIN = 90
# Sentinel: no grace cap; recoverable until end of day (or until the
# recovery_state shutdown rule kicks in).
GRACE_REST_OF_DAY = None


# ── Block-collapse policy ───────────────────────────────────────────
# Minimum number of missed/non-recoverable items in a single
# execution_group_id before we collapse them into one summary entry.
COLLAPSE_MIN_GROUP_SIZE = 2
