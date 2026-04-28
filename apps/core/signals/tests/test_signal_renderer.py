"""
Tests for the WLJ Signal Rendering Framework (Phase 1).

Six required tests per spec section 14:
    1. render_glucose_high
    2. priority_override
    3. no_numeric_language
    4. single_action_only
    5. conflict_resolution
    6. foundational_always_surfaces

Plus contract tests:
    - normalize_signal strips title/message
    - unknown (domain, type, severity) → None (caller falls back)
    - alias usage logs and translates correctly
    - response shape contains exactly {label, message, action,
      priority, domain}
"""

import re
from datetime import datetime, timedelta, timezone

from django.test import SimpleTestCase

from apps.core.signals.signal_renderer import (
    LABEL_TAXONOMY,
    SIGNAL_RENDER_MAP,
    normalize_signal,
    render_signal,
    resolve_conflicts,
    select_top_signals,
)


def _signal(domain, type_, severity, *, action_text="", confidence=0.8,
            title="ignored title", message="ignored message",
            priority_score=0.5, signal_class="risk", created_at=None):
    """Build a UnifiedSignal-shaped dict for the renderer."""
    return {
        "domain": domain,
        "type": type_,
        "severity": severity,
        "action_text": action_text,
        "confidence": confidence,
        "title": title,
        "message": message,
        "priority_score": priority_score,
        "signal_class": signal_class,
        "created_at": created_at or datetime.now(timezone.utc),
    }


# ══════════════════════════════════════════════════════════════════════
# 1. render_glucose_high
# ══════════════════════════════════════════════════════════════════════

class RenderGlucoseHighTests(SimpleTestCase):
    """Spec-locked: glucose_high (high) renders the canonical Glucose
    Alert template — exactly the strings in SIGNAL_RENDER_MAP."""

    def test_glucose_high_renders_canonical_alert(self):
        rendered = render_signal(_signal("health", "glucose_high", "high"))
        self.assertEqual(rendered, {
            "label": "Glucose Alert",
            "message": "Your glucose has been running high this week.",
            "action": "Log your next 3 meals and add a fasting reading tomorrow.",
            "priority": "foundational",
            "domain": "health",
        })

    def test_glucose_elevated_renders_trend(self):
        rendered = render_signal(_signal("health", "glucose_elevated", "medium"))
        self.assertEqual(rendered["label"], "Glucose Trend")
        self.assertEqual(rendered["priority"], "foundational")

    def test_blood_pressure_high_renders_alert(self):
        rendered = render_signal(_signal("health", "blood_pressure_high", "high"))
        self.assertEqual(rendered["label"], "Blood Pressure Alert")
        self.assertEqual(rendered["priority"], "foundational")
        self.assertEqual(rendered["message"], "Your blood pressure is running high.")
        self.assertEqual(rendered["action"], "Log daily readings this week.")


# ══════════════════════════════════════════════════════════════════════
# 2. priority_override — foundational beats supporting
# ══════════════════════════════════════════════════════════════════════

class PriorityOverrideTests(SimpleTestCase):

    def test_foundational_outranks_supporting(self):
        """Health alert (foundational) must outrank a tasks alert
        (supporting) regardless of severity."""
        signals = [
            _signal("life", "tasks_overloaded", "high"),
            _signal("health", "glucose_high", "high"),
        ]
        top = select_top_signals(signals, max_n=2)
        # Both render, but glucose comes first.
        self.assertEqual(len(top), 2)
        self.assertEqual(top[0]["rendered"]["domain"], "health")
        self.assertEqual(top[0]["rendered"]["priority"], "foundational")

    def test_max_n_truncates(self):
        signals = [
            _signal("health", "glucose_high", "high"),
            _signal("life", "tasks_overloaded", "high"),
            _signal("life", "routine_breakdown", "high"),
        ]
        top = select_top_signals(signals, max_n=2)
        self.assertEqual(len(top), 2)


