"""Glucose Snapshot — canonical Beth-grounding tests (Layer A + C).

Trust contracts under test:
  · Hard split: `glucose_latest` and `glucose_summary` are independent
    blocks. Neither falls back to the other.
  · LATEST never substitutes summary data for an event answer.
  · SUMMARY never labels itself as "latest" / "most recent" / "right now".
  · `_format_datetime` preserves time-of-day; relative-age phrase always
    present in LATEST rendered copy.
  · Trust-preserving fallback when summary exists but latest is None:
    "I can see your glucose summary, but I don't currently have access
     to the latest timestamped Dexcom reading."
  · Source label uses "Dexcom CGM" (concrete, user-preferred), never
    "CGM Reading" alone.
  · Beth NEVER queries GlucoseEntry directly inside chat code paths.
"""

import re
from datetime import datetime, time as dt_time, timedelta
from decimal import Decimal
from unittest.mock import patch

from django.conf import settings
from django.contrib.auth import get_user_model
from django.test import TestCase
from django.utils import timezone

from apps.health.models import GlucoseEntry
from apps.health.services.glucose_snapshot import (
    CGM_STALE_MINUTES,
    SUMMARY_STALE_DAYS,
    build_glucose_latest,
    build_glucose_summary,
    render_latest_message,
    render_summary_message,
)
from apps.users.models import TermsAcceptance

User = get_user_model()


def _user(email="gs@test.com"):
    u = User.objects.create_user(email=email, password="x" * 20)
    TermsAcceptance.objects.create(
        user=u,
        terms_version=settings.WLJ_SETTINGS.get("TERMS_VERSION", "1.0"),
    )
    u.preferences.has_completed_onboarding = True
    u.preferences.save()
    return u


def _log(user, value, *, minutes_ago=7, context="cgm", source="dexcom",
         trend="flat", trend_rate=None, unit="mg/dL"):
    return GlucoseEntry.objects.create(
        user=user,
        value=Decimal(str(value)),
        unit=unit,
        context=context,
        source=source,
        trend=trend,
        trend_rate=Decimal(str(trend_rate)) if trend_rate is not None else None,
        recorded_at=timezone.now() - timedelta(minutes=minutes_ago),
    )


# ── Layer A — empty / new-user state ─────────────────────────────


class EmptyStateTests(TestCase):
    def setUp(self):
        self.user = _user("empty@test.com")

    def test_latest_none_when_no_readings(self):
        self.assertIsNone(build_glucose_latest(self.user))

    def test_summary_none_when_no_readings(self):
        self.assertIsNone(build_glucose_summary(self.user))

    def test_render_latest_none_both_falls_back_helpful(self):
        msg = render_latest_message(None, None)
        # NEVER the generic "I don't have access" failure mode.
        self.assertNotIn("I don't have access", msg)
        self.assertIn("WLJ", msg)

    def test_render_summary_none_falls_back_helpful(self):
        msg = render_summary_message(None)
        self.assertNotIn("I don't have access", msg)


# ── Layer A — LATEST block round-trips ────────────────────────────


