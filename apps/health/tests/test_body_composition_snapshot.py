"""Body Composition Snapshot — canonical Beth-grounding tests.

Trust contracts under test:
  · Snapshot answers "latest vs PREVIOUS measurement date" — never
    "average" or "rolling window."
  · Comparison message NEVER falls back to "I don't have your latest
    measurements" when first-party data exists.
  · Beth's body-composition adapter routes through the snapshot — NEVER
    queries BodyCompositionEntry directly inside the chat path.
  · Largest_improvement only fires when the metric has an unambiguous
    direction-of-improvement; neutral metrics (chest, arms, etc.) are
    never auto-classified as wins.
"""

from datetime import date, timedelta
from decimal import Decimal

from django.conf import settings
from django.contrib.auth import get_user_model
from django.test import TestCase
from django.utils import timezone

from apps.health.models import BodyCompositionEntry
from apps.health.services.body_composition_snapshot import (
    build_body_composition_snapshot,
    render_comparison_message,
    render_latest_message,
)
from apps.users.models import TermsAcceptance

User = get_user_model()


def _user(email="bcsnap@test.com"):
    u = User.objects.create_user(email=email, password="x" * 20)
    TermsAcceptance.objects.create(
        user=u,
        terms_version=settings.WLJ_SETTINGS.get("TERMS_VERSION", "1.0"),
    )
    u.preferences.has_completed_onboarding = True
    u.preferences.save()
    return u


def _log(user, metric, value, days_ago=0, unit="in", source="manual"):
    return BodyCompositionEntry.objects.create(
        user=user, metric_name=metric,
        value=Decimal(str(value)), unit=unit,
        measurement_date=date.today() - timedelta(days=days_ago),
        source=source,
    )


# ── Empty / new-user state ────────────────────────────────────────


class EmptyStateTests(TestCase):
    def setUp(self):
        self.user = _user("empty@test.com")

    def test_returns_none_when_no_entries(self):
        self.assertIsNone(build_body_composition_snapshot(self.user))

    def test_comparison_message_helpful_when_none(self):
        msg = render_comparison_message(None)
        # The trust-preserving message — specific, grounded, no
        # "I don't have access."
        self.assertNotIn("I don't have", msg)
        self.assertIn("Body Composition", msg)


# ── Latest vs previous — headline contract ────────────────────────


class LatestVsPreviousTests(TestCase):
    """The canonical contract: latest MEASUREMENT DATE vs the most
    recent PRIOR measurement date — per metric. NOT average. NOT
    rolling window. The literal eyeball comparison."""

    def setUp(self):
        self.user = _user("lvp@test.com")
        # Two clean sessions: 30 days ago and today.
        _log(self.user, "waist",       43.4, days_ago=30)
        _log(self.user, "chest",       51.2, days_ago=30)
        _log(self.user, "arm_left",    16.7, days_ago=30)
        _log(self.user, "arm_right",   16.8, days_ago=30)
        _log(self.user, "thigh_left",  27.1, days_ago=30)
        _log(self.user, "thigh_right", 27.2, days_ago=30)
        # Today's session.
        _log(self.user, "waist",       42.0, days_ago=0)
        _log(self.user, "chest",       52.0, days_ago=0)
        _log(self.user, "arm_left",    16.88, days_ago=0)
        _log(self.user, "arm_right",   17.0, days_ago=0)
        _log(self.user, "thigh_left",  26.63, days_ago=0)
        _log(self.user, "thigh_right", 27.25, days_ago=0)

    def test_snapshot_has_latest_previous_and_deltas(self):
        snap = build_body_composition_snapshot(self.user)
        self.assertIsNotNone(snap)
        self.assertEqual(snap["latest_date"], date.today())
        self.assertEqual(
            snap["previous_date"], date.today() - timedelta(days=30),
        )
        self.assertEqual(snap["days_between"], 30)

        # Latest/previous/delta for waist (down 1.4 in).
        self.assertEqual(snap["latest"]["waist"], 42.0)
        self.assertEqual(snap["previous"]["waist"], 43.4)
        self.assertAlmostEqual(snap["delta"]["waist"], -1.4, places=2)

        # Latest/previous/delta for chest (up 0.8 in — neutral, NOT a win).
        self.assertEqual(snap["latest"]["chest"], 52.0)
        self.assertEqual(snap["previous"]["chest"], 51.2)
        self.assertAlmostEqual(snap["delta"]["chest"], 0.8, places=2)

    def test_largest_improvement_is_waist_not_chest(self):
        """Chest +0.8 in is bigger in absolute value than waist −1.4,
        but chest is a NEUTRAL metric (no improvement direction) so
        it can never be the headline win. Waist must be picked."""
        snap = build_body_composition_snapshot(self.user)
        win = snap["largest_improvement"]
        self.assertIsNotNone(win)
        self.assertEqual(win["metric"], "waist")
        self.assertAlmostEqual(win["delta"], -1.4, places=2)

    def test_trend_summary_uses_per_metric_noise_threshold(self):
        snap = build_body_composition_snapshot(self.user)
        joined = " | ".join(snap["trend_summary"])
        # Waist beat noise → trending down (improving).
        self.assertIn("Waist trending down (improving)", joined)
        # Chest beat noise → trending up (neutral, no improving tag).
        self.assertIn("Chest trending up", joined)
        self.assertNotIn("Chest trending up (improving)", joined)

    def test_comparison_message_is_grounded_and_specific(self):
        snap = build_body_composition_snapshot(self.user)
        msg = render_comparison_message(snap)
        # MUST NOT include the failure mode the user reported.
        self.assertNotIn("I don't have", msg)
        # Specific delta lines for the metrics that exist.
        self.assertIn("Waist: -1.4", msg)
        self.assertIn("Chest: +0.8", msg)
        # Biggest win highlights waist — never chest.
        self.assertIn("Biggest win", msg)
        self.assertIn("Waist", msg.split("Biggest win", 1)[1])


