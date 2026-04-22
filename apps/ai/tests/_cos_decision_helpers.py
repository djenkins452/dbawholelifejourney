"""
Shared assertions for the Phase 19 CoS decision-layer response shape.

After Phase 19 the deterministic router no longer emits the old
``Do this next: ... / Reason: ... / Priority: ...`` layout. The new
contract is a 2-4 line CoS-style response:

    Take your Magnesium and Metformin now — both are quick and overdue.
    Then shut it down for the night so tomorrow starts clean.

Tests previously asserted on the old markers. This helper captures the
new "Action-First" contract so individual test files can share one
check instead of duplicating assertions.
"""

from __future__ import annotations

from typing import Iterable, Optional, Union

_FORBIDDEN_OLD_MARKERS = (
    "Do this next:",
    "Your priority is:",
    "Reason:\n",
    "\nReason:\n",
    "Priority:",
)


def assert_cos_action_first(
    testcase,
    resp,
    *,
    must_contain: Optional[Union[str, Iterable[str]]] = None,
    must_not_contain: Optional[Union[str, Iterable[str]]] = None,
    allow_old_markers: bool = False,
):
    """
    Assert a CoS decision response matches the Phase 19 contract.

    The response must:
    * be a non-empty string,
    * not contain legacy layout markers (Do this next: / Reason: / Priority:),
    * optionally contain every ``must_contain`` needle,
    * optionally exclude every ``must_not_contain`` needle.

    Pass ``allow_old_markers=True`` only for tests that explicitly
    validate the old format was not enabled (rare).
    """
    testcase.assertIsNotNone(resp, "response was None")
    testcase.assertIsInstance(resp, str)
    testcase.assertTrue(resp.strip(), "response must not be empty")

    if not allow_old_markers:
        for marker in _FORBIDDEN_OLD_MARKERS:
            testcase.assertNotIn(
                marker, resp,
                f"legacy marker {marker!r} found in Phase 19 response",
            )

    if must_contain is not None:
        needles = [must_contain] if isinstance(must_contain, str) else list(must_contain)
        for needle in needles:
            testcase.assertIn(
                needle, resp,
                f"expected {needle!r} in response, got: {resp!r}",
            )

    if must_not_contain is not None:
        needles = [must_not_contain] if isinstance(must_not_contain, str) else list(must_not_contain)
        for needle in needles:
            testcase.assertNotIn(
                needle, resp,
                f"did not expect {needle!r} in response, got: {resp!r}",
            )