class LatestEventBuildTests(TestCase):
    def setUp(self):
        self.user = _user("latest@test.com")

    def test_value_unit_timestamp_round_trip(self):
        _log(self.user, 143, minutes_ago=7, trend="flat", source="dexcom")
        block = build_glucose_latest(self.user)
        self.assertIsNotNone(block)
        self.assertEqual(block["value"], 143.0)
        self.assertEqual(block["unit"], "mg/dL")
        self.assertEqual(block["source"], "dexcom")
        self.assertEqual(block["source_label"], "Dexcom CGM")
        # Timestamp is full ISO datetime, NOT a date string.
        self.assertIn("T", block["timestamp"])
        # minutes_ago is integer minutes (small fuzz tolerance for run time).
        self.assertGreaterEqual(block["minutes_ago"], 6)
        self.assertLessEqual(block["minutes_ago"], 9)

    def test_trend_arrow_mapping_for_all_choices(self):
        cases = [
            ("doubleUp", "rising rapidly", "⬆⬆"),
            ("singleUp", "rising", "⬆"),
            ("fortyFiveUp", "rising slowly", "↗"),
            ("flat", "steady", "→"),
            ("fortyFiveDown", "falling slowly", "↘"),
            ("singleDown", "falling", "⬇"),
            ("doubleDown", "falling rapidly", "⬇⬇"),
        ]
        for trend_code, label, arrow in cases:
            with self.subTest(trend=trend_code):
                GlucoseEntry.objects.filter(user=self.user).delete()
                _log(self.user, 143, trend=trend_code)
                block = build_glucose_latest(self.user)
                self.assertEqual(block["trend_label"], label)
                self.assertEqual(block["trend_arrow"], arrow)

    def test_trend_label_empty_for_inactive_codes(self):
        for code in ("none", "notComputable", "rateOutOfRange", ""):
            with self.subTest(trend=code):
                GlucoseEntry.objects.filter(user=self.user).delete()
                _log(self.user, 143, trend=code)
                block = build_glucose_latest(self.user)
                self.assertEqual(block["trend_label"], "")
                self.assertEqual(block["trend_arrow"], "")

    def test_stale_flag_true_when_cgm_over_threshold(self):
        _log(self.user, 143, minutes_ago=CGM_STALE_MINUTES + 30, source="dexcom")
        block = build_glucose_latest(self.user)
        self.assertTrue(block["stale"])

    def test_stale_flag_false_when_recent(self):
        _log(self.user, 143, minutes_ago=5, source="dexcom")
        block = build_glucose_latest(self.user)
        self.assertFalse(block["stale"])

    def test_source_label_prefers_concrete_name(self):
        """User-preferred naming: 'Dexcom CGM' over 'CGM Reading'."""
        _log(self.user, 143, source="dexcom", context="cgm")
        block = build_glucose_latest(self.user)
        self.assertEqual(block["source_label"], "Dexcom CGM")


# ── Layer A — SUMMARY block aggregation ──────────────────────────


class SummaryBuildTests(TestCase):
    def setUp(self):
        self.user = _user("summary@test.com")

    def test_7d_30d_90d_averages(self):
        # 10 readings/day for 60 days. 30 days at 119, 30 days at 130.
        # Avg 30d ≈ 119, avg 90d ≈ 124.5 (only 60 days exist).
        now = timezone.now()
        for d in range(60):
            for h in range(10):
                value = 119 if d < 30 else 130
                GlucoseEntry.objects.create(
                    user=self.user,
                    value=Decimal(str(value)),
                    unit="mg/dL",
                    source="dexcom",
                    context="cgm",
                    trend="flat",
                    recorded_at=now - timedelta(days=d, hours=h),
                )
        summary = build_glucose_summary(self.user)
        self.assertIsNotNone(summary)
        # 7d window only sees the most recent days (value 119).
        self.assertEqual(summary["average_7d"], 119)
        # 30d window — most recent 30 days, all value 119.
        self.assertEqual(summary["average_30d"], 119)
        # 90d window — 60 days of data, mix of 119/130.
        self.assertGreater(summary["average_90d"], 119)
        self.assertLess(summary["average_90d"], 130)

    def test_time_in_range_basic(self):
        now = timezone.now()
        # 10 readings: 7 in range (70-180), 3 out.
        for i, v in enumerate([90, 100, 120, 140, 160, 165, 175, 60, 200, 220]):
            GlucoseEntry.objects.create(
                user=self.user, value=Decimal(str(v)), unit="mg/dL",
                source="dexcom", context="cgm", trend="flat",
                recorded_at=now - timedelta(hours=i),
            )
        summary = build_glucose_summary(self.user)
        self.assertEqual(summary["time_in_range_pct_7d"], 70.0)

    def test_projected_a1c_with_confidence(self):
        """At least 60 readings required for any GMI estimate."""
        now = timezone.now()
        # 200 readings (medium confidence) all at 120 mg/dL.
        # GMI = 3.31 + 0.02392 * 120 = 6.18
        for i in range(200):
            GlucoseEntry.objects.create(
                user=self.user, value=Decimal("120"), unit="mg/dL",
                source="dexcom", context="cgm", trend="flat",
                recorded_at=now - timedelta(hours=i),
            )
        summary = build_glucose_summary(self.user)
        self.assertIsNotNone(summary["projected_a1c"])
        self.assertAlmostEqual(summary["projected_a1c"], 6.2, places=1)
        self.assertEqual(summary["projected_a1c_confidence"], "medium")

    def test_trend_improving_when_7d_below_30d(self):
        now = timezone.now()
        # 20 readings 8-30 days ago at 140 (older window), 20 readings in
        # the 7d window at 115 → trending DOWN = improving.
        for i in range(20):
            GlucoseEntry.objects.create(
                user=self.user, value=Decimal("140"), unit="mg/dL",
                source="dexcom", context="cgm", trend="flat",
                recorded_at=now - timedelta(days=15, hours=i),
            )
        for i in range(20):
            GlucoseEntry.objects.create(
                user=self.user, value=Decimal("115"), unit="mg/dL",
                source="dexcom", context="cgm", trend="flat",
                recorded_at=now - timedelta(days=1, hours=i),
            )
        summary = build_glucose_summary(self.user)
        self.assertEqual(summary["trend_7d_vs_30d"], "improving")

    def test_no_summary_when_no_readings(self):
        self.assertIsNone(build_glucose_summary(self.user))