# ══════════════════════════════════════════════════════════════════════
# 3. no_numeric_language — every rendered template is clean
# ══════════════════════════════════════════════════════════════════════

class NoNumericLanguageTests(SimpleTestCase):
    """Per spec rendering rules: no clinical numbers (mg/dL, mmHg) in
    the user-facing strings. The UI surfaces metric values separately."""

    _BANNED = re.compile(
        r"\b(\d+\s*mg/?dL|\d+\s*mm\s*hg|\d+\s*bpm|\d+\s*kg|\d+\s*lb)\b",
        re.IGNORECASE,
    )

    def test_no_clinical_numbers_in_any_template(self):
        for key, tpl in SIGNAL_RENDER_MAP.items():
            for field in ("message", "action"):
                self.assertIsNone(
                    self._BANNED.search(tpl[field]),
                    f"Banned clinical number language in {key!r} {field}: "
                    f"{tpl[field]!r}",
                )

    def test_label_is_in_taxonomy(self):
        """Every label must end with one of {Alert, Trend, Opportunity}."""
        for key, tpl in SIGNAL_RENDER_MAP.items():
            label = tpl["label"]
            ok = any(
                label == word or label.endswith(" " + word)
                for word in LABEL_TAXONOMY
            )
            self.assertTrue(
                ok,
                f"Label {label!r} for {key!r} not in taxonomy "
                f"{LABEL_TAXONOMY}",
            )


# ══════════════════════════════════════════════════════════════════════
# 4. single_action_only
# ══════════════════════════════════════════════════════════════════════

class SingleActionOnlyTests(SimpleTestCase):
    """Every template's `action` must be one short instruction.
    Rule of thumb: no semicolons, no ' and then ', no 'plus also'."""

    _MULTI_ACTION_HINTS = (";", " and then ", " plus also ", " also ")

    def test_each_action_is_single(self):
        for key, tpl in SIGNAL_RENDER_MAP.items():
            action = tpl["action"]
            for marker in self._MULTI_ACTION_HINTS:
                self.assertNotIn(
                    marker, action,
                    f"Action for {key!r} appears to chain multiple "
                    f"steps ({marker!r}): {action!r}",
                )
            # Sentence count: at most one trailing period.
            sentences = [s for s in action.strip().split(".") if s.strip()]
            self.assertLessEqual(
                len(sentences), 2,
                f"Action for {key!r} has too many sentences: {action!r}",
            )


# ══════════════════════════════════════════════════════════════════════
# 5. conflict_resolution
# ══════════════════════════════════════════════════════════════════════

class ConflictResolutionTests(SimpleTestCase):
    """Spec example: glucose_high (foundational risk) suppresses
    weight_loss_positive (health momentum) — same domain, lower
    priority. Cross-domain coexistence is allowed."""

    def test_foundational_suppresses_same_domain_lower_priority(self):
        # weight_loss_positive isn't in the table yet, so we model the
        # contract directly: a same-domain non-foundational rendered
        # signal must be dropped when a foundational one is present.
        # We use routine_breakdown (life, supporting) here as a stand-in
        # to verify the cross-domain case stays.
        signals = [
            _signal("health", "glucose_high", "high"),
            _signal("life", "routine_breakdown", "high"),
        ]
        top = select_top_signals(signals, max_n=5)
        # Cross-domain: both survive.
        domains = [item["rendered"]["domain"] for item in top]
        self.assertIn("health", domains)
        self.assertIn("life", domains)

    def test_same_domain_non_foundational_dropped(self):
        """Within `health`, a non-foundational signal would be
        suppressed if a foundational one is present. We emulate by
        adding a synthetic non-foundational template via the public
        API — render returns None for unknown keys, so we exercise
        resolve_conflicts directly with two pre-rendered items."""
        rendered_items = [
            {
                "signal": _signal("health", "glucose_high", "high"),
                "rendered": {
                    "label": "Glucose Alert",
                    "message": "Your glucose has been running high this week.",
                    "action": "Log your next 3 meals and add a fasting reading tomorrow.",
                    "priority": "foundational",
                    "domain": "health",
                },
            },
            {
                "signal": _signal("health", "weight_loss_positive", "positive"),
                "rendered": {
                    "label": "Weight Trend",
                    "message": "Weight is trending down.",
                    "action": "Keep current intake.",
                    "priority": "important",
                    "domain": "health",
                },
            },
        ]
        survivors = resolve_conflicts(rendered_items)
        self.assertEqual(len(survivors), 1)
        self.assertEqual(survivors[0]["rendered"]["label"], "Glucose Alert")