# ── Single-session edge case ──────────────────────────────────────


class FirstEntryTests(TestCase):
    """No prior session yet — must NOT fabricate a delta, but MUST
    still respond with the actual measurements (not "I don't have")."""

    def setUp(self):
        self.user = _user("first@test.com")
        _log(self.user, "waist", 42.0, days_ago=0)
        _log(self.user, "chest", 52.0, days_ago=0)

    def test_delta_is_none_for_first_entry(self):
        snap = build_body_composition_snapshot(self.user)
        self.assertIsNone(snap["previous_date"])
        self.assertIsNone(snap["delta"]["waist"])
        self.assertIsNone(snap["delta"]["chest"])

    def test_message_is_grounded_not_evasive(self):
        snap = build_body_composition_snapshot(self.user)
        msg = render_comparison_message(snap)
        self.assertNotIn("I don't have", msg)
        self.assertIn("42", msg)
        self.assertIn("52", msg)
        self.assertIn("first session", msg.lower())


# ── Mixed: some metrics new today, some not ──────────────────────


class PartialOverlapTests(TestCase):
    """User logged some metrics today but only some have a prior
    session. The snapshot must surface deltas for those that DO have
    a previous entry and flag the others as first-entry."""

    def setUp(self):
        self.user = _user("partial@test.com")
        _log(self.user, "waist", 43.0, days_ago=20)
        _log(self.user, "waist", 42.0, days_ago=0)
        _log(self.user, "calf_left", 14.5, days_ago=0)  # no prior

    def test_some_metrics_have_delta_others_dont(self):
        snap = build_body_composition_snapshot(self.user)
        self.assertAlmostEqual(snap["delta"]["waist"], -1.0, places=2)
        self.assertIsNone(snap["delta"]["calf_left"])

    def test_message_lists_compared_and_first_entry_metrics(self):
        snap = build_body_composition_snapshot(self.user)
        msg = render_comparison_message(snap)
        self.assertIn("Waist", msg)
        self.assertIn("First entry", msg)
        self.assertIn("Calf (Left)", msg)


# ── Tolerance / direction edge cases ─────────────────────────────