# ── Layer A — hard separation between latest and summary ─────────


class HardSeparationTests(TestCase):
    """The architectural fix: latest and summary are independent."""

    def setUp(self):
        self.user = _user("sep@test.com")
        # Single recent reading → both blocks exist.
        _log(self.user, 143, minutes_ago=5)

    def test_both_blocks_present_with_single_reading(self):
        self.assertIsNotNone(build_glucose_latest(self.user))
        # Summary will have low data but still returns non-None.
        self.assertIsNotNone(build_glucose_summary(self.user))

    def test_blocks_are_independent_dicts(self):
        latest = build_glucose_latest(self.user)
        summary = build_glucose_summary(self.user)
        # No shared keys would indicate cross-contamination of state.
        self.assertNotIn("average_7d", latest)
        self.assertNotIn("timestamp", summary)
        self.assertNotIn("minutes_ago", summary)
        self.assertNotIn("projected_a1c", latest)


# ── Layer C — LATEST render copy ─────────────────────────────────


class RenderLatestTests(TestCase):
    def setUp(self):
        self.user = _user("rl@test.com")

    def test_response_contains_time_of_day(self):
        _log(self.user, 143, minutes_ago=7)
        latest = build_glucose_latest(self.user)
        msg = render_latest_message(latest)
        # Must contain a "H:MM AM/PM" time pattern.
        self.assertRegex(msg, r"\d{1,2}:\d{2}\s*(AM|PM)")

    def test_response_contains_relative_age(self):
        _log(self.user, 143, minutes_ago=7)
        latest = build_glucose_latest(self.user)
        msg = render_latest_message(latest)
        # 7 minutes ago — relative age is mandatory per spec.
        self.assertIn("minute", msg)
        self.assertIn("ago", msg)

    def test_response_contains_trend_phrase(self):
        _log(self.user, 143, minutes_ago=7, trend="flat")
        latest = build_glucose_latest(self.user)
        msg = render_latest_message(latest)
        self.assertIn("steady", msg)
        self.assertIn("→", msg)

    def test_response_uses_concrete_source_label(self):
        _log(self.user, 143, source="dexcom")
        latest = build_glucose_latest(self.user)
        msg = render_latest_message(latest)
        self.assertIn("Dexcom CGM", msg)

    def test_stale_flag_adds_note(self):
        _log(self.user, 143, minutes_ago=CGM_STALE_MINUTES + 30, source="dexcom")
        latest = build_glucose_latest(self.user)
        msg = render_latest_message(latest)
        self.assertIn("older than 2 hours", msg)

    def test_latest_response_never_contains_summary_words(self):
        """The hard contract: LATEST copy must never read as SUMMARY."""
        _log(self.user, 143, minutes_ago=7)
        latest = build_glucose_latest(self.user)
        msg = render_latest_message(latest).lower()
        for forbidden in ("average", "weekly", "estimated a1c",
                          "time in range", "this week"):
            self.assertNotIn(
                forbidden, msg,
                f"LATEST copy must never contain {forbidden!r}",
            )