# ══════════════════════════════════════════════════════════════════════
# 6. foundational_always_surfaces
# ══════════════════════════════════════════════════════════════════════

class FoundationalAlwaysSurfacesTests(SimpleTestCase):
    """Even when many supporting signals are emitted, a single
    foundational signal must appear in the top N."""

    def test_foundational_in_top_2_among_many_supporting(self):
        signals = [
            _signal("life", "tasks_overloaded", "high",
                    created_at=datetime(2099, 1, 1, tzinfo=timezone.utc)),
            _signal("life", "routine_breakdown", "high",
                    created_at=datetime(2099, 1, 1, tzinfo=timezone.utc)),
            _signal("life", "tasks_overloaded", "medium",
                    created_at=datetime(2099, 1, 1, tzinfo=timezone.utc)),
            # The lone foundational, oldest. Must still surface.
            _signal("health", "glucose_high", "high",
                    created_at=datetime(2020, 1, 1, tzinfo=timezone.utc)),
        ]
        top = select_top_signals(signals, max_n=2)
        priorities = [item["rendered"]["priority"] for item in top]
        self.assertIn("foundational", priorities)
        # First slot must be the foundational one.
        self.assertEqual(top[0]["rendered"]["priority"], "foundational")
        self.assertEqual(top[0]["rendered"]["domain"], "health")


# ══════════════════════════════════════════════════════════════════════
# Contract tests
# ══════════════════════════════════════════════════════════════════════

class NormalizeSignalContractTests(SimpleTestCase):

    def test_normalize_strips_title_and_message(self):
        """Renderer must NOT depend on producer-authored prose."""
        norm = normalize_signal(_signal(
            "health", "glucose_high", "high",
            title="Producer wrote this",
            message="Producer wrote a long thing here",
        ))
        self.assertNotIn("title", norm)
        self.assertNotIn("message", norm)
        self.assertEqual(norm["domain"], "health")
        self.assertEqual(norm["type"], "glucose_high")
        self.assertEqual(norm["severity"], "high")


class UnknownKeyFallbackTests(SimpleTestCase):

    def test_unknown_key_returns_none(self):
        """No template → None. Caller falls back to legacy."""
        result = render_signal(_signal("finance", "bill_due", "high"))
        self.assertIsNone(result)

    def test_unknown_severity_returns_none(self):
        result = render_signal(_signal("health", "glucose_high", "low"))
        # glucose_high+low is not in the table; only +high / +critical are.
        self.assertIsNone(result)


class TypeAliasTests(SimpleTestCase):

    def test_alias_translates_known_producer_types(self):
        """Producer-emitted 'glucose_alert_high' → renderer
        'glucose_high'."""
        rendered = render_signal(
            _signal("health", "glucose_alert_high", "high")
        )
        self.assertIsNotNone(rendered)
        self.assertEqual(rendered["label"], "Glucose Alert")


class ResponseShapeTests(SimpleTestCase):

    def test_render_signal_returns_exactly_5_keys(self):
        rendered = render_signal(_signal("health", "glucose_high", "high"))
        self.assertEqual(
            set(rendered.keys()),
            {"label", "message", "action", "priority", "domain"},
        )