class ToneAndToleranceTests(TestCase):
    def setUp(self):
        self.user = _user("tone@test.com")

    def test_waist_within_noise_threshold_is_stable(self):
        _log(self.user, "waist", 42.0, days_ago=30)
        _log(self.user, "waist", 42.1, days_ago=0)  # 0.1 < 0.25 threshold
        snap = build_body_composition_snapshot(self.user)
        self.assertIn("Waist stable", snap["trend_summary"])

    def test_lean_mass_up_is_improving(self):
        _log(self.user, "lean_mass", 140.0, days_ago=30, unit="lb")
        _log(self.user, "lean_mass", 142.0, days_ago=0, unit="lb")
        snap = build_body_composition_snapshot(self.user)
        joined = " | ".join(snap["trend_summary"])
        self.assertIn("Lean Mass trending up (improving)", joined)
        # Lean mass gain IS the biggest improvement here.
        self.assertEqual(snap["largest_improvement"]["metric"], "lean_mass")

    def test_lean_mass_down_is_regression(self):
        _log(self.user, "lean_mass", 142.0, days_ago=30, unit="lb")
        _log(self.user, "lean_mass", 138.0, days_ago=0, unit="lb")
        snap = build_body_composition_snapshot(self.user)
        joined = " | ".join(snap["trend_summary"])
        self.assertIn("Lean Mass trending down", joined)
        # NOT "improving"
        self.assertNotIn("Lean Mass trending down (improving)", joined)
        self.assertEqual(snap["largest_regression"]["metric"], "lean_mass")

    def test_neutral_metric_never_classified_as_win(self):
        """Arm-left going DOWN cannot be auto-classified as a win
        (could be undesirable during muscle preservation)."""
        _log(self.user, "arm_left", 17.0, days_ago=30)
        _log(self.user, "arm_left", 16.0, days_ago=0)
        snap = build_body_composition_snapshot(self.user)
        # No improvement candidate at all.
        self.assertIsNone(snap["largest_improvement"])
        # And not auto-classified as regression either.
        self.assertIsNone(snap["largest_regression"])


# ── SAE wiring: snapshot lands on health state ────────────────────


class SAEHealthStateWiringTests(TestCase):
    """The SAE health state must expose `body_composition` — Beth's
    contract is to consume it from SAE, never to query the model."""

    def setUp(self):
        self.user = _user("sae@test.com")
        _log(self.user, "waist", 43.0, days_ago=30)
        _log(self.user, "waist", 42.0, days_ago=0)

    def test_health_state_contains_body_composition_block(self):
        from apps.core.ai_state.state_builder import build_health_state
        state = build_health_state(self.user)
        bc = state.get("body_composition")
        self.assertIsNotNone(
            bc, "SAE health state MUST expose body_composition so Beth "
            "can answer first-party measurement questions without "
            "querying the DB",
        )
        # Dates round-trip as ISO strings.
        self.assertEqual(bc["latest_date"], date.today().isoformat())
        self.assertEqual(bc["latest"]["waist"], 42.0)
        self.assertAlmostEqual(bc["delta"]["waist"], -1.0, places=2)


# ── Beth handler routing — the trust break itself ────────────────


class BethHandlerRoutingTests(TestCase):
    """The user-reported defect: Beth said "I don't have your latest
    measurements in my current view." The handler must route through
    the snapshot and return a grounded answer."""

    def setUp(self):
        self.user = _user("beth@test.com")
        _log(self.user, "chest", 51.2, days_ago=20)
        _log(self.user, "waist", 43.4, days_ago=20)
        _log(self.user, "arm_left", 16.7, days_ago=20)
        _log(self.user, "arm_right", 16.8, days_ago=20)
        _log(self.user, "thigh_left", 27.1, days_ago=20)
        _log(self.user, "thigh_right", 27.2, days_ago=20)
        _log(self.user, "chest", 52.0, days_ago=0)
        _log(self.user, "waist", 42.0, days_ago=0)
        _log(self.user, "arm_left", 16.88, days_ago=0)
        _log(self.user, "arm_right", 17.0, days_ago=0)
        _log(self.user, "thigh_left", 26.63, days_ago=0)
        _log(self.user, "thigh_right", 27.25, days_ago=0)

    def test_action_handler_returns_grounded_comparison(self):
        from apps.ai.action_handlers import ActionHandler
        handler = ActionHandler(self.user)
        result = handler.handle_query_event_history(
            query_type="lookup", domain="body_composition",
        )
        self.assertTrue(result.success)
        # MUST NOT contain the failure mode.
        self.assertNotIn("I don't have", result.message)
        # MUST be specific.
        self.assertIn("Waist", result.message)
        self.assertIn("Chest", result.message)
        # Biggest win identifies waist — NOT chest (chest = neutral).
        self.assertIn("Biggest win", result.message)
        post_win = result.message.split("Biggest win", 1)[1]
        self.assertIn("Waist", post_win)


