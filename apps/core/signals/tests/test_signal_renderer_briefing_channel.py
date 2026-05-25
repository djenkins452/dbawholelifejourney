"""
Two-channel signal renderer tests (Phase 1A · C13).

This module exists to satisfy the Wave 4 hard guardrail:

    resolve_conflicts()              = unchanged behavior
    resolve_conflicts_for_briefing() = new additive behavior

Specifically asserts:

1. **Regression**: ``resolve_conflicts`` produces byte-identical
   output for a pinned set of inputs covering every existing
   behavior path (no foundational present, foundational suppresses
   same-domain non-foundational, cross-domain coexistence). If C13
   accidentally altered the existing function, these tests fail.

2. **New behavior**: ``resolve_conflicts_for_briefing`` adds positive/
   momentum exemption — a positive momentum signal in the same domain
   as a foundational risk signal SURVIVES. Cross-domain behavior is
   identical to ``resolve_conflicts``. Acute / risk signals behave
   exactly as before.

3. **Detection** of positive/momentum semantics works for both:
   - dict-shaped signals with `signal_class` or `severity == "positive"`
   - object-shaped signals (UnifiedSignal) with the same fields

Imports nothing from health_briefing — this is a pure signal-renderer
test, scoped to the signals app.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Optional

from django.test import SimpleTestCase

from apps.core.signals.signal_renderer import (
    resolve_conflicts,
    resolve_conflicts_for_briefing,
)


# ── Test fixtures ───────────────────────────────────────────────────


def _dict_signal(
    domain: str,
    type_: str,
    severity: str,
    *,
    signal_class: str = "risk",
    confidence: float = 0.8,
) -> dict:
    return {
        "domain": domain,
        "type": type_,
        "severity": severity,
        "signal_class": signal_class,
        "confidence": confidence,
        "action_text": "",
        "title": "ignored",
        "message": "ignored",
        "priority_score": 0.5,
        "created_at": datetime.now(timezone.utc),
    }


def _pool_item(
    signal: Any,
    *,
    domain: str,
    label: str,
    priority: str,
) -> dict:
    return {
        "signal": signal,
        "rendered": {
            "label": label,
            "message": "ignored",
            "action": "ignored",
            "priority": priority,
            "domain": domain,
        },
    }


@dataclass
class _ObjSignal:
    domain: str
    type: str
    severity: str
    signal_class: str = "risk"
    confidence: float = 0.8


# ── 1. resolve_conflicts() regression ───────────────────────────────


class ResolveConflictsRegressionTests(SimpleTestCase):
    """Byte-identical behavior pinning for the pre-C13 function. If
    any assertion in this class fails, the existing alerts-feed
    behavior has changed and Bible Journey / dashboard surfaces will
    silently shift."""

    def test_empty_pool_returns_empty(self):
        self.assertEqual(resolve_conflicts([]), [])

    def test_pool_with_no_foundational_returns_unchanged(self):
        a = _pool_item(
            _dict_signal("health", "weight_trend", "medium"),
            domain="health", label="Weight Trend", priority="important",
        )
        b = _pool_item(
            _dict_signal("life", "routine_break", "medium"),
            domain="life", label="Routine", priority="supporting",
        )
        pool = [a, b]
        result = resolve_conflicts(pool)
        # Same list, in same order, with same identity.
        self.assertEqual(len(result), 2)
        self.assertIs(result[0], a)
        self.assertIs(result[1], b)

    def test_foundational_suppresses_same_domain_non_foundational(self):
        # The canonical pre-C13 behavior: glucose_high (foundational)
        # in health domain suppresses weight_trend (important) in the
        # same domain.
        foundational = _pool_item(
            _dict_signal("health", "glucose_high", "high"),
            domain="health", label="Glucose Alert", priority="foundational",
        )
        important = _pool_item(
            _dict_signal("health", "weight_trend", "medium"),
            domain="health", label="Weight Trend", priority="important",
        )
        pool = [foundational, important]
        result = resolve_conflicts(pool)
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]["rendered"]["label"], "Glucose Alert")

    def test_foundational_suppresses_even_positive_momentum_in_same_domain(self):
        # This is the failure mode C13's NEW method fixes — but the
        # pre-C13 function still does it. Pin that behavior so we
        # know the alerts feed continues to do it.
        foundational = _pool_item(
            _dict_signal("health", "glucose_high", "high"),
            domain="health", label="Glucose Alert", priority="foundational",
        )
        momentum = _pool_item(
            _dict_signal(
                "health", "metabolic_improving", "positive",
                signal_class="momentum",
            ),
            domain="health", label="Metabolic Momentum", priority="important",
        )
        pool = [foundational, momentum]
        result = resolve_conflicts(pool)
        # Pre-C13 behavior: momentum is suppressed.
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]["rendered"]["label"], "Glucose Alert")

    def test_cross_domain_coexistence_preserved(self):
        # A foundational health signal does NOT suppress a foundational
        # life signal (different domain).
        health_foundational = _pool_item(
            _dict_signal("health", "glucose_high", "high"),
            domain="health", label="Glucose Alert", priority="foundational",
        )
        life_foundational = _pool_item(
            _dict_signal("life", "task_overdue", "high"),
            domain="life", label="Task Alert", priority="foundational",
        )
        pool = [health_foundational, life_foundational]
        result = resolve_conflicts(pool)
        self.assertEqual(len(result), 2)

    def test_cross_domain_lower_priority_survives_foundational(self):
        # Foundational in health does not suppress a non-foundational in life.
        health_foundational = _pool_item(
            _dict_signal("health", "glucose_high", "high"),
            domain="health", label="Glucose Alert", priority="foundational",
        )
        life_supporting = _pool_item(
            _dict_signal("life", "routine_break", "medium"),
            domain="life", label="Routine", priority="supporting",
        )
        pool = [health_foundational, life_supporting]
        result = resolve_conflicts(pool)
        self.assertEqual(len(result), 2)

    def test_multiple_foundationals_only_suppress_their_own_domain(self):
        health_f = _pool_item(
            _dict_signal("health", "glucose_high", "high"),
            domain="health", label="Glucose Alert", priority="foundational",
        )
        life_f = _pool_item(
            _dict_signal("life", "task_overdue", "high"),
            domain="life", label="Task Alert", priority="foundational",
        )
        health_imp = _pool_item(
            _dict_signal("health", "weight_trend", "medium"),
            domain="health", label="Weight", priority="important",
        )
        life_sup = _pool_item(
            _dict_signal("life", "routine_break", "low"),
            domain="life", label="Routine", priority="supporting",
        )
        pool = [health_f, life_f, health_imp, life_sup]
        result = resolve_conflicts(pool)
        # Both health and life have foundationals; both non-foundationals
        # in those domains are dropped.
        labels = {item["rendered"]["label"] for item in result}
        self.assertEqual(labels, {"Glucose Alert", "Task Alert"})


# ── 2. resolve_conflicts_for_briefing() — new behavior ─────────────


class ResolveConflictsForBriefingTests(SimpleTestCase):
    """C13 additive method: positive/momentum signals coexist with
    same-domain foundational risk signals in the briefing channel."""

    def test_positive_momentum_signal_survives_same_domain_foundational(self):
        # The exact failure mode the Phase 0 review flagged. The new
        # method admits the momentum signal alongside the foundational
        # risk signal — both surface in the briefing channel.
        foundational = _pool_item(
            _dict_signal("health", "glucose_high", "high"),
            domain="health", label="Glucose Alert", priority="foundational",
        )
        momentum = _pool_item(
            _dict_signal(
                "health", "metabolic_improving", "positive",
                signal_class="momentum",
            ),
            domain="health", label="Metabolic Momentum", priority="important",
        )
        pool = [foundational, momentum]
        result = resolve_conflicts_for_briefing(pool)
        labels = {item["rendered"]["label"] for item in result}
        self.assertEqual(labels, {"Glucose Alert", "Metabolic Momentum"})

    def test_severity_positive_signal_survives_same_domain_foundational(self):
        # Some legacy producers only set severity="positive" without
        # explicitly setting signal_class. The exemption must catch them.
        foundational = _pool_item(
            _dict_signal("health", "glucose_high", "high"),
            domain="health", label="Glucose Alert", priority="foundational",
        )
        positive = _pool_item(
            _dict_signal(
                "health", "weight_loss_positive", "positive",
                signal_class="risk",  # producer forgot to set it
            ),
            domain="health", label="Weight Trend", priority="important",
        )
        pool = [foundational, positive]
        result = resolve_conflicts_for_briefing(pool)
        labels = {item["rendered"]["label"] for item in result}
        self.assertEqual(labels, {"Glucose Alert", "Weight Trend"})

    def test_non_positive_non_momentum_still_suppressed(self):
        # A regular risk signal in the same domain is still suppressed —
        # the exemption is specifically for positive/momentum, not all.
        foundational = _pool_item(
            _dict_signal("health", "glucose_high", "high"),
            domain="health", label="Glucose Alert", priority="foundational",
        )
        risk = _pool_item(
            _dict_signal(
                "health", "blood_pressure_elevated", "medium",
                signal_class="risk",
            ),
            domain="health", label="BP Alert", priority="important",
        )
        pool = [foundational, risk]
        result = resolve_conflicts_for_briefing(pool)
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]["rendered"]["label"], "Glucose Alert")

    def test_object_signal_with_momentum_class_exempted(self):
        # UnifiedSignal-shape (object with attributes). Pin that
        # detection works without depending on dict-keys.
        foundational = _pool_item(
            _ObjSignal(
                domain="health", type="glucose_high",
                severity="high", signal_class="risk",
            ),
            domain="health", label="Glucose Alert", priority="foundational",
        )
        momentum = _pool_item(
            _ObjSignal(
                domain="health", type="metabolic_momentum",
                severity="positive", signal_class="momentum",
            ),
            domain="health", label="Metabolic Momentum", priority="important",
        )
        pool = [foundational, momentum]
        result = resolve_conflicts_for_briefing(pool)
        labels = {item["rendered"]["label"] for item in result}
        self.assertEqual(labels, {"Glucose Alert", "Metabolic Momentum"})

    def test_opportunity_class_also_exempted(self):
        foundational = _pool_item(
            _dict_signal("health", "glucose_high", "high"),
            domain="health", label="Glucose Alert", priority="foundational",
        )
        opp = _pool_item(
            _dict_signal(
                "health", "exercise_opportunity", "low",
                signal_class="opportunity",
            ),
            domain="health", label="Exercise Tip", priority="important",
        )
        pool = [foundational, opp]
        result = resolve_conflicts_for_briefing(pool)
        labels = {item["rendered"]["label"] for item in result}
        self.assertEqual(labels, {"Glucose Alert", "Exercise Tip"})

    def test_cross_domain_unchanged_from_resolve_conflicts(self):
        # Cross-domain behavior is identical in both channels: a
        # foundational health signal does not affect life signals.
        health_f = _pool_item(
            _dict_signal("health", "glucose_high", "high"),
            domain="health", label="Glucose Alert", priority="foundational",
        )
        life_sup = _pool_item(
            _dict_signal("life", "routine_break", "low"),
            domain="life", label="Routine", priority="supporting",
        )
        pool = [health_f, life_sup]
        alerts_result = resolve_conflicts(list(pool))
        briefing_result = resolve_conflicts_for_briefing(list(pool))
        self.assertEqual(
            [it["rendered"]["label"] for it in alerts_result],
            [it["rendered"]["label"] for it in briefing_result],
        )

    def test_no_foundational_pool_returned_unchanged(self):
        # Same fast-path as resolve_conflicts(): no foundational →
        # nothing to suppress, return pool intact.
        a = _pool_item(
            _dict_signal(
                "health", "metabolic_improving", "positive",
                signal_class="momentum",
            ),
            domain="health", label="Metabolic Momentum", priority="important",
        )
        b = _pool_item(
            _dict_signal("life", "routine_break", "low"),
            domain="life", label="Routine", priority="supporting",
        )
        pool = [a, b]
        result = resolve_conflicts_for_briefing(pool)
        self.assertEqual(len(result), 2)


# ── 3. Two-channel divergence ───────────────────────────────────────


class TwoChannelDivergenceTests(SimpleTestCase):
    """The whole point of C13: same pool, different channels, different
    results. Pin the exact divergence so a future refactor that
    accidentally merges the two functions fails loudly."""

    def test_alerts_suppresses_momentum_but_briefing_keeps_it(self):
        pool = [
            _pool_item(
                _dict_signal("health", "glucose_high", "high"),
                domain="health", label="Glucose Alert",
                priority="foundational",
            ),
            _pool_item(
                _dict_signal(
                    "health", "metabolic_improving", "positive",
                    signal_class="momentum",
                ),
                domain="health", label="Metabolic Momentum",
                priority="important",
            ),
        ]
        alerts = resolve_conflicts(list(pool))
        briefing = resolve_conflicts_for_briefing(list(pool))
        self.assertEqual(len(alerts), 1)
        self.assertEqual(len(briefing), 2)
        self.assertEqual(alerts[0]["rendered"]["label"], "Glucose Alert")
        self.assertEqual(
            {it["rendered"]["label"] for it in briefing},
            {"Glucose Alert", "Metabolic Momentum"},
        )

    def test_no_divergence_when_no_momentum_signals(self):
        # If no positive/momentum signal exists, the two channels
        # produce identical output.
        pool = [
            _pool_item(
                _dict_signal("health", "glucose_high", "high"),
                domain="health", label="Glucose Alert",
                priority="foundational",
            ),
            _pool_item(
                _dict_signal(
                    "health", "weight_trend_warning", "medium",
                    signal_class="risk",
                ),
                domain="health", label="Weight Warning",
                priority="important",
            ),
        ]
        alerts = resolve_conflicts(list(pool))
        briefing = resolve_conflicts_for_briefing(list(pool))
        self.assertEqual(
            [it["rendered"]["label"] for it in alerts],
            [it["rendered"]["label"] for it in briefing],
        )