# ── Layer C — SUMMARY render copy ────────────────────────────────


class RenderSummaryTests(TestCase):
    def test_summary_response_contains_average_framing(self):
        summary = {
            "average_7d": 119, "average_30d": 124, "average_90d": 130,
            "time_in_range_pct_7d": 82.0, "time_in_range_pct_30d": 78.5,
            "projected_a1c": 6.5, "projected_a1c_confidence": "high",
            "trend_7d_vs_30d": "improving",
            "reading_count_90d": 4218, "overnight_avg": 105.0,
            "sync_stale": False,
        }
        msg = render_summary_message(summary)
        self.assertIn("7-day average glucose", msg)
        self.assertIn("119", msg)
        self.assertIn("82", msg)  # TIR
        self.assertIn("6.5", msg)  # A1C
        self.assertIn("improving", msg)

    def test_summary_response_never_contains_latest_words(self):
        """SUMMARY copy must NEVER label itself as latest/most recent/etc."""
        summary = {
            "average_7d": 119, "average_30d": 124, "average_90d": 130,
            "time_in_range_pct_7d": 82.0, "time_in_range_pct_30d": 78.5,
            "projected_a1c": 6.5, "projected_a1c_confidence": "high",
            "trend_7d_vs_30d": "improving",
            "reading_count_90d": 4218, "overnight_avg": 105.0,
            "sync_stale": False,
        }
        msg = render_summary_message(summary).lower()
        for forbidden in ("last reading", "latest", "most recent",
                          "right now", "current"):
            self.assertNotIn(
                forbidden, msg,
                f"SUMMARY copy must never contain {forbidden!r}",
            )


# ── Trust-preserving copy when only one block available ─────────


class TrustCopyTests(TestCase):
    def test_latest_none_with_summary_present_renders_trust_message(self):
        summary = {
            "average_7d": 119, "average_30d": 124, "average_90d": 130,
            "time_in_range_pct_7d": 82.0, "time_in_range_pct_30d": 78.5,
            "projected_a1c": 6.5, "projected_a1c_confidence": "high",
            "trend_7d_vs_30d": "improving",
            "reading_count_90d": 4218, "overnight_avg": 105.0,
            "sync_stale": False,
        }
        msg = render_latest_message(None, summary=summary)
        # The exact trust-preserving phrasing required by the spec.
        self.assertIn("I can see your glucose summary", msg)
        self.assertIn("latest timestamped Dexcom reading", msg)
        # Must never substitute a number from the summary.
        self.assertNotIn("119", msg)
        self.assertNotIn("6.5", msg)

    def test_both_none_renders_honest_no_data(self):
        msg = render_latest_message(None, summary=None)
        self.assertIn("WLJ", msg)
        # Never fabricate.
        self.assertNotIn("119", msg)


# ── SAE wiring — both blocks land on the health state ─────────────