# ── EventResolver registration ───────────────────────────────────


class ResolverRegistrationTests(TestCase):
    """body_composition must be a registered domain so the existing
    query_event_history flow can route it."""

    def test_resolver_registers_body_composition_adapter(self):
        from apps.core.ai_events.resolver import _DOMAIN_ADAPTERS
        self.assertIn("body_composition", _DOMAIN_ADAPTERS)

    def test_intent_enum_includes_body_composition(self):
        from apps.ai.intents.query_intents import QUERY_INTENT_TOOLS
        enums = QUERY_INTENT_TOOLS[0]["function"][
            "parameters"]["properties"]["domain"]["enum"]
        self.assertIn("body_composition", enums)


# ── Latest message helper ────────────────────────────────────────


class LatestMessageTests(TestCase):
    def test_latest_message_lists_all_metrics(self):
        u = _user("lm@test.com")
        _log(u, "waist", 42.0)
        _log(u, "chest", 52.0)
        snap = build_body_composition_snapshot(u)
        msg = render_latest_message(snap)
        self.assertIn("Waist: 42", msg)
        self.assertIn("Chest: 52", msg)
        self.assertNotIn("I don't have", msg)


# ── Export view ──────────────────────────────────────────────────


class ExportViewTests(TestCase):
    """CSV/Excel export — date-range filtering, deterministic columns,
    previous-value/diff/pct computed in-row."""

    def setUp(self):
        self.user = _user("exp@test.com")
        self.client.force_login(self.user)
        _log(self.user, "waist", 43.4, days_ago=20)
        _log(self.user, "waist", 42.0, days_ago=0)

    def test_csv_export_no_filter_returns_csv_with_headers(self):
        from django.urls import reverse
        resp = self.client.get(reverse("health:body_composition_export"))
        self.assertEqual(resp.status_code, 200)
        self.assertIn("text/csv", resp["Content-Type"])
        body = resp.content.decode("utf-8")
        self.assertIn("Date,Metric,Value,Unit,Source,Notes,"
                      "Previous Value,Difference,Percent Change", body)
        self.assertIn("Waist,43.4", body)
        # Second row computes the diff vs the first.
        self.assertIn("Waist,42.0", body)
        # Previous value column populated for the 2nd row.
        self.assertIn("43.4,-1.4,-3.2", body)

    def test_csv_export_with_date_range(self):
        from django.urls import reverse
        from_date = (date.today() - timedelta(days=5)).isoformat()
        resp = self.client.get(
            reverse("health:body_composition_export")
            + f"?from_date={from_date}",
        )
        self.assertEqual(resp.status_code, 200)
        body = resp.content.decode("utf-8")
        # Only today's row (within 5 days), not the 20-days-ago row.
        self.assertIn("Waist,42.0", body)
        self.assertNotIn("Waist,43.4", body)

    def test_xlsx_export_returns_xlsx_or_falls_back(self):
        from django.urls import reverse
        resp = self.client.get(
            reverse("health:body_composition_export") + "?format=xlsx",
        )
        self.assertEqual(resp.status_code, 200)
        # Either real xlsx, or graceful CSV fallback if openpyxl missing.
        self.assertTrue(
            "spreadsheetml" in resp["Content-Type"]
            or "text/csv" in resp["Content-Type"]
        )


# ── Sync-stale flag ─────────────────────────────────────────────


class StaleFlagTests(TestCase):
    def test_sync_stale_true_when_old_data(self):
        u = _user("stale@test.com")
        _log(u, "waist", 42.0, days_ago=120)
        snap = build_body_composition_snapshot(u)
        self.assertTrue(snap["sync_stale"])

    def test_sync_stale_false_when_recent(self):
        u = _user("fresh@test.com")
        _log(u, "waist", 42.0, days_ago=2)
        snap = build_body_composition_snapshot(u)
        self.assertFalse(snap["sync_stale"])
