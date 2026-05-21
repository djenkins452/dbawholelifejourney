"""
WLJ Visual Truth Contract — enforcement test.

This test is the codified version of the architecture rule documented at
`docs/WLJ_VISUAL_TRUTH_CONTRACT.md`:

  > The homepage UI must NEVER visually imply completion for items that
  > are not actually completed. Strike-through, "done" colours, and any
  > completion-resembling treatment are RESERVED for items where
  > `item.completed == True`.

It exists because of the 2026-05-20 incident: a single CSS rule
(`.v2-ac-item-expired .v2-ac-item-title { text-decoration: line-through }`
in `static/css/dashboard_v2.css`) applied strike-through to items that
were past their window but NOT completed. The data layer (DB → execution
truth → CoS) correctly reported these items as incomplete. The homepage
visually claimed they were done. CoS and homepage disagreed about the
state of the user's day — the deepest possible trust violation. The fix
removed the offending CSS declaration; this test ensures no future edit
can silently re-introduce strike-through (or any equivalent completion
signal) on a non-completion-gated selector in the Action Center.

Scope: this test guards the homepage Action Center stylesheet
(`static/css/dashboard_v2.css`). Other domain stylesheets (life, health,
assistant-panel, etc.) have their own contracts which were audited at the
time of the 2026-05-20 incident and found to be correctly gated on
`.completed` / `.skipped` / `{% if checked %}`. If those audits drift, a
sibling test should be added — this test does NOT pretend to cover them.

The test deliberately uses simple substring/regex parsing rather than a
full CSS AST library. The contract we're enforcing is narrow enough
that a parser dependency would be more risk than value. If you find
yourself needing to suppress a false positive, add to ALLOWED_SELECTORS
with a comment explaining WHY the selector is a legitimate completion
signal — never relax the check.
"""

import re
from pathlib import Path

from django.test import SimpleTestCase

# Absolute path to the homepage Action Center stylesheet.
_REPO_ROOT = Path(__file__).resolve().parent.parent.parent.parent
_DASHBOARD_V2_CSS = _REPO_ROOT / "static" / "css" / "dashboard_v2.css"

# Selectors that ARE allowed to declare completion-resembling visuals
# (strike-through, "completed" colours, etc.). Each entry must be gated
# on an actual completion signal in the template layer — i.e. the class
# is only applied when `item.completed`, `is_completed`, `taken`,
# `all_complete`, `all_taken`, or an equivalent boolean is True.
#
# When adding to this list, document WHY the selector is gated on real
# completion. The audit you should do: grep the codebase for the
# selector's class and verify every template application is conditional
# on a completion signal from the data layer.
_ALLOWED_COMPLETION_SELECTORS = {
    # Generic strike-through utility — template applies it only on a
    # completion boolean (e.g., `{% if item.completed %} v2-strikethrough{% endif %}`
    # at templates/dashboard_v2/partials/_action_item_v2.html:36, 38).
    ".v2-strikethrough",
    # Link variant of the strike-through utility — same gating pattern.
    ".v2-action-title-link.v2-strikethrough",
}

# Patterns that indicate a "this item looks done" visual. Any CSS
# declaration matching one of these is treated as a completion signal
# and the enclosing selector MUST be in the allowlist above.
_COMPLETION_VISUAL_PATTERNS = [
    # Strike-through in any form. line-through is the canonical
    # "this is done" visual; reserved for actual completion.
    re.compile(r"text-decoration\s*:\s*[^;]*line-through", re.IGNORECASE),
]


def _read_css() -> str:
    """Read the homepage Action Center stylesheet."""
    assert _DASHBOARD_V2_CSS.is_file(), (
        f"Expected dashboard_v2.css at {_DASHBOARD_V2_CSS} but file not found. "
        "If the stylesheet has moved, update _DASHBOARD_V2_CSS in this test."
    )
    return _DASHBOARD_V2_CSS.read_text()


def _iter_rule_blocks(css_text: str):
    """Yield (selector, body) tuples for every top-level CSS rule.

    Intentionally simple. Does not handle nested at-rules with their own
    blocks (e.g., @media containing rules) — those edge cases would
    require a real parser. The Action Center stylesheet is flat enough
    that this is fine for our contract. If we ever start nesting rules
    inside @media for this stylesheet, this test must be upgraded.
    """
    # Strip /* ... */ comments first to avoid matching declarations
    # commented out (or example code inside comment blocks).
    no_comments = re.sub(r"/\*.*?\*/", "", css_text, flags=re.DOTALL)

    # Match: <anything-but-{> { <anything-but-}> }
    # The selector may span multiple lines, so use DOTALL on the selector.
    pattern = re.compile(r"([^{}]+)\{([^{}]*)\}", flags=re.DOTALL)
    for match in pattern.finditer(no_comments):
        selector = match.group(1).strip()
        body = match.group(2).strip()
        # Skip @-rule headers like "@media (max-width: …)" — those have
        # nested blocks our naive matcher caught as outer rules but the
        # body will look like nested CSS we don't want to parse here.
        if selector.startswith("@"):
            continue
        yield selector, body