class SAEHealthStateWiringTests(TestCase):
    def setUp(self):
        self.user = _user("sae@test.com")
        _log(self.user, 143, minutes_ago=7)

    def test_health_state_contains_glucose_latest_block(self):
        from apps.core.ai_state.state_builder import build_health_state
        state = build_health_state(self.user)
        bl = state.get("glucose_latest")
        self.assertIsNotNone(
            bl, "SAE health state MUST expose glucose_latest so Beth "
            "can answer event questions without querying GlucoseEntry",
        )
        self.assertEqual(bl["value"], 143.0)
        self.assertIn("T", bl["timestamp"])
        self.assertEqual(bl["source_label"], "Dexcom CGM")

    def test_health_state_contains_glucose_summary_block(self):
        from apps.core.ai_state.state_builder import build_health_state
        state = build_health_state(self.user)
        bs = state.get("glucose_summary")
        self.assertIsNotNone(bs)
        self.assertIn("average_7d", bs)
        self.assertIn("trend_7d_vs_30d", bs)

    def test_legacy_keys_preserved(self):
        """Back-compat: existing consumers (briefing, intelligence,
        metric_registry) keep working unchanged."""
        from apps.core.ai_state.state_builder import build_health_state
        state = build_health_state(self.user)
        # Legacy event field.
        self.assertEqual(state.get("latest_glucose"), 143.0)
        self.assertEqual(state.get("latest_glucose_unit"), "mg/dL")
        # Legacy summary field.
        self.assertIn("glucose_avg_7d", state)


# ── Adapter — Beth's route through canonical snapshot ────────────


class AdapterRoutingTests(TestCase):
    """Beth's body-composition adapter pattern — replicated for glucose.
    Beth NEVER queries GlucoseEntry directly inside chat code."""

    def setUp(self):
        self.user = _user("adapter@test.com")

    def test_get_latest_message_returns_grounded_response(self):
        _log(self.user, 143, minutes_ago=7)
        from apps.core.ai_events.adapters.glucose import get_latest_message
        msg = get_latest_message(self.user)
        self.assertIn("143", msg)
        self.assertRegex(msg, r"\d{1,2}:\d{2}\s*(AM|PM)")
        self.assertIn("Dexcom CGM", msg)
        self.assertIn("ago", msg)

    def test_get_latest_message_trust_copy_when_no_data(self):
        msg = __import__(
            "apps.core.ai_events.adapters.glucose", fromlist=["get_latest_message"]
        ).get_latest_message(self.user)
        # No data at all — honest message, no fabrication.
        self.assertNotIn("119", msg)
        self.assertNotIn("143", msg)

    def test_get_summary_message_returns_summary_framing(self):
        now = timezone.now()
        for i in range(60):
            GlucoseEntry.objects.create(
                user=self.user, value=Decimal("120"), unit="mg/dL",
                source="dexcom", context="cgm", trend="flat",
                recorded_at=now - timedelta(hours=i),
            )
        from apps.core.ai_events.adapters.glucose import get_summary_message
        msg = get_summary_message(self.user)
        self.assertIn("average", msg.lower())
        # Must never label as latest.
        self.assertNotIn("last reading", msg.lower())
        self.assertNotIn("most recent", msg.lower())


# ── Action handler dispatch — Beth's grounded route ─────────────


class ActionHandlerRoutingTests(TestCase):
    """The handler-level fix: query_event_history(domain='glucose')
    routes through the snapshot adapter."""

    def setUp(self):
        self.user = _user("handler@test.com")
        _log(self.user, 143, minutes_ago=7)

    def test_handle_query_event_history_glucose_routes_through_snapshot(self):
        from apps.ai.action_handlers import ActionHandler
        handler = ActionHandler(self.user)
        result = handler.handle_query_event_history(
            query_type="lookup", domain="glucose",
        )
        self.assertTrue(result.success)
        # MUST contain time-of-day.
        self.assertRegex(result.message, r"\d{1,2}:\d{2}\s*(AM|PM)")
        # MUST contain relative age.
        self.assertIn("ago", result.message)
        # MUST use concrete source.
        self.assertIn("Dexcom CGM", result.message)
        # NEVER falls back to summary substitution.
        self.assertNotIn("7-day average", result.message)
