# ==============================================================================
# File: apps/core/tests/test_execution_decision_authority_contract.py
# Project: Whole Life Journey - Django 5.x Personal Wellness/Journaling App
# Description: CI CONTRACT — exactly ONE deterministic producer of "what should I
#              do right now?". Fails the build if any surface grows its own
#              prioritization / ordering / next-action selection.
# ==============================================================================
"""
Execution Decision Authority contract.

There must be exactly ONE deterministic producer of the current recommended action
("what should I do right now?"): `apps.core.execution.decision_authority.current_action`,
over `build_execution_state` + `selectors.get_next_action`, with the ordering library in
`apps.core.decision_engine.action_prioritizer`. Every other surface — dashboard,
check-ins, OpenAI, notifications, voice, widgets, executive summaries — is a CONSUMER:
it may FORMAT the decision but must never re-derive, re-order, or re-select it.

This test makes that structural. It fails CI if:
  1. A decision primitive is defined outside the decision packages.
  2. A consumer imports/uses a low-level decision primitive
     (`prioritize_execution_items`, `classify_urgency`, `URGENCY_ORDER`) instead of
     consuming the authority (`current_action` / `build_execution_state`).
  3. The check-in renderer stops consuming the authority (regression guard for the
     duplicate-engine bug where the dashboard and a check-in disagreed).

Display-only helpers (`group_actions`, `find_next_upcoming`, `build_grouped_action_center`)
arrange an already-decided list and are allowed in consumers.

Rationale + design: `apps/core/execution/decision_authority.py`.
"""

import re
from pathlib import Path

from django.conf import settings
from django.test import SimpleTestCase

_ROOT = Path(settings.BASE_DIR)
_APPS = _ROOT / "apps"

# The ONLY packages allowed to define/use the low-level decision machinery.
_DECISION_PKGS = ("apps/core/execution/", "apps/core/decision_engine/")

# Low-level DECISION primitives. Using any of these outside the decision packages means
# a surface is making its own prioritization/selection — the class we are eliminating.
_BANNED_IN_CONSUMERS = ("prioritize_execution_items", "classify_urgency", "URGENCY_ORDER")


def _rel(p: Path) -> str:
    return str(p.relative_to(_ROOT))


def _in_decision_pkg(p: Path) -> bool:
    r = _rel(p)
    return any(pkg in r for pkg in _DECISION_PKGS)


def _source_files():
    """All non-test, non-migration app source files."""
    for p in _APPS.rglob("*.py"):
        s = _rel(p)
        if "/migrations/" in s or "/tests/" in s or "__pycache__" in s:
            continue
        if p.name.startswith("test_") or p.name == "conftest.py":
            continue
        yield p


class ExecutionDecisionAuthorityContractTests(SimpleTestCase):

    def test_decision_primitives_defined_only_in_authority(self):
        """get_next_action / prioritize_execution_items / classify_urgency / URGENCY_ORDER
        may be DEFINED in exactly one place each — the decision packages."""
        found = {
            "def get_next_action": [],
            "def prioritize_execution_items": [],
            "def classify_urgency": [],
            "URGENCY_ORDER =": [],
        }
        for p in _source_files():
            text = p.read_text(encoding="utf-8", errors="ignore")
            for key in ("def get_next_action", "def prioritize_execution_items",
                        "def classify_urgency"):
                if re.search(rf"^{re.escape(key)}\b", text, re.M):
                    found[key].append(_rel(p))
            if re.search(r"^URGENCY_ORDER\s*=", text, re.M):
                found["URGENCY_ORDER ="].append(_rel(p))

        self.assertEqual(
            found["def get_next_action"], ["apps/core/execution/selectors.py"],
            f"get_next_action must be defined ONLY in the authority: {found['def get_next_action']}",
        )
        for key in ("def prioritize_execution_items", "def classify_urgency", "URGENCY_ORDER ="):
            self.assertEqual(
                found[key], ["apps/core/decision_engine/action_prioritizer.py"],
                f"{key} must be defined ONLY in the prioritizer library: {found[key]}",
            )

    def test_consumers_do_not_reimplement_prioritization(self):
        """No surface outside the decision packages may use the low-level decision
        primitives. Consume `current_action(user)` / `build_execution_state(user)` instead."""
        violations = []
        for p in _source_files():
            if _in_decision_pkg(p):
                continue
            text = p.read_text(encoding="utf-8", errors="ignore")
            for banned in _BANNED_IN_CONSUMERS:
                if banned in text:
                    violations.append(f"{_rel(p)} references '{banned}'")
        self.assertEqual(
            violations, [],
            "These surfaces re-implement prioritization instead of consuming the single "
            "Execution Decision Authority (apps/core/execution/decision_authority.py). "
            "Call current_action(user) or build_execution_state(user):\n  "
            + "\n  ".join(violations),
        )

    def test_checkin_renderer_consumes_the_authority(self):
        """Regression guard: the check-in renderer must consume the canonical decision,
        never select its own (the 2026-07 duplicate-engine bug where a check-in
        recommended a lower-priority item than the dashboard's LATE workout)."""
        src = (_APPS / "ai" / "beth_checkin_renderer.py").read_text(
            encoding="utf-8", errors="ignore",
        )
        self.assertIn(
            "current_action", src,
            "beth_checkin_renderer must consume ctx['current_action'] from the authority.",
        )
        self.assertNotIn(
            "actionable.sort", src,
            "beth_checkin_renderer must NOT re-order actions — that is the authority's job.",
        )
