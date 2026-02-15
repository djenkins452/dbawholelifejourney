"""
SAE — State Authority Guards.

Lightweight enforcement and documentation helpers to prevent
state-bypass drift. These do NOT block execution at runtime —
they serve as audit markers and developer warnings.

Usage:
    @state_first("Dashboard summary uses SAE for current values")
    def get_context_data(self, **kwargs):
        state = get_user_state(self.request.user)
        ...

    # Or inline documentation:
    require_state_first("health.weight_current", reason="Dashboard weight display")
"""

import functools
import logging

logger = logging.getLogger(__name__)


def state_first(reason):
    """
    Decorator documenting that a function MUST use SAE state
    for current-value access. Does not block execution.

    This is an audit/clarity mechanism:
    - Documents WHY this function should read from SAE
    - Logs a DEBUG message when the function is called
    - Makes state-first intent visible in code review

    Args:
        reason: Why this function must use SAE state-first.

    Example:
        @state_first("Dashboard health tile reads current weight from SAE")
        def get_health_context(self, user):
            state = get_user_state(user)
            ...
    """
    def decorator(func):
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            logger.debug(
                f"SAE state-first: {func.__qualname__} — {reason}"
            )
            return func(*args, **kwargs)
        # Attach metadata for introspection
        wrapper._state_first_reason = reason
        return wrapper
    return decorator


def require_state_first(field_path, reason=""):
    """
    Inline documentation helper. Call at the top of a code block
    that MUST read from SAE state rather than querying DB directly.

    This is a no-op at runtime — purely for clarity and grep-ability.

    Args:
        field_path: The SAE state path being used (e.g., "health.weight_current").
        reason: Why state-first is required here.

    Example:
        require_state_first("journal.days_since_entry", "Dashboard journal nudge")
        days_since = get_state_value(user, "journal.days_since_entry", None)
    """
    # No-op at runtime. Exists for grep-ability and code clarity.
    pass
