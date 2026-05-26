# ==============================================================================
# File: apps/ai/tests/test_escalation_directive.py
# Project: Whole Life Journey - Django 5.x Personal Wellness/Journaling App
# Description: Regression tests for the deterministic escalation directive
#              that produced the "Drop this and go to Fish Oil now" trust bug
#              on 2026-05-26.
# Owner: Danny Jenkins (admin@wholelifejourney.com)
# Created: 2026-05-26
# ==============================================================================
"""
Escalation directive regression tests.

Background: at 3:08 PM Beth told the user "Drop this and go to Fish Oil now"
when Fish Oil was scheduled for 6:00 PM and not actionable for hours. Root
cause was in `compute_escalation_level` / `_build_escalation_directive`:
`at_risk_item` was assigned unconditionally from `next_anchor_name`, so
drift-driven CRITICAL escalation falsely implicated far-future anchors.

Fix: `at_risk_item` is now gated by `_ANCHOR_AT_RISK_WINDOW_MINUTES` (45).
Anchors beyond that window are not "at risk" — the directive falls through
to a generic CRITICAL message that does NOT name a far-future item.

These tests lock the fix in CI. Test 7 is the permanent regression guard
for the exact 3 PM / 6 PM Fish Oil scenario.
"""

from datetime import datetime, timedelta, timezone as dt_timezone

from django.test import SimpleTestCase

from apps.ai.beth_checkin_renderer import (
    ESCALATION_CRITICAL,
    ESCALATION_NUDGE,
    ESCALATION_ON_TRACK,
    ESCALATION_PRESSING,
    _ANCHOR_AT_RISK_WINDOW_MINUTES,
    _build_escalation_directive,
    compute_buffer_minutes,
    compute_escalation_level,
)


def _now():
    """Fixed test 'now' in UTC for deterministic minutes math."""
    return datetime(2026, 5, 26, 15, 8, 0, tzinfo=dt_timezone.utc)


def _item(name, minutes_from_now, *, completed=False, source=""):
    """Build a Today Engine item dict for compute_* functions."""
    return {
        "name": name,
        "scheduled_time": _now() + timedelta(minutes=minutes_from_now),
        "completed": completed,
        "source": source,
    }


def _signals(*, drift_minutes=0, buffer_minutes_available=120,
             can_recover=True, next_anchor=None, schedule_status="on_track",
             expected_item=None):
    """Build a schedule_signals dict for compute_escalation_level."""
    return {
        "drift_minutes": drift_minutes,
        "buffer_minutes_available": buffer_minutes_available,
        "can_recover": can_recover,
        "next_anchor": next_anchor,
        "schedule_status": schedule_status,
        "expected_item": expected_item,
    }


# ──────────────────────────────────────────────────────────────────────
# Trust-critical regression tests for at_risk_item gating
# ──────────────────────────────────────────────────────────────────────


class TestAtRiskItemGating(SimpleTestCase):
    """Validate that far-future anchors are not declared at_risk."""

    def test_drop_this_never_fires_for_far_future_anchor(self):
        """Drift-driven CRITICAL must NOT cite a far-future anchor.

        Scenario: user is 50 minutes behind on something earlier; the
        next medication anchor (Fish Oil) is 172 minutes away. Escalation
        is correctly CRITICAL, but the directive must NOT say
        "Drop this and go to Fish Oil now."
        """
        all_items = [
            _item("Fish Oil", minutes_from_now=172, source="medication"),
        ]
        signals = _signals(drift_minutes=50, next_anchor="Fish Oil")
        result = compute_escalation_level(signals, all_items, _now())

        self.assertEqual(result["level"], ESCALATION_CRITICAL)
        self.assertIsNone(
            result["at_risk_item"],
            "at_risk_item must be None when next_anchor is beyond the "
            f"{_ANCHOR_AT_RISK_WINDOW_MINUTES}-min actionable window.",
        )
        self.assertNotIn("Fish Oil", result["directive"])
        self.assertNotIn("Drop this and go", result["directive"])

    def test_drop_this_fires_for_imminent_anchor_with_drift(self):
        """Legitimate case preserved: imminent anchor + drift = directive.

        Scenario: anchor is 20 minutes away (within 45-min window) and
        drift is 25 min. CRITICAL fires via the anchor-proximate path,
        directive should name the anchor.
        """
        all_items = [
            _item("Mounjaro", minutes_from_now=20, source="medication"),
        ]
        signals = _signals(drift_minutes=25, next_anchor="Mounjaro",
                           can_recover=False)
        result = compute_escalation_level(signals, all_items, _now())

        # Anchor is within window AND there is drift → at_risk_item set.
        self.assertEqual(result["at_risk_item"], "Mounjaro")
        # PRESSING (drift 25 + anchor within pressing) is acceptable;
        # CRITICAL requires anchor within 10 min. Either way the directive
        # should reference the anchor by name.
        self.assertIn(result["level"], (ESCALATION_PRESSING, ESCALATION_CRITICAL))
        self.assertIn("Mounjaro", result["directive"])

    def test_no_directive_when_on_track(self):
        """Zero drift → ON_TRACK → empty directive regardless of anchor.

        Even if a medication anchor is imminent, no drift means no
        urgency. Beth must not invent it.
        """
        all_items = [
            _item("Mounjaro", minutes_from_now=15, source="medication"),
        ]
        signals = _signals(drift_minutes=0, next_anchor="Mounjaro")
        result = compute_escalation_level(signals, all_items, _now())

        self.assertEqual(result["level"], ESCALATION_ON_TRACK)
        self.assertEqual(result["directive"], "")

    def test_pressing_directive_only_fires_when_anchor_proximate(self):
        """PRESSING with far anchor must use generic phrasing, not name item.

        Scenario: drift = 25 (PRESSING threshold), next anchor 120 min away.
        Should fall through to "You're behind — focus on what's next."
        without naming Fish Oil.
        """
        all_items = [
            _item("Fish Oil", minutes_from_now=120, source="medication"),
        ]
        signals = _signals(drift_minutes=25, next_anchor="Fish Oil")
        result = compute_escalation_level(signals, all_items, _now())

        # Drift 25 >= _DRIFT_PRESSING_MINUTES (20) → PRESSING. Not CRITICAL
        # because drift < 40 and anchor not imminent.
        self.assertEqual(result["level"], ESCALATION_PRESSING)
        self.assertIsNone(result["at_risk_item"])
        self.assertNotIn("Fish Oil", result["directive"])
        self.assertIn("focus on what's next", result["directive"].lower())

    def test_critical_with_far_anchor_uses_generic_directive(self):
        """Drift-only CRITICAL with far anchor → generic safe directive."""
        all_items = [
            _item("Fish Oil", minutes_from_now=180, source="medication"),
        ]
        signals = _signals(drift_minutes=55, next_anchor="Fish Oil",
                           can_recover=False)
        result = compute_escalation_level(signals, all_items, _now())

        self.assertEqual(result["level"], ESCALATION_CRITICAL)
        self.assertIsNone(result["at_risk_item"])
        self.assertEqual(
            result["directive"],
            "You need to act now — plan is at serious risk.",
        )

    def test_compute_buffer_minutes_still_finds_next_anchor(self):
        """The fix must NOT break next_anchor population for other consumers.

        compute_buffer_minutes still returns next_anchor even for far-future
        medications — only at_risk_item assignment in compute_escalation_level
        is gated. Other display/buffer code can still see the anchor name.
        """
        all_items = [
            _item("Fish Oil", minutes_from_now=172, source="medication"),
        ]
        buffer = compute_buffer_minutes(all_items, _now())
        self.assertEqual(buffer["next_anchor"], "Fish Oil")


