"""
Signal Confidence Rules — centralized, deterministic, auditable.

Every SignalSnapshot gets a confidence value based on the quality
of evidence behind it. This module is the single source of truth
for confidence assignment. No magic numbers scattered elsewhere.

Confidence scale (0.0–1.0):
    1.0  EXPLICIT    — direct structured log with clear timestamp/status
                       (completion log, explicit skip log, verified measurement)
    0.8  DERIVED     — state computed from multiple records or partial evidence
                       (partial completion ratio, aggregated sub-scores)
    0.6  ABSENCE     — ETE expected activity but signal computer found none
                       (the user was expected to act in this domain today but
                       no records exist — weaker evidence than explicit action)
    0.9  NOT_EXPECTED — domain not expected today per ETE
                       (high confidence in the expectation itself; slightly
                       below 1.0 because ETE expectations are derived from
                       routine/schedule names, not absolute guarantees)

NOTE: Signals are only created when a signal computer produces real
output. Untracked domains with no data produce NO signal at all.
CONFIDENCE_ABSENCE applies only when a computer explicitly returns
a 'missed' state (e.g., medication adherence computer finds active
schedules but no logs).
"""


# Named constants for clarity and grep-ability
CONFIDENCE_EXPLICIT = 1.0      # Direct structured evidence
CONFIDENCE_DERIVED = 0.8       # Computed from partial/multiple records
CONFIDENCE_ABSENCE = 0.6       # Expected activity with no evidence found
CONFIDENCE_NOT_EXPECTED = 0.9  # ETE says not expected today


def confidence_for_state(state, has_explicit_evidence=True):
    """
    Return the appropriate confidence value for a signal state.

    Args:
        state: The signal state (completed, partial, missed, skipped, not_expected)
        has_explicit_evidence: Whether the state is backed by a direct log record.
            True for explicit completion/skip logs, False for computed/aggregated.

    Returns:
        float: Confidence value 0.0–1.0
    """
    if state == 'not_expected':
        return CONFIDENCE_NOT_EXPECTED

    if state == 'skipped':
        # Skipped is ONLY set when there's explicit skip evidence
        return CONFIDENCE_EXPLICIT

    if state == 'completed':
        return CONFIDENCE_EXPLICIT if has_explicit_evidence else CONFIDENCE_DERIVED

    if state == 'partial':
        return CONFIDENCE_DERIVED  # Partial is always computed from records

    if state == 'missed':
        return CONFIDENCE_ABSENCE  # Missed = absence of evidence

    # Legacy/unknown state — treat as derived
    return CONFIDENCE_DERIVED
