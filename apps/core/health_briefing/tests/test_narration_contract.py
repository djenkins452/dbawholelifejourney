"""
Tests for the C14 Beth narration addendum.

Three test surfaces:

1. **Static base addendum** — text contains every guardrail the user
   specified and avoids forbidden language.

2. **Dynamic per-briefing addendum** — `build_briefing_addendum`
   correctly surfaces acute alerts first, the insufficient_data flag,
   the positive_recognition requirement, pre-ranked driver lists, the
   insulin gate, and inputs_missing guidance.

3. **Validation-scenario alignment** — for representative fixtures
   shaped like the 15 scenarios in
   `docs/health_briefing_validation_scenarios.md`, the addendum
   contains the expected guidance keywords (e.g., scenario 3 emits
   "ACUTE" and a glucose value; scenario 9 emits the insulin-gate
   line).

This module is pure: no DB, no Django ORM. Imports the C1 contract
dataclasses to construct synthetic HealthBriefing fixtures.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Optional

from django.test import SimpleTestCase

from apps.core.health_briefing.contract import (
    COMPOSER_VERSION,
    DEFAULT_TTL_SECONDS,
    AcuteAlert,
    AcuteSeverity,
    ComposedOver,
    Driver,
    HealthBriefing,
    OverallStatus,
    RiskLevel,
    Trend,
    TrendDirection,
)
from apps.core.health_briefing.narration_contract import (
    ADDENDUM_NAME,
    HEALTH_BRIEFING_NARRATION_ADDENDUM_BASE,
    build_briefing_addendum,
    get_registered_addenda,
    is_addendum_registered,
    register_health_briefing_addendum,
    unregister_health_briefing_addendum,
)


# ── Helpers ─────────────────────────────────────────────────────────


def _trend(
    direction: TrendDirection = TrendDirection.FLAT,
    magnitude: int = 0,
    confidence: float = 0.5,
    window_days: int = 7,
) -> Trend:
    return Trend(
        direction=direction,
        magnitude=magnitude,
        confidence=confidence,
        window_days=window_days,
    )


def _briefing(**overrides) -> HealthBriefing:
    now = datetime(2026, 5, 25, 12, 0, tzinfo=timezone.utc)
    defaults = dict(
        briefing_id="a" * 64,
        user_id=1,
        generated_at_utc=now,
        composer_version=COMPOSER_VERSION,
        composed_over=ComposedOver(
            start_utc=now - timedelta(days=30), end_utc=now,
        ),
        ttl_seconds=DEFAULT_TTL_SECONDS,
        overall_status=OverallStatus.STABLE,
        overall_confidence=0.7,
        risk_level=RiskLevel.NONE,
        headline_summary="Metabolic profile is stable.",
        glucose_trend_7d=_trend(window_days=7),
        glucose_trend_30d=_trend(window_days=30),
        glucose_trend_90d=_trend(window_days=90),
        weight_trend_30d=_trend(window_days=30),
        insulin_trend_30d=None,
    )
    defaults.update(overrides)
    return HealthBriefing(**defaults)


def _driver(key: str, label: str, score: float, why: str) -> Driver:
    return Driver(key=key, label=label, score=score, why=why)


def _acute(
    key: str = "glucose_critical_low",
    label: str = "Critical low glucose",
    severity: AcuteSeverity = AcuteSeverity.CRITICAL,
    why: str = "Most recent reading 48 mg/dL",
) -> AcuteAlert:
    return AcuteAlert(
        key=key, label=label, severity=severity,
        why=why, evidence_ref="latest_glucose",
    )


# ── 1. Static base addendum ─────────────────────────────────────────


class BaseAddendumContentTests(SimpleTestCase):
    """The static base addendum carries every user-required guardrail."""

    def test_addendum_exists_and_is_non_empty(self):
        self.assertIsInstance(HEALTH_BRIEFING_NARRATION_ADDENDUM_BASE, str)
        self.assertGreater(len(HEALTH_BRIEFING_NARRATION_ADDENDUM_BASE), 500)

    def test_addendum_states_role_as_narrator(self):
        text = HEALTH_BRIEFING_NARRATION_ADDENDUM_BASE
        self.assertIn("narrator", text.lower())
        self.assertIn("not an analyst", text.lower())

    def test_addendum_forbids_contradicting_the_briefing(self):
        text = HEALTH_BRIEFING_NARRATION_ADDENDUM_BASE
        # Guardrail #2.
        self.assertIn("authoritative", text.lower())
        self.assertIn("do not contradict", text.lower())

    def test_addendum_forbids_re_ranking(self):
        # Guardrail #3. The addendum uses a "YOU MUST NOT" section
        # header with "re-rank top_positive_drivers..." as the first
        # bullet. Confirm both pieces are present.
        normalized = " ".join(HEALTH_BRIEFING_NARRATION_ADDENDUM_BASE.split()).lower()
        self.assertIn("must not", normalized)
        self.assertIn("re-rank top_positive_drivers", normalized)

    def test_addendum_forbids_invented_conclusions(self):
        text = HEALTH_BRIEFING_NARRATION_ADDENDUM_BASE
        # Guardrail #4: no invented metabolic conclusions.
        self.assertIn("do not invent", text.lower())
        self.assertIn("do not fabricate", text.lower())

    def test_addendum_requires_acute_first(self):
        # Guardrail #5. Same whitespace-normalization as above.
        normalized = " ".join(HEALTH_BRIEFING_NARRATION_ADDENDUM_BASE.split()).lower()
        self.assertIn("acute", normalized)
        self.assertIn("first sentence", normalized)

    def test_addendum_requires_positive_recognition(self):
        text = HEALTH_BRIEFING_NARRATION_ADDENDUM_BASE
        # Guardrail #6.
        self.assertIn("positive_recognition_required", text)
        self.assertIn("top_positive_drivers", text)

    def test_addendum_requires_insufficient_data_acknowledgement(self):
        text = HEALTH_BRIEFING_NARRATION_ADDENDUM_BASE
        # Guardrail #7.
        self.assertIn("insufficient_data_flag", text)
        self.assertIn("not enough data", text.lower())

    def test_addendum_forbids_causal_claims(self):
        text = HEALTH_BRIEFING_NARRATION_ADDENDUM_BASE
        # Guardrail #8.
        self.assertIn("association", text.lower())
        self.assertIn("never causal", text.lower())

    def test_addendum_includes_insulin_gate(self):
        text = HEALTH_BRIEFING_NARRATION_ADDENDUM_BASE
        self.assertIn("insulin", text.lower())
        self.assertIn("insulin_trend_30d", text)
        self.assertIn("absence", text.lower())

    def test_addendum_includes_staleness_acknowledgement(self):
        text = HEALTH_BRIEFING_NARRATION_ADDENDUM_BASE
        self.assertIn("staleness_flags", text)
        self.assertIn("stale", text.lower())

    def test_addendum_includes_tone_bar(self):
        text = HEALTH_BRIEFING_NARRATION_ADDENDUM_BASE
        for word in ("wise", "balanced", "encouraging", "truthful",
                     "non-alarmist", "high-trust"):
            self.assertIn(word, text.lower(), f"missing tone word: {word}")

    def test_addendum_does_not_quote_alerts_feed(self):
        text = HEALTH_BRIEFING_NARRATION_ADDENDUM_BASE
        # The two-channel rule: briefing-addendum must instruct Beth
        # NOT to quote the alerts-feed text.
        self.assertIn("alerts feed", text.lower())
        self.assertIn("two channels", text.lower())


# ── 2. Dynamic per-briefing addendum ────────────────────────────────


class DynamicAddendumStructureTests(SimpleTestCase):
    def test_addendum_includes_briefing_id(self):
        b = _briefing(briefing_id="abc123def456" + "x" * 52)
        out = build_briefing_addendum(b)
        self.assertIn("briefing_id=abc123def456", out)

    def test_addendum_includes_headline_status_and_confidence(self):
        b = _briefing(
            overall_status=OverallStatus.IMPROVING,
            overall_confidence=0.82,
        )
        out = build_briefing_addendum(b)
        self.assertIn("Headline: improving", out)
        self.assertIn("0.82", out)

    def test_addendum_includes_risk_level(self):
        b = _briefing(risk_level=RiskLevel.MODERATE)
        out = build_briefing_addendum(b)
        self.assertIn("Risk: moderate", out)

    def test_acute_block_emitted_when_alerts_present(self):
        b = _briefing(
            risk_level=RiskLevel.ACUTE,
            overall_status=OverallStatus.AT_RISK,
            acute_alerts=[_acute()],
            inputs_used={"latest_glucose": 48},
        )
        out = build_briefing_addendum(b)
        self.assertIn("ACUTE", out)
        self.assertIn("surface FIRST", out)
        self.assertIn("48 mg/dL", out)

    def test_acute_block_absent_when_no_alerts(self):
        b = _briefing()
        out = build_briefing_addendum(b)
        self.assertNotIn("ACUTE", out)

    def test_insufficient_data_line_emitted_when_flagged(self):
        b = _briefing(
            overall_status=OverallStatus.INSUFFICIENT_DATA,
            insufficient_data_flag=True,
        )
        out = build_briefing_addendum(b)
        self.assertIn("INSUFFICIENT DATA", out)
        self.assertIn("explicitly say so", out)

    def test_positive_recognition_line_emitted_when_required(self):
        b = _briefing(
            overall_status=OverallStatus.IMPROVING,
            top_positive_drivers=[
                _driver("weight_trajectory", "Weight Trajectory", 12, "down 5 lb"),
            ],
            positive_recognition_required=True,
        )
        out = build_briefing_addendum(b)
        self.assertIn("POSITIVE RECOGNITION REQUIRED", out)
        self.assertIn("Weight Trajectory", out)

    def test_positive_recognition_line_absent_when_not_required(self):
        b = _briefing(positive_recognition_required=False)
        out = build_briefing_addendum(b)
        self.assertNotIn("POSITIVE RECOGNITION REQUIRED", out)

    def test_drivers_listed_with_scores_and_why(self):
        b = _briefing(
            top_positive_drivers=[
                _driver("glycemic_control", "Glycemic Control", 18, "85% TIR"),
                _driver("weight_trajectory", "Weight Trajectory", 12, "down 5 lb"),
            ],
            watch_items=[
                _driver("sleep_recovery", "Sleep Recovery", -8, "5.4h avg"),
            ],
        )
        out = build_briefing_addendum(b)
        self.assertIn("Glycemic Control", out)
        self.assertIn("(+18)", out)
        self.assertIn("85% TIR", out)
        self.assertIn("Sleep Recovery", out)
        self.assertIn("(-8)", out)
        self.assertIn("do NOT re-rank", out)

    def test_insulin_gate_line_emitted_when_insulin_trend_is_none(self):
        b = _briefing(insulin_trend_30d=None)
        out = build_briefing_addendum(b)
        self.assertIn(
            "No insulin observation", out,
        )
        self.assertIn("do NOT mention insulin", out)

    def test_insulin_gate_line_absent_when_insulin_trend_present(self):
        b = _briefing(insulin_trend_30d=_trend(
            direction=TrendDirection.DOWN, magnitude=30, confidence=0.7,
            window_days=30,
        ))
        out = build_briefing_addendum(b)
        self.assertNotIn("No insulin observation", out)

    def test_inputs_missing_guidance_emitted_when_present(self):
        b = _briefing(
            inputs_missing=["latest_glucose", "glucose_avg_7d", "hba1c"],
        )
        out = build_briefing_addendum(b)
        self.assertIn("No data on", out)
        self.assertIn("hba1c", out)

    def test_staleness_guidance_emitted_when_flagged(self):
        b = _briefing(
            staleness_flags=["latest_glucose"],
            inputs_used={"latest_glucose": 135},
        )
        out = build_briefing_addendum(b)
        self.assertIn("Stale data flagged", out)
        self.assertIn("latest_glucose", out)
        self.assertIn("Acknowledge the gap", out)

    def test_deterministic(self):
        b = _briefing(
            overall_status=OverallStatus.IMPROVING,
            overall_confidence=0.8,
            top_positive_drivers=[
                _driver("a", "A", 10, "why a"),
                _driver("b", "B", 8, "why b"),
            ],
            positive_recognition_required=True,
        )
        a1 = build_briefing_addendum(b)
        a2 = build_briefing_addendum(b)
        self.assertEqual(a1, a2)


# ── 3. Registration pattern ─────────────────────────────────────────


class RegistrationTests(SimpleTestCase):
    def setUp(self):
        unregister_health_briefing_addendum()

    def tearDown(self):
        unregister_health_briefing_addendum()

    def test_addendum_name_is_health_briefing(self):
        self.assertEqual(ADDENDUM_NAME, "health_briefing")

    def test_not_registered_by_default(self):
        self.assertFalse(is_addendum_registered())

    def test_register_makes_it_available(self):
        register_health_briefing_addendum()
        self.assertTrue(is_addendum_registered())
        registered = get_registered_addenda()
        self.assertIn("health_briefing", registered)
        self.assertEqual(
            registered["health_briefing"],
            HEALTH_BRIEFING_NARRATION_ADDENDUM_BASE,
        )

    def test_register_is_idempotent(self):
        register_health_briefing_addendum()
        register_health_briefing_addendum()
        self.assertEqual(len(get_registered_addenda()), 1)

    def test_get_registered_returns_copy(self):
        register_health_briefing_addendum()
        registered = get_registered_addenda()
        registered["spoof"] = "x"
        # Mutating the returned dict must NOT mutate the registry.
        self.assertNotIn("spoof", get_registered_addenda())


# ── 4. Validation-scenario alignment ───────────────────────────────


class ValidationScenarioAlignmentTests(SimpleTestCase):
    """For representative scenario shapes from
    docs/health_briefing_validation_scenarios.md, verify the addendum
    surfaces the right guidance keywords. This is the bridge between
    the static doc and the runtime contract: if scenario 3 says
    "Beth MUST surface the acute first", this test pins that the
    addendum tells Beth so.
    """

    def test_scenario_1_canonical_progress_emits_positive_recognition(self):
        # Improving + drivers + no acute + insulin observed → addendum
        # carries POSITIVE RECOGNITION REQUIRED + insulin trend line.
        b = _briefing(
            overall_status=OverallStatus.IMPROVING,
            overall_confidence=0.82,
            risk_level=RiskLevel.LOW,
            top_positive_drivers=[
                _driver("insulin_dependence", "Insulin Dependence", 18,
                        "Recent daily 35u vs 30d avg 41u"),
                _driver("weight_trajectory", "Weight Trajectory", 12,
                        "Weight down 7.0 lb over 30d"),
                _driver("glycemic_control", "Glycemic Control", 8,
                        "76% time-in-range"),
            ],
            watch_items=[
                _driver("glycemic_trajectory", "Glycemic Trajectory", -3,
                        "7d avg above 30d baseline"),
            ],
            positive_recognition_required=True,
            insulin_trend_30d=_trend(
                direction=TrendDirection.DOWN, magnitude=18,
                confidence=0.7, window_days=30,
            ),
        )
        out = build_briefing_addendum(b)
        self.assertIn("POSITIVE RECOGNITION REQUIRED", out)
        self.assertIn("Insulin Dependence", out)
        self.assertNotIn("ACUTE", out)
        self.assertNotIn("No insulin observation", out)

    def test_scenario_3_acute_low_emits_acute_first_with_value(self):
        b = _briefing(
            overall_status=OverallStatus.AT_RISK,
            risk_level=RiskLevel.ACUTE,
            acute_alerts=[
                _acute(
                    key="glucose_critical_low",
                    label="Critical low glucose",
                    why="Most recent reading 48 mg/dL",
                ),
            ],
            inputs_used={"latest_glucose": 48},
            # Acute overrides positive_recognition even when drivers exist.
            top_positive_drivers=[
                _driver("weight_trajectory", "Weight Trajectory", 12, "down"),
            ],
            positive_recognition_required=False,
        )
        out = build_briefing_addendum(b)
        # First non-header line about ACUTE.
        lines = out.split("\n")
        acute_idx = next(i for i, ln in enumerate(lines) if "ACUTE" in ln)
        # ACUTE block precedes any positive-recognition or driver lines.
        for ln in lines[acute_idx + 1:]:
            self.assertNotIn("POSITIVE RECOGNITION", ln)
        self.assertIn("48 mg/dL", out)
        self.assertIn("[critical]", out)

    def test_scenario_5_insufficient_data_emits_explicit_flag(self):
        b = _briefing(
            overall_status=OverallStatus.INSUFFICIENT_DATA,
            overall_confidence=0.0,
            risk_level=RiskLevel.NONE,
            insufficient_data_flag=True,
            inputs_missing=[
                "latest_glucose", "glucose_avg_7d", "weight_change_30d",
            ],
        )
        out = build_briefing_addendum(b)
        self.assertIn("INSUFFICIENT DATA", out)
        self.assertIn("explicitly say so", out)
        self.assertIn("Do not fabricate", out)
        self.assertIn("No data on", out)

    def test_scenario_9_insulin_absent_emits_insulin_gate(self):
        b = _briefing(
            overall_status=OverallStatus.IMPROVING,
            top_positive_drivers=[
                _driver("glycemic_control", "Glycemic Control", 8, "74% TIR"),
                _driver("weight_trajectory", "Weight Trajectory", 6, "down"),
            ],
            positive_recognition_required=True,
            insulin_trend_30d=None,
            inputs_missing=[
                "insulin_total_today_units",
                "insulin_total_7d_units",
                "insulin_daily_avg_30d_units",
            ],
        )
        out = build_briefing_addendum(b)
        self.assertIn("No insulin observation", out)
        self.assertIn("do NOT mention insulin", out)

    def test_scenario_6_horizon_disagreement_emits_drivers_with_window_context(self):
        # Long-term improving + short-term slip. Composer emits both;
        # addendum lists both as pre-ranked.
        b = _briefing(
            overall_status=OverallStatus.IMPROVING,
            overall_confidence=0.7,
            top_positive_drivers=[
                _driver("weight_trajectory", "Weight Trajectory", 12,
                        "Weight down 5.0 lb over 30d"),
                _driver("glycemic_trajectory", "Glycemic Trajectory", 8,
                        "30d avg below 90d baseline"),
            ],
            watch_items=[
                _driver("glycemic_control", "Glycemic Control", -5,
                        "7d TIR 61% (slip)"),
            ],
            positive_recognition_required=True,
        )
        out = build_briefing_addendum(b)
        self.assertIn("Pre-ranked positive drivers", out)
        self.assertIn("Pre-ranked watch items", out)
        self.assertIn("Weight Trajectory", out)
        self.assertIn("Glycemic Control", out)

    def test_scenario_8_cgm_stale_emits_staleness_acknowledgement(self):
        b = _briefing(
            overall_status=OverallStatus.MIXED,
            staleness_flags=["latest_glucose", "glucose_avg_7d"],
            inputs_used={"latest_glucose": 135, "weight_change_30d": -3},
            inputs_missing=["time_in_range_pct_7d"],
        )
        out = build_briefing_addendum(b)
        self.assertIn("Stale data flagged", out)
        self.assertIn("latest_glucose", out)
        self.assertIn("Acknowledge the gap", out)