class VisualTruthContractTests(SimpleTestCase):
    """Lock in the rule: only actual completion may visually look done."""

    def test_no_unauthorised_strikethrough_in_action_center_css(self):
        """Every CSS rule with text-decoration: line-through (or any
        equivalent completion-resembling declaration) must be on a
        selector that the template only applies when the underlying
        item is actually completed.

        See the 2026-05-20 incident in docs/wlj_claude_changelog.md and
        the contract doc at docs/WLJ_VISUAL_TRUTH_CONTRACT.md.
        """
        css = _read_css()
        violations = []
        for selector, body in _iter_rule_blocks(css):
            for pattern in _COMPLETION_VISUAL_PATTERNS:
                if pattern.search(body):
                    # Found a completion-resembling visual. The selector
                    # must be in the allowlist or this is a violation.
                    if selector not in _ALLOWED_COMPLETION_SELECTORS:
                        violations.append(
                            f"  selector={selector!r}\n"
                            f"  body=...{pattern.search(body).group(0)}..."
                        )

        if violations:
            self.fail(
                "WLJ Visual Truth Contract violation in static/css/dashboard_v2.css:\n"
                "The following selectors declare a completion-resembling visual "
                "(strike-through / 'done' styling) but are NOT in the completion-"
                "gated allowlist.\n\n"
                "Only `item.completed == True` may produce 'done' visuals. "
                "Past-window / behind / missed / recoverable / overdue items must "
                "communicate their state via badges, muted tone, left-rail rings, "
                "or subtle dimming — NEVER via completion-resembling treatments.\n\n"
                "See docs/WLJ_VISUAL_TRUTH_CONTRACT.md.\n\n"
                "Violations:\n" + "\n".join(violations) + "\n\n"
                "If you genuinely need a new completion-gated selector, add it to "
                "_ALLOWED_COMPLETION_SELECTORS in this test WITH a comment proving "
                "the template only applies the class on a completion signal."
            )

    def test_v2_ac_item_expired_does_not_declare_strikethrough(self):
        """Belt-and-suspenders for the specific 2026-05-20 incident
        site: the past-window item selector must NEVER declare
        strike-through, even if a future broader rule were to be added
        that accidentally captured it.

        This test names the exact site of the original violation so a
        regression here produces an obvious, actionable failure rather
        than a generic contract failure.
        """
        css = _read_css()
        for selector, body in _iter_rule_blocks(css):
            if ".v2-ac-item-expired" in selector:
                self.assertNotRegex(
                    body,
                    r"text-decoration\s*:\s*[^;]*line-through",
                    msg=(
                        f"Regression of the 2026-05-20 trust-breaking incident. "
                        f"Selector {selector!r} declares text-decoration: line-through. "
                        f"Past-window items are NOT completed. Strike-through is "
                        f"reserved for `item.completed == True`. See "
                        f"docs/WLJ_VISUAL_TRUTH_CONTRACT.md."
                    ),
                )

    def test_recovery_dim_opacity_is_humane(self):
        """`.v2-ac-recovery-dim` opacity must stay in a range that reads
        as 'lower priority, still actionable' — never 'already handled
        / dismissed'. 0.55 (the previous value) was psychologically too
        strong. Floor 0.70 ensures the item remains clearly present.
        """
        css = _read_css()
        match = re.search(
            r"\.v2-ac-recovery-dim\s*\{[^}]*opacity\s*:\s*([0-9.]+)",
            css,
        )
        self.assertIsNotNone(
            match,
            ".v2-ac-recovery-dim must declare an opacity (currently missing).",
        )
        opacity = float(match.group(1))
        self.assertGreaterEqual(
            opacity, 0.70,
            f".v2-ac-recovery-dim opacity={opacity} is too aggressive. "
            f"Values below 0.70 read as 'dismissed / handled' and break the "
            f"Visual Truth Contract for overdue-but-still-actionable items."
        )
        self.assertLessEqual(
            opacity, 0.95,
            f".v2-ac-recovery-dim opacity={opacity} is too close to fully opaque "
            f"to be visually distinct as de-emphasis. Keep it < 0.95 so the "
            f"de-emphasis is still perceptible."
        )
