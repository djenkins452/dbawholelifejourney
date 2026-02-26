"""WLJ UI Test Framework — Safety Controls.

Implements production safety mode, cleanup prefix enforcement,
rate limiting, and destructive action blocking per Section 11
of the master requirements.
"""

import re
import time
from datetime import datetime, timezone


# --- Cleanup prefix pattern per Section 11.2 ---

CLEANUP_PREFIX_PATTERN = re.compile(r'^AUTOTEST\|[a-z_]+\|[a-f0-9]+\|')


class SafetyError(Exception):
    """Raised when a safety control blocks an operation."""


class SafetyController:
    """Enforces production safety controls for the test framework.

    Automatically detects production vs development environments and
    applies appropriate safety constraints:
    - Cleanup prefix enforcement
    - Rate limiting between actions/navigations
    - Destructive action blocking
    - Mandatory artifact capture
    - Audit logging
    """

    # Rate limits per Section 11.1
    NAVIGATION_DELAY_MS = 500
    ACTION_DELAY_MS = 200

    # Blocked action patterns in production
    BLOCKED_KEYWORDS = {"DELETE", "DROP", "TRUNCATE", "DESTROY"}

    def __init__(self, base_url, module, run_id):
        """Initialize safety controller.

        Args:
            base_url: The target URL being tested.
            module: Module name for prefix validation.
            run_id: Current run ID (8-char hex) for prefix validation.
        """
        self.base_url = base_url
        self.module = module
        self.run_id = run_id
        self.is_prod = is_production(base_url)
        self._last_navigation = 0.0
        self._last_action = 0.0
        self._audit_log = []

    @property
    def production_mode(self):
        """Whether production safety controls are active."""
        return self.is_prod

    # --- Cleanup prefix enforcement (Section 11.2) ---

    def validate_cleanup_prefix(self, value):
        """Validate that a test data value matches the cleanup prefix.

        Args:
            value: The string to validate (e.g., test entry title).

        Returns:
            True if valid.

        Raises:
            SafetyError: If prefix doesn't match in production mode.
        """
        if not isinstance(value, str):
            return True

        if CLEANUP_PREFIX_PATTERN.match(value):
            return True

        if self.is_prod:
            raise SafetyError(
                f"Cleanup prefix violation in production mode. "
                f"Value '{value[:50]}...' does not match required pattern "
                f"'AUTOTEST|<MODULE>|<RUN_ID>|<description>'. "
                f"Expected prefix: 'AUTOTEST|{self.module}|{self.run_id}|'"
            )

        return False

    def make_cleanup_prefix(self, description=""):
        """Generate a properly formatted cleanup prefix string.

        Args:
            description: Human-readable description to append.

        Returns:
            String with format: AUTOTEST|<module>|<run_id>|<description>
        """
        return f"AUTOTEST|{self.module}|{self.run_id}|{description}"

    # --- Rate limiting (Section 11.1) ---

    def pre_navigation(self):
        """Apply rate limiting before a page navigation.

        In production mode, enforces minimum 500ms between navigations.
        """
        if not self.is_prod:
            return

        elapsed = _elapsed_since(self._last_navigation)
        remaining = self.NAVIGATION_DELAY_MS - elapsed
        if remaining > 0:
            time.sleep(remaining / 1000.0)
        self._last_navigation = _now_ms()
        self._audit("navigation_throttled")

    def pre_action(self):
        """Apply rate limiting before a browser action.

        In production mode, enforces minimum 200ms between actions.
        """
        if not self.is_prod:
            return

        elapsed = _elapsed_since(self._last_action)
        remaining = self.ACTION_DELAY_MS - elapsed
        if remaining > 0:
            time.sleep(remaining / 1000.0)
        self._last_action = _now_ms()

    # --- Destructive action blocking (Section 11.1) ---

    def check_action_allowed(self, action, url=None):
        """Check if an action is allowed in the current environment.

        Args:
            action: The action type (e.g., 'NAVIGATE', 'CLICK').
            url: Optional URL being targeted.

        Raises:
            SafetyError: If the action is blocked in production mode.
        """
        if not self.is_prod:
            return

        action_upper = (action or "").upper()
        if action_upper in self.BLOCKED_KEYWORDS:
            raise SafetyError(
                f"Destructive action '{action}' is blocked in production mode"
            )

        # Check URL for destructive API patterns
        if url:
            url_upper = url.upper()
            for keyword in self.BLOCKED_KEYWORDS:
                if keyword in url_upper:
                    raise SafetyError(
                        f"Destructive URL pattern '{keyword}' detected in "
                        f"'{url}' — blocked in production mode"
                    )

    # --- Artifact capture enforcement (Section 11.1) ---

    def must_capture_artifacts(self):
        """Whether artifact capture is mandatory (always true in prod)."""
        return self.is_prod

    # --- Audit logging (Section 11.1) ---

    def _audit(self, event, **kwargs):
        """Log an audit event."""
        entry = {
            "event": event,
            "timestamp": datetime.now(timezone.utc).isoformat(
                timespec="milliseconds"
            ),
            "production_mode": self.is_prod,
        }
        entry.update(kwargs)
        self._audit_log.append(entry)

    def get_audit_log(self):
        """Return the audit log entries."""
        return list(self._audit_log)


# --- Environment detection (Section 11.3) ---

def is_production(base_url):
    """Determine if the target is a production environment.

    Per Section 11.3: defaults to production safety if unknown.
    """
    production_indicators = ["railway.app", "wholelifejourney.com"]
    development_indicators = ["localhost", "127.0.0.1", "0.0.0.0"]

    base_url_lower = (base_url or "").lower()

    for indicator in development_indicators:
        if indicator in base_url_lower:
            return False
    for indicator in production_indicators:
        if indicator in base_url_lower:
            return True

    # Default to production safety if unknown
    return True


# --- Helpers ---

def _now_ms():
    """Return current time in milliseconds."""
    return time.monotonic() * 1000


def _elapsed_since(timestamp_ms):
    """Return milliseconds elapsed since a timestamp."""
    if timestamp_ms == 0.0:
        return float("inf")
    return _now_ms() - timestamp_ms