class TestDirectiveBuilderBoundary(SimpleTestCase):
    """Direct test of _build_escalation_directive boundary semantics."""

    def test_critical_with_at_risk_item_none_returns_generic(self):
        """When at_risk_item=None at CRITICAL level, returns the generic
        directive that does not name any specific item."""
        directive = _build_escalation_directive(
            level=ESCALATION_CRITICAL,
            drift_min=55,
            buffer_min=0,
            can_recover=False,
            at_risk_item=None,
            minutes_to_anchor=172,
        )
        self.assertEqual(
            directive,
            "You need to act now — plan is at serious risk.",
        )
        self.assertNotIn("Drop this and go", directive)


# ──────────────────────────────────────────────────────────────────────
# PERMANENT REGRESSION GUARD — the exact 3:08 PM Fish Oil scenario
# from the 2026-05-26 trust-bug investigation.
# If this test ever fails, the trust contract has regressed.
# ──────────────────────────────────────────────────────────────────────


class TestFishOilAt3PmPermanentGuard(SimpleTestCase):
    """Permanent CI guard for the exact incident that triggered this PR.

    Scenario verbatim from the 2026-05-26 bug report:
      - Current time: 15:08
      - Fish Oil:         18:00 (172 min away)
      - Magnesium citrate: 18:00
      - Log Nutrition:     18:00
      - Empty Dishwasher:  18:30
      - Journal:           20:00
      - User has drift from earlier missed items pushing escalation to
        CRITICAL via the drift-only path.

    Required behavior: Beth must NOT say "Drop this and go to Fish Oil now."
    She may still acknowledge drift; she may not name a 3-hour-out
    supplement as the urgent thing.
    """

    def test_no_drop_this_for_fish_oil_when_3hr_away(self):
        all_items = [
            _item("Fish Oil", minutes_from_now=172, source="medication"),
            _item("Magnesium citrate", minutes_from_now=172, source="medication"),
            _item("Log Nutrition", minutes_from_now=172, source="task"),
            _item("Empty Dishwasher", minutes_from_now=202, source="task"),
            _item("Journal", minutes_from_now=292, source="task"),
        ]
        signals = _signals(
            drift_minutes=50,        # 50 min behind — CRITICAL via drift path
            buffer_minutes_available=30,
            can_recover=False,
            next_anchor="Fish Oil",  # buffer compute picks first medication
        )
        result = compute_escalation_level(signals, all_items, _now())

        # Escalation should be CRITICAL (drift >= 40).
        self.assertEqual(result["level"], ESCALATION_CRITICAL)

        # But the directive MUST NOT cite Fish Oil — it is 172 min away,
        # far beyond the 45-min actionable window.
        self.assertNotIn("Fish Oil", result["directive"])
        self.assertNotIn("Drop this and go", result["directive"])
        self.assertNotIn("Magnesium", result["directive"])
        self.assertNotIn("Empty Dishwasher", result["directive"])

        # Verify the safe fallback fires.
        self.assertEqual(
            result["directive"],
            "You need to act now — plan is at serious risk.",
        )

        # at_risk_item is reported as None to downstream consumers.
        self.assertIsNone(result["at_risk_item"])
