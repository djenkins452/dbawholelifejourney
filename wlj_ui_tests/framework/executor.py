"""WLJ UI Test Framework — Action Execution Engine.

Translates YAML action types to Playwright browser actions.
Supports: NAVIGATE, CLICK, TYPE, SELECT, WAIT, ASSERT.

Retry layer (Phase 14): CLICK, TYPE, WAIT, and ASSERT actions are
retried up to max_retries times (default 2) with exponential backoff
on transient failures. NAVIGATE and SELECT are NOT retried — navigation
failures indicate real problems, and SELECT on the wrong element
could cause data corruption.
"""

import time

from .selectors import resolve_selector


class ExecutionError(Exception):
    """Raised when an action or assertion fails during execution."""

    def __init__(self, message, step_index=None, action=None, selector=None,
                 retries_attempted=0):
        super().__init__(message)
        self.step_index = step_index
        self.action = action
        self.selector = selector
        self.retries_attempted = retries_attempted


# Actions eligible for retry — NAVIGATE and SELECT are excluded
RETRYABLE_ACTIONS = {"CLICK", "TYPE", "WAIT", "ASSERT"}

# Base delay between retries (milliseconds), doubled each attempt
RETRY_BASE_DELAY_MS = 500


class ActionExecutor:
    """Translates YAML step definitions to Playwright page actions.

    Each action type maps to a Playwright page method per Section 5/Phase 3.
    Selector resolution is basic here; Phase 4 SelectorResolver enhances it.

    Retry layer: CLICK, TYPE, WAIT, and ASSERT actions are automatically
    retried up to max_retries times with exponential backoff.
    """

    DEFAULT_TIMEOUT_MS = 5000
    DEFAULT_MAX_RETRIES = 2

    def __init__(self, page, defaults=None, max_retries=None):
        """Initialize with a Playwright page and optional suite defaults.

        Args:
            page: Playwright Page object.
            defaults: Suite-level defaults dict (timeout_ms, base_url, etc.).
            max_retries: Max retry attempts for retryable actions.
                Defaults to 2. Set to 0 to disable retries.
        """
        self.page = page
        self.defaults = defaults or {}
        self.timeout_ms = self.defaults.get("timeout_ms", self.DEFAULT_TIMEOUT_MS)
        self.max_retries = (
            max_retries if max_retries is not None
            else self.DEFAULT_MAX_RETRIES
        )

    def execute_case(self, case):
        """Execute all steps and assertions for a test case.

        Raises ExecutionError with context on any step or assertion failure.
        Retryable actions (CLICK, TYPE, WAIT, ASSERT) are automatically
        retried up to max_retries times.
        """
        steps = case.get("steps", [])
        asserts = case.get("asserts", [])

        for i, step in enumerate(steps):
            action = (step.get("action") or "").upper()
            retries = self.max_retries if action in RETRYABLE_ACTIONS else 0

            try:
                self._execute_with_retry(
                    lambda s=step: self.execute_step(s),
                    max_retries=retries,
                )
            except Exception as exc:
                raise ExecutionError(
                    str(exc),
                    step_index=i,
                    action=action,
                    selector=step.get("selector"),
                    retries_attempted=retries,
                ) from exc

        for i, assertion in enumerate(asserts):
            try:
                self._execute_with_retry(
                    lambda a=assertion: self.execute_assert(a),
                    max_retries=self.max_retries,
                )
            except Exception as exc:
                raise ExecutionError(
                    str(exc),
                    step_index=len(steps) + i,
                    action="ASSERT",
                    selector=assertion.get("selector"),
                    retries_attempted=self.max_retries,
                ) from exc

    def _execute_with_retry(self, fn, max_retries=0):
        """Execute a callable with retry and exponential backoff.

        Args:
            fn: Zero-arg callable to execute.
            max_retries: Maximum number of retry attempts (0 = no retries).

        Raises:
            The last exception if all attempts fail.
        """
        for attempt in range(max_retries + 1):
            try:
                return fn()
            except Exception:
                if attempt < max_retries:
                    delay_ms = RETRY_BASE_DELAY_MS * (2 ** attempt)
                    time.sleep(delay_ms / 1000.0)
                    continue
                raise

    def execute_step(self, step):
        """Execute a single YAML step definition."""
        action = step.get("action", "").upper()
        timeout = step.get("timeout_ms", self.timeout_ms)

        handlers = {
            "NAVIGATE": self._navigate,
            "CLICK": self._click,
            "TYPE": self._type,
            "SELECT": self._select,
            "WAIT": self._wait,
        }

        handler = handlers.get(action)
        if not handler:
            raise ExecutionError(f"Unknown action type: {action}")
        handler(step, timeout)

    def execute_assert(self, assertion):
        """Execute a single YAML assertion definition."""
        assert_type = assertion.get("type", "").lower()

        handlers = {
            "text_contains": self._assert_text_contains,
            "text_equals": self._assert_text_equals,
            "url_contains": self._assert_url_contains,
            "url_equals": self._assert_url_equals,
            "element_visible": self._assert_element_visible,
            "element_not_visible": self._assert_element_not_visible,
            "element_count": self._assert_element_count,
            "attribute_equals": self._assert_attribute_equals,
        }

        handler = handlers.get(assert_type)
        if not handler:
            raise ExecutionError(f"Unknown assertion type: {assert_type}")
        handler(assertion)

    # --- Action Handlers ---

    def _navigate(self, step, timeout):
        """NAVIGATE → page.goto(url)."""
        url = step.get("url", "")
        base_url = self.defaults.get("base_url", "")
        if url.startswith("/") and base_url:
            url = base_url.rstrip("/") + url
        self.page.goto(url, timeout=timeout)

    def _click(self, step, timeout):
        """CLICK → page.locator(selector).click()."""
        locator_str = resolve_selector(step.get("selector", {}))
        self.page.locator(locator_str).click(timeout=timeout)

    def _type(self, step, timeout):
        """TYPE → page.locator(selector).fill(value)."""
        locator_str = resolve_selector(step.get("selector", {}))
        value = step.get("input", "")
        self.page.locator(locator_str).fill(value, timeout=timeout)

    def _select(self, step, timeout):
        """SELECT → page.locator(selector).select_option(value)."""
        locator_str = resolve_selector(step.get("selector", {}))
        value = step.get("value", "")
        self.page.locator(locator_str).select_option(value, timeout=timeout)

    def _wait(self, step, timeout):
        """WAIT → locator.wait_for() or page.wait_for_timeout(ms)."""
        selector = step.get("selector")
        if selector:
            locator_str = resolve_selector(selector)
            self.page.locator(locator_str).wait_for(timeout=timeout)
        else:
            wait_ms = step.get("timeout_ms", timeout)
            self.page.wait_for_timeout(wait_ms)

    # --- Assertion Handlers (Section 7.3) ---

    def _assert_text_contains(self, assertion):
        locator_str = resolve_selector(assertion.get("selector", {}))
        expected = assertion.get("expected", "")
        text = self.page.locator(locator_str).text_content(timeout=self.timeout_ms)
        if expected not in (text or ""):
            raise AssertionError(
                f"text_contains: expected '{expected}' in '{text}'"
            )

    def _assert_text_equals(self, assertion):
        locator_str = resolve_selector(assertion.get("selector", {}))
        expected = assertion.get("expected", "")
        text = self.page.locator(locator_str).text_content(timeout=self.timeout_ms)
        if (text or "").strip() != expected:
            raise AssertionError(
                f"text_equals: expected '{expected}' but got '{text}'"
            )

    def _assert_url_contains(self, assertion):
        expected = assertion.get("expected", "")
        current = self.page.url
        if expected not in current:
            raise AssertionError(
                f"url_contains: expected '{expected}' in '{current}'"
            )

    def _assert_url_equals(self, assertion):
        expected = assertion.get("expected", "")
        current = self.page.url
        if current != expected:
            raise AssertionError(
                f"url_equals: expected '{expected}' but got '{current}'"
            )

    def _assert_element_visible(self, assertion):
        locator_str = resolve_selector(assertion.get("selector", {}))
        if not self.page.locator(locator_str).is_visible(timeout=self.timeout_ms):
            raise AssertionError(
                f"element_visible: '{locator_str}' is not visible"
            )

    def _assert_element_not_visible(self, assertion):
        locator_str = resolve_selector(assertion.get("selector", {}))
        if self.page.locator(locator_str).is_visible():
            raise AssertionError(
                f"element_not_visible: '{locator_str}' is visible"
            )

    def _assert_element_count(self, assertion):
        locator_str = resolve_selector(assertion.get("selector", {}))
        expected = int(assertion.get("expected", 0))
        actual = self.page.locator(locator_str).count()
        if actual != expected:
            raise AssertionError(
                f"element_count: expected {expected} but found {actual} "
                f"for '{locator_str}'"
            )

    def _assert_attribute_equals(self, assertion):
        locator_str = resolve_selector(assertion.get("selector", {}))
        attribute = assertion.get("attribute", "")
        expected = assertion.get("expected", "")
        actual = self.page.locator(locator_str).get_attribute(
            attribute, timeout=self.timeout_ms
        )
        if actual != expected:
            raise AssertionError(
                f"attribute_equals: '{attribute}' expected '{expected}' "
                f"but got '{actual}'"
            )

# Note: resolve_selector is imported from .selectors (Phase 4)
